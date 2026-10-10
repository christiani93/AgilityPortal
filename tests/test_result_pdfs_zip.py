"""
Test für den ZIP-Export aller Ranglisten-PDFs eines Turniers
(/club/events/<id>/results/pdfs.zip) — nur Veranstalter (gleicher Club) oder
Superadmin dürfen exportieren.
"""
import io
import os
import zipfile

import pytest

from app import create_app
from app.extensions import db
from app import models as M


@pytest.fixture()
def app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


def _seed(app):
    club = M.Club(vereinsnummer="V1", name="Club")
    other_club = M.Club(vereinsnummer="V2", name="Anderer Club")
    db.session.add_all([club, other_club])
    db.session.flush()

    event = M.Event(name="Testturnier", type="regular", organiser_club_id=club.id, is_published=True)
    db.session.add(event)
    db.session.flush()

    db.session.add_all([
        M.ResultPDF(event_id=event.id, pdf_data=b"%PDF-1 Agility", ring="1",
                    discipline="agility", category_code="Large", class_level=3),
        M.ResultPDF(event_id=event.id, pdf_data=b"%PDF-1 Jumping", ring="1",
                    discipline="jumping", category_code="Large", class_level=3),
    ])

    organiser = M.User(email="organiser@test.ch", role="club_admin", club_id=club.id)
    other_club_admin = M.User(email="other@test.ch", role="club_admin", club_id=other_club.id)
    superadmin = M.User(email="admin@test.ch", role="superadmin")
    handler = M.User(email="handler@test.ch", role="handler", club_id=club.id)
    db.session.add_all([organiser, other_club_admin, superadmin, handler])
    db.session.commit()
    return event.id, organiser.id, other_club_admin.id, superadmin.id, handler.id


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_organiser_can_export_zip(app):
    event_id, organiser_id, _, _, _ = _seed(app)
    client = app.test_client()
    _login(client, organiser_id)

    resp = client.get(f"/club/events/{event_id}/results/pdfs.zip")
    assert resp.status_code == 200
    assert resp.mimetype == "application/zip"

    zf = zipfile.ZipFile(io.BytesIO(resp.data))
    assert len(zf.namelist()) == 2


def test_superadmin_can_export_zip(app):
    event_id, _, _, superadmin_id, _ = _seed(app)
    client = app.test_client()
    _login(client, superadmin_id)

    resp = client.get(f"/club/events/{event_id}/results/pdfs.zip")
    assert resp.status_code == 200


def test_other_club_admin_forbidden(app):
    event_id, _, other_club_admin_id, _, _ = _seed(app)
    client = app.test_client()
    _login(client, other_club_admin_id)

    resp = client.get(f"/club/events/{event_id}/results/pdfs.zip")
    assert resp.status_code == 403


def test_same_club_handler_can_export(app):
    """_assert_event_access (wie bei allen anderen Veranstalter-Aktionen in diesem
    Blueprint) erlaubt jedem User mit passender club_id, unabhängig von der
    genauen Rolle — konsistent mit event_detail & Co."""
    event_id, _, _, _, handler_id = _seed(app)
    client = app.test_client()
    _login(client, handler_id)

    resp = client.get(f"/club/events/{event_id}/results/pdfs.zip")
    assert resp.status_code == 200


def test_anonymous_redirected_to_login(app):
    event_id, *_ = _seed(app)
    client = app.test_client()

    resp = client.get(f"/club/events/{event_id}/results/pdfs.zip")
    assert resp.status_code == 302


def test_no_pdfs_returns_404(app):
    club = M.Club(vereinsnummer="V3", name="Club ohne PDFs")
    db.session.add(club)
    db.session.flush()
    event = M.Event(name="Leer", type="regular", organiser_club_id=club.id, is_published=True)
    superadmin = M.User(email="admin2@test.ch", role="superadmin")
    db.session.add_all([event, superadmin])
    db.session.commit()

    client = app.test_client()
    _login(client, superadmin.id)
    resp = client.get(f"/club/events/{event.id}/results/pdfs.zip")
    assert resp.status_code == 404
