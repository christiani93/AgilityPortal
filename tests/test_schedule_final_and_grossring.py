"""Zeitplan: Finalblock (fixe Berechnung aus Finalteilnehmern) + Grossring-Parsing."""
from types import SimpleNamespace

from app.extensions import db
from app import models as M
from app.blueprints.club.schedule_utils import (
    _split_into_groups,
    compute_detailed_segments,
    compute_timeline,
    final_participant_total,
    parse_final_participants,
    parse_grossring_rings,
)


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _block(**kw):
    kw.setdefault("block_type", "run")
    kw.setdefault("discipline", "agility")
    kw.setdefault("category_code", "Large")
    kw.setdefault("class_level", 1)
    kw.setdefault("sort_index", 0)
    kw.setdefault("title", None)
    kw.setdefault("_display_title", kw.get("title"))
    kw.setdefault("_participant_count", 0)
    kw.setdefault("skip_changeover", False)
    kw.setdefault("skip_briefing", False)
    kw.setdefault("force_new_group", False)
    kw.setdefault("id", kw["sort_index"])
    return SimpleNamespace(**kw)


# ── Parser ─────────────────────────────────────────────────────────────────
def test_parse_grossring_rings():
    assert parse_grossring_rings('["Ring 3"]') == {"Ring 3"}
    assert parse_grossring_rings(None) == set()
    assert parse_grossring_rings("kaputt") == set()
    assert parse_grossring_rings('{"a": 1}') == set()  # kein list → leer


def test_parse_final_participants_and_total():
    js = '{"Large": 32, "Intermediate": 16, "Medium": 16, "Small": 16}'
    assert parse_final_participants(js) == {
        "Large": 32, "Intermediate": 16, "Medium": 16, "Small": 16}
    assert final_participant_total(js) == 80
    assert final_participant_total(None) == 0
    assert parse_final_participants('{"Large": "x"}') == {}  # nicht-int übersprungen


# ── Grouping ───────────────────────────────────────────────────────────────
def test_final_block_is_standalone_group():
    blocks = [
        _block(sort_index=1, discipline="agility", class_level=3),
        _block(sort_index=2, block_type="final"),
        _block(sort_index=3, discipline="jumping", class_level=3),
    ]
    groups = _split_into_groups(blocks)
    types = [g[0] for g in groups]
    assert types == ["run_group", "final", "run_group"]


# ── Timing ─────────────────────────────────────────────────────────────────
def test_final_duration_from_count_times_final_secs():
    # 80 Finalstarter × 240 Sek. = 19200 Sek. = 320 Min. = 5h 20min
    final = _block(sort_index=1, block_type="final", _participant_count=80,
                   title="Finale HCS", _display_title="Finale HCS")
    segs = compute_detailed_segments(
        {"Ring 3": [final]}, {"Ring 3": "15:45"}, "2026-10-31", round_minutes=5,
    )["Ring 3"]
    assert len(segs) == 1
    seg = segs[0]
    assert seg["segment"] == "final"
    assert seg["label"] == "Finale HCS"
    assert seg["start_time"] == "15:45"
    assert seg["end_time"] == "21:05"
    assert seg["participants"] == 80


def test_final_respects_run_time_config_override():
    final = _block(sort_index=1, block_type="final", _participant_count=10)
    # 10 × 120 Sek. = 1200 Sek. = 20 Min.
    tl = compute_timeline(
        {"Ring 1": [final]}, {"Ring 1": "08:00"}, "2026-10-31",
        run_time_config={"final": 120},
    )["Ring 1"]
    assert tl[0]["start_time"] == "08:00"
    assert tl[0]["run_min"] == 20
    assert tl[0]["participants"] == 10


# ── Route-Smoke (fängt Jinja-/Route-Fehler bei Finalblock + Grossring) ───────
def _seed_club_admin():
    club = M.Club(vereinsnummer="V9", name="Club")
    admin = M.User(email="sched@test.ch", role="club_admin")
    db.session.add_all([club, admin])
    db.session.flush()
    admin.club_id = club.id
    db.session.commit()
    return club, admin


def test_club_schedule_renders_with_final_and_grossring(app):
    import json
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_admin()
        event = M.Event(name="HCS Sa", organiser_club_id=club.id, ring_count=3,
                        is_published=True,
                        grossring_rings=json.dumps(["Ring 3"]),
                        final_participants=json.dumps({"Large": 32, "Small": 16}))
        db.session.add(event)
        db.session.flush()
        db.session.add(M.ScheduleBlock(event_id=event.id, ring="Ring 3",
                                       block_type="final", title="Finale HCS",
                                       sort_index=1))
        db.session.commit()
        eid = event.id

        client = app.test_client()
        _login(client, admin.id)
        body = client.get(f"/club/events/{eid}/schedule").get_data(as_text=True)
        assert "Finale HCS" in body
        assert "Grossring" in body
        # 48 Finalstarter × 240 Sek. = 11520 Sek. = 192 Min.
        assert "192" in body


def test_schedule_add_final_block_route(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        club, admin = _seed_club_admin()
        event = M.Event(name="HCS", organiser_club_id=club.id, ring_count=3,
                        is_published=True)
        db.session.add(event)
        db.session.commit()
        eid = event.id

        client = app.test_client()
        _login(client, admin.id)
        client.post(f"/club/events/{eid}/schedule/add",
                    data={"block_type": "final", "ring": "Ring 3", "title": "Finale"})
        blocks = M.ScheduleBlock.query.filter_by(event_id=eid, block_type="final").all()
        assert len(blocks) == 1 and blocks[0].ring == "Ring 3"
