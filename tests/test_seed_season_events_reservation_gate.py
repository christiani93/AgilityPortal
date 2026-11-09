"""`flask seed-season-events` darf ein Turnier NUR anlegen, wenn für dessen
Datum bereits eine bestätigte AdminPortal-Reservation mit AIS-Turniernummer
existiert (Lehre aus Reservation #63, die nie mit den Portal-Events
verknüpft wurde - siehe [[project_bccs_sm_portal_infrastructure_20261109]]).
`reservation`/`reservation_event` gehören zum AdminPortal-Schema, in der
SQLite-Test-DB existieren sie nicht automatisch - für die Tests, die eine
Reservation simulieren, legen wir sie hier manuell per raw SQL an."""
from datetime import date

from app.extensions import db
from app import models as M
from app.commands import _SEASON_EVENTS


def _create_reservation_tables():
    db.session.execute(db.text("""
        CREATE TABLE reservation (
            id INTEGER PRIMARY KEY,
            status VARCHAR(20) NOT NULL,
            date_from DATE NOT NULL,
            date_to DATE,
            ais_turniernummer INTEGER
        )
    """))
    db.session.execute(db.text("""
        CREATE TABLE reservation_event (
            id INTEGER PRIMARY KEY,
            reservation_id INTEGER NOT NULL,
            portal_event_id INTEGER,
            ais_turniernummer INTEGER,
            event_name VARCHAR(255),
            date_from DATE
        )
    """))
    db.session.commit()


def _run_seed(app, dry_run=False):
    runner = app.test_cli_runner()
    args = ["seed-season-events"] + (["--dry-run"] if dry_run else [])
    result = runner.invoke(args=args)
    assert result.exit_code == 0, result.output
    return result.output


def test_without_reservation_tables_everything_is_skipped(app):
    """Ohne AdminPortal-Schema (Default-Test-DB) wird alles übersprungen,
    kein Crash."""
    with app.app_context():
        output = _run_seed(app)
        assert "ohne Reservation übersprungen" in output
        assert db.session.execute(db.select(M.Event)).scalars().first() is None


def test_event_created_from_reservation_event_breakdown(app):
    spec = next(s for s in _SEASON_EVENTS if s["ext"] == "SEASON_2627_seeland_abendmeeting")
    with app.app_context():
        _create_reservation_tables()
        db.session.execute(db.text(
            "INSERT INTO reservation (id, status, date_from, date_to) "
            "VALUES (63, 'confirmed', '2026-11-20', '2026-11-22')"
        ))
        db.session.execute(db.text(
            "INSERT INTO reservation_event (reservation_id, portal_event_id, "
            "ais_turniernummer, event_name, date_from) "
            "VALUES (63, NULL, 12322, 'Abendmeeting 20.11.2026', :d)"
        ), {"d": spec["start"].isoformat()})
        db.session.commit()

        output = _run_seed(app)
        assert "AIS 12322" in output

        event = db.session.execute(
            db.select(M.Event).filter_by(external_id=spec["ext"])
        ).scalar_one()
        assert event.ais_turniernummer == 12322
        assert event.reservation_id == 63
        assert event.reservation_synced_at is not None


def test_event_without_matching_reservation_is_skipped(app):
    spec = next(s for s in _SEASON_EVENTS if s["ext"] == "SEASON_2627_seeland_abendmeeting")
    with app.app_context():
        _create_reservation_tables()
        # Reservation existiert, aber an einem ANDEREN Datum.
        db.session.execute(db.text(
            "INSERT INTO reservation (id, status, date_from, date_to) "
            "VALUES (1, 'confirmed', '2099-01-01', NULL)"
        ))
        db.session.commit()

        output = _run_seed(app)
        assert "übersprungen" in output

        event = db.session.execute(
            db.select(M.Event).filter_by(external_id=spec["ext"])
        ).scalar_one_or_none()
        assert event is None


def test_single_day_reservation_falls_back_to_main_table(app):
    """Eintages-Reservation ohne reservation_event-Aufschlüsselung ist ein
    gültiger Fallback-Match (date_to NULL oder == date_from)."""
    spec = next(s for s in _SEASON_EVENTS if s["ext"] == "SEASON_2627_seeland_abendmeeting")
    with app.app_context():
        _create_reservation_tables()
        db.session.execute(db.text(
            "INSERT INTO reservation (id, status, date_from, date_to, ais_turniernummer) "
            "VALUES (99, 'confirmed', :d, NULL, 12999)"
        ), {"d": spec["start"].isoformat()})
        db.session.commit()

        _run_seed(app)
        event = db.session.execute(
            db.select(M.Event).filter_by(external_id=spec["ext"])
        ).scalar_one()
        assert event.ais_turniernummer == 12999
        assert event.reservation_id == 99


def test_multiday_main_reservation_without_breakdown_does_not_match_secondary_day(app):
    """Mehrtage-Reservation OHNE reservation_event-Zeilen darf für einen
    Folgetag (nicht date_from) NICHT raten, welche AIS-Nummer gilt."""
    bccs_sa = next(s for s in _SEASON_EVENTS if s["ext"] == "SEASON_2627_bccs_sm_sa")
    with app.app_context():
        _create_reservation_tables()
        # Reservation beginnt am Vortag, deckt bccs_sa.start aber als Folgetag ab.
        db.session.execute(db.text(
            "INSERT INTO reservation (id, status, date_from, date_to, ais_turniernummer) "
            "VALUES (63, 'confirmed', '2026-11-20', '2026-11-22', 12322)"
        ))
        db.session.commit()

        _run_seed(app)
        event = db.session.execute(
            db.select(M.Event).filter_by(external_id=bccs_sa["ext"])
        ).scalar_one_or_none()
        assert event is None
