"""Tests für die Cup-Saison-Ranglisten (WiMeSma-Fundament).

Deckt ab:
- Cup.points_for_rank / points_map (Punktetabelle, Top-N)
- Cup.counting_disciplines / discipline_counts (Agility zählt bei WiMeSma nicht)
- Cup.apply_wimesma_placeholder (Platzhalter, überschreibt nicht)
- compute_standings: Disziplinen-Filter, Summen, beste-N-Meetings
"""
from datetime import datetime

from app.extensions import db
from app.models import Cup, CupEvent, Event, ResultImport, Result
from app.services.cup_standings import compute_standings


# --------------------------------------------------------------------------
# Pure-Unit: Cup-Methoden (kein DB nötig)
# --------------------------------------------------------------------------

def test_points_for_rank_and_map():
    cup = Cup(name="x", season=2026, points_table='{"1": 20, "2": 17, "10": 1}')
    assert cup.points_map == {1: 20, 2: 17, 10: 1}
    assert cup.points_for_rank(1) == 20
    assert cup.points_for_rank(10) == 1
    assert cup.points_for_rank(11) == 0     # ausserhalb Top-N
    assert cup.points_for_rank(None) == 0


def test_points_table_leer_oder_ungueltig():
    assert Cup(name="x", season=2026).points_for_rank(1) == 0
    assert Cup(name="x", season=2026, points_table="kein json").points_map == {}


def test_counting_disciplines_und_filter():
    cup = Cup(name="x", season=2026, standings_disciplines='["open", "jumping"]')
    assert cup.counting_disciplines == {"open", "jumping"}
    assert cup.discipline_counts("Open") is True
    assert cup.discipline_counts("Jumping") is True
    assert cup.discipline_counts("Agility") is False
    # None-Konfig = alle zählen
    cup2 = Cup(name="y", season=2026)
    assert cup2.counting_disciplines is None
    assert cup2.discipline_counts("Agility") is True


def test_apply_wimesma_placeholder():
    cup = Cup(name="w", season=2026, special_ruleset="wimesma_cup")
    cup.apply_wimesma_placeholder()
    assert cup.points_for_rank(1) == 20
    assert cup.discipline_counts("Open") is True
    assert cup.discipline_counts("Agility") is False     # Agility zählt nicht
    # überschreibt bestehende Werte NICHT
    cup2 = Cup(name="w2", season=2026, special_ruleset="wimesma_cup",
               points_table='{"1": 99}')
    cup2.apply_wimesma_placeholder()
    assert cup2.points_for_rank(1) == 99


# --------------------------------------------------------------------------
# Integration: compute_standings
# --------------------------------------------------------------------------

def _result(ri, ev, **kw):
    base = dict(result_import_id=ri.id, event_id=ev.id, eliminated=False,
                category_code="Small", class_level=1)
    base.update(kw)
    return Result(**base)


def test_compute_standings_agility_zaehlt_nicht_und_summiert(app):
    cup = Cup(name="WiMeSma Test", season=2026,
              points_table='{"1": 20, "2": 17, "3": 15}',
              standings_disciplines='["open", "jumping"]',
              split_by_class=False)
    db.session.add(cup)
    db.session.flush()

    ev = Event(name="Meeting 1", starts_at=datetime(2026, 11, 15))
    db.session.add(ev)
    db.session.flush()
    db.session.add(CupEvent(cup_id=cup.id, event_id=ev.id, meeting_no=1))
    ri = ResultImport(event_id=ev.id, schema="test")
    db.session.add(ri)
    db.session.flush()

    db.session.add_all([
        _result(ri, ev, discipline="Open",    dog_name="A", handler_name="HA", rank=1),  # 20
        _result(ri, ev, discipline="Jumping", dog_name="A", handler_name="HA", rank=2),  # 17
        _result(ri, ev, discipline="Agility", dog_name="A", handler_name="HA", rank=1),  # NICHT zählen
        _result(ri, ev, discipline="Open",    dog_name="B", handler_name="HB", rank=2),  # 17
    ])
    db.session.commit()

    standings = compute_standings(cup)
    assert "Small" in standings
    rows = {s.dog_name: s for s in standings["Small"]}
    assert rows["A"].total_points == 37     # 20 + 17, Agility (20) ignoriert
    assert rows["B"].total_points == 17
    assert [s.dog_name for s in standings["Small"]] == ["A", "B"]


def test_compute_standings_beste_n_meetings(app):
    cup = Cup(name="BestN", season=2026,
              points_table='{"1": 20, "2": 10}',
              standings_disciplines='["open"]',
              count_best_meetings=1, split_by_class=False)
    db.session.add(cup)
    db.session.flush()

    for mno, (date, rank) in enumerate(
            [(datetime(2026, 11, 15), 1), (datetime(2026, 12, 12), 2)], start=1):
        ev = Event(name=f"M{mno}", starts_at=date)
        db.session.add(ev)
        db.session.flush()
        db.session.add(CupEvent(cup_id=cup.id, event_id=ev.id, meeting_no=mno))
        ri = ResultImport(event_id=ev.id, schema="t")
        db.session.add(ri)
        db.session.flush()
        db.session.add(_result(ri, ev, discipline="Open", dog_name="A",
                               handler_name="HA", rank=rank))
    db.session.commit()

    standings = compute_standings(cup)
    a = {s.dog_name: s for s in standings["Small"]}["A"]
    assert a.total_points == 20      # nur bestes Meeting (20), nicht 30
    assert a.counted_meetings == 1
