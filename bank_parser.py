"""
Commerzbank CSV Parser

Importiert Banktransaktionen und ordnet Universa-Erstattungen automatisch zu.
"""

import csv
import hashlib
import os
import re
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client

# .env laden
load_dotenv(Path(__file__).parent / ".env")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_supabase_client():
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def parse_german_date(date_str: str) -> str:
    """Konvertiert DD.MM.YYYY zu YYYY-MM-DD."""
    parts = date_str.strip().split(".")
    return f"{parts[2]}-{parts[1]}-{parts[0]}"


def parse_german_amount(amount_str: str) -> float:
    """Konvertiert deutschen Betrag (1.234,56) zu float."""
    cleaned = amount_str.replace(".", "").replace(",", ".")
    return float(cleaned)


def generate_transaction_hash(row: dict) -> str:
    """Generiert einen eindeutigen Hash für Duplikat-Erkennung."""
    unique_str = f"{row['booking_date']}|{row['description']}|{row['amount']}"
    return hashlib.md5(unique_str.encode()).hexdigest()


def extract_settlement_number(description: str) -> str | None:
    """Extrahiert Abrechnungsnummer (R/25/XX) aus Buchungstext."""
    match = re.search(r'R/\d+/\d+', description)
    return match.group(0) if match else None


def is_universa_payment(description: str) -> bool:
    """Prüft ob es eine Universa-Zahlung ist."""
    desc_lower = description.lower()
    # "Leistungsabrechnung" kann getrennt sein: "Leistungsabr echnung"
    return "universa krankenversicherung" in desc_lower and "leistungsabr" in desc_lower


def parse_commerzbank_csv(csv_path: str) -> list[dict]:
    """Parst Commerzbank CSV und gibt Transaktionen zurück."""

    transactions = []

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=";")

        for row in reader:
            # Skip rows with empty dates (pending transactions)
            if not row.get("Buchungstag") or not row.get("Buchungstag").strip():
                continue
            if not row.get("Wertstellung") or not row.get("Wertstellung").strip():
                continue

            amount = parse_german_amount(row["Betrag"])

            # Filter: Alle Ausgaben ODER Universa-Einnahmen
            is_expense = amount < 0
            is_universa = is_universa_payment(row["Buchungstext"])

            if not is_expense and not is_universa:
                continue  # Überspringe nicht-Universa Einnahmen

            transaction = {
                "booking_date": parse_german_date(row["Buchungstag"]),
                "value_date": parse_german_date(row["Wertstellung"]),
                "transaction_type": row["Umsatzart"],
                "description": row["Buchungstext"],
                "amount": amount,
                "currency": row["Währung"],
                "iban": row["IBAN Kontoinhaber"],
                "category": row["Kategorie"],
                "is_universa_payment": is_universa,
                "settlement_number": extract_settlement_number(row["Buchungstext"]) if is_universa else None,
            }

            transaction["import_hash"] = generate_transaction_hash(transaction)
            transactions.append(transaction)

    return transactions


