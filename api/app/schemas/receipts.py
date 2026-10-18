"""
Receipt Schemas - Eingereichte Belege
"""
from datetime import date, datetime
from pydantic import BaseModel
from typing import Optional


class ReceiptBase(BaseModel):
    """Basis-Felder für Belege"""
    submission_date: date
    pdf_filename: str
    pdf_hash: str

    filename_person: Optional[str] = None
    filename_provider: Optional[str] = None

    receipt_type: Optional[str] = None
    provider_name: Optional[str] = None
    provider_address: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    invoice_amount: Optional[float] = None

    insured_person: Optional[str] = None
    insured_birthdate: Optional[date] = None

    description: Optional[str] = None
    treatment_period: Optional[str] = None

    due_date: Optional[date] = None
    due_date_source: Optional[str] = None


class ReceiptResponse(ReceiptBase):
    """Response für einzelnen Beleg"""
    id: str
    status: str = "submitted"
    settlement_item_id: Optional[str] = None
    reimbursed_amount: Optional[float] = None
    reimbursed_date: Optional[date] = None
    rejection_reason: Optional[str] = None
    # Payment tracking
    payment_transaction_id: Optional[str] = None
    paid_date: Optional[date] = None
    paid_amount: Optional[float] = None  # Bezahlter Betrag (aus Transaktion)
    # Payment details for QR code
    payment_recipient: Optional[str] = None  # Überweisungsempfänger
    payment_iban: Optional[str] = None  # IBAN
    payment_reference: Optional[str] = None  # Verwendungszweck
    # PDF storage
    pdf_url: Optional[str] = None  # Storage path, not full URL
    raw_text: Optional[str] = None  # Parsed text from PDF
    # Originally parsed parameters from Claude Vision (preserved after edits)
    parsed_params: Optional[dict] = None
    # Settlement info (from JOIN)
    settlement_number: Optional[str] = None  # e.g. "R/26/117"
    receipt_number: Optional[str] = None  # e.g. "B/26/1201"
    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    class Config:
        from_attributes = True


class ReceiptListResponse(BaseModel):
    """Response für Beleg-Liste"""
    receipts: list[ReceiptResponse]
    total: int
    total_amount: float
    pending_count: int
    overdue_count: int  # Zahlung überfällig (alle Belege, nicht nur offene)
    reimbursement_overdue_count: int = 0  # Erstattung überfällig (>30 Tage)
    unpaid_count: int = 0  # Noch nicht bezahlt (excl. Rezepte)
    liqui_saldo: float = 0  # Minus Summe aller bezahlten, noch nicht erstatteten Belege (Rezepte gelten als bezahlt)


class ReceiptUploadResponse(BaseModel):
    """Response nach Upload"""
    success: bool
    receipt_id: str
    receipt_type: str
    invoice_amount: Optional[float]
    due_date: Optional[date]
    message: str


class ReceiptUpdateRequest(BaseModel):
    """Request zum Aktualisieren eines Belegs"""
    status: Optional[str] = None
    settlement_item_id: Optional[str] = None
    reimbursed_amount: Optional[float] = None
    reimbursed_date: Optional[date] = None
    rejection_reason: Optional[str] = None
    # Payment tracking
    payment_transaction_id: Optional[str] = None
    paid_date: Optional[date] = None
    # Force unlink payment from another receipt (if already assigned)
    force_unlink_payment: bool = False
    # Skip date plausibility check for manual settlement linking
    skip_date_check: bool = False
    # Editable fields from EditReceiptFieldsModal
    submission_date: Optional[date] = None
    provider_name: Optional[str] = None
    invoice_amount: Optional[float] = None
    invoice_date: Optional[date] = None
    insured_person: Optional[str] = None
    receipt_type: Optional[str] = None
    description: Optional[str] = None
    treatment_period: Optional[str] = None
    due_date: Optional[date] = None
    invoice_number: Optional[str] = None
    # Payment details for QR code
    payment_recipient: Optional[str] = None
    payment_iban: Optional[str] = None
    payment_reference: Optional[str] = None


class ReceiptStats(BaseModel):
    """Statistiken für Belege"""
    total_count: int
    submitted_count: int
    reimbursed_count: int
    rejected_count: int
    total_submitted_amount: float
    total_reimbursed_amount: float
    overdue_count: int
    due_soon_count: int


class ReceiptImportRequest(BaseModel):
    """
    Request für n8n Import - extrahierte Daten von Claude Vision.
    PDF wird separat als multipart/form-data gesendet.
    """
    receipt_type: Optional[str] = None  # arzt/rezept/pflege/hilfsmittel/sonstige
    provider_name: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[date] = None
    invoice_amount: Optional[float] = None
    insured_person: Optional[str] = None
    description: Optional[str] = None
    treatment_period: Optional[str] = None
    due_date: Optional[date] = None
    # Optional: Override submission_date (default: today)
    submission_date: Optional[date] = None
    # Payment details for QR code generation
    payment_recipient: Optional[str] = None  # Überweisungsempfänger
    payment_iban: Optional[str] = None  # IBAN
    payment_reference: Optional[str] = None  # Verwendungszweck


class ReceiptImportResponse(BaseModel):
    """Response nach n8n Import"""
    success: bool
    receipt_id: str
    receipt_type: Optional[str]
    provider_name: Optional[str]
    invoice_amount: Optional[float]
    message: str
    duplicate: bool = False  # True wenn Beleg bereits existierte


class PaymentQRRequest(BaseModel):
    """Request für QR-Code Generierung"""
    recipient: str  # Empfängername (max 70 Zeichen)
    iban: str  # IBAN
    amount: float  # Betrag in EUR
    reference: str  # Verwendungszweck (max 140 Zeichen)


class PaymentQRResponse(BaseModel):
    """Response mit QR-Code Daten"""
    success: bool
    qr_data: Optional[str] = None  # EPC QR Code String
    recipient: str
    iban: str
    amount: float
    reference: str
    iban_valid: bool
    error: Optional[str] = None
