"""Regression: Ergebnis-Klassen müssen nach Kategorie L→I→M→S erscheinen,
nicht alphabetisch nach category_code (I-L-M-S). Siehe _result_class_order_key."""

from app.extensions import db
from app.models import Event, ResultImport, Result, EventFinalist


def _add_result(import_id, event_id, category_full, rank):
    db.session.add(Result(
        result_import_id=import_id,
        event_id=event_id,
        ring="Ring 1",
        discipline="Agility",
        category_code=category_full,
        class_level=1,
        rank=rank,
        dog_name=f"Hund {category_full}",
        handler_name="Führer",
    ))


def test_live_json_category_order_is_lims(app):
    with app.app_context():
        event = Event(name="Order Event", status="open")
        db.session.add(event)
        db.session.commit()

        imp = ResultImport(event_id=event.id, schema="resultexport.v1", final=False)
        db.session.add(imp)
        db.session.commit()

        # Bewusst verwürfelt einfügen (alphabetisch wäre Intermediate, Large, Medium, Small)
        for cat in ("Small", "Medium", "Large", "Intermediate"):
            _add_result(imp.id, event.id, cat, rank=1)
        db.session.commit()

        client = app.test_client()
        resp = client.get(f"/club/api/events/{event.id}/live.json")
        assert resp.status_code == 200

        cats = [rc["category_code"] for rc in resp.get_json()["result_classes"]]
        assert cats == ["Large", "Intermediate", "Medium", "Small"], cats


def test_live_json_bccs_sm_without_result_import_does_not_crash(app):
    """Regression: UnboundLocalError('groupby') auf /club/api/events/<id>/live.json,
    wenn ein BCCS-SM-Event Finalisten hat, aber noch KEIN ResultImport existiert
    (Finalisten werden vor dem ersten Ergebnis-Import gesetzt). `groupby` wurde nur
    innerhalb des `if latest_import:`-Blocks importiert, der BCCS-SM-Block darunter
    nutzte es aber unabhängig davon erneut."""
    with app.app_context():
        event = Event(name="BCCS Event", status="open", type="bccs_sm")
        db.session.add(event)
        db.session.commit()

        db.session.add(EventFinalist(
            event_id=event.id, license="CH-1", dog_name="Rex",
            handler_name="Muster", source="agility", category="Intermediate",
            position=1,
        ))
        db.session.commit()

        client = app.test_client()
        resp = client.get(f"/club/api/events/{event.id}/live.json")
        assert resp.status_code == 200
        assert resp.get_json()["bccs_result_classes"] == []
