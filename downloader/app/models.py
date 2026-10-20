from pydantic import BaseModel
from typing import Optional


class LoginStartResponse(BaseModel):
    session_id: str
    status: str
    message: str
    requires_2fa: bool


class SubmitPinRequest(BaseModel):
    session_id: str
    pin: str


class SubmitPinResponse(BaseModel):
    success: bool
    message: str
    # Success: new session for the document calls (the portal replaces its session cookie at the PIN step).
    # Wrong PIN: session for another try.
    session_id: Optional[str] = None


class DocumentInfo(BaseModel):
    id: str
    name: str
    date: str


class DocumentsResponse(BaseModel):
    success: bool
    documents: list[DocumentInfo]
    message: Optional[str] = None


class SessionStatusResponse(BaseModel):
    session_id: str
    status: str
    created_at: str
    error_message: Optional[str] = None


class HealthResponse(BaseModel):
    status: str
    message: str


class DownloadedDocument(BaseModel):
    filename: str
    date: str
    content_base64: str


class DownloadRecentResponse(BaseModel):
    success: bool
    documents: list[DownloadedDocument]
    message: Optional[str] = None
