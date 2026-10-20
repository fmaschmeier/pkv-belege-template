"""
Client for the Universa customer portal, without a browser.

The portal is a single-page app that fetches everything as JSON from `/rest/…`. This client
makes the same calls its web app makes:

  GET  /login                          session cookie + CSRF token
  POST /rest/weblogin                  username + password; the portal mails a PIN
  POST /rest/weblogin                  the same again with the PIN
  GET  /rest/document/list             document list, paged
  GET  /rest/document/get/<abrufUrl>.pdf   one PDF

How the portal keeps the login (checked on 2026-10-20):

- A session cookie (`JSESSIONID`). The portal replaces it when it accepts the PIN, so the
  cookies from before the PIN are worthless afterwards (401).
- A CSRF token in the header `X-CSRF-TOKEN`. The portal hands out a fresh one with every
  response; POST requests must send the latest one. GET requests work without it.
- 401, 403 or 405 mean the session has expired.

The state between two calls (cookies + CSRF token) lives in `PortalState`; `session_token.py`
turns it into the `session_id` that n8n passes along.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import quote, unquote

import httpx

BASE_URL = "https://kundenportal.universa.de"
TIMEOUT = httpx.Timeout(30.0)
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36"
)
LIST_QUERY = {"insurance": "all", "period": "all", "documentType": "all"}
MAX_PAGES = 20
EXPIRED = (401, 403, 405)


class PortalError(Exception):
    """The portal answered in a way this client does not understand."""


class SessionExpired(PortalError):
    """The portal no longer accepts the session (401/403/405)."""


@dataclass
class PortalState:
    cookies: dict[str, str] = field(default_factory=dict)
    csrf: Optional[str] = None


@dataclass
class LoginResult:
    success: bool
    message: str
    requires_2fa: bool = False
    # On failure: "rejected" (the portal refuses the login, e.g. wrong password or PIN),
    # "timeout" (the portal did not answer in time), "error" (anything else)
    error_kind: Optional[str] = None


@dataclass
class Document:
    id: str  # abrufUrl from the portal; stable per document, used for the download
    name: str
    date: str  # DD.MM.YYYY


def _message(res: httpx.Response) -> str:
    """The portal's own error text, if it sent one.

    Errors come as JSON with `message`, or with `violations`/`errors` for single fields
    (that is how the portal's web app reads them).
    """
    try:
        body = res.json()
    except ValueError:
        body = None
    texts = []
    if isinstance(body, dict):
        msg = body.get("message") or body.get("body")
        if isinstance(msg, str) and msg:
            texts.append(msg)
        for key in ("violations", "errors"):
            for v in body.get(key) or []:
                text = (v.get("message") or v.get("defaultMessage")) if isinstance(v, dict) else v
                if isinstance(text, str) and text:
                    texts.append(text)
    return f"HTTP {res.status_code}: " + "; ".join(texts)[:300] if texts else f"HTTP {res.status_code}"


def _filename(res: httpx.Response, doc_id: str) -> str:
    """File name as the portal suggests it (Content-Disposition), else the last part of the URL.

    A browser picks the name the same way; n8n compares it with the files already in Google Drive.
    """
    cd = res.headers.get("Content-Disposition", "")
    m = re.search(r"filename\*\s*=\s*[^']*'[^']*'([^;]+)", cd)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename\s*=\s*"?([^";]+)"?', cd)
    if m:
        return m.group(1).strip()
    return f"{doc_id}.pdf"


class PortalClient:
    def __init__(self, state: Optional[PortalState] = None, transport: Optional[httpx.AsyncBaseTransport] = None):
        self.state = state or PortalState()
        self._transport = transport  # tests only

    async def _request(self, method: str, path: str, *, json_body=None, params=None, api: bool = True) -> httpx.Response:
        headers = {"User-Agent": USER_AGENT, "Accept-Language": "de-DE,de;q=0.9"}
        if api:
            headers.update({"Accept": "application/json", "Origin": BASE_URL, "Referer": f"{BASE_URL}/login"})
            if self.state.csrf:
                headers["X-CSRF-TOKEN"] = self.state.csrf
        else:
            headers["Accept"] = "text/html,application/pdf,*/*;q=0.8"
        if self.state.cookies:
            headers["Cookie"] = "; ".join(f"{k}={v}" for k, v in self.state.cookies.items())

        # A fresh client per call: the cookies are kept in PortalState only, never in a client jar.
        async with httpx.AsyncClient(base_url=BASE_URL, timeout=TIMEOUT, follow_redirects=False,
                                     transport=self._transport) as client:
            res = await client.request(method, path, json=json_body, params=params, headers=headers)

        sent = sorted(self.state.cookies)
        set_names = sorted({c.split("=", 1)[0].strip() for c in res.headers.get_list("set-cookie")})
        for name, value in res.cookies.items():
            self.state.cookies[name] = value
        token = res.headers.get("X-CSRF-TOKEN")
        if token:
            self.state.csrf = token
        if path in ("/login", "/rest/weblogin"):
            # Names and flags only, never values: enough to see where a login goes wrong
            keys = sorted(self._json(res)) if "json" in res.headers.get("Content-Type", "") else []
            print(f"portal {method} {path}: HTTP {res.status_code} · {res.headers.get('Content-Type', '-')} · "
                  f"JSON keys {keys} · sent cookies {sent} · CSRF sent {'X-CSRF-TOKEN' in headers} · "
                  f"set-cookie {set_names} · new CSRF {bool(token)}", flush=True)
        return res

    # --- Login -----------------------------------------------------------------------------

    async def start_login(self, username: str, password: str) -> LoginResult:
        """Open the login page and send username + password. The portal then mails a PIN."""
        try:
            page = await self._request("GET", "/login", api=False)
            if page.status_code != 200:
                return LoginResult(False, f"Login page answered HTTP {page.status_code}", error_kind="error")
            if not self.state.csrf:
                m = re.search(r'<meta name="_csrf" content="([^"]+)"', page.text)
                self.state.csrf = m.group(1) if m else None
            if not self.state.csrf:
                return LoginResult(False, "Login page without CSRF token", error_kind="error")

            res = await self._request("POST", "/rest/weblogin", json_body={
                "username": username, "password": password, "twoFACode": "", "saveTwoFACookie": ""})
        except httpx.TimeoutException as e:
            return LoginResult(False, f"Timeout during login: {e}", error_kind="timeout")
        except httpx.HTTPError as e:
            return LoginResult(False, f"Error during login: {e}", error_kind="error")

        body = self._json(res)
        if res.status_code in (200, 201) and body.get("twoFaMethod"):
            return LoginResult(True, "Login successful, 2FA code sent to email. Waiting for PIN.", requires_2fa=True)
        if res.status_code == 200 and body.get("userDataDTO"):
            return LoginResult(True, "Login successful, no 2FA required", requires_2fa=False)
        if 400 <= res.status_code < 500:
            return LoginResult(False, _message(res), error_kind="rejected")
        return LoginResult(False, f"Unexpected answer to login: {_message(res)}", error_kind="error")

    async def submit_pin(self, username: str, password: str, pin: str) -> LoginResult:
        """Send the PIN. The portal's web app repeats username and password in this call."""
        try:
            res = await self._request("POST", "/rest/weblogin", json_body={
                "username": username, "password": password, "twoFACode": pin, "saveTwoFACookie": ""})
        except httpx.TimeoutException as e:
            return LoginResult(False, f"Timeout during 2FA: {e}", error_kind="timeout")
        except httpx.HTTPError as e:
            return LoginResult(False, f"Error during 2FA: {e}", error_kind="error")

        if res.status_code == 200 and self._json(res).get("userDataDTO"):
            return LoginResult(True, "2FA successful, logged in")
        return LoginResult(False, f"2FA verification failed: {_message(res)}", error_kind="rejected")

    async def logout(self) -> None:
        try:
            await self._request("GET", "/logout", api=False)
        except httpx.HTTPError:
            pass  # the session expires on its own

    # --- Documents -------------------------------------------------------------------------

    async def get_documents(self, page_index: int = 0) -> tuple[list[Document], bool]:
        """One page of the inbox (newest first) and whether there are more pages."""
        res = await self._request("GET", "/rest/document/list", params={"pageIndex": page_index, **LIST_QUERY})
        if res.status_code in EXPIRED:
            raise SessionExpired("Portal session expired. Please start a new login.")
        if res.status_code != 200:
            raise PortalError(f"Document list answered {_message(res)}")
        body = self._json(res)
        raw = [d for d in body.get("documentDTOs") or [] if isinstance(d, dict) and d.get("abrufUrl")]
        if raw:
            # Types and shapes only (digits -> 9, letters -> a), never values
            print(f"portal GET /rest/document/list: {len(raw)} documents · " + " · ".join(
                f"{k} {_shape(raw[0].get(k))}" for k in ("abrufUrl", "dokumentDatum", "dokumentTypNames")), flush=True)
        docs = []
        for d in raw:
            when = _parse_date(d.get("dokumentDatum"))
            name = " - ".join(x for x in (_text(d.get("dokumentBeschreibung")), _text(d.get("dokumentTypNames"))) if x)
            docs.append(Document(id=str(d["abrufUrl"]), name=name or str(d["abrufUrl"]),
                                 date=when.strftime("%d.%m.%Y") if when else ""))
        return docs, bool(body.get("hasMoreElements"))

    async def download_document(self, document_id: str) -> tuple[bytes, str]:
        """One PDF. Returns (content, filename)."""
        res = await self._request("GET", f"/rest/document/get/{quote(document_id, safe='')}.pdf", api=False)
        if res.status_code in EXPIRED:
            raise SessionExpired("Portal session expired. Please start a new login.")
        if res.status_code != 200 or not res.content.startswith(b"%PDF"):
            raise PortalError(f"Download answered HTTP {res.status_code}, {res.headers.get('Content-Type')}")
        return res.content, _filename(res, document_id)

    async def download_recent_documents(self, max_age_days: int = 3) -> list[tuple[bytes, str, str]]:
        """All documents at most max_age_days old: list of (content, filename, date)."""
        cutoff = datetime.now() - timedelta(days=max_age_days)
        recent: list[Document] = []
        for page in range(MAX_PAGES):
            docs, more = await self.get_documents(page)
            dated = [(d, self._date(d.date)) for d in docs]
            recent += [d for d, when in dated if when and when >= cutoff]
            # The list is sorted newest first; once a page reaches past the cutoff, stop.
            if not more or any(when and when < cutoff for _, when in dated):
                break

        downloaded = []
        for doc in recent:
            try:
                content, filename = await self.download_document(doc.id)
                downloaded.append((content, filename, doc.date))
            except SessionExpired:
                raise
            except PortalError as e:
                print(f"Failed to download a document: {e}")  # no document name in the log
        return downloaded

    # --- Helpers ---------------------------------------------------------------------------

    @staticmethod
    def _json(res: httpx.Response) -> dict:
        try:
            body = res.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    @staticmethod
    def _date(text: str) -> Optional[datetime]:
        return _parse_date(text)


def _text(value) -> str:
    """A field that is a string in one answer and a list of strings in another."""
    if isinstance(value, list):
        return ", ".join(str(v) for v in value if v)
    return str(value) if value else ""


def _parse_date(value) -> Optional[datetime]:
    """Dates as the portal may send them: DD.MM.YYYY, ISO (with or without time), epoch ms."""
    if isinstance(value, (int, float)) and value > 0:
        return datetime.fromtimestamp(value / 1000 if value > 1e11 else value)
    if not isinstance(value, str) or not value:
        return None
    for fmt in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(value[:10], fmt)
        except ValueError:
            pass
    return None


def _shape(value) -> str:
    if isinstance(value, list):
        return f"list[{len(value)}] of {_shape(value[0]) if value else '-'}"
    if isinstance(value, str):
        return "str '" + re.sub(r"[^\W\d_]", "a", re.sub(r"\d", "9", value))[:40] + "'"
    return type(value).__name__
