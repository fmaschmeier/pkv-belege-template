"""
Parser Service - Wraps the PDF parser
"""
import sys
import tempfile
import logging
from pathlib import Path
from typing import Optional

# Add parent directory to path for parser import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from parser import parse_settlement_with_text, settlement_to_dict, NotASettlementError
from bank_parser import parse_commerzbank_csv, extract_settlement_number

from ..core.database import get_supabase

logger = logging.getLogger(__name__)


class ParserService:
    """Service for parsing settlement PDFs and bank CSVs."""

    def __init__(self):
        self.supabase = get_supabase()

    def parse_settlement_pdf(self, file_content: bytes, filename: str) -> dict:
        """
        Parse a settlement PDF, save to database, and store PDF in storage.
        Returns the parsed settlement data.
        """
        # Save to temp file for parsing
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Parse PDF and get raw_text
            settlement, raw_text = parse_settlement_with_text(tmp_path)
            data = settlement_to_dict(settlement)

            # Override filename with original
            data["pdf_filename"] = filename
            data["raw_text"] = raw_text

            # Save to Supabase (returns settlement_id)
            result = self._save_settlement(data)

            # Upload PDF to Storage
            settlement_id = result["id"]
            storage_path = f"{settlement_id}/{filename}"

            try:
                self.supabase.storage.from_("settlements").upload(
                    storage_path,
                    file_content,
                    {"content-type": "application/pdf"}
                )

                # Update settlement with pdf_url
                self.supabase.table("settlements").update({
                    "pdf_url": storage_path
                }).eq("id", settlement_id).execute()

                logger.info(f"PDF uploaded to storage: {storage_path}")
            except Exception as e:
                logger.warning(f"Could not upload PDF to storage: {e}")

            return result

        except NotASettlementError as e:
            raise ValueError(f"Keine Leistungsabrechnung: {e.doc_type}")
        finally:
            # Cleanup temp file
            Path(tmp_path).unlink(missing_ok=True)

    def _save_settlement(self, data: dict) -> dict:
        """Save settlement to Supabase, return with ID."""

        # Check if already exists
        existing = self.supabase.table("settlements").select("id").eq(
            "settlement_number", data["settlement_number"]
        ).execute()

        if existing.data:
            raise ValueError(f"Settlement {data['settlement_number']} existiert bereits")

        # Insert settlement
        result = self.supabase.table("settlements").insert({
            "settlement_number": data["settlement_number"],
            "settlement_date": data["settlement_date"],
            "insurance_number": data["insurance_number"],
            "total_invoiced": data["total_invoiced"],
            "total_reimbursed": data["total_reimbursed"],
            "pdf_filename": data["pdf_filename"],
            "raw_text": data.get("raw_text"),
        }).execute()

        settlement_id = result.data[0]["id"]

        # Insert items
        for item in data["items"]:
            self.supabase.table("settlement_items").insert({
                "settlement_id": settlement_id,
                "receipt_number": item["receipt_number"],
                "tariff": item.get("tariff"),
                "insured_person": item.get("insured_person"),
                "description": item.get("description"),
                "treatment_period": item.get("treatment_period"),
                "invoice_amount": item.get("invoice_amount"),
                "reimbursed_amount": item.get("reimbursed_amount"),
                "notes": item.get("notes"),
            }).execute()

        return {
            "id": settlement_id,
            "settlement_number": data["settlement_number"],
            "settlement_date": data["settlement_date"],
            "items_count": len(data["items"]),
            "total_invoiced": data["total_invoiced"],
            "total_reimbursed": data["total_reimbursed"],
            "items": data["items"],  # Alle geparsten Items
        }

    def import_bank_csv(self, file_content: bytes) -> dict:
        """
        Import bank CSV and match to settlements.
        Returns import statistics.
        """
        # Save to temp file
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="wb") as tmp:
            tmp.write(file_content)
            tmp_path = tmp.name

        try:
            # Parse CSV
            transactions = parse_commerzbank_csv(tmp_path)

            # Load settlement map
            settlements = self.supabase.table("settlements").select("id, settlement_number").execute()
            settlement_map = {s["settlement_number"]: s["id"] for s in settlements.data}

            inserted = 0
            skipped = 0
            matched = 0
            errors = []

            for tx in transactions:
                # Settlement matching
                settlement_id = None
                if tx.get("settlement_number") and tx["settlement_number"] in settlement_map:
                    settlement_id = settlement_map[tx["settlement_number"]]
                    matched += 1

                try:
                    self.supabase.table("bank_transactions").insert({
                        "booking_date": tx["booking_date"],
                        "value_date": tx["value_date"],
                        "transaction_type": tx["transaction_type"],
                        "description": tx["description"],
                        "amount": tx["amount"],
                        "currency": tx["currency"],
                        "iban": tx.get("iban"),
                        "category": tx.get("category"),
                        "is_universa_payment": tx["is_universa_payment"],
                        "settlement_id": settlement_id,
                        "import_hash": tx["import_hash"],
                    }).execute()
                    inserted += 1

                except Exception as e:
                    if "duplicate" in str(e).lower() or "23505" in str(e):
                        skipped += 1
                    else:
                        errors.append(f"{tx['booking_date']}: {str(e)}")

            return {
                "inserted": inserted,
                "skipped": skipped,
                "matched": matched,
                "errors": errors[:10],  # Limit errors
            }

        finally:
            Path(tmp_path).unlink(missing_ok=True)

    def update_settlement_links(self) -> dict:
        """Update settlement links for unmatched Universa transactions."""

        # Load settlements
        settlements = self.supabase.table("settlements").select("id, settlement_number").execute()
        settlement_map = {s["settlement_number"]: s["id"] for s in settlements.data}

        # Load unmatched
        unmatched = self.supabase.table("bank_transactions").select(
            "id, description"
        ).eq("is_universa_payment", True).is_("settlement_id", "null").execute()

        updated = 0
        for tx in unmatched.data:
            settlement_nr = extract_settlement_number(tx["description"])
            if settlement_nr and settlement_nr in settlement_map:
                self.supabase.table("bank_transactions").update({
                    "settlement_id": settlement_map[settlement_nr]
                }).eq("id", tx["id"]).execute()
                updated += 1

        return {
            "unmatched_before": len(unmatched.data),
            "updated": updated,
            "still_open": len(unmatched.data) - updated,
        }
