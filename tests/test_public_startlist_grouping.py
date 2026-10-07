"""Tests für die öffentliche Startliste: Dreistufen-Datenquelle
(StartNumber-Tabelle → Registration.start_number → Meldeliste) und die
Gruppierung pro (Kategorie, Klasse) wie in der AgilitySoftware."""
from app.extensions import db
from app import models as M
from app.blueprints.public.routes_events import (
    _collect_startlist_rows,
    _group_startlist_rows,
)


def _seed_event(published=True):
    club = M.Club(vereinsnummer="295", name="LyTiWee")
    db.session.add(club)
    db.session.flush()
    event = M.Event(name="Jump Into Fall (TEST)", organiser_club_id=club.id,
                    is_published=published)
    db.session.add(event)
    db.session.flush()
    return event, club


def _add_reg(event, lic, dogname, cat, cls, start_number=None,
             status=M.RegistrationStatus.CONFIRMED, breed="Border Collie"):
    dog = M.Dog(name=dogname, license_no=lic, license_kind=M.LicenseKind.CH, breed=breed)
    person = M.Person(first_name="HF", last_name=lic)
    db.session.add_all([dog, person])
    db.session.flush()
    reg = M.Registration(event_id=event.id, dog_id=dog.id, handler_id=person.id,
                         status=status, class_level=cls, category_code=cat,
                         start_number=start_number)
    db.session.add(reg)
    db.session.flush()
    return reg


def test_tier2_falls_back_to_registration_start_number(app):
    """Ohne StartNumber-Tabelle, aber mit Registration.start_number →
    echte Startliste (has_numbers=True), nicht die Meldeliste."""
    with app.app_context():
        event, _ = _seed_event()
        _add_reg(event, "1001", "Alpha", "Large", 3, start_number=1301)
        _add_reg(event, "1002", "Bravo", "Large", 3, start_number=1302)
        db.session.commit()

        rows, has_numbers = _collect_startlist_rows(event.id)
        assert has_numbers is True
        assert {r["start_no"] for r in rows} == {1301, 1302}


def test_startnumber_table_takes_priority(app):
    """Befüllte StartNumber-Tabelle hat Vorrang vor Registration.start_number."""
    with app.app_context():
        event, _ = _seed_event()
        reg = _add_reg(event, "1001", "Alpha", "Large", 3, start_number=1301)
        db.session.add(M.StartNumber(event_id=event.id, registration_id=reg.id,
                                     start_no=9999))
        db.session.commit()

        rows, has_numbers = _collect_startlist_rows(event.id)
        assert has_numbers is True
        assert [r["start_no"] for r in rows] == [9999]


def test_tier3_meldeliste_without_numbers(app):
    with app.app_context():
        event, _ = _seed_event()
        _add_reg(event, "1001", "Alpha", "Small", 1, start_number=None)
        db.session.commit()

        rows, has_numbers = _collect_startlist_rows(event.id)
        assert has_numbers is False
        assert rows and rows[0]["start_no"] is None


def test_grouping_orders_blocks_and_filters(app):
    with app.app_context():
        event, _ = _seed_event()
        _add_reg(event, "1001", "L3a", "Large", 3, start_number=1302)
        _add_reg(event, "1002", "L3b", "Large", 3, start_number=1301)
        _add_reg(event, "1003", "S1a", "Small", 1, start_number=4101)
        db.session.commit()

        rows, _hn = _collect_startlist_rows(event.id)
        groups = _group_startlist_rows(rows)
        # S-M-I-L: Small/1 kommt vor Large/3
        assert [(g["category_code"], g["class_level"]) for g in groups] == [
            ("Small", 1), ("Large", 3)]
        large = groups[1]
        assert large["count"] == 2
        # innerhalb des Blocks nach Startnummer sortiert
        assert [r["start_no"] for r in large["rows"]] == [1301, 1302]

        # Einzelblock-Filter für Einzel-PDF
        only = _group_startlist_rows(rows, only_cat="Large", only_cls=3)
        assert len(only) == 1 and only[0]["count"] == 2


def test_zip_download_one_pdf_per_block(app):
    import io
    import zipfile
    with app.app_context():
        event, _ = _seed_event()
        _add_reg(event, "1001", "Shy’m", "Large", 3, start_number=1301)
        _add_reg(event, "1002", "Stellar", "Small", 1, start_number=4101)
        db.session.commit()
        client = app.test_client()
        r = client.get(f"/events/{event.id}/startlists.zip")
        assert r.status_code == 200
        assert r.headers["Content-Type"] == "application/zip"
        zf = zipfile.ZipFile(io.BytesIO(r.get_data()))
        names = zf.namelist()
        assert len(names) == 2  # ein PDF je Block
        for n in names:
            assert zf.read(n)[:4] == b"%PDF"
        # S-M-I-L: Small-Block zuerst
        assert names[0].startswith("01_") and "Small" in names[0]
