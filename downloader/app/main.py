import base64
import traceback
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import Response

from app.auth import verify_bearer_token
from app.config import get_settings
from app.portal_client import PortalClient, PortalError
from app.session_token import Session, seal, unseal
from app.models import (
    LoginStartResponse,
    SubmitPinRequest,
    SubmitPinResponse,
    DocumentInfo,
    DocumentsResponse,
    SessionStatusResponse,
    HealthResponse,
    DownloadedDocument,
    DownloadRecentResponse,
)


app = FastAPI(
    title="Universa Document Downloader",
    description="API for downloading documents from Universa insurance portal with 2FA support",
    version="2.0.0",
)


def _session(session_id: str, expected: str) -> Session:
    """Decrypt the session_id; 404 if unknown or expired, 400 if in the wrong state."""
    session = unseal(session_id)
    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired. Please start a new login.",
        )
    if session.status != expected:
        if expected == "authenticated":
            detail = f"Session not authenticated. Current status: {session.status}"
        else:
            detail = f"Invalid session status: {session.status}. Expected '{expected}'."
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=detail)
    return session


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint for Cloud Run."""
    return HealthResponse(status="healthy", message="Service is running")


@app.post(
    "/login/start",
    response_model=LoginStartResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def start_login():
    """
    Start the login process.

    This will initiate login with stored credentials and trigger the 2FA email.
    Returns a session_id that must be used when submitting the PIN.
    """
    settings = get_settings()
    client = PortalClient()
    result = await client.start_login(settings.universa_username, settings.universa_password)

    if not result.success:
        # 401 only if the portal refuses the login. A timeout is not a credentials problem;
        # otherwise n8n misleadingly reports "please check your credentials".
        code = {
            "rejected": status.HTTP_401_UNAUTHORIZED,
            "timeout": status.HTTP_504_GATEWAY_TIMEOUT,
        }.get(result.error_kind, status.HTTP_502_BAD_GATEWAY)
        raise HTTPException(status_code=code, detail=result.message)

    state = "pending_2fa" if result.requires_2fa else "authenticated"
    return LoginStartResponse(
        session_id=seal(client.state, state),
        status=state,
        message=result.message,
        requires_2fa=result.requires_2fa,
    )


@app.post(
    "/login/complete",
    response_model=SubmitPinResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def complete_login(request: SubmitPinRequest):
    """
    Complete the login by submitting the 2FA PIN received via email.

    Use the session_id from the /login/start response. On success the answer carries a new
    session_id for the document calls: the portal replaces its session cookie at this step.
    After a wrong PIN it carries a session_id for another try (the portal's CSRF token moved on).
    """
    session = _session(request.session_id, "pending_2fa")
    settings = get_settings()
    client = PortalClient(session.state)
    result = await client.submit_pin(settings.universa_username, settings.universa_password, request.pin)

    return SubmitPinResponse(
        success=result.success,
        message=result.message,
        session_id=seal(client.state, "authenticated" if result.success else "pending_2fa"),
    )


@app.get(
    "/documents",
    response_model=DocumentsResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def list_documents(session_id: str, page: int = 0):
    """
    List the documents on one page of the inbox (newest first).

    Requires an authenticated session.
    """
    session = _session(session_id, "authenticated")
    try:
        documents, _ = await PortalClient(session.state).get_documents(page)
        return DocumentsResponse(
            success=True,
            documents=[DocumentInfo(id=d.id, name=d.name, date=d.date) for d in documents],
        )
    except PortalError as e:
        return DocumentsResponse(success=False, documents=[], message=str(e))
    except Exception as e:  # unexpected answer from the portal; keep n8n's contract
        traceback.print_exc()
        return DocumentsResponse(success=False, documents=[], message=f"{type(e).__name__}: {e}")


@app.get(
    "/documents/recent",
    response_model=DownloadRecentResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def download_recent_documents(session_id: str, max_age_days: int = 3):
    """
    Download all documents from the last X days (default: 3).

    Returns documents as base64-encoded PDFs.
    """
    session = _session(session_id, "authenticated")
    try:
        downloaded = await PortalClient(session.state).download_recent_documents(max_age_days)
    except PortalError as e:
        return DownloadRecentResponse(success=False, documents=[], message=str(e))
    except Exception as e:  # unexpected answer from the portal; keep n8n's contract
        traceback.print_exc()
        return DownloadRecentResponse(success=False, documents=[], message=f"{type(e).__name__}: {e}")

    documents = [
        DownloadedDocument(
            filename=filename,
            date=date,
            content_base64=base64.b64encode(content).decode("utf-8"),
        )
        for content, filename, date in downloaded
    ]
    return DownloadRecentResponse(
        success=True,
        documents=documents,
        message=f"Downloaded {len(documents)} document(s) from the last {max_age_days} days",
    )


@app.get(
    "/documents/{document_id}/download",
    dependencies=[Depends(verify_bearer_token)],
)
async def download_document(document_id: str, session_id: str):
    """
    Download a specific document by its id from /documents.

    Returns the document as a binary PDF file.
    """
    session = _session(session_id, "authenticated")
    try:
        content, filename = await PortalClient(session.state).download_document(document_id)
    except PortalError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {e}",
        )
    return Response(
        content=content,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get(
    "/session/{session_id}",
    response_model=SessionStatusResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def get_session_status(session_id: str):
    """
    Get the status of a session.
    """
    session = unseal(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired.")
    return SessionStatusResponse(
        session_id=session_id,
        status=session.status,
        created_at=session.created_at.isoformat(),
    )


@app.delete(
    "/session/{session_id}",
    dependencies=[Depends(verify_bearer_token)],
)
async def delete_session(session_id: str):
    """
    Log out at the portal. The session_id itself cannot be revoked; it expires on its own.
    """
    session = unseal(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found or expired.")
    await PortalClient(session.state).logout()
    return {"message": "Session deleted"}
