"""Test: KO-Cup-Final-Import (Titelverteidiger-Automatik).

Software liefert `cup_finals.json` → Portal schreibt CupFinal/CupFinalParticipant/
CupFinalResult zum Cup (special_ruleset+season). Im Folgejahr findet
detect_title_defenders die Vorjahressieger (CupFinalResult final_rank==1).
"""
import io
import json
import zipfile

from app.extensions import db
from app.models import Cup, CupFinal, CupFinalParticipant, CupFinalResult
from app.services.exchange_service import (
    _import_cup_finals, import_result_export_zip, RESULT_EXPORT_SCHEMA,
)
from app.services.cup_qualification import detect_title_defenders


def _zip(payload):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("cup_finals.json", json.dumps(payload))
    buf.seek(0)
    return zipfile.ZipFile(buf)


def _payload(season=2026, ruleset="halloween_cup"):
    return {
        "event_external_id": "EV1",
        "cup_ruleset": ruleset,
        "season": season,
        "finals": [
            {"category_code": "Large", "class_level": None, "group_label": "Large",
             "is_published": False,
             "participants": [
                 {"license": "14554", "dog_name": "Youri", "handler_name": "Roland Marro",
                  "draw_number": 18, "seeding_rank": 1, "source": "run"},
                 {"license": "15709", "dog_name": "Feivel", "handler_name": "Nadine Gass",
                  "draw_number": 5, "seeding_rank": 2, "source": "run"}],
             "results": [{"license": "14554", "final_rank": 1},
                         {"license": "15709", "final_rank": 2}]},
        ],
    }


def _make_cup(season, ruleset="halloween_cup"):
    cup = Cup(name=f"HCS {season}", season=season, special_ruleset=ruleset)
    db.session.add(cup)
    db.session.flush()
    return cup


def test_import_writes_cupfinal_and_results(app):
    cup = _make_cup(2026)
    _import_cup_finals(_zip(_payload(2026)))
    db.session.commit()

    finals = CupFinal.query.filter_by(cup_id=cup.id).all()
    assert len(finals) == 1
    assert CupFinalParticipant.query.filter_by(final_id=finals[0].id).count() == 2
    winner = (CupFinalResult.query
              .filter_by(final_id=finals[0].id, final_rank=1).one())
    assert winner.participant.license_no == "14554"
    assert winner.participant.dog_name == "Youri"


def test_import_without_matching_cup_is_noop(app):
    # Kein Cup für die Saison angelegt → nichts geschrieben.
    _import_cup_finals(_zip(_payload(2099)))
    db.session.commit()
    assert CupFinal.query.count() == 0


def test_import_idempotent_replaces_not_duplicates(app):
    cup = _make_cup(2026)
    _import_cup_finals(_zip(_payload(2026)))
    db.session.commit()
    _import_cup_finals(_zip(_payload(2026)))
    db.session.commit()
    assert CupFinal.query.filter_by(cup_id=cup.id).count() == 1
    fid = CupFinal.query.filter_by(cup_id=cup.id).one().id
    assert CupFinalResult.query.filter_by(final_id=fid).count() == 2


def test_detect_title_defenders_finds_imported_winner(app):
    _make_cup(2026)
    _import_cup_finals(_zip(_payload(2026)))
    db.session.commit()

    cup_2027 = _make_cup(2027)
    db.session.commit()
    candidates = detect_title_defenders(cup_2027)
    # Erwartung: der Large-Sieger 14554 wird als Titelverteidiger-Kandidat gefunden.
    found = [c for c in candidates.values() if c.get("license_no") == "14554"]
    assert found, f"Vorjahressieger nicht erkannt: {candidates}"
    assert found[0]["category_code"] == "Large"


def _full_result_zip(cup_finals_payload):
    """Vollständiges resultexport.v1-ZIP (manifest + results.json + cup_finals.json)."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("manifest.json", json.dumps(
            {"schema": RESULT_EXPORT_SCHEMA, "generated_at": "2026-11-01T00:00:00Z"}))
        zf.writestr("results.json", json.dumps(
            {"event_external_id": "EV1", "classes": [], "documents": [], "final": True}))
        zf.writestr("cup_finals.json", json.dumps(cup_finals_payload))
    return buf.getvalue()


def test_full_import_result_export_reaches_cup_finals(app):
    """Der echte Eintrittspunkt import_result_export_zip verarbeitet cup_finals.json."""
    cup = _make_cup(2026)
    db.session.commit()
    import_result_export_zip(_full_result_zip(_payload(2026)))
    winner = (CupFinalResult.query
              .join(CupFinal, CupFinalResult.final_id == CupFinal.id)
              .filter(CupFinal.cup_id == cup.id, CupFinalResult.final_rank == 1)
              .one())
    assert winner.participant.license_no == "14554"
