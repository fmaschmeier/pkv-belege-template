"""
Supabase Sync - Speichert geparste Settlements in Supabase
"""

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from supabase import create_client, Client
from datetime import datetime

# .env laden
load_dotenv(Path(__file__).parent / ".env")

# Supabase Credentials
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")


def get_supabase_client() -> Client:
    """Erstellt Supabase Client."""
    if not SUPABASE_KEY:
        raise ValueError("SUPABASE_KEY nicht gesetzt! Bitte als Umgebungsvariable setzen.")
    return create_client(SUPABASE_URL, SUPABASE_KEY)


def sync_settlements(json_file: str = "parsed_settlements.json"):
    """Synchronisiert alle Settlements aus JSON-Datei nach Supabase."""

    # JSON laden
    json_path = Path(__file__).parent / json_file
    if not json_path.exists():
        raise FileNotFoundError(f"JSON-Datei nicht gefunden: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        settlements = json.load(f)

    print(f"Gefunden: {len(settlements)} Settlements in {json_file}")

    # Supabase Client
    supabase = get_supabase_client()

    inserted = 0
    updated = 0
    errors = []

    for settlement in settlements:
        try:
            # Prüfe ob Settlement bereits existiert
            existing = supabase.table("settlements").select("id").eq(
                "settlement_number", settlement["settlement_number"]
            ).execute()

            if existing.data:
                # Update
                settlement_id = existing.data[0]["id"]
                supabase.table("settlements").update({
                    "settlement_date": settlement["settlement_date"],
                    "insurance_number": settlement["insurance_number"],
                    "total_invoiced": settlement["total_invoiced"],
                    "total_reimbursed": settlement["total_reimbursed"],
                    "pdf_filename": settlement["pdf_filename"],
                }).eq("id", settlement_id).execute()

                # Alte Items löschen und neu einfügen
                supabase.table("settlement_items").delete().eq(
                    "settlement_id", settlement_id
                ).execute()

                updated += 1
                print(f"  Updated: {settlement['settlement_number']}")
            else:
                # Insert
                result = supabase.table("settlements").insert({
                    "settlement_number": settlement["settlement_number"],
                    "settlement_date": settlement["settlement_date"],
                    "insurance_number": settlement["insurance_number"],
                    "total_invoiced": settlement["total_invoiced"],
                    "total_reimbursed": settlement["total_reimbursed"],
                    "pdf_filename": settlement["pdf_filename"],
                }).execute()

                settlement_id = result.data[0]["id"]
                inserted += 1
                print(f"  Inserted: {settlement['settlement_number']}")

            # Items einfügen
            for item in settlement["items"]:
                supabase.table("settlement_items").insert({
                    "settlement_id": settlement_id,
                    "receipt_number": item["receipt_number"],
                    "insured_person": item["insured_person"],
                    "insured_birthdate": item["insured_birthdate"],
                    "description": item["description"],
                    "treatment_period": item["treatment_period"],
                    "invoice_amount": item["invoice_amount"],
                    "tariff": item["tariff"],
                    "receipt_portion": item["receipt_portion"],
                    "corrected_amount": item["corrected_amount"],
                    "deferred_amount": item["deferred_amount"],
                    "reimbursable_amount": item["reimbursable_amount"],
                    "own_contribution": item["own_contribution"],
                    "deductible": item["deductible"],
                    "reimbursed_amount": item["reimbursed_amount"],
                    "notes": item["notes"] if item["notes"] else None,
                }).execute()

        except Exception as e:
            errors.append((settlement.get("settlement_number", "?"), str(e)))
            print(f"  FEHLER: {settlement.get('settlement_number', '?')}: {e}")

    print(f"\n{'='*60}")
    print(f"ZUSAMMENFASSUNG")
    print(f"{'='*60}")
    print(f"Neu eingefügt: {inserted}")
    print(f"Aktualisiert: {updated}")
    print(f"Fehler: {len(errors)}")

    if errors:
        print(f"\nFehler:")
        for num, err in errors:
            print(f"  - {num}: {err}")


def check_connection():
    """Testet die Supabase-Verbindung."""
    try:
        supabase = get_supabase_client()
        # Versuche eine einfache Abfrage
        result = supabase.table("settlements").select("count", count="exact").execute()
        print(f"Verbindung OK! Settlements in DB: {result.count}")
        return True
    except Exception as e:
        print(f"Verbindungsfehler: {e}")
        return False


def show_stats():
    """Zeigt Statistiken aus der Datenbank."""
    supabase = get_supabase_client()

    # Settlements zählen
    settlements = supabase.table("settlements").select("*", count="exact").execute()
    print(f"Settlements: {settlements.count}")

    # Items zählen
    items = supabase.table("settlement_items").select("*", count="exact").execute()
    print(f"Items: {items.count}")

    # Summen
    if settlements.data:
        total_reimbursed = sum(s["total_reimbursed"] or 0 for s in settlements.data)
        print(f"Gesamt erstattet: {total_reimbursed:,.2f}€")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "check":
            check_connection()
        elif cmd == "stats":
            show_stats()
        elif cmd == "sync":
            sync_settlements()
        else:
            print(f"Unbekannter Befehl: {cmd}")
            print("Verfügbar: check, stats, sync")
    else:
        print("Usage: python supabase_sync.py [check|stats|sync]")
        print("  check - Teste Verbindung")
        print("  stats - Zeige Statistiken")
        print("  sync  - Synchronisiere Daten")
