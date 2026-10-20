"""
The login session travels inside the session_id, encrypted, instead of in the memory of one
Cloud Run instance.

n8n passes the session_id from call to call and stores it for a few minutes to reuse it. Only
this service can read it. Inside: the portal cookies, the current CSRF token and the state
(`pending_2fa` or `authenticated`). Because the portal replaces its session cookie when it
accepts the PIN, `/login/complete` returns a new session_id; the one from `/login/start` only
works for the PIN step.

Key: derived from BEARER_TOKEN (HKDF-SHA256), so no further secret is needed. A new bearer
token ends all open sessions. Lifetime: SESSION_TIMEOUT_SECONDS, checked on every call.
"""

import base64
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from app.config import get_settings
from app.portal_client import PortalState

_INFO = b"pkv-belege-downloader session v1"


@dataclass
class Session:
    state: PortalState
    status: str  # pending_2fa | authenticated
    created_at: datetime


def _fernet() -> Fernet:
    secret = get_settings().bearer_token.encode()
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_INFO).derive(secret)
    return Fernet(base64.urlsafe_b64encode(key))


def seal(state: PortalState, status: str) -> str:
    payload = json.dumps({"c": state.cookies, "t": state.csrf, "s": status}, separators=(",", ":"))
    return _fernet().encrypt(payload.encode()).decode()


def unseal(session_id: str) -> Optional[Session]:
    """The session, or None if the session_id is unknown, tampered with or expired."""
    f = _fernet()
    try:
        raw = f.decrypt(session_id.encode(), ttl=get_settings().session_timeout_seconds)
        created = datetime.fromtimestamp(f.extract_timestamp(session_id.encode()), tz=timezone.utc)
        data = json.loads(raw)
    except (InvalidToken, ValueError, TypeError):
        return None
    return Session(state=PortalState(cookies=data.get("c") or {}, csrf=data.get("t")),
                   status=data.get("s") or "", created_at=created)
