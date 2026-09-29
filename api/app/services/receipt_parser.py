"""
Receipt Parser - Eingereichte Belege

Extrahiert strukturierte Daten aus verschiedenen Belegtypen:
- Rezepte (Apotheke)
- Arztrechnungen
- Hilfsmittel (Optiker, Hörgeräte)
- Pflegeleistungen (Lebenshilfe, etc.)

Nutzt pdf.co API für PDF → Text Konvertierung mit Caching.
"""

import hashlib
import json
import os
import re
import requests
import subprocess
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from pypdf import PdfReader


# pdf.co API Key (aus Umgebungsvariable)
PDFCO_API_KEY = os.environ.get("PDFCO_API_KEY", "")

# Cache-Verzeichnis
CACHE_DIR = Path(__file__).parent / ".cache"


@dataclass
class ParsedReceipt:
    """Geparster Beleg"""
    # Metadaten
    submission_date: str              # PDF Erstellungsdatum (YYYY-MM-DD)
    pdf_filename: str
    pdf_hash: str

    # Aus Dateiname
    filename_person: Optional[str]    # Mila, Ben, Helga
    filename_provider: Optional[str]  # Entlastung, Apotheke

    # Aus PDF extrahiert
    receipt_type: str                 # rezept/arzt/hilfsmittel/pflege/sonstige
    provider_name: Optional[str]      # Familienentlastender Dienst Musterstadt e.V.
    provider_address: Optional[str]
    invoice_number: Optional[str]     # EL-26-00417
    invoice_date: Optional[str]       # YYYY-MM-DD
    invoice_amount: Optional[float]   # 173.25

    # Person
    insured_person: Optional[str]     # Helga Beispiel
    insured_birthdate: Optional[str]  # YYYY-MM-DD

    # Details
    description: Optional[str]        # Verhinderungspflege §39 SGB XI
    treatment_period: Optional[str]   # 01.07.-31.07.2026

    # Fälligkeit
    due_date: Optional[str]           # YYYY-MM-DD
    due_date_source: str              # explicit/calculated

    # Raw text für Debugging
    raw_text: Optional[str] = None


def get_file_hash(file_path: str) -> str:
    """Berechnet SHA256-Hash einer Datei für Cache-Key und Duplikaterkennung."""
    hasher = hashlib.sha256()
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


def get_pdf_creation_date(pdf_path: str) -> Optional[str]:
    """
    Extrahiert das Erstellungsdatum aus PDF-Metadaten.
    Fallback: Datei-Änderungsdatum.
    """
    try:
        reader = PdfReader(pdf_path)
        if reader.metadata and reader.metadata.creation_date:
            return reader.metadata.creation_date.strftime("%Y-%m-%d")
    except Exception:
        pass

    # Fallback: File modification time
    try:
        mtime = os.path.getmtime(pdf_path)
        return datetime.fromtimestamp(mtime).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now().strftime("%Y-%m-%d")


def parse_filename(filename: str) -> tuple[Optional[str], Optional[str]]:
    """
    Parst den Dateinamen nach dem Schema: YYYY-MM-DD PKV Provider Person.pdf

    Returns:
        (person, provider)
    """
    # Entferne Pfad und Extension
    name = Path(filename).stem

    # Pattern: Datum PKV Provider Person
    # Beispiel: 2026-08-03 PKV Entlastung Helga
    match = re.match(r'\d{4}-\d{2}-\d{2}\s+PKV\s+(\S+)\s+(\S+)', name)
    if match:
        return match.group(2), match.group(1)  # Person, Provider

    # Fallback: Versuche Person am Ende zu finden
    # Load known persons from environment
    known_persons = os.environ.get('INSURED_PERSONS', '').split(',')
    parts = name.split()
    if len(parts) >= 2:
        person = parts[-1] if parts[-1] in known_persons else None
        return person, None

    return None, None


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


def extract_text_from_pdf(file_url: str) -> str:
    """Extrahiert Text aus PDF via pdf.co API."""

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

    if not response.ok:
        print(f"pdf.co Error: {response.status_code} - {response.text}")
        response.raise_for_status()

    return response.json()["body"]