def import_transactions(csv_path: str):
    """Importiert Transaktionen in Supabase und ordnet Universa-Zahlungen zu."""

    print(f"Parse CSV: {csv_path}")
    transactions = parse_commerzbank_csv(csv_path)

    print(f"Gefunden: {len(transactions)} relevante Transaktionen")
    print(f"  - Ausgaben: {len([t for t in transactions if t['amount'] < 0])}")
    print(f"  - Universa-Einnahmen: {len([t for t in transactions if t['is_universa_payment']])}")

    supabase = get_supabase_client()

    # Lade alle Settlements für Zuordnung
    settlements = supabase.table("settlements").select("id, settlement_number").execute()
    settlement_map = {s["settlement_number"]: s["id"] for s in settlements.data}

    inserted = 0
    skipped = 0
    matched = 0
    errors = []

    for tx in transactions:
        # Settlement-Zuordnung
        settlement_id = None
        if tx["settlement_number"] and tx["settlement_number"] in settlement_map:
            settlement_id = settlement_map[tx["settlement_number"]]
            matched += 1

        try:
            # Versuche Insert (Duplikate werden durch import_hash abgefangen)
            supabase.table("bank_transactions").insert({
                "booking_date": tx["booking_date"],
                "value_date": tx["value_date"],
                "transaction_type": tx["transaction_type"],
                "description": tx["description"],
                "amount": tx["amount"],
                "currency": tx["currency"],
                "iban": tx["iban"],
                "category": tx["category"],
                "is_universa_payment": tx["is_universa_payment"],
                "settlement_id": settlement_id,
                "import_hash": tx["import_hash"],
            }).execute()
            inserted += 1

        except Exception as e:
            if "duplicate" in str(e).lower() or "23505" in str(e):
                skipped += 1  # Duplikat
            else:
                errors.append((tx["booking_date"], str(e)))

    print(f"\n{'='*60}")
    print(f"ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"Neu eingefügt: {inserted}")
    print(f"Duplikate übersprungen: {skipped}")
    print(f"Universa-Zuordnungen: {matched}")
    print(f"Fehler: {len(errors)}")

    if errors:
        print(f"\nFehler:")
        for date, err in errors[:5]:
            print(f"  - {date}: {err}")


def show_universa_matches():
    """Zeigt alle Universa-Zahlungen mit Zuordnung."""

    supabase = get_supabase_client()

    result = supabase.table("bank_transactions").select(
        "booking_date, amount, description, settlement_id"
    ).eq("is_universa_payment", True).order("booking_date", desc=True).execute()

    print(f"\nUniversa-Zahlungen ({len(result.data)} Stück):")
    print("-" * 80)

    for tx in result.data:
        status = "✓ zugeordnet" if tx["settlement_id"] else "✗ nicht zugeordnet"
        # Extrahiere R/XX/XX aus description
        match = re.search(r'R/\d+/\d+', tx["description"])
        settlement_nr = match.group(0) if match else "?"
        print(f"{tx['booking_date']} | {tx['amount']:>10.2f}€ | {settlement_nr} | {status}")


def update_settlement_links():
    """
    Aktualisiert settlement_id für alle nicht zugeordneten Universa-Transaktionen.
    Nützlich nach dem Import neuer Settlements.
    """
    supabase = get_supabase_client()

    # Lade alle Settlements
    settlements = supabase.table("settlements").select("id, settlement_number").execute()
    settlement_map = {s["settlement_number"]: s["id"] for s in settlements.data}

    # Lade alle nicht zugeordneten Universa-Transaktionen
    unmatched = supabase.table("bank_transactions").select(
        "id, description"
    ).eq("is_universa_payment", True).is_("settlement_id", "null").execute()

    updated = 0
    for tx in unmatched.data:
        settlement_nr = extract_settlement_number(tx["description"])
        if settlement_nr and settlement_nr in settlement_map:
            supabase.table("bank_transactions").update({
                "settlement_id": settlement_map[settlement_nr]
            }).eq("id", tx["id"]).execute()
            updated += 1
            print(f"  ✓ {settlement_nr} verknüpft")

    print(f"\n{'='*60}")
    print(f"ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"Nicht zugeordnet vorher: {len(unmatched.data)}")
    print(f"Neu verknüpft: {updated}")
    print(f"Noch offen: {len(unmatched.data) - updated}")


def update_item_payment_status():
    """
    Aktualisiert payment_status für settlement_items:
    - Rezepte -> 'paid_cash'
    - Pflegeleistungen -> 'not_applicable'
    """

    supabase = get_supabase_client()

    # Rezepte als bar bezahlt markieren
    result = supabase.table("settlement_items").update({
        "payment_status": "paid_cash",
        "payment_note": "Rezept/Apotheke - bar bezahlt"
    }).ilike("description", "%Rezept%").execute()
    print(f"Rezepte als 'paid_cash' markiert: {len(result.data)}")

    # Pflegeleistungen als nicht anwendbar markieren (Pauschalen)
    # Diese erkennt man am Tarif (PVN = Pflegeversicherung) oder Beschreibung
    result = supabase.table("settlement_items").update({
        "payment_status": "not_applicable",
        "payment_note": "Pflegeleistung - pauschale Erstattung"
    }).or_("tariff.eq.PVN,description.ilike.%Pflege%").execute()
    print(f"Pflegeleistungen als 'not_applicable' markiert: {len(result.data)}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python bank_parser.py <command> [args]")
        print("  import <csv_path>  - Importiere Commerzbank CSV")
        print("  matches            - Zeige Universa-Zuordnungen")
        print("  update-links       - Verknüpfe Transaktionen mit neuen Settlements")
        print("  update-status      - Aktualisiere Item Payment Status")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "import" and len(sys.argv) > 2:
        import_transactions(sys.argv[2])
    elif cmd == "matches":
        show_universa_matches()
    elif cmd == "update-links":
        update_settlement_links()
    elif cmd == "update-status":
        update_item_payment_status()
    else:
        print(f"Unbekannter Befehl: {cmd}")
