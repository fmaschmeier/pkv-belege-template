"""
Receipts API Routes - Eingereichte Belege
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from typing import Optional
from datetime import date, datetime, timedelta
import tempfile
from pathlib import Path
import sys
import base64
import httpx

# Add parent for parser import
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))
from receipt_parser import parse_receipt, receipt_to_dict, get_pdf_creation_date

from ..core.database import get_supabase
from ..core.auth import get_current_user
from ..core.config import get_settings
from ..schemas.receipts import (
    ReceiptResponse,
    ReceiptListResponse,
    ReceiptUploadResponse,
    ReceiptUpdateRequest,
    ReceiptStats,
    ReceiptImportRequest,
    ReceiptImportResponse,
    PaymentQRRequest,
    PaymentQRResponse,
)
import hashlib
import json
import re
import unicodedata


def sanitize_filename(filename: str) -> str:
    """
    Sanitize filename for Supabase Storage.
    - Replace spaces with underscores
    - Replace German umlauts
    - Remove other special characters
    """
    # Replace German umlauts
    replacements = {
        'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss',
        'Ä': 'Ae', 'Ö': 'Oe', 'Ü': 'Ue',
    }
    for old, new in replacements.items():
        filename = filename.replace(old, new)

    # Replace spaces with underscores
    filename = filename.replace(' ', '_')

    # Remove any remaining non-ASCII characters
    filename = unicodedata.normalize('NFKD', filename).encode('ASCII', 'ignore').decode('ASCII')

    # Remove any characters that aren't alphanumeric, underscore, dash, or dot
    filename = re.sub(r'[^\w\-.]', '', filename)

    return filename


def validate_iban(iban: str) -> tuple[bool, str]:
    """
    Validiert eine IBAN mittels Prüfsumme (ISO 13616).
    Returns (is_valid, error_message)
    """
    # Entferne Leerzeichen und konvertiere zu Großbuchstaben
    iban = iban.replace(" ", "").upper()

    # Prüfe Länge (min 15, max 34)
    if len(iban) < 15 or len(iban) > 34:
        return False, "IBAN muss zwischen 15 und 34 Zeichen lang sein"

    # Prüfe Format: 2 Buchstaben + 2 Ziffern + Rest alphanumerisch
    if not re.match(r'^[A-Z]{2}[0-9]{2}[A-Z0-9]+$', iban):
        return False, "Ungültiges IBAN-Format"

    # Deutsche IBAN: DE + 2 Prüfziffern + 8 BLZ + 10 Kontonummer = 22 Zeichen
    if iban.startswith("DE") and len(iban) != 22:
        return False, "Deutsche IBAN muss 22 Zeichen haben"

    # ISO 13616 Prüfsumme: Verschiebe erste 4 Zeichen ans Ende
    rearranged = iban[4:] + iban[:4]

    # Konvertiere Buchstaben zu Zahlen (A=10, B=11, ..., Z=35)
    numeric = ""
    for char in rearranged:
        if char.isalpha():
            numeric += str(ord(char) - ord('A') + 10)
        else:
            numeric += char

    # Prüfe ob Modulo 97 = 1
    if int(numeric) % 97 != 1:
        return False, "IBAN-Prüfsumme ungültig"

    return True, ""


def normalize_provider_name(name: str) -> str:
    """
    Normalisiert einen Provider-Namen für Lookup.
    Entfernt Sonderzeichen, Kleinbuchstaben, trimmt.
    """
    if not name:
        return ""
    # Kleinbuchstaben, trimmen, mehrfache Leerzeichen entfernen
    normalized = name.lower().strip()
    normalized = re.sub(r'\s+', ' ', normalized)
    return normalized


def generate_epc_qr_data(recipient: str, iban: str, amount: float, reference: str) -> str:
    """
    Generiert EPC QR Code String (SEPA Credit Transfer).
    Format nach EPC069-12 Version 2.1
    """
    # Bereinige IBAN
    iban_clean = iban.replace(" ", "").upper()

    # Begrenze Längen nach SEPA-Standard
    recipient = recipient[:70]
    reference = reference[:140]

    # EPC QR Code Format
    lines = [
        "BCD",           # Service Tag
        "002",           # Version
        "1",             # Character set (UTF-8)
        "SCT",           # Identification (SEPA Credit Transfer)
        "",              # BIC (optional, leer lassen)
        recipient,       # Empfängername
        iban_clean,      # IBAN
        f"EUR{amount:.2f}",  # Betrag
        "",              # Purpose (leer)
        "",              # Structured Reference (leer)
        reference,       # Unstructured Reference (Verwendungszweck)
        ""               # Beneficiary to originator info (leer)
    ]

    return "\n".join(lines)

router = APIRouter(prefix="/receipts", tags=["Receipts"])


@router.get("", response_model=ReceiptListResponse)
async def list_receipts(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Filter by status"),
    person: Optional[str] = Query(None, description="Filter by insured person"),
    receipt_type: Optional[str] = Query(None, description="Filter by receipt type"),
    overdue_only: bool = Query(False, description="Only overdue receipts"),
    current_user: dict = Depends(get_current_user),
):
    """List all submitted receipts with filters."""
    supabase = get_supabase()

    query = supabase.table("submitted_receipts").select("*")

    if status:
        query = query.eq("status", status)

    if person:
        query = query.ilike("insured_person", f"%{person}%")

    if receipt_type:
        query = query.eq("receipt_type", receipt_type)

    result = query.order("submission_date", desc=True).execute()

    receipts = result.data

    # Enrich with settlement info for linked receipts
    linked_item_ids = [r["settlement_item_id"] for r in receipts if r.get("settlement_item_id")]
    settlement_info = {}

    if linked_item_ids:
        items_result = supabase.table("settlement_items").select(
            "id, receipt_number, settlements(settlement_number)"
        ).in_("id", linked_item_ids).execute()

        for item in items_result.data:
            settlement = item.get("settlements", {}) or {}
            settlement_info[item["id"]] = {
                "receipt_number": item.get("receipt_number"),
                "settlement_number": settlement.get("settlement_number"),
            }

    # Enrich with payment transaction info for linked payments
    linked_tx_ids = [r["payment_transaction_id"] for r in receipts if r.get("payment_transaction_id")]
    payment_info = {}

    if linked_tx_ids:
        tx_result = supabase.table("bank_transactions").select(
            "id, amount, booking_date, description"
        ).in_("id", linked_tx_ids).execute()

        for tx in tx_result.data:
            payment_info[tx["id"]] = {
                "paid_amount": abs(tx.get("amount", 0)),  # Store as positive value
                "payment_description": tx.get("description", "")[:50],
            }

    # Add settlement info and payment info to receipts
    for receipt in receipts:
        item_id = receipt.get("settlement_item_id")
        if item_id and item_id in settlement_info:
            receipt["settlement_number"] = settlement_info[item_id].get("settlement_number")
            receipt["receipt_number"] = settlement_info[item_id].get("receipt_number")
        else:
            receipt["settlement_number"] = None
            receipt["receipt_number"] = None

        # Add payment transaction info (only if not already in DB)
        tx_id = receipt.get("payment_transaction_id")
        if tx_id and tx_id in payment_info:
            # Only set if not already stored in DB
            if not receipt.get("paid_amount"):
                receipt["paid_amount"] = payment_info[tx_id].get("paid_amount")
            receipt["payment_description"] = payment_info[tx_id].get("payment_description")
        else:
            # Don't overwrite DB value
            if "payment_description" not in receipt:
                receipt["payment_description"] = None

    # Filter overdue in Python (date comparison)
    today = date.today()
    if overdue_only:
        receipts = [
            r for r in receipts
            if r.get("status") == "submitted"
            and r.get("due_date")
            and datetime.strptime(r["due_date"], "%Y-%m-%d").date() < today
        ]

    # =========================================================================
    # STATS BERECHNUNG - Zwei unabhängige Beziehungen:
    # 1. PKV-ERSTATTUNG: Beziehung zur Krankenversicherung (status, reimbursed_*)
    # 2. ZAHLUNG AN LEISTUNGSERBRINGER: Arzt, Apotheke etc. (paid_date, paid_amount)
    # =========================================================================

    # === PKV-ERSTATTUNG ===
    # Belege die bei PKV eingereicht aber noch nicht erstattet wurden
    pending = [r for r in receipts if r.get("status") == "submitted"]
    total_amount = sum(r.get("invoice_amount") or 0 for r in pending)

    # Erstattung überfällig: >30 Tage seit Einreichung, PKV hat noch nicht erstattet
    reimbursement_overdue = [
        r for r in pending
        if r.get("submission_date")
        and datetime.strptime(r["submission_date"], "%Y-%m-%d").date() + timedelta(days=30) < today
    ]

    # === ZAHLUNG AN LEISTUNGSERBRINGER ===
    # Zahlung überfällig: Zahlungsfrist überschritten, Leistungserbringer noch nicht bezahlt
    # UNABHÄNGIG vom PKV-Status - auch erstattete Belege können unbezahlt sein!
    payment_overdue = [
        r for r in receipts
        if r.get("due_date")
        and datetime.strptime(r["due_date"], "%Y-%m-%d").date() < today
        and not r.get("paid_date")
        and r.get("receipt_type") != "rezept"  # Rezepte: Direktzahlung in Apotheke
    ]

    # Unbezahlt: Leistungserbringer noch nicht bezahlt (unabhängig von PKV-Erstattung)
    unpaid = [
        r for r in receipts
        if r.get("receipt_type") not in ["rezept"]
        and not r.get("paid_date")
    ]

    # === LIQUIDITÄT ===
    # Liqui Saldo = Geld das aktuell "draußen" ist
    # Bezahlt aber noch nicht erstattet = Geld fehlt mir
    # Negativ = so viel Geld habe ich ausgegeben und noch nicht zurückbekommen
    paid_awaiting_reimbursement = [
        r for r in receipts
        if r.get("status") == "submitted"  # Noch nicht erstattet
        and r.get("paid_date")  # Aber schon bezahlt
    ]
    liqui_saldo = -sum(r.get("paid_amount") or r.get("invoice_amount") or 0 for r in paid_awaiting_reimbursement)

    total_count = len(receipts)

    # Apply pagination
    receipts = receipts[offset:offset + limit]

    return ReceiptListResponse(
        receipts=receipts,
        total=total_count,
        total_amount=total_amount,
        pending_count=len(pending),
        overdue_count=len(payment_overdue),
        reimbursement_overdue_count=len(reimbursement_overdue),
        unpaid_count=len(unpaid),
        liqui_saldo=liqui_saldo,
    )


@router.get("/stats", response_model=ReceiptStats)
async def get_receipt_stats(
    current_user: dict = Depends(get_current_user),
):
    """Get receipt statistics."""
    supabase = get_supabase()

    result = supabase.table("submitted_receipts").select("*").execute()
    receipts = result.data

    today = date.today()

    submitted = [r for r in receipts if r.get("status") == "submitted"]
    reimbursed = [r for r in receipts if r.get("status") == "reimbursed"]
    rejected = [r for r in receipts if r.get("status") == "rejected"]

    overdue = [
        r for r in submitted
        if r.get("due_date") and datetime.strptime(r["due_date"], "%Y-%m-%d").date() < today
    ]

    due_soon = [
        r for r in submitted
        if r.get("due_date")
        and today <= datetime.strptime(r["due_date"], "%Y-%m-%d").date() < today.replace(day=today.day + 7)
    ]

    return ReceiptStats(
        total_count=len(receipts),
        submitted_count=len(submitted),
        reimbursed_count=len(reimbursed),
        rejected_count=len(rejected),
        total_submitted_amount=sum(r.get("invoice_amount") or 0 for r in submitted),
        total_reimbursed_amount=sum(r.get("reimbursed_amount") or 0 for r in reimbursed),
        overdue_count=len(overdue),
        due_soon_count=len(due_soon),
    )


@router.get("/{receipt_id}", response_model=ReceiptResponse)
async def get_receipt(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single receipt by ID."""
    supabase = get_supabase()

    result = supabase.table("submitted_receipts").select("*").eq("id", receipt_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    return result.data[0]


@router.post("/upload", response_model=ReceiptUploadResponse)
async def upload_receipt(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload and parse a receipt PDF."""

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt")

    content = await file.read()

    # Save to temp file
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Parse receipt
        receipt = parse_receipt(tmp_path)
        data = receipt_to_dict(receipt)

        # Override filename with original
        data["pdf_filename"] = file.filename

        # Remove raw_text before saving
        data.pop("raw_text", None)

        # Save to Supabase
        supabase = get_supabase()

        # Check for duplicate
        existing = supabase.table("submitted_receipts").select("id").eq(
            "pdf_hash", data["pdf_hash"]
        ).execute()

        if existing.data:
            raise HTTPException(
                status_code=409,
                detail=f"Beleg bereits vorhanden (ID: {existing.data[0]['id']})"
            )

        result = supabase.table("submitted_receipts").insert(data).execute()

        receipt_id = result.data[0]["id"]

        return ReceiptUploadResponse(
            success=True,
            receipt_id=receipt_id,
            receipt_type=data.get("receipt_type", "sonstige"),
            invoice_amount=data.get("invoice_amount"),
            due_date=data.get("due_date"),
            message=f"Beleg erfolgreich hochgeladen: {data.get('provider_name', 'Unbekannt')}",
        )

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parser-Fehler: {str(e)}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import", response_model=ReceiptImportResponse)
async def import_receipt(
    file: UploadFile = File(...),
    data: str = Query(..., description="JSON string with extracted receipt data"),
    current_user: dict = Depends(get_current_user),
):
    """
    Import a receipt with pre-extracted data (from n8n/Claude Vision).

    This endpoint is designed for automated workflows where:
    1. n8n triggers on new file in Google Drive
    2. Claude Vision extracts the data
    3. n8n calls this endpoint with the file + extracted JSON

    Parameters:
    - file: The PDF/image file (multipart/form-data)
    - data: JSON string with extracted fields (Query parameter)

    Example data JSON:
    {
        "receipt_type": "arzt",
        "provider_name": "Dr. Müller",
        "invoice_amount": 123.45,
        "invoice_date": "2025-01-15",
        "insured_person": "Mila",
        "description": "U-Untersuchung",
        "submission_date": "2025-01-09"  // Optional: defaults to PDF creation date
    }
    """
    supabase = get_supabase()

    # Parse the JSON data
    try:
        parsed_data = json.loads(data)
    except json.JSONDecodeError as e:
        raise HTTPException(status_code=400, detail=f"Ungültiges JSON: {str(e)}")

    # Read file content
    content = await file.read()

    # Calculate hash for duplicate detection
    pdf_hash = hashlib.sha256(content).hexdigest()

    # Extract PDF creation date for submission_date fallback
    pdf_creation_date = None
    if file.filename and file.filename.lower().endswith(".pdf"):
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(content)
            tmp_path = tmp.name
        try:
            pdf_creation_date = get_pdf_creation_date(tmp_path)
        except Exception:
            pass
        finally:
            Path(tmp_path).unlink(missing_ok=True)

    # Check for duplicate by pdf_hash
    existing = supabase.table("submitted_receipts").select("id, provider_name, invoice_amount").eq(
        "pdf_hash", pdf_hash
    ).execute()

    if existing.data:
        existing_receipt = existing.data[0]
        return ReceiptImportResponse(
            success=True,
            receipt_id=existing_receipt["id"],
            receipt_type=None,
            provider_name=existing_receipt.get("provider_name"),
            invoice_amount=existing_receipt.get("invoice_amount"),
            message=f"Beleg bereits vorhanden (gleiche Datei)",
            duplicate=True,
        )

    # Check for duplicate by content (provider + amount + date + person)
    provider_name = parsed_data.get("provider_name")
    invoice_amount = parsed_data.get("invoice_amount")
    invoice_date = parsed_data.get("invoice_date")
    insured_person = parsed_data.get("insured_person")

    if provider_name and invoice_amount and invoice_date:
        query = supabase.table("submitted_receipts").select("id, provider_name, invoice_amount, insured_person").eq(
            "provider_name", provider_name
        ).eq(
            "invoice_amount", invoice_amount
        ).eq(
            "invoice_date", invoice_date
        )
        if insured_person:
            query = query.eq("insured_person", insured_person)
        content_duplicate = query.execute()

        if content_duplicate.data:
            existing_receipt = content_duplicate.data[0]
            return ReceiptImportResponse(
                success=True,
                receipt_id=existing_receipt["id"],
                receipt_type=None,
                provider_name=existing_receipt.get("provider_name"),
                invoice_amount=existing_receipt.get("invoice_amount"),
                message=f"Beleg bereits vorhanden (gleicher Anbieter, Betrag, Datum und Person)",
                duplicate=True,
            )

    # Build receipt data
    today = date.today()

    # Calculate due_date: use provided value, or 30 days from invoice_date, or 30 days from today
    due_date = parsed_data.get("due_date")
    if not due_date:
        invoice_date_str = parsed_data.get("invoice_date")
        if invoice_date_str:
            try:
                invoice_date_obj = datetime.strptime(invoice_date_str, "%Y-%m-%d").date()
                due_date = (invoice_date_obj + timedelta(days=30)).isoformat()
            except ValueError:
                due_date = (today + timedelta(days=30)).isoformat()
        else:
            due_date = (today + timedelta(days=30)).isoformat()

    receipt_data = {
        "submission_date": parsed_data.get("submission_date") or pdf_creation_date or today.isoformat(),
        "pdf_filename": file.filename,
        "pdf_hash": pdf_hash,
        "status": "submitted",
        # Extracted fields from Claude Vision
        "receipt_type": parsed_data.get("receipt_type"),
        "provider_name": parsed_data.get("provider_name"),
        "invoice_number": parsed_data.get("invoice_number"),
        "invoice_date": parsed_data.get("invoice_date"),
        "invoice_amount": parsed_data.get("invoice_amount"),
        "insured_person": parsed_data.get("insured_person"),
        "description": parsed_data.get("description"),
        "treatment_period": parsed_data.get("treatment_period"),
        "due_date": due_date,
        "due_date_source": "api" if parsed_data.get("due_date") else "calculated",
        # Payment details for QR code generation
        "payment_recipient": parsed_data.get("payment_recipient"),
        "payment_iban": parsed_data.get("payment_iban"),
        "payment_reference": parsed_data.get("payment_reference"),
        # Store original parsed params for reference (even after manual edits)
        "parsed_params": parsed_data,
    }

    # Remove None values to let DB defaults apply
    receipt_data = {k: v for k, v in receipt_data.items() if v is not None}

    try:
        # Insert receipt into database
        result = supabase.table("submitted_receipts").insert(receipt_data).execute()
        receipt_id = result.data[0]["id"]

        # Upload PDF to Supabase Storage (sanitize filename for Supabase)
        safe_filename = sanitize_filename(file.filename)
        storage_path = f"{receipt_id}/{safe_filename}"
        try:
            supabase.storage.from_("receipts").upload(
                storage_path,
                content,
                {"content-type": file.content_type or "application/pdf"}
            )

            # Update receipt with storage path
            supabase.table("submitted_receipts").update({
                "pdf_url": storage_path
            }).eq("id", receipt_id).execute()

        except Exception as storage_error:
            # Log but don't fail - receipt is saved, just no PDF
            print(f"Storage upload failed: {storage_error}")

        return ReceiptImportResponse(
            success=True,
            receipt_id=receipt_id,
            receipt_type=receipt_data.get("receipt_type"),
            provider_name=receipt_data.get("provider_name"),
            invoice_amount=receipt_data.get("invoice_amount"),
            message=f"Beleg erfolgreich importiert: {receipt_data.get('provider_name', 'Unbekannt')}",
            duplicate=False,
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import fehlgeschlagen: {str(e)}")


@router.patch("/{receipt_id}", response_model=ReceiptResponse)
async def update_receipt(
    receipt_id: str,
    update: ReceiptUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update receipt status or link to settlement."""
    supabase = get_supabase()

    # Check receipt exists and get current data
    existing = supabase.table("submitted_receipts").select("*").eq("id", receipt_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    receipt = existing.data[0]

    # Build update dict with proper date serialization
    # Use model_dump(exclude_unset=True) to distinguish between None and not provided
    update_data = {}
    raw_data = update.model_dump(exclude_unset=True)

    # Protected fields that must never be updated via PATCH
    # These are set during upload and should remain immutable
    protected_fields = {'parsed_params', 'raw_text', 'pdf_hash', 'id', 'created_at'}

    for k, v in raw_data.items():
        # Skip protected fields
        if k in protected_fields:
            continue
        # Convert date objects to ISO strings for Supabase
        if v is not None and hasattr(v, 'isoformat'):
            update_data[k] = v.isoformat()
        else:
            update_data[k] = v

    if not update_data:
        raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

    # Handle unlinking: if settlement_item_id is explicitly set to None
    if "settlement_item_id" in update_data and update_data["settlement_item_id"] is None:
        # Reset all reimbursement-related fields
        update_data["settlement_item_id"] = None
        update_data["reimbursed_amount"] = None
        update_data["reimbursed_date"] = None
        update_data["status"] = "submitted"

    # Validate settlement_item_id if provided (not None)
    if update_data.get("settlement_item_id"):
        item_check = supabase.table("settlement_items").select(
            "id, receipt_number, settlements(settlement_date)"
        ).eq("id", update_data["settlement_item_id"]).execute()

        if not item_check.data:
            raise HTTPException(
                status_code=400,
                detail=f"Settlement Item nicht gefunden: {update_data['settlement_item_id']}"
            )

        # Plausibility check: settlement_date must be after submission_date
        # Can be skipped for manual linking via skip_date_check flag
        skip_date_check = update.skip_date_check
        if not skip_date_check:
            item_data = item_check.data[0]
            settlement = item_data.get("settlements", {}) or {}
            settlement_date_str = settlement.get("settlement_date")
            submission_date_str = receipt.get("submission_date")

            if settlement_date_str and submission_date_str:
                settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
                submission_date = datetime.strptime(submission_date_str, "%Y-%m-%d").date()

                if settlement_date < submission_date:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Ungültige Verknüpfung: Erstattungsdatum ({settlement_date_str}) liegt vor Einreichungsdatum ({submission_date_str})"
                    )

    # Check if payment_transaction_id is already linked to another receipt
    if update_data.get("payment_transaction_id"):
        txn_id = update_data["payment_transaction_id"]

        # Fetch transaction to get the paid_amount
        txn_data = supabase.table("bank_transactions").select(
            "id, amount, booking_date"
        ).eq("id", txn_id).execute()

        if txn_data.data:
            txn = txn_data.data[0]
            # Store paid_amount as positive value (transactions are negative for payments)
            update_data["paid_amount"] = abs(txn.get("amount", 0))
            # Also update paid_date if not already set
            if not update_data.get("paid_date") and txn.get("booking_date"):
                update_data["paid_date"] = txn["booking_date"]

            # Validate that payment date is not before invoice date
            txn_date = txn.get("booking_date")
            invoice_date = receipt.get("invoice_date")
            if txn_date and invoice_date and txn_date < invoice_date:
                raise HTTPException(
                    status_code=400,
                    detail=f"Ungültige Verknüpfung: Zahlungsdatum ({txn_date}) liegt vor Rechnungsdatum ({invoice_date})"
                )

        existing_link = supabase.table("submitted_receipts").select(
            "id, provider_name, invoice_amount"
        ).eq("payment_transaction_id", txn_id).neq("id", receipt_id).execute()

        if existing_link.data:
            other_receipt = existing_link.data[0]
            force_unlink = update.force_unlink_payment

            if not force_unlink:
                # Return error with info about the other receipt
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Zahlung bereits einem anderen Beleg zugeordnet",
                        "linked_receipt": {
                            "id": other_receipt["id"],
                            "provider_name": other_receipt.get("provider_name"),
                            "invoice_amount": other_receipt.get("invoice_amount"),
                        }
                    }
                )

            # Force unlink: remove payment from other receipt
            supabase.table("submitted_receipts").update({
                "payment_transaction_id": None,
                "paid_date": None,
            }).eq("id", other_receipt["id"]).execute()

    # Remove non-DB fields from update_data
    update_data.pop("force_unlink_payment", None)
    update_data.pop("skip_date_check", None)

    # Update
    result = supabase.table("submitted_receipts").update(update_data).eq("id", receipt_id).execute()

    return result.data[0]


