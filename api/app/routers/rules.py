"""
Rules API Routes - Correction Rules und Matching Rules
"""
from fastapi import APIRouter, HTTPException, Depends
from typing import Optional

from ..core.database import get_supabase
from ..core.auth import get_current_user
from ..schemas.rules import (
    CorrectionRuleCreate,
    CorrectionRuleUpdate,
    CorrectionRuleResponse,
    CorrectionRuleListResponse,
    MatchingRuleCreate,
    MatchingRuleUpdate,
    MatchingRuleResponse,
    MatchingRuleListResponse,
    ProviderPaymentInfoCreate,
    ProviderPaymentInfoUpdate,
    ProviderPaymentInfoResponse,
    ProviderPaymentInfoListResponse,
)

router = APIRouter(prefix="/rules", tags=["Rules"])


# === Correction Rules ===

@router.get("/corrections", response_model=CorrectionRuleListResponse)
async def list_correction_rules(
    active_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """List all correction rules."""
    supabase = get_supabase()

    query = supabase.table("correction_rules").select("*")

    if active_only:
        query = query.eq("active", True)

    result = query.order("field_name").order("raw_value").execute()

    return CorrectionRuleListResponse(
        rules=result.data,
        total=len(result.data),
    )


@router.get("/corrections/{rule_id}", response_model=CorrectionRuleResponse)
async def get_correction_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single correction rule."""
    supabase = get_supabase()

    result = supabase.table("correction_rules").select("*").eq("id", rule_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    return result.data[0]


@router.post("/corrections", response_model=CorrectionRuleResponse)
async def create_correction_rule(
    rule: CorrectionRuleCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new correction rule."""
    supabase = get_supabase()

    # Check for existing active rule with same field_name + raw_value
    existing = supabase.table("correction_rules").select("id").eq(
        "field_name", rule.field_name
    ).eq("raw_value", rule.raw_value).eq("active", True).execute()

    if existing.data:
        raise HTTPException(
            status_code=409,
            detail=f"Aktive Regel für '{rule.field_name}' mit Wert '{rule.raw_value}' existiert bereits"
        )

    result = supabase.table("correction_rules").insert(rule.model_dump()).execute()

    return result.data[0]


@router.patch("/corrections/{rule_id}", response_model=CorrectionRuleResponse)
async def update_correction_rule(
    rule_id: str,
    update: CorrectionRuleUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a correction rule."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("correction_rules").select("id").eq("id", rule_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

    result = supabase.table("correction_rules").update(update_data).eq("id", rule_id).execute()

    return result.data[0]


@router.delete("/corrections/{rule_id}")
async def delete_correction_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a correction rule."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("correction_rules").select("id").eq("id", rule_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    supabase.table("correction_rules").delete().eq("id", rule_id).execute()

    return {"success": True, "message": "Regel gelöscht"}


# === Matching Rules ===

@router.get("/matching", response_model=MatchingRuleListResponse)
async def list_matching_rules(
    active_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """List all matching rules."""
    supabase = get_supabase()

    query = supabase.table("matching_rules").select("*")

    if active_only:
        query = query.eq("active", True)

    result = query.order("priority", desc=True).order("provider_pattern").execute()

    return MatchingRuleListResponse(
        rules=result.data,
        total=len(result.data),
    )


@router.get("/matching/{rule_id}", response_model=MatchingRuleResponse)
async def get_matching_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single matching rule."""
    supabase = get_supabase()

    result = supabase.table("matching_rules").select("*").eq("id", rule_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    return result.data[0]


@router.post("/matching", response_model=MatchingRuleResponse)
async def create_matching_rule(
    rule: MatchingRuleCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new matching rule."""
    supabase = get_supabase()

    result = supabase.table("matching_rules").insert(rule.model_dump()).execute()

    return result.data[0]


@router.patch("/matching/{rule_id}", response_model=MatchingRuleResponse)
async def update_matching_rule(
    rule_id: str,
    update: MatchingRuleUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a matching rule."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("matching_rules").select("id").eq("id", rule_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

    result = supabase.table("matching_rules").update(update_data).eq("id", rule_id).execute()

    return result.data[0]


@router.delete("/matching/{rule_id}")
async def delete_matching_rule(
    rule_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a matching rule."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("matching_rules").select("id").eq("id", rule_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Regel nicht gefunden")

    supabase.table("matching_rules").delete().eq("id", rule_id).execute()

    return {"success": True, "message": "Regel gelöscht"}


# === Provider Payment Info ===

@router.get("/payment-info", response_model=ProviderPaymentInfoListResponse)
async def list_provider_payment_info(
    active_only: bool = False,
    current_user: dict = Depends(get_current_user),
):
    """List all saved provider payment info (bank details)."""
    supabase = get_supabase()

    query = supabase.table("provider_payment_info").select("*")

    if active_only:
        query = query.eq("active", True)

    result = query.order("provider_pattern").execute()

    return ProviderPaymentInfoListResponse(
        items=result.data,
        total=len(result.data),
    )


@router.get("/payment-info/{info_id}", response_model=ProviderPaymentInfoResponse)
async def get_provider_payment_info(
    info_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Get a single provider payment info entry."""
    supabase = get_supabase()

    result = supabase.table("provider_payment_info").select("*").eq("id", info_id).execute()

    if not result.data:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    return result.data[0]


@router.post("/payment-info", response_model=ProviderPaymentInfoResponse)
async def create_provider_payment_info(
    info: ProviderPaymentInfoCreate,
    current_user: dict = Depends(get_current_user),
):
    """Create a new provider payment info entry."""
    supabase = get_supabase()

    # Check for existing entry with same provider_pattern
    existing_pattern = supabase.table("provider_payment_info").select("*").eq(
        "provider_pattern", info.provider_pattern
    ).execute()

    if existing_pattern.data:
        raise HTTPException(
            status_code=409,
            detail={
                "type": "duplicate_pattern",
                "message": f"Bankverbindung für '{info.provider_pattern}' existiert bereits",
                "existing": existing_pattern.data[0]
            }
        )

    # Check for existing entry with same IBAN (if provided)
    if info.payment_iban:
        existing_iban = supabase.table("provider_payment_info").select("*").eq(
            "payment_iban", info.payment_iban
        ).execute()

        if existing_iban.data:
            raise HTTPException(
                status_code=409,
                detail={
                    "type": "duplicate_iban",
                    "message": f"IBAN bereits für '{existing_iban.data[0]['provider_pattern']}' gespeichert",
                    "existing": existing_iban.data[0]
                }
            )

    result = supabase.table("provider_payment_info").insert(info.model_dump()).execute()

    return result.data[0]


@router.patch("/payment-info/{info_id}", response_model=ProviderPaymentInfoResponse)
async def update_provider_payment_info(
    info_id: str,
    update: ProviderPaymentInfoUpdate,
    current_user: dict = Depends(get_current_user),
):
    """Update a provider payment info entry."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("provider_payment_info").select("id").eq("id", info_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    update_data = {k: v for k, v in update.model_dump().items() if v is not None}

    if not update_data:
        raise HTTPException(status_code=400, detail="Keine Änderungen angegeben")

    result = supabase.table("provider_payment_info").update(update_data).eq("id", info_id).execute()

    return result.data[0]


@router.delete("/payment-info/{info_id}")
async def delete_provider_payment_info(
    info_id: str,
    current_user: dict = Depends(get_current_user),
):
    """Delete a provider payment info entry."""
    supabase = get_supabase()

    # Check exists
    existing = supabase.table("provider_payment_info").select("id").eq("id", info_id).execute()
    if not existing.data:
        raise HTTPException(status_code=404, detail="Eintrag nicht gefunden")

    supabase.table("provider_payment_info").delete().eq("id", info_id).execute()

    return {"success": True, "message": "Bankverbindung gelöscht"}