def detect_receipt_type(text: str) -> str:
    """Erkennt den Belegtyp anhand des Textes."""

    text_lower = text.lower()

    # Pflege (check first - most specific)
    if any(x in text_lower for x in ['verhinderungspflege', '§39 sgb', 'pflegeleistung', 'lebenshilfe', 'pflegedienst']):
        return 'pflege'

    # Arzt (check before rezept to avoid false positives like "Apothekerbank")
    arzt_keywords = ['praxis', 'dr.', 'goä', 'gop', 'gebührenordnung', 'gebihrenordnung',
                     'ärzt', 'labor', 'behandlung', 'psychotherap', 'pvs', 'abrechnungsdienst',
                     'honorar', 'sprechstunde', 'therapie', 'klinik', 'ambulanz']
    if any(x in text_lower for x in arzt_keywords):
        return 'arzt'

    # Rezept / Apotheke (use word boundaries to avoid matching "Apothekerbank")
    rezept_keywords = ['rezept', 'pharma', 'pzn', 'arzneimittel', 'medikament']
    if any(x in text_lower for x in rezept_keywords):
        return 'rezept'
    # Standalone "apotheke" (not as part of "apothekerbank")
    if re.search(r'\bapotheke\b', text_lower) and 'apothekerbank' not in text_lower and 'apotheker-' not in text_lower:
        return 'rezept'

    # Hilfsmittel
    if any(x in text_lower for x in ['optik', 'brillen', 'hörgerät', 'akustik', 'hilfsmittel', 'sanitätshaus']):
        return 'hilfsmittel'

    return 'sonstige'


def parse_german_date(date_str: str) -> Optional[str]:
    """Konvertiert deutsches Datum (DD.MM.YYYY) zu ISO (YYYY-MM-DD)."""
    if not date_str:
        return None

    # Verschiedene Formate versuchen
    for fmt in ['%d.%m.%Y', '%d.%m.%y', '%Y-%m-%d']:
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.strftime('%Y-%m-%d')
        except ValueError:
            continue

    return None


