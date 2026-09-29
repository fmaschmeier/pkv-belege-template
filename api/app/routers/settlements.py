"""
Settlement API Routes
"""
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from typing import Optional

from ..core.database import get_supabase

logger = logging.getLogger(__name__)
from ..core.auth import get_current_user
from ..schemas.settlements import (
    SettlementResponse,
    SettlementListResponse,
    SettlementUploadResponse,
    SettlementItemResponse,
    SettlementItemUpdateRequest,
    ItemListResponse,
)
from ..services.parser_service import ParserService

router = APIRouter(prefix="/settlements", tags=["Settlements"])


@router.get("", response_model=SettlementListResponse)
async def list_settlements(
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
    person: Optional[str] = Query(None, description="Filter by insured person"),
    year: Optional[int] = Query(None, description="Filter by year"),
    current_user: dict = Depends(get_current_user),
):
    """List all settlements with optional filters."""
    supabase = get_supabase()

    query = supabase.table("settlements").select("*, settlement_items(*)")

    if year:
        query = query.gte("settlement_date", f"{year}-01-01").lte("settlement_date", f"{year}-12-31")

    result = query.order("settlement_date", desc=True).range(offset, offset + limit - 1).execute()

    # Filter by person if specified (post-query filter since it's in items)
    settlements = result.data
    if person:
        settlements = [
            s for s in settlements
            if any(person.lower() in (item.get("insured_person") or "").lower()
                   for item in s.get("settlement_items", []))
        ]

    return SettlementListResponse(
        settlements=settlements,
        total=len(settlements),
    )


