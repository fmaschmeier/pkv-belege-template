"""
Bank Transaction Schemas
"""
from datetime import date
from pydantic import BaseModel
from typing import Optional


class BankTransactionBase(BaseModel):
    booking_date: date
    value_date: date
    transaction_type: Optional[str] = None
    description: str
    amount: float
    currency: str = "EUR"
    category: Optional[str] = None
    is_universa_payment: bool = False
    settlement_id: Optional[str] = None


class LinkedReceiptInfo(BaseModel):
    """Info über verknüpften Beleg"""
    id: str
    provider_name: Optional[str] = None
    invoice_amount: Optional[float] = None
    status: str


class BankTransactionResponse(BankTransactionBase):
    id: str
    iban: Optional[str] = None
    import_hash: Optional[str] = None
    linked_receipt: Optional[LinkedReceiptInfo] = None  # Verknüpfter Beleg

    class Config:
        from_attributes = True


class BankImportResponse(BaseModel):
    success: bool
    inserted: int
    skipped: int
    matched: int
    errors: list[str]


class BankTransactionListResponse(BaseModel):
    transactions: list[BankTransactionResponse]
    total: int
    total_amount: float
