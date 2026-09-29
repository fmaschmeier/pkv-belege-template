"""
Settlement Items API Routes
"""
from fastapi import APIRouter, Query, Depends
from typing import Optional, List
from datetime import date
from pydantic import BaseModel

from ..core.database import get_supabase
from ..core.auth import get_current_user
from ..schemas.settlements import ItemListResponse

router = APIRouter(prefix="/items", tags=["Items"])


class ItemMatch(BaseModel):
    """Ein potentieller Match für einen eingereichten Beleg"""
    id: str
    receipt_number: str
    settlement_number: str
    settlement_date: str
    insured_person: Optional[str]
    description: Optional[str]
    treatment_period: Optional[str]
    invoice_amount: Optional[float]
    reimbursed_amount: Optional[float]
    match_score: int  # 0-100, höher = besserer Match


class ItemSearchResponse(BaseModel):
    """Response für Item-Suche"""
    matches: List[ItemMatch]
    total: int


@router.get("", response_model=ItemListResponse)
async def list_items(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    person: Optional[str] = Query(None, description="Filter by insured person"),
    date_from: Optional[date] = Query(None, description="Start date"),
    date_to: Optional[date] = Query(None, description="End date"),
    year: Optional[int] = Query(None, description="Filter by year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    current_user: dict = Depends(get_current_user),
):
    """List all settlement items with filters."""
    supabase = get_supabase()

    # Query items with settlement info
    query = supabase.table("settlement_items").select(
        "*, settlements(settlement_number, settlement_date)"
    )

    result = query.execute()

    items = []
    for item in result.data:
        settlement = item.pop("settlements", {}) or {}
        item["settlement_number"] = settlement.get("settlement_number", "")
        item["settlement_date"] = settlement.get("settlement_date", "")
        items.append(item)

    # Apply filters
    if person:
        items = [i for i in items if person.lower() in (i.get("insured_person") or "").lower()]

    if date_from:
        items = [i for i in items if i.get("settlement_date") and i["settlement_date"] >= str(date_from)]

    if date_to:
        items = [i for i in items if i.get("settlement_date") and i["settlement_date"] <= str(date_to)]

    if year:
        items = [i for i in items if i.get("settlement_date") and i["settlement_date"].startswith(str(year))]

    if month and year:
        month_str = f"{year}-{month:02d}"
        items = [i for i in items if i.get("settlement_date") and i["settlement_date"].startswith(month_str)]

    # Sort by settlement date descending
    items.sort(key=lambda x: x.get("settlement_date", ""), reverse=True)

    # Calculate totals before pagination
    # Bei Pflegegeld/Tagegeld ist invoice_amount null - dann reimbursed_amount verwenden
    total_reimbursed = sum(i.get("reimbursed_amount") or 0 for i in items)
    total_invoiced = sum(
        i.get("invoice_amount") if i.get("invoice_amount") is not None
        else (i.get("reimbursed_amount") or 0)
        for i in items
    )
    total_count = len(items)

    # Apply pagination
    items = items[offset:offset + limit]

    return ItemListResponse(
        items=items,
        total=total_count,
        total_reimbursed=total_reimbursed,
        total_invoiced=total_invoiced,
    )


@router.get("/unlinked", response_model=ItemListResponse)
async def list_unlinked_items(
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """
    List settlement items that are not yet linked to a submitted receipt.
    Useful for showing available items when manually linking receipts.
    """
    supabase = get_supabase()

    # Get all items with settlement info
    items_result = supabase.table("settlement_items").select(
        "*, settlements(settlement_number, settlement_date)"
    ).execute()

    # Get all linked item IDs from submitted_receipts
    linked_result = supabase.table("submitted_receipts").select(
        "settlement_item_id"
    ).not_.is_("settlement_item_id", "null").execute()

    linked_ids = {r["settlement_item_id"] for r in linked_result.data if r.get("settlement_item_id")}

    # Filter to unlinked items
    items = []
    for item in items_result.data:
        if item["id"] not in linked_ids:
            settlement = item.pop("settlements", {}) or {}
            item["settlement_number"] = settlement.get("settlement_number", "")
            item["settlement_date"] = settlement.get("settlement_date", "")
            items.append(item)

    # Sort by settlement date descending
    items.sort(key=lambda x: x.get("settlement_date", ""), reverse=True)

    total_count = len(items)
    total_reimbursed = sum(i.get("reimbursed_amount") or 0 for i in items)
    total_invoiced = sum(
        i.get("invoice_amount") if i.get("invoice_amount") is not None
        else (i.get("reimbursed_amount") or 0)
        for i in items
    )

    # Apply pagination
    items = items[offset:offset + limit]

    return ItemListResponse(
        items=items,
        total=total_count,
        total_reimbursed=total_reimbursed,
        total_invoiced=total_invoiced,
    )


@router.get("/search", response_model=ItemSearchResponse)
async def search_items_for_matching(
    amount: float = Query(..., description="Invoice amount to match (exact)"),
    person: Optional[str] = Query(None, description="Insured person name (partial match)"),
    treatment_date: Optional[str] = Query(None, description="Treatment date or period to match"),
    submission_date: Optional[str] = Query(None, description="Receipt submission date - settlements before this date are excluded"),
    current_user: dict = Depends(get_current_user),
):
    """
    Search for settlement items that match a submitted receipt.
    Used for finding potential matches when linking receipts.

    Returns items sorted by match_score (best matches first).
    Match criteria:
    - invoice_amount must match EXACTLY
    - settlement_date must be >= submission_date (if provided)
    - person name is optional bonus
    - treatment_period overlap is optional bonus
    """
    supabase = get_supabase()

    # Get all items with settlement info
    result = supabase.table("settlement_items").select(
        "*, settlements(settlement_number, settlement_date)"
    ).execute()

    matches = []
    for item in result.data:
        item_amount = item.get("invoice_amount")

        # EXACT amount match required
        if item_amount is None or abs(item_amount - amount) > 0.01:
            continue

        # Extract settlement info (and remove from item dict)
        settlement = item.pop("settlements", {}) or {}
        settlement_date_value = settlement.get("settlement_date")

        # Settlement date must be after submission date
        if submission_date and settlement_date_value and settlement_date_value < submission_date:
            continue

        # Calculate match score
        score = 50  # Base score for exact amount match

        # Person match bonus (+30)
        if person:
            item_person = (item.get("insured_person") or "").lower()
            if person.lower() in item_person or item_person in person.lower():
                score += 30

        # Treatment period bonus (+20)
        if treatment_date:
            item_period = item.get("treatment_period") or ""
            if treatment_date in item_period or item_period in treatment_date:
                score += 20

        matches.append(ItemMatch(
            id=item["id"],
            receipt_number=item.get("receipt_number", ""),
            settlement_number=settlement.get("settlement_number", ""),
            settlement_date=settlement.get("settlement_date", ""),
            insured_person=item.get("insured_person"),
            description=item.get("description"),
            treatment_period=item.get("treatment_period"),
            invoice_amount=item.get("invoice_amount"),
            reimbursed_amount=item.get("reimbursed_amount"),
            match_score=score,
        ))

    # Sort by score descending
    matches.sort(key=lambda x: x.match_score, reverse=True)

    return ItemSearchResponse(
        matches=matches,
        total=len(matches),
    )