def parse_amount(amount_str: str) -> Optional[float]:
    """Parst deutschen Geldbetrag (1.234,56 €) zu float."""
    if not amount_str:
        return None

    # Entferne Währungssymbole und Whitespace
    cleaned = re.sub(r'[€\s]', '', amount_str)
    # Deutsches Format: 1.234,56 -> 1234.56
    cleaned = cleaned.replace('.', '').replace(',', '.')

    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_receipt_data(text: str, receipt_type: str) -> dict:
    """
    Extrahiert strukturierte Daten aus dem PDF-Text.
    Angepasst an den Belegtyp.
    """
    data = {
        'provider_name': None,
        'provider_address': None,
        'invoice_number': None,
        'invoice_date': None,
        'invoice_amount': None,
        'insured_person': None,
        'insured_birthdate': None,
        'description': None,
        'treatment_period': None,
        'explicit_due_date': None,
    }

    # --- Spezialfall: Universa Verhinderungspflege-Formular ---
    if receipt_type == 'pflege' and 'verhinderungspflege' in text.lower():
        # Ersatzpflegeperson = Provider
        # Pattern: "Vor- und Zuname der Ersatzpflegeperson:" followed by name
        ersatz_match = re.search(
            r'(?:Vor-?\s*und\s*Zuname\s*der\s*)?Ersatzpflegeperson:?\s*([A-Za-zäöüÄÖÜß]+\s+[A-Za-zäöüÄÖÜß]+)',
            text
        )
        if ersatz_match:
            data['provider_name'] = ersatz_match.group(1).strip()

        # Betrag: "insgesamt X,XX EUR erhalten"
        betrag_match = re.search(r'insgesamt\s*([\d.,]+)\s*EUR\s*erhalten', text, re.IGNORECASE)
        if betrag_match:
            data['invoice_amount'] = parse_amount(betrag_match.group(1))

        # Person: "Verhinderungspflege bei [Name]"
        person_match = re.search(r'Verhinderungspflege\s+bei\s+([A-Za-zäöüÄÖÜß]+\s+[A-Za-zäöüÄÖÜß]+)', text)
        if person_match:
            data['insured_person'] = person_match.group(1).strip()

        # Leistungsdatum aus Tabelle extrahieren
        # Format in Tabelle: "Datum:" gefolgt von DD.MM.YYYY (erste Spalte)
        # Suche nach Datum in Tabellenzeile (nach "Datum:" Header oder direkt das erste Datum)
        datum_patterns = [
            r'Datum:\s*\n?\s*(\d{2}\.\d{2}\.\d{4})',  # Nach "Datum:" Header
            r'\b(\d{2}\.\d{2}\.202\d)\b',  # Erstes 202X Datum (Leistungstag)
        ]
        for pattern in datum_patterns:
            datum_match = re.search(pattern, text)
            if datum_match:
                data['invoice_date'] = parse_german_date(datum_match.group(1))
                data['treatment_period'] = datum_match.group(1)  # Auch als treatment_period speichern
                break

        data['description'] = 'Verhinderungspflege §39 SGB XI'

        # Wenn Verhinderungspflege erfolgreich geparst wurde, früh zurückkehren
        if data['provider_name'] and data['invoice_amount']:
            return data

    # --- Rechnungsnummer ---
    # Verschiedene Formate: EL-26-00417, RE-12345, 2026/1234
    invoice_patterns = [
        r'Rechnung\s+([A-Z]{2,3}-?\d{2,4}-?\d+)',
        r'Rechnungs?-?Nr\.?:?\s*([A-Z0-9/-]+)',
        r'Invoice\s+#?\s*([A-Z0-9/-]+)',
    ]
    for pattern in invoice_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['invoice_number'] = match.group(1).strip()
            break

    # --- Rechnungsdatum ---
    date_patterns = [
        r'vom\s+(\d{2}\.\d{2}\.\d{4})',
        r'Datum:?\s*(\d{2}\.\d{2}\.\d{4})',
        r'(\d{2}\.\d{2}\.\d{4})',  # Fallback: erstes Datum
    ]
    for pattern in date_patterns:
        match = re.search(pattern, text)
        if match:
            data['invoice_date'] = parse_german_date(match.group(1))
            break

    # --- Gesamtbetrag ---
    amount_patterns = [
        r'Gesamt\s*\(?Rechnung\)?:?\s*([\d.,]+)\s*€',
        r'Gesamtbetrag:?\s*([\d.,]+)\s*€',
        r'Summe:?\s*([\d.,]+)\s*€',
        r'Rechnungsbetrag:?\s*([\d.,]+)\s*€',
        r'zu zahlen:?\s*([\d.,]+)\s*€',
        r'Insgesamt\s*([\d.,]+)\s*(?:€|Euro)',  # "Insgesamt 173,25 Euro"
        r'Endbetrag:?\s*([\d.,]+)\s*€',
        r'Bruttobetrag:?\s*([\d.,]+)\s*€',
    ]
    for pattern in amount_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['invoice_amount'] = parse_amount(match.group(1))
            break

    # --- Anbieter ---
    lines = text.strip().split('\n')

    # First try: Look for typical business indicators
    for i, line in enumerate(lines[:15]):
        line_clean = line.strip()
        if any(x in line.lower() for x in ['gmbh', 'e.v.', 'praxis', 'apotheke', 'dr.', 'mvz', 'klinik', 'uniklinik']):
            data['provider_name'] = line_clean
            if i + 1 < len(lines) and re.search(r'\d{5}', lines[i+1]):
                data['provider_address'] = lines[i+1].strip()
            break

    # Second try: Look for names in uppercase (headers) or after keywords
    if not data['provider_name']:
        for i, line in enumerate(lines[:10]):
            line_clean = line.strip()
            # Uppercase names like "ERIKA MUSTERFRAU"
            if re.match(r'^[A-ZÄÖÜ\s]{5,}$', line_clean) and len(line_clean) > 5:
                data['provider_name'] = line_clean.title()
                break
            # Names with "Psychotherapie" etc.
            if 'psychotherapie' in line.lower() and '—' in line:
                # "Psychotherapie für Kinder und Jugendliche — Hanna Wiesner"
                parts = line.split('—')
                if len(parts) > 1:
                    data['provider_name'] = parts[-1].strip()
                    break

    # --- Versicherte Person ---
    person_patterns = [
        # "für Mila Beispiel, Geburtsdatum: 05.06.2013" - Name is 2-3 capitalized words
        r'f[üu]r\s+([A-Z][a-zäöüß]+(?:\s+[A-Z][a-zäöüß]+){1,2}),?\s*Geburtsdatum:?\s*(\d{2}\.\d{2}\.\d{4})',
        # Simple: "Name Name, Geburtsdatum: DD.MM.YYYY"
        r'([A-Z][a-zäöüß]+\s+[A-Z][a-zäöüß]+),?\s*Geburtsdatum:?\s*(\d{2}\.\d{2}\.\d{4})',
        # "Betreute: Beispiel, Helga geb. 02.02.1942" -> "Helga Beispiel"
        r'Betreute:?\s*([^,]+),\s*([^\s]+)\s+geb\.?\s*(\d{2}\.\d{2}\.\d{4})',
        # "Betreute: Helga Beispiel geb. 02.02.1942"
        r'Betreute:?\s*([A-Za-zäöüß\s]+)\s+geb\.?\s*(\d{2}\.\d{2}\.\d{4})',
        r'Patient:?\s*([^,\n]+)',
        r'Versicherte[r]?:?\s*([^,\n]+)',
        r'Name:?\s*([^,\n]+)',
    ]
    for pattern in person_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) >= 3:
                # Format: Nachname, Vorname, Geburtsdatum
                lastname, firstname, birthdate = groups[0].strip(), groups[1].strip(), groups[2]
                data['insured_person'] = f"{firstname} {lastname}"
                data['insured_birthdate'] = parse_german_date(birthdate)
            elif len(groups) >= 2 and re.match(r'\d{2}\.\d{2}\.\d{4}', groups[1]):
                # Format: Name, Geburtsdatum
                data['insured_person'] = groups[0].strip()
                data['insured_birthdate'] = parse_german_date(groups[1])
            else:
                data['insured_person'] = groups[0].strip()
            break

    # --- Behandlungszeitraum ---
    period_patterns = [
        r'Zeitraum:?\s*([\d.]+\s*-\s*[\d.]+)',
        r'(\d{2}\.\d{2}\.\d{2,4})\s*-\s*(\d{2}\.\d{2}\.\d{2,4})',
        r'Rechnungsmonat:?\s*(\d{1,2}/\d{4})',
    ]
    for pattern in period_patterns:
        match = re.search(pattern, text)
        if match:
            data['treatment_period'] = match.group(0).replace('Zeitraum:', '').strip()
            break

    # --- Beschreibung ---
    if receipt_type == 'pflege':
        if 'verhinderungspflege' in text.lower():
            data['description'] = 'Verhinderungspflege §39 SGB XI'
        elif 'entlastung' in text.lower():
            data['description'] = 'Entlastungsleistungen §45b SGB XI'
    elif receipt_type == 'rezept':
        data['description'] = 'Rezept/Arzneimittel'
    elif receipt_type == 'arzt':
        data['description'] = 'Arztrechnung'
    elif receipt_type == 'hilfsmittel':
        data['description'] = 'Hilfsmittel'

    # --- Fälligkeit (explizit) ---
    due_patterns = [
        r'zahlbar bis:?\s*(\d{2}\.\d{2}\.\d{4})',
        r'fällig:?\s*(\d{2}\.\d{2}\.\d{4})',
        r'Zahlungsziel:?\s*(\d{2}\.\d{2}\.\d{4})',
    ]
    for pattern in due_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data['explicit_due_date'] = parse_german_date(match.group(1))
            break

    return data


