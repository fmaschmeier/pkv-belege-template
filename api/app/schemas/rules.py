"""
Pydantic Models für Correction Rules und Matching Rules
"""
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime


# === Correction Rules ===

class CorrectionRuleBase(BaseModel):
    field_name: str
    raw_value: str
    corrected_value: str
    active: bool = True
    description: Optional[str] = None


class CorrectionRuleCreate(CorrectionRuleBase):
    pass


class CorrectionRuleUpdate(BaseModel):
    field_name: Optional[str] = None
    raw_value: Optional[str] = None
    corrected_value: Optional[str] = None
    active: Optional[bool] = None
    description: Optional[str] = None


class CorrectionRuleResponse(CorrectionRuleBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class CorrectionRuleListResponse(BaseModel):
    rules: List[CorrectionRuleResponse]
    total: int


# === Matching Rules ===

class MatchingRuleBase(BaseModel):
    provider_pattern: str
    bank_patterns: List[str]
    match_type: str = "provider"
    priority: int = 0
    active: bool = True
    description: Optional[str] = None


class MatchingRuleCreate(MatchingRuleBase):
    pass


class MatchingRuleUpdate(BaseModel):
    provider_pattern: Optional[str] = None
    bank_patterns: Optional[List[str]] = None
    match_type: Optional[str] = None
    priority: Optional[int] = None
    active: Optional[bool] = None
    description: Optional[str] = None


class MatchingRuleResponse(MatchingRuleBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class MatchingRuleListResponse(BaseModel):
    rules: List[MatchingRuleResponse]
    total: int


# === Provider Payment Info ===

class ProviderPaymentInfoBase(BaseModel):
    provider_pattern: str  # Normalisierter Anbieter-Name
    payment_recipient: Optional[str] = None  # Überweisungsempfänger
    payment_iban: Optional[str] = None  # IBAN
    active: bool = True


class ProviderPaymentInfoCreate(ProviderPaymentInfoBase):
    pass


class ProviderPaymentInfoUpdate(BaseModel):
    provider_pattern: Optional[str] = None
    payment_recipient: Optional[str] = None
    payment_iban: Optional[str] = None
    active: Optional[bool] = None


class ProviderPaymentInfoResponse(ProviderPaymentInfoBase):
    id: str
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ProviderPaymentInfoListResponse(BaseModel):
    items: List[ProviderPaymentInfoResponse]
    total: int
