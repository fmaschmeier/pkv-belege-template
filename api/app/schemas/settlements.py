"""
Settlement Schemas
"""
from datetime import date
from pydantic import BaseModel, field_validator
from typing import Optional, Union


class SettlementItemBase(BaseModel):
    receipt_number: str
    tariff: Optional[str] = None
    insured_person: Optional[str] = None
    description: Optional[str] = None
    treatment_period: Optional[str] = None
    invoice_amount: Optional[float] = None
    reimbursed_amount: Optional[float] = None
    notes: Optional[str] = None
    payment_status: str = "pending"
    payment_note: Optional[str] = None

    @field_validator('notes', mode='before')
    @classmethod
    def convert_notes_list_to_string(cls, v):
        if isinstance(v, list):
            return ' | '.join(str(item) for item in v)
        return v


class SettlementItemResponse(SettlementItemBase):
    id: str
    settlement_id: str

    class Config:
        from_attributes = True


class SettlementBase(BaseModel):
    settlement_number: str
    settlement_date: date
    insurance_number: str
    total_invoiced: Optional[float] = None
    total_reimbursed: Optional[float] = None
    pdf_filename: Optional[str] = None
    pdf_url: Optional[str] = None
    raw_text: Optional[str] = None


class SettlementResponse(SettlementBase):
    id: str
    settlement_items: list[SettlementItemResponse] = []

    class Config:
        from_attributes = True


class SettlementItemUpdateRequest(BaseModel):
    """Request zum Aktualisieren eines Settlement Items"""
    description: Optional[str] = None
    invoice_amount: Optional[float] = None
    reimbursed_amount: Optional[float] = None
    treatment_period: Optional[str] = None
    insured_person: Optional[str] = None
    payment_status: Optional[str] = None
    payment_note: Optional[str] = None
    notes: Optional[str] = None


class SettlementListResponse(BaseModel):
    settlements: list[SettlementResponse]
    total: int


class ParsedItemResponse(BaseModel):
    """Geparste Position für Upload-Response"""
    receipt_number: str
    insured_person: Optional[str] = None
    description: Optional[str] = None
    treatment_period: Optional[str] = None
    invoice_amount: Optional[float] = None
    reimbursed_amount: Optional[float] = None
    notes: Optional[str] = None
    has_notes: bool = False

    @field_validator('notes', mode='before')
    @classmethod
    def convert_notes_list_to_string(cls, v):
        if isinstance(v, list):
            return ' | '.join(str(item) for item in v)
        return v


class SettlementUploadResponse(BaseModel):
    success: bool
    settlement_id: str
    settlement_number: str
    settlement_date: str
    items_count: int
    total_invoiced: float
    total_reimbursed: float
    message: str
    # Für n8n: Prüfung erforderlich?
    requires_review: bool = False
    review_reason: Optional[str] = None
    items_with_notes_count: int = 0
    # Alle geparsten Items
    items: list[ParsedItemResponse] = []
    # Nur Items mit Anmerkungen (für schnellen Überblick)
    items_with_notes: list[ParsedItemResponse] = []


class ItemWithSettlement(SettlementItemBase):
    """Item with settlement info for flat list view."""
    id: str
    settlement_id: str
    settlement_number: str
    settlement_date: date

    class Config:
        from_attributes = True


class ItemListResponse(BaseModel):
    items: list[ItemWithSettlement]
    total: int
    total_reimbursed: float
    total_invoiced: float
