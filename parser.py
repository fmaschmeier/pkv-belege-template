"""
Universa Leistungsabrechnung Parser

Extrahiert strukturierte Daten aus Universa PDF-Abrechnungen.
Nutzt pdf.co API für PDF → CSV Konvertierung, dann regelbasiertes Parsing.
"""

import csv
import hashlib
import io
import json
import os
import re
import requests
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


class NotASettlementError(Exception):
    """Wird geworfen wenn das PDF keine Leistungsabrechnung ist."""
    def __init__(self, pdf_name: str, doc_type: str = "unbekannt"):
        self.pdf_name = pdf_name
        self.doc_type = doc_type
        super().__init__(f"{pdf_name}: Keine Leistungsabrechnung ({doc_type})")


def detect_document_type(header_text: str) -> tuple[bool, str]:
    """
    Erkennt den Dokumenttyp anhand des Header-Texts.

    Returns:
        (is_settlement, doc_type): True wenn Leistungsabrechnung, sonst Dokumenttyp
    """
    # Leistungsabrechnung erkennen
    if re.search(r'Leistungsabrechnung\s+R/\d+/\d+', header_text):
        return True, "Leistungsabrechnung"

    # Andere Dokumenttypen erkennen
    if "Tipps" in header_text and "Einreichung" in header_text:
        return False, "Info-Dokument"

    if "Pflegepflichtversicherung" in header_text:
        if "Pflegeeinsatz" in header_text or "Berichtsbogen" in header_text:
            return False, "Pflegeeinsatz-Bestätigung"
        if "Entlastungsleistungen" in header_text or "Entlastungsbetrag" in header_text:
            return False, "Entlastungsleistungen-Brief"
        if "Nachbarschaftshelfer" in header_text:
            return False, "Nachbarschaftshelfer-Brief"
        return False, "Pflegeversicherung-Brief"

    if "Ihre E-Mail" in header_text or "Ihr Schreiben" in header_text:
        return False, "Korrespondenz-Antwort"

    # Fallback: Prüfe ob typische Abrechnungselemente fehlen
    if not re.search(r'überweisen heute|Auszahlungsbetrag', header_text):
        return False, "Unbekanntes Dokument"

    return True, "Leistungsabrechnung"


# pdf.co API Key (aus Umgebungsvariable)
PDFCO_API_KEY = os.getenv("PDFCO_API_KEY", "")

# Cache-Verzeichnis
CACHE_DIR = Path(__file__).parent / ".cache"


def get_file_hash(file_path: str) -> str:
    """Berechnet MD5-Hash einer Datei für Cache-Key."""
    hasher = hashlib.md5()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def get_cached_result(file_hash: str, result_type: str) -> Optional[str]:
    """Lädt gecachtes Ergebnis falls vorhanden."""
    cache_file = CACHE_DIR / f"{file_hash}_{result_type}.txt"
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")
    return None


def save_to_cache(file_hash: str, result_type: str, content: str) -> None:
    """Speichert Ergebnis im Cache."""
    CACHE_DIR.mkdir(exist_ok=True)
    cache_file = CACHE_DIR / f"{file_hash}_{result_type}.txt"
    cache_file.write_text(content, encoding="utf-8")


@dataclass
class SettlementItem:
    """Einzelposition in einer Leistungsabrechnung"""
    receipt_number: str              # B/26/1201
    insured_person: str              # Max Mustermann
    insured_birthdate: Optional[str] # YYYY-MM-DD
    description: str                 # Linden-Apotheke, Rezept/Quittung
    treatment_period: str            # 12.05.-19.05.2026
    invoice_amount: float            # 413.00
    tariff: str                      # KA1
    receipt_portion: float           # 413.00
    corrected_amount: Optional[float]  # 355.00
    deferred_amount: Optional[float]   # zurückgestellt
    reimbursable_amount: float       # 355.00
    own_contribution: Optional[float]  # tariflicher Eigenanteil
    deductible: Optional[float]      # Selbstbeteiligung
    reimbursed_amount: float         # 355.00
    notes: list[str]                 # Anmerkungen


