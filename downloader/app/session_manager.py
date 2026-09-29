import asyncio
import uuid
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Optional
from playwright.async_api import async_playwright, Browser, BrowserContext, Page, Playwright

from app.config import get_settings


@dataclass
class LoginSession:
    """Holds the state of a login session waiting for 2FA."""

    session_id: str
    browser_context: BrowserContext
    page: Page
    created_at: datetime
    status: str = "pending_2fa"  # pending_2fa, authenticated, expired, failed
    error_message: Optional[str] = None

    def is_expired(self, timeout_seconds: int) -> bool:
        return datetime.now() > self.created_at + timedelta(seconds=timeout_seconds)


class SessionManager:
    """Manages login sessions with Playwright browser contexts for 2FA flow."""

    def __init__(self):
        self._sessions: dict[str, LoginSession] = {}
        self._lock = asyncio.Lock()
        self._playwright: Optional[Playwright] = None
        self._browser: Optional[Browser] = None

    async def _ensure_browser(self) -> Browser:
        """Ensure browser is started."""
        if self._playwright is None:
            self._playwright = await async_playwright().start()

        if self._browser is None or not self._browser.is_connected():
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--disable-blink-features=AutomationControlled",
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                ]
            )

        return self._browser

    async def create_session(self) -> LoginSession:
        """Create a new session with a fresh browser context."""
        session_id = str(uuid.uuid4())

        browser = await self._ensure_browser()

        # Create isolated browser context (like incognito)
        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        # Create page
        page = await context.new_page()

        session = LoginSession(
            session_id=session_id,
            browser_context=context,
            page=page,
            created_at=datetime.now(),
        )

        async with self._lock:
            self._sessions[session_id] = session

        return session

    async def get_session(self, session_id: str) -> Optional[LoginSession]:
        """Get a session by ID, returns None if not found or expired."""
        settings = get_settings()

        async with self._lock:
            session = self._sessions.get(session_id)

            if session is None:
                return None

            if session.is_expired(settings.session_timeout_seconds):
                await self._cleanup_session(session_id)
                return None

            return session

    async def update_session_status(
        self, session_id: str, status: str, error_message: Optional[str] = None
    ) -> None:
        """Update the status of a session."""
        async with self._lock:
            if session_id in self._sessions:
                self._sessions[session_id].status = status
                self._sessions[session_id].error_message = error_message

    async def remove_session(self, session_id: str) -> None:
        """Remove and cleanup a session."""
        async with self._lock:
            await self._cleanup_session(session_id)

    async def _cleanup_session(self, session_id: str) -> None:
        """Internal cleanup - must be called with lock held."""
        if session_id in self._sessions:
            session = self._sessions[session_id]
            try:
                await session.page.close()
                await session.browser_context.close()
            except Exception:
                pass  # Ignore cleanup errors
            del self._sessions[session_id]

    async def cleanup_expired(self) -> int:
        """Remove all expired sessions. Returns count of removed sessions."""
        settings = get_settings()
        removed = 0

        async with self._lock:
            expired_ids = [
                sid
                for sid, session in self._sessions.items()
                if session.is_expired(settings.session_timeout_seconds)
            ]

            for sid in expired_ids:
                await self._cleanup_session(sid)
                removed += 1

        return removed

    async def shutdown(self) -> None:
        """Shutdown browser and cleanup all sessions."""
        async with self._lock:
            for session_id in list(self._sessions.keys()):
                await self._cleanup_session(session_id)

        if self._browser:
            await self._browser.close()
            self._browser = None

        if self._playwright:
            await self._playwright.stop()
            self._playwright = None


# Global session manager instance
session_manager = SessionManager()
