from contextlib import asynccontextmanager
import asyncio
import base64
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.responses import Response

from app.auth import verify_bearer_token
from app.config import get_settings
from app.session_manager import session_manager
from app.universa_client import UniversaClient
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


async def cleanup_task():
    """Background task to periodically clean up expired sessions."""
    while True:
        await asyncio.sleep(60)  # Run every minute
        removed = await session_manager.cleanup_expired()
        if removed > 0:
            print(f"Cleaned up {removed} expired sessions")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for the FastAPI app."""
    # Start background cleanup task
    task = asyncio.create_task(cleanup_task())
    yield
    # Shutdown
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    # Shutdown browser and cleanup all sessions
    await session_manager.shutdown()


app = FastAPI(
    title="Universa Document Downloader",
    description="API for downloading documents from Universa insurance portal with 2FA support",
    version="1.0.0",
    lifespan=lifespan,
)


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
    session = await session_manager.create_session()

    client = UniversaClient(session)
    result = await client.start_login()

    if not result.success:
        await session_manager.update_session_status(
            session.session_id, "failed", result.message
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=result.message,
        )

    if result.requires_2fa:
        await session_manager.update_session_status(session.session_id, "pending_2fa")
    else:
        await session_manager.update_session_status(session.session_id, "authenticated")

    return LoginStartResponse(
        session_id=session.session_id,
        status="pending_2fa" if result.requires_2fa else "authenticated",
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

    Use the session_id from the /login/start response.
    """
    session = await session_manager.get_session(request.session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired. Please start a new login.",
        )

    if session.status != "pending_2fa":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid session status: {session.status}. Expected 'pending_2fa'.",
        )

    client = UniversaClient(session)
    result = await client.submit_2fa_code(request.pin)

    if result.success:
        await session_manager.update_session_status(
            request.session_id, "authenticated"
        )
    else:
        await session_manager.update_session_status(
            request.session_id, "failed", result.message
        )

    return SubmitPinResponse(success=result.success, message=result.message)


@app.get(
    "/documents",
    response_model=DocumentsResponse,
    dependencies=[Depends(verify_bearer_token)],
)
async def list_documents(session_id: str):
    """
    List available documents for download.

    Requires an authenticated session.
    """
    session = await session_manager.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired. Please start a new login.",
        )

    if session.status != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session not authenticated. Current status: {session.status}",
        )

    client = UniversaClient(session)

    try:
        documents = await client.get_documents()
        return DocumentsResponse(
            success=True,
            documents=[
                DocumentInfo(id=doc.id, name=doc.name, date=doc.date)
                for doc in documents
            ],
        )
    except Exception as e:
        return DocumentsResponse(
            success=False,
            documents=[],
            message=str(e),
        )


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
    session = await session_manager.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired. Please start a new login.",
        )

    if session.status != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session not authenticated. Current status: {session.status}",
        )

    client = UniversaClient(session)

    try:
        downloaded = await client.download_recent_documents(max_age_days)

        documents = [
            DownloadedDocument(
                filename=filename,
                date=date,
                content_base64=base64.b64encode(content).decode('utf-8'),
            )
            for content, filename, date in downloaded
        ]

        return DownloadRecentResponse(
            success=True,
            documents=documents,
            message=f"Downloaded {len(documents)} document(s) from the last {max_age_days} days",
        )
    except Exception as e:
        return DownloadRecentResponse(
            success=False,
            documents=[],
            message=str(e),
        )


@app.get(
    "/documents/{document_id}/download",
    dependencies=[Depends(verify_bearer_token)],
)
async def download_document(document_id: str, session_id: str):
    """
    Download a specific document by index.

    Returns the document as a binary PDF file.
    """
    session = await session_manager.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired. Please start a new login.",
        )

    if session.status != "authenticated":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Session not authenticated. Current status: {session.status}",
        )

    client = UniversaClient(session)

    try:
        content, filename = await client.download_document(document_id)
        return Response(
            content=content,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to download document: {str(e)}",
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
    session = await session_manager.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired.",
        )

    return SessionStatusResponse(
        session_id=session.session_id,
        status=session.status,
        created_at=session.created_at.isoformat(),
        error_message=session.error_message,
    )


@app.delete(
    "/session/{session_id}",
    dependencies=[Depends(verify_bearer_token)],
)
async def delete_session(session_id: str):
    """
    Delete a session and clean up resources.
    """
    session = await session_manager.get_session(session_id)

    if session is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or expired.",
        )

    await session_manager.remove_session(session_id)
    return {"message": "Session deleted"}
