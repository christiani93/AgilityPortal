"""
Tests für den serverseitigen TKAMO-Proxy (/club/tkamo/<ais>).

Der Proxy ersetzt den früheren direkten Browser-Fetch auf admin.z-b.tech, der an
fehlendem CORS scheiterte. Der externe Call wird hier gemockt.
"""
import requests as _requests

from app.extensions import db
from app import models as M


class _FakeResp:
    def __init__(self, content, status=200, ctype="application/json"):
        self.content = content
        self.status_code = status
        self.headers = {"Content-Type": ctype}


def _login_superadmin(app, client):
    u = M.User(email="admin@test.ch", role="superadmin")
    db.session.add(u)
    db.session.commit()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(u.id)
        sess["_fresh"] = True


def test_tkamo_proxy_requires_login(app):
    client = app.test_client()
    r = client.get("/club/tkamo/11338")
    assert r.status_code in (302, 401)  # login_required


def test_tkamo_proxy_passes_through_admin_json(app, monkeypatch):
    client = app.test_client()
    _login_superadmin(app, client)
    payload = b'{"title": "LyTiWee \\u2013 09.10.2026", "location": "M\\u00fcnsingen", "date_from": "2026-10-09"}'
    monkeypatch.setattr(_requests, "get", lambda *a, **k: _FakeResp(payload))

    r = client.get("/club/tkamo/11338")
    assert r.status_code == 200
    data = r.get_json()
    assert data["title"] == "LyTiWee – 09.10.2026"
    assert data["location"] == "Münsingen"
    assert data["date_from"] == "2026-10-09"


def test_tkamo_proxy_rejects_non_numeric_ais(app):
    client = app.test_client()
    _login_superadmin(app, client)
    r = client.get("/club/tkamo/abc")
    assert r.status_code == 400
    assert "error" in r.get_json()


def test_tkamo_proxy_handles_admin_unreachable(app, monkeypatch):
    client = app.test_client()
    _login_superadmin(app, client)

    def _boom(*a, **k):
        raise _requests.RequestException("boom")
    monkeypatch.setattr(_requests, "get", _boom)

    r = client.get("/club/tkamo/11338")
    assert r.status_code == 502
    assert "error" in r.get_json()
