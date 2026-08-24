"""
Regressionstest für das Löschen eines Events mit allen abhängigen Daten.

Hintergrund: `event_delete` löschte Registrations per Bulk-DELETE, ohne die
abhängigen `start_numbers` (und weitere event_id-FKs ohne ON DELETE CASCADE)
vorher zu entfernen → auf MySQL `IntegrityError (1451)`. Auf SQLite fiel das nie
auf, weil FK-Constraints dort standardmäßig NICHT erzwungen werden.

Dieser Test schaltet FK-Enforcement (`PRAGMA foreign_keys=ON`) VOR `create_all()`
ein und ruft die echte Route auf — so würde eine fehlende/falsch geordnete
Löschung wie auf MySQL fehlschlagen.
"""
import os

import pytest
from sqlalchemy import event as sa_event, text

from app import create_app
from app.extensions import db
from app import models as M


@pytest.fixture()
def fk_app():
    os.environ["DATABASE_URL"] = "sqlite:///:memory:"
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        # FK-Enforcement einschalten, BEVOR die erste Verbindung (via create_all) geöffnet wird
        sa_event.listen(db.engine, "connect",
                        lambda dbapi, rec: dbapi.cursor().execute("PRAGMA foreign_keys=ON"))
        db.create_all()
        assert db.session.execute(text("PRAGMA foreign_keys")).scalar() == 1
        yield app
        db.session.remove()
        db.drop_all()


def _seed_event_with_dependents():
    """Legt ein Event mit je einer Zeile in allen event-abhängigen Tabellen an."""
    club = M.Club(vereinsnummer="V1", name="Club")
    judge = M.Judge(first_name="J", last_name="R")
    dog = M.Dog(name="Rex", license_kind=M.LicenseKind.CH, license_no="123456")
    admin = M.User(email="admin@test.ch", role="superadmin")
    db.session.add_all([club, judge, dog, admin])
    db.session.flush()
    cup = M.Cup(name="Cup", season=2026)
    db.session.add(cup)
    db.session.flush()
    ev = M.Event(name="__delete_me__", type="regular", organiser_club_id=club.id, is_published=False)
    db.session.add(ev)
    db.session.flush()
    eid = ev.id

    reg = M.Registration(event_id=eid, dog_id=dog.id, status=M.RegistrationStatus.CONFIRMED,
                         class_level=1, category_code="Large")
    db.session.add(reg)
    db.session.flush()
    db.session.add_all([
        M.StartNumber(event_id=eid, registration_id=reg.id, start_no=1),
        M.ScheduleBlock(event_id=eid, ring="Ring 1"),
        M.EventRun(event_id=eid, run_type="agility", category="Large", class_level=1),
        M.EventJudge(event_id=eid, judge_id=judge.id),
        M.ResultPDF(event_id=eid, pdf_data=b"x"),
        M.LiveUpdate(event_id=eid, event_external_id="e", source_system="s",
                     source_device="d", sequence_no=1, payload_json="{}"),
        M.ExchangeExportLog(event_id=eid, export_type="x", schema="s"),
        M.EventFinalist(event_id=eid, position=1),
        M.CupEvent(cup_id=cup.id, event_id=eid, meeting_no=1),
    ])
    # TKA-Kette: Batch -> Row/Import -> Finding
    batch = M.TkaExportBatch(event_id=eid, export_type=M.TkaExportType.EVENT_CHECK)
    db.session.add(batch)
    db.session.flush()
    imp = M.TkaImport(batch_id=batch.id)
    db.session.add(imp)
    db.session.flush()
    db.session.add_all([
        M.TkaExportRow(batch_id=batch.id, registration_id=reg.id, dog_id=dog.id,
                       license_no="123456", category_code="Large", class_level=1),
        M.TkaFinding(tka_import_id=imp.id, registration_id=reg.id,
                     finding_kind=M.TkaFindingKind.LICENSE_UNKNOWN,
                     issue_type=M.TkaIssueType.LICENSE_UNKNOWN),
    ])
    # Ergebnis-Kette: ResultImport -> Result/Document
    ri = M.ResultImport(event_id=eid, schema="resultexport.v1")
    db.session.add(ri)
    db.session.flush()
    db.session.add_all([
        M.Result(result_import_id=ri.id, event_id=eid),
        M.Document(result_import_id=ri.id, kind="pdf", name="x", path="/x"),
    ])
    # Cup-Quali-Kette: QualificationRun -> QualifiedTeam
    qr = M.CupQualificationRun(cup_id=cup.id, event_id=eid, discipline="agility",
                               spots=1, run_order=1)
    db.session.add(qr)
    db.session.flush()
    db.session.add(M.CupQualifiedTeam(cup_id=cup.id, category_code="Large", dog_name="Rex",
                                      handler_name="H", qualification_source="run", qual_run_id=qr.id))
    db.session.commit()
    return eid, admin.id


def test_event_delete_removes_all_dependents(fk_app):
    eid, admin_id = _seed_event_with_dependents()
    client = fk_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(admin_id)
        sess["_fresh"] = True

    resp = client.post(f"/club/events/{eid}/delete")
    assert resp.status_code == 302  # Redirect zum Dashboard, KEIN 500

    # Event + alle abhängigen Zeilen weg
    assert M.Event.query.count() == 0
    assert M.Registration.query.count() == 0
    assert M.StartNumber.query.count() == 0
    assert M.EventRun.query.count() == 0          # ORM-Cascade
    assert M.EventJudge.query.count() == 0        # ORM-Cascade
    assert M.TkaExportBatch.query.count() == 0
    assert M.TkaExportRow.query.count() == 0
    assert M.TkaImport.query.count() == 0
    assert M.TkaFinding.query.count() == 0
    assert M.ResultImport.query.count() == 0
    assert M.Result.query.count() == 0
    assert M.Document.query.count() == 0
    assert M.ResultPDF.query.count() == 0
    assert M.LiveUpdate.query.count() == 0
    assert M.ExchangeExportLog.query.count() == 0
    assert M.EventFinalist.query.count() == 0
    assert M.CupEvent.query.count() == 0
    assert M.CupQualificationRun.query.count() == 0
    assert M.CupQualifiedTeam.query.count() == 0
    assert M.ScheduleBlock.query.count() == 0

    # Geteilte Entitäten bleiben erhalten (nur die Verknüpfung wurde gelöst)
    assert M.Cup.query.count() == 1
    assert M.Dog.query.count() == 1
    assert M.Club.query.count() == 1


def test_event_delete_requires_superadmin(fk_app):
    """Nicht-Superadmin bekommt 403, kein Löschen."""
    eid, _ = _seed_event_with_dependents()
    non_admin = M.User(email="user@test.ch", role="club_admin")
    db.session.add(non_admin)
    db.session.commit()
    client = fk_app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = str(non_admin.id)
        sess["_fresh"] = True
    resp = client.post(f"/club/events/{eid}/delete")
    assert resp.status_code == 403
    assert M.Event.query.count() == 1