@dataclass
class Settlement:
    """Universa Leistungsabrechnung"""
    settlement_number: str           # R/26/117
    settlement_date: str             # Erstattungsdatum, Format: YYYY-MM-DD
    insurance_number: str            # 12345678
    total_invoiced: float            # 1500.45
    total_reimbursed: float          # 923.41
    pdf_filename: str                # 20260717_40012345_Leistungsinformationen_7100117.pdf
    items: list[SettlementItem]


def upload_pdf_to_pdfco(pdf_path: str) -> str:
    """Upload PDF zu pdf.co und gibt die temporäre URL zurück."""

    # 1. Presigned URL holen
    response = requests.get(
        "https://api.pdf.co/v1/file/upload/get-presigned-url",
        headers={"x-api-key": PDFCO_API_KEY},
        params={"name": "document.pdf", "contenttype": "application/pdf"}
    )
    response.raise_for_status()
    data = response.json()

    presigned_url = data["presignedUrl"]
    file_url = data["url"]

    # 2. Datei hochladen
    with open(pdf_path, "rb") as f:
        requests.put(
            presigned_url,
            headers={"Content-Type": "application/pdf"},
            data=f
        )

    return file_url


def extract_csv_from_pdf(file_url: str, page: int = 1) -> str:
    """Extrahiert CSV-Daten aus PDF via pdf.co API."""

    response = requests.post(
        "https://api.pdf.co/v1/pdf/convert/to/csv",
        headers={
            "x-api-key": PDFCO_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "url": file_url,
            "inline": True,
            "pages": str(page)
        }
    )
    response.raise_for_status()
    return response.json()["body"]


def extract_text_from_pdf(file_url: str) -> str:
    """Extrahiert Text aus PDF via pdf.co API (für Deckblatt)."""

    response = requests.post(
        "https://api.pdf.co/v1/pdf/convert/to/text",
        headers={
            "x-api-key": PDFCO_API_KEY,
            "Content-Type": "application/json"
        },
        json={
            "url": file_url,
            "inline": True,
            "pages": "0"  # Nur erste Seite
        }
    )
    response.raise_for_status()
    return response.json()["body"]


def parse_header(text: str) -> dict:
    """Parst das Deckblatt und extrahiert Kopfdaten."""

    header = {
        "settlement_number": None,
        "settlement_date": None,
        "insurance_number": None,
        "total_reimbursed": None
    }

    # Abrechnungsnummer: R/26/117
    match = re.search(r'Leistungsabrechnung\s+(R/\d+/\d+)', text)
    if match:
        header["settlement_number"] = match.group(1)

    # Datum
    match = re.search(r'(\d{1,2})\.\s*(Januar|Februar|März|April|Mai|Juni|Juli|August|September|Oktober|November|Dezember)\s*(\d{4})', text)
    if match:
        months = {
            "Januar": "01", "Februar": "02", "März": "03", "April": "04",
            "Mai": "05", "Juni": "06", "Juli": "07", "August": "08",
            "September": "09", "Oktober": "10", "November": "11", "Dezember": "12"
        }
        day = match.group(1).zfill(2)
        month = months.get(match.group(2), "01")
        year = match.group(3)
        header["settlement_date"] = f"{year}-{month}-{day}"

    # Versicherungsnummer
    match = re.search(r'Versicherungsnummer\s*(\d+)', text)
    if match:
        header["insurance_number"] = match.group(1)

    # Auszahlungsbetrag
    match = re.search(r'überweisen heute\s*([\d.,]+)\s*EUR', text)
    if match:
        header["total_reimbursed"] = parse_german_number(match.group(1))

    return header


def parse_german_number(text: str) -> Optional[float]:
    """Konvertiert deutsche Zahlenformate (1.234,56) zu float."""
    if not text or text.strip() == "":
        return None
    # Entferne Tausendertrennzeichen, ersetze Komma durch Punkt
    cleaned = text.replace(".", "").replace(",", ".")
    try:
        return float(cleaned)
    except ValueError:
        return None


