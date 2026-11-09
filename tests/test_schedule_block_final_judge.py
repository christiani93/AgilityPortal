"""Finale-Blöcke (block_type=='final') haben keinen EventRun-Link (fassen
mehrere Kategorien/Klassen zusammen), brauchen im Zeitplan aber trotzdem
einen Richter. ScheduleBlock.judge_id erlaubt das direkt am Block, getrennt
vom EventRun-basierten Richter der normalen Lauf-Blöcke."""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def _seed_event_with_judges():
    club = M.Club(vereinsnummer="V1", name="Club")
    admin = M.User(email="admin@test.ch", role="superadmin")
    judge_a = M.Judge(first_name="Ismael", last_name="Elpida")
    judge_b = M.Judge(first_name="Salas", last_name="Alejandro")
    db.session.add_all([club, admin, judge_a, judge_b])
    db.session.flush()

    event = M.Event(name="Zeitplan-Test", organiser_club_id=club.id)
    db.session.add(event)
    db.session.flush()
    db.session.commit()
    return event.id, admin.id, judge_a.id, judge_b.id


def test_judge_property_prefers_event_run_for_run_blocks(app):
    """Bei verknüpften 'run'-Blöcken bleibt der EventRun kanonisch, auch wenn
    (fälschlich) ein direct_judge_id gesetzt wäre."""
    with app.app_context():
        run = M.EventRun(run_type="agility", category="L", class_level=3)
        run.judge = M.Judge(first_name="Via", last_name="EventRun")
        block = M.ScheduleBlock(block_type="run")
        block.event_run = run
        block.judge_id = 999  # sollte ignoriert werden
        assert block.judge is run.judge


def test_judge_property_falls_back_to_direct_judge_without_event_run(app):
    with app.app_context():
        direct = M.Judge(first_name="Direkt", last_name="Final")
        block = M.ScheduleBlock(block_type="final")
        block.direct_judge = direct
        assert block.judge is direct


def test_add_final_block_with_judge(app):
    with app.app_context():
        event_id, admin_id, judge_a_id, judge_b_id = _seed_event_with_judges()
        db.session.add(M.EventJudge(event_id=event_id, judge_id=judge_a_id))
        db.session.commit()
        client = app.test_client()
        _login(client, admin_id)

        resp = client.post(f"/club/events/{event_id}/schedule/add", data={
            "block_type": "final",
            "ring": "Ring 1",
            "title": "Jumping Finale I/L BCCS",
            "judge_id": str(judge_a_id),
        })
        assert resp.status_code == 302
        block = db.session.execute(
            db.select(M.ScheduleBlock).filter_by(event_id=event_id, block_type="final")
        ).scalar_one()
        assert block.judge_id == judge_a_id
        assert block.judge.full_name == "Ismael Elpida"
        assert block.event_run_id is None


def test_set_judge_on_existing_final_block(app):
    with app.app_context():
        event_id, admin_id, judge_a_id, judge_b_id = _seed_event_with_judges()
        block = M.ScheduleBlock(event_id=event_id, ring="Ring 1", block_type="final",
                                title="Finale", sort_index=10)
        db.session.add(block)
        db.session.commit()
        block_id = block.id

        client = app.test_client()
        _login(client, admin_id)
        resp = client.post(
            f"/club/events/{event_id}/schedule/blocks/{block_id}/judge",
            data={"judge_id": str(judge_b_id)},
        )
        assert resp.status_code == 302
        block = db.session.get(M.ScheduleBlock, block_id)
        assert block.judge_id == judge_b_id

        # Wieder auf "kein Richter" zurücksetzen
        client.post(
            f"/club/events/{event_id}/schedule/blocks/{block_id}/judge",
            data={"judge_id": "0"},
        )
        block = db.session.get(M.ScheduleBlock, block_id)
        assert block.judge_id is None
