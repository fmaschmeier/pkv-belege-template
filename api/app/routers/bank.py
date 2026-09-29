"""
Bank Transaction API Routes
"""
from fastapi import APIRouter, UploadFile, File, HTTPException, Query, Depends
from typing import Optional

from ..core.database import get_supabase
from ..core.auth import get_current_user
from ..schemas.bank import (
    BankTransactionResponse,
    BankTransactionListResponse,
    BankImportResponse,
)
from ..services.parser_service import ParserService

router = APIRouter(prefix="/bank", tags=["Bank Transactions"])


@router.get("/transactions/{transaction_id}", response_model=BankTransactionResponse)
async def get_transaction(
    transaction_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single bank transaction by ID."""
    supabase = get_supabase()

    result = supabase.table("bank_transactions").select("*").eq("id", transaction_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Transaktion nicht gefunden")

    return result.data[0]


@router.get("/transactions", response_model=BankTransactionListResponse)
async def list_transactions(
    limit: int = Query(50, ge=1, le=2000),
    offset: int = Query(0, ge=0),
    universa_only: bool = Query(False, description="Only Universa payments"),
    unmatched_only: bool = Query(False, description="Only unmatched Universa payments"),
    year: Optional[int] = Query(None, description="Filter by year"),
    month: Optional[int] = Query(None, ge=1, le=12, description="Filter by month"),
    current_user: dict = Depends(get_current_user),
):
    """List bank transactions with filters."""
    supabase = get_supabase()

    query = supabase.table("bank_transactions").select("*")

    if universa_only:
        query = query.eq("is_universa_payment", True)

    if unmatched_only:
        query = query.eq("is_universa_payment", True).is_("settlement_id", "null")

    if year:
        query = query.gte("booking_date", f"{year}-01-01").lte("booking_date", f"{year}-12-31")

    if month and year:
        month_str = f"{month:02d}"
        query = query.gte("booking_date", f"{year}-{month_str}-01")
        if month == 12:
            query = query.lte("booking_date", f"{year}-12-31")
        else:
            next_month = f"{month + 1:02d}"
            query = query.lt("booking_date", f"{year}-{next_month}-01")

    result = query.order("booking_date", desc=True).range(offset, offset + limit - 1).execute()

    total_amount = sum(t["amount"] for t in result.data)

    # Load linked receipts for these transactions
    transaction_ids = [t["id"] for t in result.data]
    if transaction_ids:
        receipts_result = supabase.table("submitted_receipts").select(
            "id, payment_transaction_id, provider_name, invoice_amount, status"
        ).in_("payment_transaction_id", transaction_ids).execute()

        # Create lookup map
        receipt_by_tx = {r["payment_transaction_id"]: r for r in receipts_result.data}

        # Add linked_receipt to transactions
        for tx in result.data:
            linked = receipt_by_tx.get(tx["id"])
            if linked:
                tx["linked_receipt"] = {
                    "id": linked["id"],
                    "provider_name": linked.get("provider_name"),
                    "invoice_amount": linked.get("invoice_amount"),
                    "status": linked.get("status", "submitted"),
                }

    return BankTransactionListResponse(
        transactions=result.data,
        total=len(result.data),
        total_amount=total_amount,
    )


@router.post("/import", response_model=BankImportResponse)
async def import_bank_csv(
    file: UploadFile = File(...),
    current_user: dict = Depends(get_current_user),
):
    """Import a Commerzbank CSV file."""

    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Nur CSV-Dateien erlaubt")

    content = await file.read()

    try:
        service = ParserService()
        result = service.import_bank_csv(content)

        return BankImportResponse(
            success=True,
            inserted=result["inserted"],
            skipped=result["skipped"],
            matched=result["matched"],
            errors=result["errors"],
        )

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Import-Fehler: {str(e)}")


@router.post("/update-links")
async def update_settlement_links(current_user: dict = Depends(get_current_user)):
    """Update settlement links for unmatched Universa payments."""
    service = ParserService()
    result = service.update_settlement_links()

    return {
        "success": True,
        "message": f"{result['updated']} Transaktionen verknüpft",
        **result,
    }


@router.get("/stats/summary")
async def get_bank_stats(
    year: Optional[int] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """Get bank transaction statistics."""
    supabase = get_supabase()

    # All transactions
    query = supabase.table("bank_transactions").select("amount, is_universa_payment, settlement_id")
    if year:
        query = query.gte("booking_date", f"{year}-01-01").lte("booking_date", f"{year}-12-31")
    result = query.execute()

    expenses = [t for t in result.data if t["amount"] < 0]
    universa = [t for t in result.data if t["is_universa_payment"]]
    matched = [t for t in universa if t["settlement_id"]]

    return {
        "total_transactions": len(result.data),
        "total_expenses": len(expenses),
        "total_expenses_amount": sum(t["amount"] for t in expenses),
        "universa_payments": len(universa),
        "universa_matched": len(matched),
        "universa_unmatched": len(universa) - len(matched),
        "universa_total_amount": sum(t["amount"] for t in universa),
        "year": year or "all",
    }


@router.get("/universa-matches")
async def get_universa_matches(current_user: dict = Depends(get_current_user)):
    """Get all Universa payments with match status."""
    supabase = get_supabase()

    result = supabase.table("bank_transactions").select(
        "id, booking_date, amount, description, settlement_id"
    ).eq("is_universa_payment", True).order("booking_date", desc=True).execute()

    # Enrich with settlement numbers
    settlement_ids = [t["settlement_id"] for t in result.data if t["settlement_id"]]
    settlements = {}
    if settlement_ids:
        s_result = supabase.table("settlements").select("id, settlement_number").in_("id", settlement_ids).execute()
        settlements = {s["id"]: s["settlement_number"] for s in s_result.data}

    matches = []
    for tx in result.data:
        matches.append({
            "id": tx["id"],
            "booking_date": tx["booking_date"],
            "amount": tx["amount"],
            "settlement_id": tx["settlement_id"],
            "settlement_number": settlements.get(tx["settlement_id"]),
            "matched": tx["settlement_id"] is not None,
        })

    return {
        "total": len(matches),
        "matched": len([m for m in matches if m["matched"]]),
        "unmatched": len([m for m in matches if not m["matched"]]),
        "payments": matches,
    }