def parse_csv_table(csv_text: str) -> list[SettlementItem]:
    """Parst die CSV-Tabelle und extrahiert Einzelpositionen."""

    items = []
    current_person = None
    current_birthdate = None
    current_item = None
    pending_notes = []
    collecting_note = False  # Flag: sammle mehrzeilige Anmerkung

    reader = csv.reader(io.StringIO(csv_text))

    for row in reader:
        if len(row) < 2:
            continue

        col0 = row[0].strip() if row[0] else ""
        col1 = row[1].strip() if len(row) > 1 and row[1] else ""

        # Neue Person erkannt
        if ", geb. " in col0:
            match = re.match(r'(.+),\s*geb\.\s*(\d{2}\.\d{2}\.\d{4})', col0)
            if match:
                current_person = match.group(1).strip()
                # Datum konvertieren DD.MM.YYYY -> YYYY-MM-DD
                date_parts = match.group(2).split(".")
                current_birthdate = f"{date_parts[2]}-{date_parts[1]}-{date_parts[0]}"
            collecting_note = False
            continue

        # Belegposition erkannt
        if re.match(r'B/\d+/\d+', col0):
            # Vorherige Position speichern
            if current_item:
                current_item.notes = pending_notes
                items.append(current_item)
                pending_notes = []

            collecting_note = False

            # Neue Position erstellen
            current_item = SettlementItem(
                receipt_number=col0,
                insured_person=current_person or "",
                insured_birthdate=current_birthdate,
                description=col1,
                treatment_period=row[2].strip() if len(row) > 2 else "",
                invoice_amount=parse_german_number(row[3]) if len(row) > 3 else 0,
                tariff=row[4].strip() if len(row) > 4 else "",
                receipt_portion=parse_german_number(row[5]) if len(row) > 5 else 0,
                corrected_amount=parse_german_number(row[6]) if len(row) > 6 else None,
                deferred_amount=parse_german_number(row[7]) if len(row) > 7 else None,
                reimbursable_amount=parse_german_number(row[8]) if len(row) > 8 else 0,
                own_contribution=parse_german_number(row[9]) if len(row) > 9 else None,
                deductible=parse_german_number(row[10]) if len(row) > 10 else None,
                reimbursed_amount=parse_german_number(row[11]) if len(row) > 11 else 0,
                notes=[]
            )
            continue

        # Fortsetzungszeile (gleiche Belegnummer, weitere Tarif-Zeile)
        if col0 == "" and len(row) > 4 and row[4].strip() != "":
            # Das ist eine Aufspaltung derselben Position in mehrere Tarife
            # Wir addieren die Beträge zur aktuellen Position
            if current_item:
                additional_portion = parse_german_number(row[5]) if len(row) > 5 else 0
                additional_reimbursable = parse_german_number(row[8]) if len(row) > 8 else 0
                additional_reimbursed = parse_german_number(row[11]) if len(row) > 11 else 0

                if additional_portion:
                    current_item.receipt_portion = (current_item.receipt_portion or 0) + additional_portion
                if additional_reimbursable:
                    current_item.reimbursable_amount = (current_item.reimbursable_amount or 0) + additional_reimbursable
                if additional_reimbursed:
                    current_item.reimbursed_amount = (current_item.reimbursed_amount or 0) + additional_reimbursed
            continue

        # Anmerkung erkannt
        if col0 == "" and col1 and current_item:
            # Ignoriere Header-Zeilen
            if "Zu Ihrer Information" in col1:
                continue

            # Start einer neuen Anmerkung (Info-Code erkannt)
            if col1.startswith("Information zur Position") or col1.startswith("Zu Position"):
                collecting_note = True
                continue

            # Info-Code mit Text (z.B. "400:", "156:", "920:")
            if re.match(r'^\d{3}:', col1):
                collecting_note = True
                pending_notes.append(col1)
                continue

            # Fortsetzung einer mehrzeiligen Anmerkung
            if collecting_note and col1:
                # Füge zur letzten Note hinzu oder erstelle neue
                if pending_notes and not pending_notes[-1].endswith('.'):
                    pending_notes[-1] += " " + col1
                elif col1.startswith(("Die Kosten", "Für ", "Bei ", "Wir haben", "Das ", "Der ", "Es ")):
                    pending_notes.append(col1)
                elif pending_notes:
                    pending_notes[-1] += " " + col1
                continue

        # Gesamtsumme - Position abschließen
        if "Gesamtsumme" in col0:
            if current_item:
                current_item.notes = pending_notes
                items.append(current_item)
                current_item = None
                pending_notes = []
            collecting_note = False
            continue

    # Letzte Position speichern
    if current_item:
        current_item.notes = pending_notes
        items.append(current_item)

    return items