@router.delete("/{receipt_id}")
async def delete_receipt(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a receipt."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("submitted_receipts").select("id").eq("id", receipt_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    supabase.table("submitted_receipts").delete().eq("id", receipt_id).execute()

    return {"success": True, "message": "Beleg gelöscht"}


@router.post("/{receipt_id}/upload-pdf")
async def upload_receipt_pdf(
    receipt_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload PDF to Supabase Storage and link to receipt."""
    supabase = get_supabase()

    # Check receipt exists
    existing = supabase.table("submitted_receipts").select("id,pdf_filename").eq("id", receipt_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt")

    content = await file.read()

    # Upload to Supabase Storage (sanitize filename for Supabase)
    safe_filename = sanitize_filename(file.filename)
    storage_path = f"{receipt_id}/{safe_filename}"

    try:
        # Upload file to 'receipts' bucket
        supabase.storage.from_("receipts").upload(
            storage_path,
            content,
            {"content-type": "application/pdf"}
        )

        # Update receipt with storage path (not full URL!)
        supabase.table("submitted_receipts").update({
            "pdf_url": storage_path,
            "pdf_filename": file.filename
        }).eq("id", receipt_id).execute()

        return {
            "success": True,
            "storage_path": storage_path,
            "message": "PDF erfolgreich hochgeladen"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Upload fehlgeschlagen: {str(e)}")


@router.get("/{receipt_id}/pdf-url")
async def get_receipt_pdf_url(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate a signed URL for the receipt PDF (valid for 1 hour)."""
    supabase = get_supabase()

    # Get receipt with pdf_url (which is the storage path)
    result = supabase.table("submitted_receipts").select("id, pdf_url, pdf_filename").eq("id", receipt_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    receipt = result.data[0]
    storage_path = receipt.get("pdf_url")

    if not storage_path:
        raise HTTPException(status_code=404, detail="Kein PDF für diesen Beleg vorhanden")

    # If it's an old full URL, extract just the path
    if storage_path.startswith("http"):
        parts = storage_path.split("/receipts/", 1)
        if len(parts) > 1:
            storage_path = parts[1]
        else:
            raise HTTPException(status_code=400, detail="Ungültiger PDF-Pfad")

    try:
        # Generate signed URL valid for 1 hour (3600 seconds)
        signed_url_result = supabase.storage.from_("receipts").create_signed_url(
            storage_path,
            expires_in=3600
        )

        return {
            "signed_url": signed_url_result["signedURL"],
            "expires_in": 3600,
            "filename": receipt.get("pdf_filename")
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Signed URL Erstellung fehlgeschlagen: {str(e)}")


@router.delete("/{receipt_id}/pdf")
async def delete_receipt_pdf(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Delete PDF from storage and reset PDF-related fields.
    This allows uploading a new/correct PDF afterwards.

    Resets: pdf_url, pdf_filename, pdf_hash, parsed_params
    """
    supabase = get_supabase()

    # Get receipt with pdf_url
    result = supabase.table("submitted_receipts").select(
        "id, pdf_url, pdf_filename"
    ).eq("id", receipt_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    receipt = result.data[0]
    storage_path = receipt.get("pdf_url")

    # Delete from storage if exists
    if storage_path:
        # Handle old full URLs
        if storage_path.startswith("http"):
            parts = storage_path.split("/receipts/", 1)
            if len(parts) > 1:
                storage_path = parts[1]

        try:
            supabase.storage.from_("receipts").remove([storage_path])
        except Exception as e:
            # Log but continue - file might not exist
            print(f"Storage delete warning: {e}")

    # Reset PDF-related fields in database
    supabase.table("submitted_receipts").update({
        "pdf_url": None,
        "pdf_filename": None,
        "pdf_hash": None,
        "parsed_params": None,
    }).eq("id", receipt_id).execute()

    return {
        "success": True,
        "message": "PDF und zugehörige Parameter entfernt. Ein neues PDF kann jetzt hochgeladen werden."
    }


@router.post("/match-settlements")
async def match_receipts_to_settlements(
    current_user: dict = Depends(get_current_user),
):
    """
    Try to match submitted receipts with settlement items.

    Match criteria:
    - invoice_amount must match EXACTLY (before any PKV deductions)
    - Person match is optional (sometimes billed under different family member)
    - If multiple matches found, picks the one with best score

    Returns details about matches found and any ambiguous cases.
    """
    supabase = get_supabase()

    # Get unmatched receipts
    receipts = supabase.table("submitted_receipts").select("*").eq(
        "status", "submitted"
    ).is_("settlement_item_id", "null").execute()

    # Get settlement items with settlement info
    items = supabase.table("settlement_items").select(
        "*, settlements(settlement_date, settlement_number)"
    ).execute()

    # Get already linked item IDs to avoid double-linking
    linked_result = supabase.table("submitted_receipts").select(
        "settlement_item_id"
    ).not_.is_("settlement_item_id", "null").execute()
    linked_ids = {r["settlement_item_id"] for r in linked_result.data if r.get("settlement_item_id")}

    matched = 0
    match_details = []

    for receipt in receipts.data:
        receipt_amount = receipt.get("invoice_amount")
        if not receipt_amount:
            continue

        receipt_person = (receipt.get("insured_person") or "").lower()
        receipt_period = receipt.get("treatment_period") or receipt.get("description") or ""
        receipt_submission_date_str = receipt.get("submission_date")

        # Parse receipt submission date for plausibility check
        receipt_submission_date = None
        if receipt_submission_date_str:
            try:
                receipt_submission_date = datetime.strptime(receipt_submission_date_str, "%Y-%m-%d").date()
            except ValueError:
                pass

        # Find all matching items by EXACT amount
        candidates = []
        for item in items.data:
            # Skip already linked items
            if item["id"] in linked_ids:
                continue

            item_amount = item.get("invoice_amount")

            # EXACT amount match required (invoice_amount, not reimbursed_amount)
            if item_amount is None or abs(item_amount - receipt_amount) > 0.01:
                continue

            # Plausibility check: settlement_date must be >= submission_date
            settlement = item.get("settlements", {}) or {}
            settlement_date_str = settlement.get("settlement_date")
            if receipt_submission_date and settlement_date_str:
                try:
                    settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
                    if settlement_date < receipt_submission_date:
                        # Skip - reimbursement cannot happen before submission
                        continue
                except ValueError:
                    pass

            # Calculate match score for ranking
            score = 50  # Base score for exact amount match

            # Person match bonus
            item_person = (item.get("insured_person") or "").lower()
            if receipt_person and item_person:
                if receipt_person in item_person or item_person in receipt_person:
                    score += 30

            # Treatment period bonus
            item_period = item.get("treatment_period") or ""
            if receipt_period and item_period:
                if any(part in item_period for part in receipt_period.split() if len(part) > 3):
                    score += 20

            # Calculate days between submission and settlement for tie-breaking
            days_diff = 9999
            if receipt_submission_date and settlement_date_str:
                try:
                    settlement_date = datetime.strptime(settlement_date_str, "%Y-%m-%d").date()
                    days_diff = (settlement_date - receipt_submission_date).days
                except ValueError:
                    pass

            candidates.append((item, score, days_diff))

        if not candidates:
            continue

        # Sort by score (desc), then by days_diff (asc) - closest settlement date wins
        candidates.sort(key=lambda x: (-x[1], x[2]))

        # Always pick the best candidate (highest score, closest date)
        if len(candidates) >= 1:
            best_item, best_score, best_days = candidates[0]
            settlement = best_item.get("settlements", {}) or {}

            supabase.table("submitted_receipts").update({
                "status": "reimbursed",
                "settlement_item_id": best_item["id"],
                "reimbursed_amount": best_item.get("reimbursed_amount"),
                "reimbursed_date": settlement.get("settlement_date"),
            }).eq("id", receipt["id"]).execute()

            linked_ids.add(best_item["id"])  # Mark as used
            matched += 1

            match_details.append({
                "receipt_id": receipt["id"],
                "provider": receipt.get("provider_name"),
                "matched_to": best_item.get("receipt_number"),
                "score": best_score,
                "days_after_submission": best_days,
            })

    return {
        "success": True,
        "checked": len(receipts.data),
        "matched": matched,
        "details": match_details,
        "message": f"{matched} Belege verknüpft",
    }


def load_matching_rules(supabase) -> list:
    """Load active matching rules from database, ordered by priority."""
    result = supabase.table("matching_rules").select("*").eq(
        "active", True
    ).order("priority", desc=True).execute()
    return result.data


def matches_provider_with_rules(txn_desc: str, provider_name: str, rules: list) -> tuple[bool, str]:
    """
    Check if provider name matches transaction description using dynamic rules.
    Returns (is_match, match_type)
    """
    if not txn_desc or not provider_name:
        return False, ""

    desc_upper = txn_desc.upper()
    provider_upper = provider_name.upper()

    # Direct match
    if provider_upper in desc_upper:
        return True, "provider"

    # Check against dynamic rules from database
    for rule in rules:
        pattern = rule.get("provider_pattern", "").upper()
        bank_patterns = rule.get("bank_patterns", [])
        match_type = rule.get("match_type", "provider")

        if pattern and pattern in provider_upper:
            for bank_pattern in bank_patterns:
                if bank_pattern.upper() in desc_upper:
                    return True, match_type

    # Fallback: Try each word >= 3 chars from provider name
    provider_words = [w for w in provider_upper.split() if len(w) >= 3]
    if any(word in desc_upper for word in provider_words):
        return True, "provider"

    return False, ""


def extract_treatment_date(description: str) -> str | None:
    """Extract treatment date (DD.MM.YYYY) from bank description."""
    import re
    if not description:
        return None
    match = re.search(r'(\d{2}\.\d{2}\.\d{4})', description)
    return match.group(1) if match else None


def parse_german_date(german_date: str) -> str | None:
    """Convert DD.MM.YYYY to YYYY-MM-DD."""
    import re
    if not german_date:
        return None
    match = re.match(r'(\d{2})\.(\d{2})\.(\d{4})', german_date)
    if not match:
        return None
    return f"{match.group(3)}-{match.group(2)}-{match.group(1)}"


@router.get("/{receipt_id}/suggest-payments")
async def suggest_payments_for_receipt(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Get payment suggestions for a specific receipt.
    Returns matching transactions based on dynamic rules from database.
    Includes info about which transactions are already linked to other receipts.
    """
    supabase = get_supabase()

    # Get the receipt
    receipt_result = supabase.table("submitted_receipts").select("*").eq(
        "id", receipt_id
    ).single().execute()
    receipt = receipt_result.data

    if not receipt:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    # Load matching rules
    rules = load_matching_rules(supabase)

    # Get all outgoing bank transactions (limit higher than default 1000)
    transactions = supabase.table("bank_transactions").select("*").lt(
        "amount", 0
    ).order("booking_date", desc=True).limit(10000).execute()

    # Get all receipts that have payment links (to check for already-assigned transactions)
    linked_receipts = supabase.table("submitted_receipts").select(
        "id, payment_transaction_id, provider_name, invoice_amount, invoice_date"
    ).not_.is_("payment_transaction_id", "null").execute()

    # Build a map: transaction_id -> linked receipt info
    transaction_to_receipt = {}
    for r in linked_receipts.data:
        txn_id = r.get("payment_transaction_id")
        if txn_id and r["id"] != receipt_id:  # Exclude current receipt
            transaction_to_receipt[txn_id] = {
                "receipt_id": r["id"],
                "provider_name": r.get("provider_name"),
                "invoice_amount": r.get("invoice_amount"),
                "invoice_date": r.get("invoice_date"),
            }

    receipt_amount = receipt.get("invoice_amount") or 0
    provider_name = receipt.get("provider_name") or ""
    invoice_date = receipt.get("invoice_date")
    treatment_period = receipt.get("treatment_period")

    matching = []
    same_amount = []

    for txn in transactions.data:
        txn_amount = abs(txn["amount"])
        amount_matches = abs(txn_amount - receipt_amount) < 0.02

        if not amount_matches:
            continue

        # Zahlung muss nach Rechnungsdatum sein
        txn_date = txn.get("booking_date")
        if invoice_date and txn_date and txn_date < invoice_date:
            continue

        txn_desc = txn.get("description") or ""
        is_match, match_type = matches_provider_with_rules(txn_desc, provider_name, rules)

        # For Verhinderungspflege: also check treatment date
        if match_type == "verhinderungspflege" and is_match:
            treatment_date_in_bank = extract_treatment_date(txn_desc)
            treatment_date_iso = parse_german_date(treatment_date_in_bank)

            # Must match invoice_date or treatment_period
            date_matches = False
            if treatment_date_iso and invoice_date == treatment_date_iso:
                date_matches = True
            if treatment_date_in_bank and treatment_period and treatment_date_in_bank in treatment_period:
                date_matches = True

            if not date_matches:
                # Downgrade to same_amount if date doesn't match
                same_amount.append({
                    **txn,
                    "treatment_date": treatment_date_in_bank,
                    "match_reason": "amount_only",
                    "linked_to_receipt": transaction_to_receipt.get(txn["id"]),
                })
                continue

        # Check if this transaction is already linked to another receipt
        linked_info = transaction_to_receipt.get(txn["id"])

        if is_match:
            matching.append({
                **txn,
                "treatment_date": extract_treatment_date(txn_desc),
                "match_reason": f"amount+{match_type}",
                "linked_to_receipt": linked_info,
            })
        else:
            same_amount.append({
                **txn,
                "treatment_date": extract_treatment_date(txn_desc),
                "match_reason": "amount_only",
                "linked_to_receipt": linked_info,
            })

    return {
        "receipt_id": receipt_id,
        "matching": matching,
        "same_amount": same_amount[:20],  # Limit fallback list
    }


@router.post("/match-payments")
async def match_receipts_to_payments(
    current_user: dict = Depends(get_current_user),
):
    """
    Try to match submitted receipts with bank payments.
    Uses dynamic matching rules from database.
    Only matches outgoing payments (negative amounts).
    Limited to transactions from last 365 days.
    """
    supabase = get_supabase()

    # Load matching rules from database
    rules = load_matching_rules(supabase)

    # Get receipts without payment link (exclude rezept type - those are typically paid at pharmacy)
    receipts = supabase.table("submitted_receipts").select("*").is_(
        "payment_transaction_id", "null"
    ).neq("receipt_type", "rezept").execute()

    # Get outgoing bank transactions from last 365 days (negative amounts = payments)
    # Limit to 10000 rows AND last year as double safeguard for growing data
    from datetime import datetime, timedelta
    one_year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    transactions = supabase.table("bank_transactions").select("*").lt(
        "amount", 0
    ).gte("booking_date", one_year_ago).order("booking_date", desc=True).limit(10000).execute()

    # Get already linked transaction IDs to avoid double-linking
    linked_transactions = supabase.table("submitted_receipts").select(
        "payment_transaction_id"
    ).not_.is_("payment_transaction_id", "null").execute()
    linked_tx_ids = {r["payment_transaction_id"] for r in linked_transactions.data if r.get("payment_transaction_id")}

    matched = 0

    for receipt in receipts.data:
        if not receipt.get("invoice_amount"):
            continue

        receipt_amount = receipt["invoice_amount"]
        provider_name = receipt.get("provider_name") or ""
        invoice_date = receipt.get("invoice_date")
        treatment_period = receipt.get("treatment_period")

        for txn in transactions.data:
            # Amount match
            txn_amount = abs(txn["amount"])
            if abs(txn_amount - float(receipt_amount)) > 0.01:
                continue

            # Zahlung muss nach Rechnungsdatum sein
            txn_date = txn.get("booking_date")
            if invoice_date and txn_date and txn_date < invoice_date:
                continue

            txn_desc = txn.get("description") or ""

            # Provider matching with dynamic rules
            is_match, match_type = matches_provider_with_rules(txn_desc, provider_name, rules)

            if not is_match:
                continue

            # For Verhinderungspflege: also check treatment date
            if match_type == "verhinderungspflege":
                treatment_date_in_bank = extract_treatment_date(txn_desc)
                treatment_date_iso = parse_german_date(treatment_date_in_bank)

                date_matches = False
                if treatment_date_iso and invoice_date == treatment_date_iso:
                    date_matches = True
                if treatment_date_in_bank and treatment_period and treatment_date_in_bank in treatment_period:
                    date_matches = True

                if not date_matches:
                    continue

            # Skip if transaction already linked to another receipt
            if txn["id"] in linked_tx_ids:
                continue

            txn_date = txn.get("booking_date")
            txn_amount = abs(txn.get("amount", 0))  # Store as positive value

            # If receipt was manually marked as paid, payment date must be
            # within -1 day to +3 days (exclusive) of the paid_date
            paid_date = receipt.get("paid_date")
            if paid_date and txn_date:
                from datetime import date as date_type
                paid_dt = datetime.strptime(paid_date, "%Y-%m-%d").date()
                txn_dt = datetime.strptime(txn_date, "%Y-%m-%d").date()
                diff = (txn_dt - paid_dt).days
                if diff < -1 or diff >= 3:
                    continue

            # Match found - update receipt
            supabase.table("submitted_receipts").update({
                "payment_transaction_id": txn["id"],
                "paid_date": txn_date,
                "paid_amount": txn_amount,
            }).eq("id", receipt["id"]).execute()

            # Mark transaction as used to avoid double-linking in this run
            linked_tx_ids.add(txn["id"])

            matched += 1
            break

    return {
        "success": True,
        "checked": len(receipts.data),
        "matched": matched,
        "message": f"{matched} Belege mit Zahlungen verknüpft",
    }


@router.post("/{receipt_id}/payment-qr", response_model=PaymentQRResponse)
async def generate_payment_qr(
    receipt_id: str,
    request: PaymentQRRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    Generiert EPC QR-Code Daten für SEPA-Überweisung.

    Der QR-Code kann von Banking-Apps gescannt werden.
    IBAN wird validiert bevor der QR-Code generiert wird.
    Bei Erfolg wird die IBAN für diesen Anbieter gespeichert.
    """
    supabase = get_supabase()

    # Validiere IBAN
    iban_valid, iban_error = validate_iban(request.iban)

    if not iban_valid:
        return PaymentQRResponse(
            success=False,
            recipient=request.recipient,
            iban=request.iban,
            amount=request.amount,
            reference=request.reference,
            iban_valid=False,
            error=iban_error
        )

    # Generiere QR-Code Daten
    qr_data = generate_epc_qr_data(
        recipient=request.recipient,
        iban=request.iban,
        amount=request.amount,
        reference=request.reference
    )

    cleaned_iban = request.iban.replace(" ", "").upper()

    # Speichere Zahlungsdaten für diesen Anbieter (für zukünftige Verwendung)
    try:
        # Hole den Beleg für den Provider-Namen
        receipt_result = supabase.table("submitted_receipts").select("provider_name").eq("id", receipt_id).execute()
        if receipt_result.data:
            provider_name = receipt_result.data[0].get("provider_name")
            if provider_name:
                provider_pattern = normalize_provider_name(provider_name)

                # Upsert: Update wenn existiert, sonst Insert
                supabase.table("provider_payment_info").upsert({
                    "provider_pattern": provider_pattern,
                    "payment_recipient": request.recipient,
                    "payment_iban": cleaned_iban,
                    "active": True,
                }, on_conflict="provider_pattern").execute()
    except Exception as e:
        # Fehler beim Speichern ignorieren - QR-Code wurde trotzdem generiert
        print(f"Fehler beim Speichern der Provider-Zahlungsdaten: {e}")

    return PaymentQRResponse(
        success=True,
        qr_data=qr_data,
        recipient=request.recipient,
        iban=cleaned_iban,
        amount=request.amount,
        reference=request.reference,
        iban_valid=True
    )


@router.get("/{receipt_id}/payment-defaults")
async def get_payment_defaults(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Holt die Zahlungsdaten für einen Beleg.
    Priorität für IBAN/Empfänger:
    1. Am Beleg gespeichert (payment_iban, payment_recipient)
    2. Früher für diesen Anbieter gespeichert (provider_payment_info)
    3. Leer (Nutzer muss eingeben)
    """
    supabase = get_supabase()

    result = supabase.table("submitted_receipts").select("*").eq("id", receipt_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    receipt = result.data[0]
    provider_name = receipt.get("provider_name") or ""

    # Defaults generieren - Priorität: 1. Am Beleg, 2. Provider-Lookup, 3. Leer
    recipient = receipt.get("payment_recipient") or ""
    iban = receipt.get("payment_iban") or ""

    # Wenn keine IBAN am Beleg, suche in provider_payment_info
    if not iban and provider_name:
        provider_pattern = normalize_provider_name(provider_name)
        try:
            provider_info = supabase.table("provider_payment_info").select("*").eq(
                "provider_pattern", provider_pattern
            ).eq("active", True).execute()

            if provider_info.data:
                saved = provider_info.data[0]
                if not iban:
                    iban = saved.get("payment_iban") or ""
                if not recipient:
                    recipient = saved.get("payment_recipient") or ""
        except Exception as e:
            print(f"Fehler beim Laden der Provider-Zahlungsdaten: {e}")

    # Fallback für Empfänger: Provider-Name
    if not recipient:
        recipient = provider_name

    # Verwendungszweck: gespeichert oder generiert
    reference = receipt.get("payment_reference")
    if not reference:
        invoice_number = receipt.get("invoice_number") or "ohne Nr."
        invoice_date = receipt.get("invoice_date")
        if invoice_date:
            # Format: DD.MM.YYYY
            parts = invoice_date.split("-")
            if len(parts) == 3:
                invoice_date = f"{parts[2]}.{parts[1]}.{parts[0]}"
        else:
            invoice_date = "ohne Datum"
        reference = f"Rechnung Nr. {invoice_number} vom {invoice_date}"

    amount = receipt.get("invoice_amount") or 0

    # Prüfe ob IBAN gültig ist (falls vorhanden)
    iban_valid = False
    if iban:
        iban_valid, _ = validate_iban(iban)

    return {
        "receipt_id": receipt_id,
        "recipient": recipient,
        "iban": iban,
        "reference": reference,
        "amount": amount,
        "iban_valid": iban_valid,
        # Zusätzliche Infos für das Modal
        "provider_name": provider_name,
        "invoice_number": receipt.get("invoice_number"),
        "invoice_date": receipt.get("invoice_date"),
    }


# Claude Vision prompt for receipt parsing
CLAUDE_VISION_PROMPT = """Analysiere dieses PDF einer deutschen Rechnung/eines Belegs und extrahiere folgende Informationen als JSON:

{
  "receipt_type": "arzt|rezept|pflege|hilfsmittel|sonstige",
  "provider_name": "Name des Anbieters/Praxis/Apotheke",
  "invoice_number": "Rechnungsnummer falls vorhanden",
  "invoice_date": "YYYY-MM-DD",
  "invoice_amount": 123.45,
  "insured_person": "Name der behandelten/versicherten Person",
  "description": "Kurze Beschreibung der Leistung",
  "due_date": "YYYY-MM-DD falls angegeben, sonst null",
  "payment_recipient": "Name des Zahlungsempfängers für Überweisung",
  "payment_iban": "IBAN ohne Leerzeichen (z.B. DE89370400440532013000)",
  "payment_reference": "Verwendungszweck falls angegeben"
}

Regeln:
- receipt_type: "arzt" für Ärzte/Therapeuten/Kliniken, "rezept" für Apotheken, "pflege" für Pflegedienste/Lebenshilfe, "hilfsmittel" für Sanitätshäuser/Optiker/Hörgeräte
- invoice_amount: Der Gesamtbetrag als Zahl (z.B. 48.24, nicht "48,24 €")
- payment_recipient: Der Kontoinhaber/Zahlungsempfänger für die Überweisung. Oft identisch mit provider_name, kann aber auch eine privatärztliche Verrechnungsstelle (PVS) o.ä. sein wenn über Abrechnungsstelle
- payment_iban: IBAN ohne Leerzeichen, nur Großbuchstaben und Zahlen. Deutsche IBANs beginnen mit "DE" und haben 22 Zeichen
- payment_reference: Vorgegebener Verwendungszweck falls auf der Rechnung angegeben
- Wenn ein Feld nicht erkennbar ist, setze null
- Antworte NUR mit dem JSON, keine Erklärungen"""


@router.post("/{receipt_id}/reparse")
async def reparse_receipt(
    receipt_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    Re-parse a receipt's PDF using Claude Vision.
    Updates parsed_params with the extracted data.
    """
    settings = get_settings()
    supabase = get_supabase()

    # Check if API key is configured
    if not settings.anthropic_claude_api_key:
        raise HTTPException(
            status_code=500,
            detail="Claude API Key nicht konfiguriert"
        )

    # Get receipt and check if PDF exists
    result = supabase.table("submitted_receipts").select(
        "id, pdf_url, pdf_filename"
    ).eq("id", receipt_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Beleg nicht gefunden")

    receipt = result.data[0]

    if not receipt.get("pdf_url"):
        raise HTTPException(
            status_code=400,
            detail="Kein PDF vorhanden. Bitte zuerst PDF hochladen."
        )

    # Download PDF from Supabase Storage
    try:
        pdf_data = supabase.storage.from_("receipts").download(receipt["pdf_url"])
        if not pdf_data:
            raise HTTPException(
                status_code=500,
                detail="PDF konnte nicht aus Storage geladen werden"
            )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Laden des PDFs: {str(e)}"
        )

    # Convert to base64
    pdf_base64 = base64.b64encode(pdf_data).decode("utf-8")

    # Call Claude Vision API
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_claude_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.anthropic_claude_model,
                    "max_tokens": 1024,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_base64
                                    }
                                },
                                {
                                    "type": "text",
                                    "text": CLAUDE_VISION_PROMPT
                                }
                            ]
                        }
                    ]
                }
            )

            if response.status_code != 200:
                error_detail = response.text
                raise HTTPException(
                    status_code=500,
                    detail=f"Claude API Fehler: {error_detail}"
                )

            claude_response = response.json()

    except httpx.TimeoutException:
        raise HTTPException(
            status_code=500,
            detail="Claude API Timeout - bitte erneut versuchen"
        )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise
        raise HTTPException(
            status_code=500,
            detail=f"Fehler bei Claude API Aufruf: {str(e)}"
        )

    # Parse Claude response
    try:
        text_content = claude_response["content"][0]["text"]
        # Remove markdown code blocks if present
        json_string = text_content.replace("```json\n", "").replace("```\n", "").replace("```", "").strip()
        parsed_params = json.loads(json_string)
    except (KeyError, json.JSONDecodeError) as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Parsen der Claude-Antwort: {str(e)}"
        )

    # Get current receipt data to check which fields are empty
    current_result = supabase.table("submitted_receipts").select("*").eq("id", receipt_id).execute()
    current_receipt = current_result.data[0] if current_result.data else {}

    # Build update dict - always update parsed_params, fill empty main fields
    update_data = {"parsed_params": parsed_params}
    fields_updated = []

    # Mapping from parsed_params keys to DB column names
    field_mapping = {
        "receipt_type": "receipt_type",
        "provider_name": "provider_name",
        "invoice_number": "invoice_number",
        "invoice_date": "invoice_date",
        "invoice_amount": "invoice_amount",
        "insured_person": "insured_person",
        "description": "description",
        "due_date": "due_date",
        "iban": "iban",
        "payment_reference": "payment_reference",
    }

    # For each field: if current value is empty/null and new value exists, update it
    for param_key, db_column in field_mapping.items():
        current_value = current_receipt.get(db_column)
        new_value = parsed_params.get(param_key)

        # Check if current is empty (None, empty string, or 0 for amounts)
        is_current_empty = current_value is None or current_value == "" or (
            db_column == "invoice_amount" and (current_value is None or current_value == 0)
        )

        # Check if new value is meaningful
        has_new_value = new_value is not None and new_value != ""

        if is_current_empty and has_new_value:
            update_data[db_column] = new_value
            fields_updated.append(db_column)

    # Update receipt and get the updated data
    try:
        result = supabase.table("submitted_receipts").update(update_data).eq("id", receipt_id).execute()
        updated_receipt = result.data[0] if result.data else None
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Fehler beim Speichern: {str(e)}"
        )

    return {
        "success": True,
        "receipt_id": receipt_id,
        "parsed_params": parsed_params,
        "fields_updated": fields_updated,
        "message": f"PDF erfolgreich neu geparst. {len(fields_updated)} leere Felder aktualisiert.",
        "receipt": updated_receipt,
    }