@router.get("/{settlement_id}", response_model=SettlementResponse)
async def get_settlement(
    settlement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single settlement with all items."""
    supabase = get_supabase()

    result = supabase.table("settlements").select(
        "*, settlement_items(*)"
    ).eq("id", settlement_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Settlement nicht gefunden")

    return result.data[0]


@router.post("/upload", response_model=SettlementUploadResponse)
async def upload_settlement(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload and parse a settlement PDF."""

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt")

    content = await file.read()

    try:
        service = ParserService()
        result = service.parse_settlement_pdf(content, file.filename)

        # Build parsed items for response
        from ..schemas.settlements import ParsedItemResponse

        parsed_items = []
        items_with_notes = []

        for item in result.get("items", []):
            # Convert notes list to string if needed
            notes = item.get("notes")
            if isinstance(notes, list):
                notes = " | ".join(str(n) for n in notes) if notes else None

            has_notes = bool(notes)

            parsed_item = ParsedItemResponse(
                receipt_number=item.get("receipt_number", ""),
                insured_person=item.get("insured_person"),
                description=item.get("description"),
                treatment_period=item.get("treatment_period"),
                invoice_amount=item.get("invoice_amount"),
                reimbursed_amount=item.get("reimbursed_amount"),
                notes=notes,
                has_notes=has_notes,
            )
            parsed_items.append(parsed_item)

            if has_notes:
                items_with_notes.append(parsed_item)

        # Determine if review is required
        requires_review = len(items_with_notes) > 0
        review_reason = None
        if requires_review:
            review_reason = f"{len(items_with_notes)} Position(en) mit PKV-Anmerkungen (z.B. Ablehnung, Kürzung)"

        return SettlementUploadResponse(
            success=True,
            settlement_id=result["id"],
            settlement_number=result["settlement_number"],
            settlement_date=result["settlement_date"],
            items_count=result["items_count"],
            total_invoiced=result.get("total_invoiced", 0) or 0,
            total_reimbursed=result["total_reimbursed"],
            message=f"Settlement {result['settlement_number']} erfolgreich importiert",
            requires_review=requires_review,
            review_reason=review_reason,
            items_with_notes_count=len(items_with_notes),
            items=parsed_items,
            items_with_notes=items_with_notes,
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Parser-Fehler: {str(e)}")


@router.get("/stats/summary")
async def get_settlement_stats(
    year: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get settlement statistics."""
    supabase = get_supabase()

    query = supabase.table("settlements").select("settlement_date, total_reimbursed")

    if year:
        query = query.gte("settlement_date", f"{year}-01-01").lte("settlement_date", f"{year}-12-31")

    result = query.execute()

    total_reimbursed = sum(s["total_reimbursed"] or 0 for s in result.data)

    # Get items count
    items_query = supabase.table("settlement_items").select("id", count="exact")
    items_result = items_query.execute()

    return {
        "settlements_count": len(result.data),
        "items_count": items_result.count,
        "total_reimbursed": total_reimbursed,
        "year": year or "all",
    }


@router.post("/{settlement_id}/upload-pdf")
async def upload_settlement_pdf(
    settlement_id: str,
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Upload PDF to Supabase Storage and link to settlement."""
    supabase = get_supabase()

    # Check settlement exists
    existing = supabase.table("settlements").select("id,pdf_filename").eq("id", settlement_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Settlement nicht gefunden")

    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Nur PDF-Dateien erlaubt")

    content = await file.read()

    # Upload to Supabase Storage
    storage_path = f"{settlement_id}/{file.filename}"

    try:
        # List buckets first to debug
        logger.info(f"Attempting to upload to bucket 'settlements', path: {storage_path}")

        try:
            buckets = supabase.storage.list_buckets()
            bucket_names = [b.name for b in buckets]
            logger.info(f"Available buckets: {bucket_names}")
        except Exception as bucket_err:
            logger.warning(f"Could not list buckets: {bucket_err}")

        # Upload file
        storage_result = supabase.storage.from_("settlements").upload(
            storage_path,
            content,
            {"content-type": "application/pdf"}
        )
        logger.info(f"Upload result: {storage_result}")

        # Store only the storage path (not public URL) - we'll generate signed URLs on demand
        supabase.table("settlements").update({
            "pdf_url": storage_path,  # Just the path, not full URL
            "pdf_filename": file.filename
        }).eq("id", settlement_id).execute()
        logger.info(f"Stored storage path: {storage_path}")

        return {
            "success": True,
            "storage_path": storage_path,
            "message": f"PDF erfolgreich hochgeladen"
        }

    except Exception as e:
        logger.error(f"Upload failed: {type(e).__name__}: {str(e)}")
        # Include more detail in error response
        error_detail = f"Upload fehlgeschlagen: {type(e).__name__}: {str(e)}"
        raise HTTPException(status_code=500, detail=error_detail)


@router.get("/{settlement_id}/pdf-url")
async def get_settlement_pdf_url(
    settlement_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Generate a signed URL for the settlement PDF (valid for 1 hour)."""
    supabase = get_supabase()

    # Get settlement with pdf_url (which is actually the storage path)
    result = supabase.table("settlements").select("id, pdf_url, pdf_filename").eq("id", settlement_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Settlement nicht gefunden")

    settlement = result.data[0]
    storage_path = settlement.get("pdf_url")

    if not storage_path:
        raise HTTPException(status_code=404, detail="Kein PDF für dieses Settlement vorhanden")

    # If it's an old full URL, extract just the path
    if storage_path.startswith("http"):
        # Extract path from URL like: .../settlements/uuid/filename.pdf
        parts = storage_path.split("/settlements/", 1)
        if len(parts) > 1:
            storage_path = parts[1]
        else:
            raise HTTPException(status_code=400, detail="Ungültiger PDF-Pfad")

    try:
        # Generate signed URL valid for 1 hour (3600 seconds)
        signed_url_result = supabase.storage.from_("settlements").create_signed_url(
            storage_path,
            expires_in=3600
        )

        return {
            "signed_url": signed_url_result["signedURL"],
            "expires_in": 3600,
            "filename": settlement.get("pdf_filename")
        }

    except Exception as e:
        logger.error(f"Failed to create signed URL: {type(e).__name__}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Signed URL Erstellung fehlgeschlagen: {str(e)}")


@router.patch("/items/{item_id}", response_model=SettlementItemResponse)
async def update_settlement_item(
    item_id: str,
    update: SettlementItemUpdateRequest,
    current_user: dict = Depends(get_current_user),
):
    """Update a settlement item."""
    supabase = get_supabase()

    # Check item exists
    existing = supabase.table("settlement_items").select("id").eq("id", item_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Item nicht gefunden")

    # Build update dict - use exclude_unset to distinguish between "not sent" and "sent as null"
    raw_data = update.model_dump(exclude_unset=True)
    update_data = {}

    for k, v in raw_data.items():
        if k == "notes":
            # Special handling for notes: convert string to array (DB stores as array)
            if v is None or v == "":
                update_data["notes"] = None
            elif isinstance(v, str):
                update_data["notes"] = [v]
            else:
                update_data["notes"] = v  # Already a list
        elif v is not None:
            update_data[k] = v

    if not update_data:
        raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

    # Update
    result = supabase.table("settlement_items").update(update_data).eq("id", item_id).execute()

    return result.data[0]