def calculate_due_date(receipt_type: str, invoice_date: Optional[str], explicit_due_date: Optional[str], submission_date: Optional[str] = None) -> tuple[Optional[str], str]:
    """
    Berechnet das Fälligkeitsdatum.

    Returns:
        (due_date, source): Datum und Quelle ('explicit', 'calculated', oder 'from_submission')
    """
    if explicit_due_date:
        return explicit_due_date, 'explicit'

    if receipt_type == 'rezept':
        # Rezepte: Direkt bezahlt, keine Fälligkeit relevant
        return None, 'not_applicable'

    # Basisdatum: Rechnungsdatum oder Einreichungsdatum als Fallback
    base_date = invoice_date or submission_date
    if not base_date:
        return None, 'unknown'

    base_dt = datetime.strptime(base_date, '%Y-%m-%d')
    source = 'calculated' if invoice_date else 'from_submission'

    # 30 Tage ab Basisdatum
    due_dt = base_dt + timedelta(days=30)
    return due_dt.strftime('%Y-%m-%d'), source


def parse_receipt(pdf_path: str) -> ParsedReceipt:
    """
    Parst einen eingereichten Beleg.
    Nutzt pdf.co mit Caching.

    Args:
        pdf_path: Pfad zur PDF-Datei

    Returns:
        ParsedReceipt mit extrahierten Daten
    """
    pdf_path = str(pdf_path)
    filename = Path(pdf_path).name

    # Hash für Cache und Duplikaterkennung
    file_hash = get_file_hash(pdf_path)

    # PDF-Erstellungsdatum
    submission_date = get_pdf_creation_date(pdf_path)

    # Dateiname parsen
    filename_person, filename_provider = parse_filename(filename)

    # Text aus Cache oder API
    cached_text = get_cached_result(file_hash, "receipt_text")

    if cached_text:
        text = cached_text
    else:
        # pdf.co API
        file_url = upload_pdf_to_pdfco(pdf_path)
        text = extract_text_from_pdf(file_url)
        save_to_cache(file_hash, "receipt_text", text)

    # Belegtyp erkennen
    receipt_type = detect_receipt_type(text)

    # Daten extrahieren
    data = extract_receipt_data(text, receipt_type)

    # Fälligkeit berechnen
    due_date, due_date_source = calculate_due_date(
        receipt_type,
        data['invoice_date'],
        data['explicit_due_date'],
        submission_date
    )

    return ParsedReceipt(
        submission_date=submission_date,
        pdf_filename=filename,
        pdf_hash=file_hash,
        filename_person=filename_person,
        filename_provider=filename_provider,
        receipt_type=receipt_type,
        provider_name=data['provider_name'],
        provider_address=data['provider_address'],
        invoice_number=data['invoice_number'],
        invoice_date=data['invoice_date'],
        invoice_amount=data['invoice_amount'],
        insured_person=data['insured_person'],
        insured_birthdate=data['insured_birthdate'],
        description=data['description'],
        treatment_period=data['treatment_period'],
        due_date=due_date,
        due_date_source=due_date_source,
        raw_text=text[:2000] if text else None,  # Nur erste 2000 Zeichen für Debug
    )


def receipt_to_dict(receipt: ParsedReceipt) -> dict:
    """Konvertiert ParsedReceipt zu Dictionary für JSON/DB."""
    return asdict(receipt)


# --- CLI für Tests ---
if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python receipt_parser.py <pdf_path>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    print(f"Parsing: {pdf_path}")

    receipt = parse_receipt(pdf_path)

    print(f"\n{'='*50}")
    print(f"Belegtyp: {receipt.receipt_type}")
    print(f"Einreichdatum: {receipt.submission_date}")
    print(f"Anbieter: {receipt.provider_name}")
    print(f"Rechnungsnr: {receipt.invoice_number}")
    print(f"Rechnungsdatum: {receipt.invoice_date}")
    print(f"Betrag: {receipt.invoice_amount}€")
    print(f"Person: {receipt.insured_person}")
    print(f"Fälligkeit: {receipt.due_date} ({receipt.due_date_source})")
    print(f"{'='*50}")

    # JSON ausgeben
    print("\nJSON:")
    print(json.dumps(receipt_to_dict(receipt), indent=2, ensure_ascii=False))
