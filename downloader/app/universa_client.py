"""
Universa Portal Client using Playwright

This module handles the interaction with the Universa insurance portal.
Uses Playwright for browser automation to handle JavaScript-based pages.

IMPORTANT: You need to inspect the portal in your browser (DevTools) and adjust
the selectors below based on the actual HTML structure.
"""

from dataclasses import dataclass
from typing import Optional
from datetime import datetime, timedelta
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.config import get_settings
from app.session_manager import LoginSession


# URLs - Adjust if different
BASE_URL = "https://kundenportal.universa.de"
LOGIN_URL = f"{BASE_URL}/login"

# Timeouts
DEFAULT_TIMEOUT = 30000  # 30 seconds
NAVIGATION_TIMEOUT = 60000  # 60 seconds


@dataclass
class LoginResult:
    success: bool
    message: str
    requires_2fa: bool = False


@dataclass
class Document:
    id: str
    name: str
    date: str
    download_url: str


class UniversaClient:
    """Client for interacting with the Universa portal using Playwright."""

    def __init__(self, session: LoginSession):
        self.session = session
        self.page: Page = session.page
        self.settings = get_settings()

    async def start_login(self) -> LoginResult:
        """
        Start the login process - this should trigger the 2FA email.

        Returns LoginResult indicating if 2FA is required.
        """
        try:
            # Navigate to login page
            await self.page.goto(LOGIN_URL, timeout=NAVIGATION_TIMEOUT)

            # Wait for page to be fully loaded
            await self.page.wait_for_load_state("networkidle", timeout=DEFAULT_TIMEOUT)

            # Take screenshot for debugging (optional, can be removed in production)
            # await self.page.screenshot(path="/tmp/login_page.png")

            # =================================================================
            # ADJUST SELECTORS BELOW based on actual portal structure
            # Use browser DevTools to inspect the login form elements
            # =================================================================

            # Wait for and fill email field
            email_selector = '#input-email'
            await self.page.wait_for_selector(email_selector, timeout=DEFAULT_TIMEOUT)
            await self.page.fill(email_selector, self.settings.universa_username)

            # Wait for and fill password field
            password_selector = '#input-password'
            await self.page.fill(password_selector, self.settings.universa_password)

            # Click login button
            login_button_selector = 'button[type="submit"]:has-text("Anmelden")'
            await self.page.click(login_button_selector)

            # SPA: Wait for 2FA field to appear (page doesn't reload, just swaps content)
            try:
                await self.page.wait_for_selector('#input-twoFACode', timeout=15000)
                return LoginResult(
                    success=True,
                    message="Login successful, 2FA code sent to email. Waiting for PIN.",
                    requires_2fa=True,
                )
            except:
                pass  # 2FA field didn't appear

            # Check for error message
            error_message = await self._extract_error_message()
            if error_message:
                return LoginResult(success=False, message=error_message)

            # Check if somehow logged in without 2FA
            await self.page.wait_for_timeout(2000)
            if await self._is_logged_in():
                return LoginResult(
                    success=True,
                    message="Login successful, no 2FA required",
                    requires_2fa=False,
                )

            return LoginResult(
                success=False,
                message="Login failed - 2FA field did not appear",
            )

        except PlaywrightTimeout as e:
            return LoginResult(success=False, message=f"Timeout during login: {str(e)}")
        except Exception as e:
            return LoginResult(success=False, message=f"Error during login: {str(e)}")

    async def submit_2fa_code(self, code: str) -> LoginResult:
        """
        Submit the 2FA code received via email.
        """
        try:
            # Wait for and fill 2FA code field
            code_selector = '#input-twoFACode'
            await self.page.wait_for_selector(code_selector, timeout=DEFAULT_TIMEOUT)
            await self.page.fill(code_selector, code)

            # Click submit button
            submit_selector = 'button[type="submit"]:has-text("Anmelden")'
            await self.page.click(submit_selector)

            # SPA: Wait for "Postfach" heading to appear (indicates successful login)
            try:
                await self.page.wait_for_selector('h2:has-text("Postfach")', timeout=15000)
                return LoginResult(success=True, message="2FA successful, logged in")
            except:
                pass

            # Check for error message
            error_message = await self._extract_error_message()
            if error_message:
                return LoginResult(success=False, message=error_message)

            # Still on 2FA page?
            if await self._is_2fa_page():
                return LoginResult(
                    success=False,
                    message="2FA verification failed - still on verification page",
                )

            return LoginResult(success=False, message="Login state unclear after 2FA")

        except PlaywrightTimeout as e:
            return LoginResult(success=False, message=f"Timeout during 2FA: {str(e)}")
        except Exception as e:
            return LoginResult(success=False, message=f"Error during 2FA: {str(e)}")

    async def get_documents(self) -> list[Document]:
        """
        Fetch the list of available documents from Postfach.
        """
        # Click on Postfach to open the document list
        try:
            await self.page.click('h2:has-text("Postfach")', timeout=10000)
            await self.page.wait_for_timeout(2000)  # Wait for content to load
        except:
            pass  # Maybe already on Postfach

        # Wait for articles to appear
        await self.page.wait_for_selector('article', timeout=10000)

        documents = []

        # Parse all document articles
        doc_elements = await self.page.query_selector_all('article')

        for idx, elem in enumerate(doc_elements):
            try:
                # Get title from h3
                title_elem = await elem.query_selector('h3')
                title = await title_elem.inner_text() if title_elem else "Unknown"

                # Get date - look for the date paragraph
                date = ""
                p_elements = await elem.query_selector_all('p')
                for p in p_elements:
                    text = await p.inner_text()
                    # Date format: DD.MM.YYYY
                    if text and len(text) == 10 and text[2] == '.' and text[5] == '.':
                        date = text
                        break

                # Get additional info (e.g., "Krankenversicherung Nr. 12345678")
                info_elem = await elem.query_selector('p.text-blaugrau')
                info = await info_elem.inner_text() if info_elem else ""

                # Check if unread - look for bold font or specific styling
                # Unread documents typically have font-bold class on h3
                h3_class = await title_elem.get_attribute('class') if title_elem else ""
                is_unread = 'font-bold' in (h3_class or '') or 'font-semibold' in (h3_class or '')

                # Use index as ID since there's no explicit ID
                documents.append(Document(
                    id=str(idx),
                    name=f"{title.strip()} - {info.strip()}".strip(' -'),
                    date=date,
                    download_url="",  # Will need to click to download
                ))
            except Exception:
                continue

        return documents

    async def download_document(self, document_id: str) -> tuple[bytes, str]:
        """
        Download a specific document by index.

        Returns tuple of (content_bytes, filename)
        """
        # Make sure we're on the Postfach page
        try:
            await self.page.click('h2:has-text("Postfach")', timeout=5000)
            await self.page.wait_for_timeout(2000)
        except:
            pass

        # Get all article elements
        articles = await self.page.query_selector_all('article')
        idx = int(document_id)

        if idx >= len(articles):
            raise Exception(f"Document index {idx} out of range (only {len(articles)} documents)")

        # Get the clickable link inside the article
        article = articles[idx]
        link = await article.query_selector('a')

        if not link:
            raise Exception("Could not find clickable link in document")

        # Set up download handler and click
        async with self.page.expect_download(timeout=NAVIGATION_TIMEOUT) as download_info:
            await link.click()

        download = await download_info.value

        # Get the downloaded file
        path = await download.path()
        filename = download.suggested_filename or f"document_{document_id}.pdf"

        # Read file content
        with open(path, "rb") as f:
            content = f.read()

        return content, filename

    async def download_recent_documents(self, max_age_days: int = 3) -> list[tuple[bytes, str, str]]:
        """
        Download all documents that are at most max_age_days old.

        Returns list of tuples: (content_bytes, filename, date_str)
        """
        # Get all documents first
        documents = await self.get_documents()

        # Calculate cutoff date
        today = datetime.now()
        cutoff_date = today - timedelta(days=max_age_days)

        # Filter documents by date
        recent_docs = []
        for doc in documents:
            try:
                # Parse date (format: DD.MM.YYYY)
                doc_date = datetime.strptime(doc.date, "%d.%m.%Y")
                if doc_date >= cutoff_date:
                    recent_docs.append(doc)
            except ValueError:
                # If date parsing fails, skip this document
                continue

        # Download each recent document
        downloaded = []
        for doc in recent_docs:
            try:
                content, filename = await self.download_document(doc.id)
                downloaded.append((content, filename, doc.date))
            except Exception as e:
                # Log error but continue with other documents
                print(f"Failed to download document {doc.id}: {e}")
                continue

        return downloaded

    # =========================================================================
    # Helper methods - ADJUST based on actual portal HTML structure
    # =========================================================================

    async def _is_2fa_page(self) -> bool:
        """Check if the current page is the 2FA verification page."""
        # Check for the specific 2FA input field first (most reliable)
        try:
            code_field = await self.page.query_selector('#input-twoFACode')
            if code_field:
                return True
        except:
            pass

        page_content = await self.page.content()
        page_content_lower = page_content.lower()

        # Check page content for 2FA indicators
        indicators = [
            "bestätigungscode" in page_content_lower,
            "verifizierungscode" in page_content_lower,
            "neuer bestätigungscode" in page_content_lower,
        ]

        return any(indicators)

    async def _is_logged_in(self) -> bool:
        """Check if we're successfully logged in."""
        # First check if we're still on 2FA page
        if await self._is_2fa_page():
            return False

        page_content = await self.page.content()
        page_content_lower = page_content.lower()

        # Check if still on login page (but not 2FA)
        if "/login" in self.page.url:
            # Check if login form is still visible
            try:
                login_field = await self.page.query_selector('#input-email')
                if login_field:
                    return False
            except:
                pass

        # Check for dashboard/home indicators
        indicators = [
            "willkommen" in page_content_lower,
            "meine dokumente" in page_content_lower,
            "abmelden" in page_content_lower,
            "logout" in page_content_lower,
            "dashboard" in self.page.url,
            "home" in self.page.url,
        ]

        if any(indicators):
            return True

        # Check for logout button
        try:
            logout_btn = await self.page.query_selector('a:has-text("Abmelden"), a:has-text("Logout"), button:has-text("Abmelden")')
            if logout_btn:
                return True
        except:
            pass

        return False

    async def _extract_error_message(self) -> Optional[str]:
        """Extract error message from page."""
        error_selectors = [
            '.text-alert',  # Universa "Fehlerhafte Eingabe"
            '.error-message',
            '.alert-danger',
            '.alert-error',
            '[role="alert"]',
            '.error',
            '.message.error',
        ]

        for selector in error_selectors:
            try:
                error_elem = await self.page.query_selector(selector)
                if error_elem:
                    text = await error_elem.inner_text()
                    if text.strip():
                        return text.strip()
            except:
                continue

        # Check for the specific "account locked" message
        try:
            locked_elem = await self.page.query_selector('p.text-lg.font-bold')
            if locked_elem:
                text = await locked_elem.inner_text()
                if "Zugangsdaten" in text and "gesperrt" in text:
                    return text.strip()
        except:
            pass

        return None

    async def take_debug_screenshot(self, name: str = "debug") -> str:
        """Take a screenshot for debugging. Returns the path."""
        path = f"/tmp/{name}_{self.session.session_id}.png"
        await self.page.screenshot(path=path)
        return path
