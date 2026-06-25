"""Test: Finalisten-Import (SKBS-SM ohne, BCCS-SM mit category/division)."""
import io
import json
import zipfile

from app.extensions import db
from app.models import Event, EventFinalist
from app.services.exchange_service import _import_finalists


def _zip_with_finalists(payload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("finalists.json", json.dumps(payload))
    buf.seek(0)
    return zipfile.ZipFile(buf)


def test_import_bccs_finalists_mit_category_division(app):
    ev = Event(name="BCCS-SM Test")
    db.session.add(ev)
    db.session.flush()

    zf = _zip_with_finalists({"veranstaltungsart": "BCCS-SM", "finalists": [
        {"license": "L0", "dog_name": "Movie", "handler_name": "HF0", "source": "agility",
         "from_class": 3, "quali_rank": 1, "category": "Large", "division": "sm"},
        {"license": "N1", "dog_name": "Nano", "handler_name": "HFN", "source": "jumping",
         "from_class": 1, "quali_rank": 2, "category": "Intermediate", "division": "nachwuchs"},
    ]})
    _import_finalists(zf, ev)
    db.session.commit()

    rows = {f.license: f for f in EventFinalist.query.filter_by(event_id=ev.id)}
    assert rows["L0"].category == "Large" and rows["L0"].division == "sm"
    assert rows["N1"].category == "Intermediate" and rows["N1"].division == "nachwuchs"
    assert rows["L0"].position == 1 and rows["N1"].position == 2


def test_import_skbs_finalists_ohne_category_division(app):
    ev = Event(name="SKBS-SM Test")
    db.session.add(ev)
    db.session.flush()

    zf = _zip_with_finalists({"veranstaltungsart": "SKBS-SM", "finalists": [
        {"license": "A", "dog_name": "Aaron", "handler_name": "HA", "source": "agility",
         "from_class": 3, "quali_rank": 1},
    ]})
    _import_finalists(zf, ev)
    db.session.commit()

    f = EventFinalist.query.filter_by(event_id=ev.id).one()
    assert f.category is None and f.division is None
    assert f.source == "agility" and f.from_class == 3


def test_import_finalists_idempotent(app):
    """Erneuter Import ersetzt die Liste statt zu duplizieren."""
    ev = Event(name="Re-Import")
    db.session.add(ev)
    db.session.flush()
    payload = {"finalists": [{"license": "X", "source": "agility", "category": "Large", "division": "sm"}]}
    _import_finalists(_zip_with_finalists(payload), ev)
    db.session.commit()
    _import_finalists(_zip_with_finalists(payload), ev)
    db.session.commit()
    assert EventFinalist.query.filter_by(event_id=ev.id).count() == 1
