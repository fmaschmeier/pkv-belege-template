"""
The downloader end to end against a fake portal, in the order n8n calls it.

The fake portal behaves like the real one did on 2026-10-20: a fresh CSRF token with every
response, required on POST; a new JSESSIONID once the PIN is accepted, the old one then 401.

    pip install -r requirements.txt pytest && pytest -q tests
"""

import base64
import json
import os
from datetime import datetime, timedelta

import httpx
import pytest

os.environ.update(BEARER_TOKEN="test-bearer-token-not-a-secret", UNIVERSA_USERNAME="user@example.com",
                  UNIVERSA_PASSWORD="example-password", SESSION_TIMEOUT_SECONDS="300")

from fastapi.testclient import TestClient  # noqa: E402

from app import portal_client  # noqa: E402
from app.main import app  # noqa: E402

PIN = "123456"
AUTH = {"Authorization": "Bearer test-bearer-token-not-a-secret"}


def day(offset: int) -> str:
    return (datetime.now() - timedelta(days=offset)).strftime("%d.%m.%Y")


class FakePortal:
    def __init__(self):
        self.csrf_n = 0
        self.pages_requested = []

    def _csrf(self) -> str:
        self.csrf_n += 1
        return f"csrf-{self.csrf_n}"

    def _cookies(self, req) -> dict:
        raw = req.headers.get("Cookie", "")
        return dict(p.split("=", 1) for p in raw.split("; ") if "=" in p)

    def __call__(self, req: httpx.Request) -> httpx.Response:
        path, cookies = req.url.path, self._cookies(req)
        if path == "/login":
            return httpx.Response(200, text="<html></html>", headers=[
                ("X-CSRF-TOKEN", self._csrf()), ("Set-Cookie", "JSESSIONID=pre; Path=/; HttpOnly"),
                ("Set-Cookie", "cookiesession1=lb; Path=/")])
        if path == "/rest/weblogin":
            assert req.headers.get("X-CSRF-TOKEN") == f"csrf-{self.csrf_n}", "POST needs the latest CSRF token"
            assert cookies.get("JSESSIONID") == "pre"
            data = json.loads(req.content)
            assert data["username"] == "user@example.com" and data["password"] == "example-password"
            if data["twoFACode"] == "":
                return httpx.Response(201, json={"message": "Code gesendet", "twoFaMethod": "EMAIL", "userDataDTO": None},
                                      headers={"X-CSRF-TOKEN": self._csrf()})
            if data["twoFACode"] == PIN:
                return httpx.Response(200, json={"message": "ok", "twoFaMethod": None, "userDataDTO": {"name": "x"}},
                                      headers=[("X-CSRF-TOKEN", self._csrf()), ("Set-Cookie", "JSESSIONID=post; Path=/")])
            return httpx.Response(400, json={"violations": [{"field": "twoFACode", "message": "Der Code ist falsch."}]},
                                  headers={"X-CSRF-TOKEN": self._csrf()})
        if cookies.get("JSESSIONID") != "post":
            return httpx.Response(401)
        if path == "/rest/document/list":
            page = int(req.url.params["pageIndex"])
            self.pages_requested.append(page)
            # Mixed shapes on purpose: type names as list or string, dates German or ISO
            docs = [{"abrufUrl": "doc0", "dokumentDatum": day(0), "dokumentBeschreibung": "Leistungsinformationen",
                     "dokumentTypNames": ["Abrechnung"]},
                    {"abrufUrl": "doc1", "dokumentDatum": (datetime.now() - timedelta(days=2)).strftime("%Y-%m-%d"),
                     "dokumentBeschreibung": "Leistungsinformationen", "dokumentTypNames": "Abrechnung"},
                    {"abrufUrl": "doc2", "dokumentDatum": day(10), "dokumentBeschreibung": "Brief", "dokumentTypNames": []}]
            return httpx.Response(200, json={"documentDTOs": docs, "hasMoreElements": True, "partnernummer": "p"},
                                  headers={"X-CSRF-TOKEN": self._csrf()})
        if path.startswith("/rest/document/get/"):
            doc = path.rsplit("/", 1)[1].removesuffix(".pdf")
            return httpx.Response(200, content=b"%PDF-1.4 " + doc.encode(), headers={
                "Content-Type": "application/pdf;charset=UTF-8",
                "Content-Disposition": f'attachment; filename="20261020_X_Leistungsinformationen_{doc}.pdf"'})
        if path == "/logout":
            return httpx.Response(302, headers={"Location": "/index.html"})
        return httpx.Response(404)