def parse_settlement(pdf_path: str) -> Settlement:
    """Hauptfunktion: Parst eine Universa Leistungsabrechnung."""
    settlement, _ = parse_settlement_with_text(pdf_path)
    return settlement


def parse_settlement_with_text(pdf_path: str) -> tuple[Settlement, str]:
    """Parst eine Universa Leistungsabrechnung und gibt auch den raw_text zurück."""

    pdf_name = Path(pdf_path).name

    # Cache-Key basierend auf Datei-Hash
    file_hash = get_file_hash(pdf_path)
    print(f"PDF: {pdf_name} (Hash: {file_hash[:8]}...)")

    # Prüfe Cache für Header-Text
    header_text = get_cached_result(file_hash, "header")
    if header_text:
        print("  Header: aus Cache geladen")
    else:
        print("  Header: von pdf.co abrufen...")
        file_url = upload_pdf_to_pdfco(pdf_path)
        header_text = extract_text_from_pdf(file_url)
        save_to_cache(file_hash, "header", header_text)

    # Dokumenttyp prüfen
    is_settlement, doc_type = detect_document_type(header_text)
    if not is_settlement:
        print(f"  -> Übersprungen: {doc_type}")
        raise NotASettlementError(pdf_name, doc_type)

    header = parse_header(header_text)

    # Prüfe Cache für CSV
    csv_text = get_cached_result(file_hash, "csv")
    if csv_text:
        print("  CSV: aus Cache geladen")
    else:
        print("  CSV: von pdf.co abrufen...")
        # Falls noch keine file_url, nochmal hochladen
        if 'file_url' not in locals():
            file_url = upload_pdf_to_pdfco(pdf_path)
        csv_text = extract_csv_from_pdf(file_url, page=1)
        save_to_cache(file_hash, "csv", csv_text)

    items = parse_csv_table(csv_text)

    # Fix: Bei Pflegegeld/Tagegeld ist invoice_amount oft leer, aber receipt_portion hat den Wert
    # In diesem Fall verwenden wir receipt_portion als invoice_amount
    for item in items:
        if not item.invoice_amount and item.receipt_portion:
            item.invoice_amount = item.receipt_portion

    # Gesamtsumme berechnen
    total_invoiced = sum(item.invoice_amount or 0 for item in items)

    # Combine raw texts
    raw_text = f"=== HEADER ===\n{header_text}\n\n=== CSV DATA ===\n{csv_text}"

    settlement = Settlement(
        settlement_number=header.get("settlement_number", ""),
        settlement_date=header.get("settlement_date", ""),
        insurance_number=header.get("insurance_number", ""),
        total_invoiced=total_invoiced,
        total_reimbursed=header.get("total_reimbursed", 0),
        pdf_filename=Path(pdf_path).name,
        items=items
    )

    return settlement, raw_text


def settlement_to_dict(settlement: Settlement) -> dict:
    """Konvertiert Settlement zu Dictionary für JSON-Export."""
    return {
        "settlement_number": settlement.settlement_number,
        "settlement_date": settlement.settlement_date,
        "insurance_number": settlement.insurance_number,
        "total_invoiced": settlement.total_invoiced,
        "total_reimbursed": settlement.total_reimbursed,
        "pdf_filename": settlement.pdf_filename,
        "items": [asdict(item) for item in settlement.items]
    }


# CLI Entry Point
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python parser.py <pdf_path>")
        print("Example: python parser.py /path/to/Leistungsabrechnung.pdf")
        sys.exit(1)

    pdf_path = sys.argv[1]

    try:
        settlement = parse_settlement(pdf_path)
        result = settlement_to_dict(settlement)
        print("\n" + "=" * 60)
        print("ERGEBNIS:")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"Fehler: {e}")
        sys.exit(1)