@pytest.fixture
def portal(monkeypatch):
    fake = FakePortal()
    original = portal_client.PortalClient.__init__

    def init(self, state=None, transport=None):
        original(self, state, httpx.MockTransport(fake))

    monkeypatch.setattr(portal_client.PortalClient, "__init__", init)
    return fake


@pytest.fixture
def client():
    return TestClient(app)


def test_n8n_flow(portal, client):
    start = client.post("/login/start", headers=AUTH)
    assert start.status_code == 200, start.text
    s1 = start.json()
    assert s1["requires_2fa"] and s1["status"] == "pending_2fa"

    done = client.post("/login/complete", headers=AUTH, json={"session_id": s1["session_id"], "pin": PIN})
    assert done.status_code == 200 and done.json()["success"], done.text
    s2 = done.json()["session_id"]
    assert s2 and s2 != s1["session_id"]

    # The session_id from /login/start does not open the documents
    early = client.get("/documents/recent", headers=AUTH, params={"session_id": s1["session_id"], "max_age_days": 4})
    assert early.status_code == 400

    recent = client.get("/documents/recent", headers=AUTH, params={"session_id": s2, "max_age_days": 4})
    assert recent.status_code == 200 and recent.json()["success"], recent.text
    docs = recent.json()["documents"]
    assert [d["filename"] for d in docs] == ["20261020_X_Leistungsinformationen_doc0.pdf",
                                             "20261020_X_Leistungsinformationen_doc1.pdf"]
    assert all(base64.b64decode(d["content_base64"]).startswith(b"%PDF") for d in docs)
    assert [d["date"] for d in docs] == [day(0), day(2)], "dates go out as DD.MM.YYYY, as before"
    assert portal.pages_requested == [0], "stops paging once a page reaches past the cutoff"

    listing = client.get("/documents", headers=AUTH, params={"session_id": s2})
    assert [d["id"] for d in listing.json()["documents"]] == ["doc0", "doc1", "doc2"]
    pdf = client.get("/documents/doc1/download", headers=AUTH, params={"session_id": s2})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")

    status = client.get(f"/session/{s2}", headers=AUTH)
    assert status.json()["status"] == "authenticated"
    assert client.delete(f"/session/{s2}", headers=AUTH).status_code == 200


def test_wrong_pin(portal, client):
    s1 = client.post("/login/start", headers=AUTH).json()["session_id"]
    done = client.post("/login/complete", headers=AUTH, json={"session_id": s1, "pin": "000000"})
    assert done.status_code == 200
    assert done.json()["success"] is False
    assert "HTTP 400: Der Code ist falsch." in done.json()["message"]
    # Second try with the right PIN on the session_id from the failed attempt (latest CSRF token)
    retry = done.json()["session_id"]
    assert client.get("/documents/recent", headers=AUTH, params={"session_id": retry}).status_code == 400
    again = client.post("/login/complete", headers=AUTH, json={"session_id": retry, "pin": PIN})
    assert again.json()["success"] and again.json()["session_id"]


def test_tampered_or_foreign_session_id(portal, client):
    s1 = client.post("/login/start", headers=AUTH).json()["session_id"]
    tampered = s1[:-4] + ("AAAA" if not s1.endswith("AAAA") else "BBBB")
    assert client.post("/login/complete", headers=AUTH, json={"session_id": tampered, "pin": PIN}).status_code == 404
    assert client.get("/documents/recent", headers=AUTH, params={"session_id": "an-old-uuid"}).status_code == 404


def test_bearer_token_required(portal, client):
    assert client.post("/login/start").status_code == 403
    assert client.post("/login/start", headers={"Authorization": "Bearer wrong"}).status_code == 401


def test_session_id_reveals_nothing(portal, client):
    s1 = client.post("/login/start", headers=AUTH).json()["session_id"]
    decoded = base64.urlsafe_b64decode(s1 + "=" * (-len(s1) % 4))
    assert b"JSESSIONID" not in decoded and b"csrf" not in decoded


def test_portal_timeout_is_504(monkeypatch, client):
    def boom(req):
        raise httpx.ConnectTimeout("slow")

    original = portal_client.PortalClient.__init__
    monkeypatch.setattr(portal_client.PortalClient, "__init__",
                        lambda self, state=None, transport=None: original(self, state, httpx.MockTransport(boom)))
    assert client.post("/login/start", headers=AUTH).status_code == 504
