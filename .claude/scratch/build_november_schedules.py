"""Einmal-Skript: baut die Zeitplaene fuer die drei November-Events (33, 34, 35)
exakt nach den vom Veranstalter bereitgestellten Zeitplan-PDFs
(20.11/21.11/22.11, Ordner "Zeitnehmung Braunschweiler/AgilityEvents").

Faehrt mit DRY_RUN=True zuerst nur eine Vorschau (kein Commit), dann mit
DRY_RUN=False fuer den echten Schreibvorgang.
"""
import json
import os
import sys

DRY_RUN = os.environ.get("DRY_RUN", "1") == "1"

from wsgi import app
from app.extensions import db
from app import models as M
from app.services.schedule_service import link_block_to_run


def get_or_create_judge(first, last):
    j = M.Judge.query.filter_by(first_name=first, last_name=last).first()
    if not j:
        j = M.Judge(first_name=first, last_name=last)
        db.session.add(j)
        db.session.flush()
        print(f"  [NEU] Judge {first} {last} (id={j.id})")
    else:
        print(f"  [OK]  Judge {first} {last} (id={j.id}) existiert bereits")
    return j


def ensure_present(event_id, judge):
    exists = M.EventJudge.query.filter_by(event_id=event_id, judge_id=judge.id).first()
    if not exists:
        db.session.add(M.EventJudge(event_id=event_id, judge_id=judge.id))
        print(f"  [NEU] EventJudge event={event_id} judge={judge.full_name}")


class RingBuilder:
    """Sammelt ScheduleBlocks fuer EIN Ring eines Events in Reihenfolge."""

    def __init__(self, event_id, ring="Ring 1"):
        self.event_id = event_id
        self.ring = ring
        self.idx = 0
        self.created_runs = 0
        self.created_ranks = 0
        self.created_finals = 0

    def _next_idx(self):
        self.idx += 10
        return self.idx

    def run_block(self, run_type, category_letter, class_level, judge):
        category_code = {"S": "Small", "M": "Medium", "I": "Intermediate", "L": "Large"}[category_letter]
        existing = M.ScheduleBlock.query.filter_by(
            event_id=self.event_id, ring=self.ring, block_type="run",
            discipline=run_type, category_code=category_code, class_level=class_level,
        ).first()
        if existing:
            print(f"    [OK]  Block existiert schon: {run_type} {category_code} Kl.{class_level}")
            return existing
        block = M.ScheduleBlock(
            event_id=self.event_id, ring=self.ring, block_type="run",
            discipline=run_type, category_code=category_code, class_level=class_level,
            sort_index=self._next_idx(),
        )
        db.session.add(block)
        db.session.flush()
        run = link_block_to_run(block)
        if run is not None:
            run.judge_id = judge.id if judge else None
        self.created_runs += 1
        print(f"    [NEU] {run_type} {category_code} Kl.{class_level} - Richter {judge.full_name if judge else '-'}")
        return block

    def rank_block(self, title, duration_minutes=None):
        block = M.ScheduleBlock(
            event_id=self.event_id, ring=self.ring, block_type="rank_announcement",
            title=title, duration_minutes=duration_minutes,
            sort_index=self._next_idx(),
        )
        db.session.add(block)
        self.created_ranks += 1
        print(f"    [NEU] Rangverkuendigung/Ansage: {title}")
        return block

    def final_block(self, title, judge, participant_count):
        block = M.ScheduleBlock(
            event_id=self.event_id, ring=self.ring, block_type="final",
            title=title, judge_id=(judge.id if judge else None),
            participant_count_override=participant_count,
            sort_index=self._next_idx(),
        )
        db.session.add(block)
        self.created_finals += 1
        print(f"    [NEU] Final-Block: {title} - Richter {judge.full_name if judge else '-'} - {participant_count} Starter")
        return block


def set_ring_config(event_id, start_time, grossring):
    event = db.session.get(M.Event, event_id)
    event.ring_count = 1
    event.ring_start_times = json.dumps({"Ring 1": start_time})
    event.grossring_rings = json.dumps(["Ring 1"]) if grossring else None
    print(f"  Event {event_id}: ring_count=1, start={start_time}, grossring={grossring}")


with app.app_context():
    print("=== Richter ===")
    ismael = get_or_create_judge("Ismael", "Elpida")
    salas = get_or_create_judge("Salas", "Alejandro")
    db.session.flush()

    print("=== Anwesenheit (EventJudge) ===")
    ensure_present(33, salas)
    ensure_present(34, ismael)
    ensure_present(34, salas)
    ensure_present(35, ismael)
    ensure_present(35, salas)

    print("=== Ring-Konfiguration ===")
    set_ring_config(33, "16:00", grossring=False)
    set_ring_config(34, "07:30", grossring=True)
    set_ring_config(35, "07:30", grossring=True)

    # ------------------------------------------------------------------
    # Event 33: Abendmeeting 20.11.2026 - S/M/I/L, EIN Richter (Salas)
    # ------------------------------------------------------------------
    print("=== Event 33 (20.11., Abendmeeting) ===")
    r33 = RingBuilder(33)
    for cat in ("S", "M", "I", "L"):
        r33.run_block("jumping", cat, 1, salas)
    for cat in ("S", "M", "I", "L"):
        r33.run_block("jumping", cat, 2, salas)
    for cat in ("S", "M", "I", "L"):
        r33.run_block("agility", cat, 1, salas)
    for cat in ("S", "M", "I", "L"):
        r33.run_block("agility", cat, 2, salas)
    r33.rank_block("Rangverkündigung")
    for cat in ("S", "M", "I", "L"):
        r33.run_block("agility", cat, 3, salas)
    for cat in ("S", "M", "I", "L"):
        r33.run_block("jumping", cat, 3, salas)
    r33.rank_block("Rangverkündigung")

    # ------------------------------------------------------------------
    # Event 34: BCCS SM 21.11.2026 - nur I/L, Richter wechseln
    # ------------------------------------------------------------------
    print("=== Event 34 (21.11., BCCS SM Sa) ===")
    r34 = RingBuilder(34)
    for cat in ("I", "L"):
        r34.run_block("agility", cat, 1, ismael)
    for cat in ("I", "L"):
        r34.run_block("jumping", cat, 1, salas)
    r34.rank_block("Rangverkündigung")
    for cat in ("I", "L"):
        r34.run_block("jumping", cat, 2, ismael)
    for cat in ("I", "L"):
        r34.run_block("agility", cat, 2, salas)
    r34.rank_block("Rangverkündigung")
    for cat in ("I", "L"):
        r34.run_block("agility", cat, 3, ismael)
    for cat in ("I", "L"):
        r34.run_block("jumping", cat, 3, salas)
    r34.rank_block("Rangverkündigung")
    r34.rank_block("Bekanntgabe der Finalisten", duration_minutes=45)
    r34.final_block("Jumping Finale I/L BCCS", ismael, 34)
    r34.final_block("Agility Finale I/L BCCS", salas, 34)
    r34.rank_block("Rangverkündigung")

    # ------------------------------------------------------------------
    # Event 35: BCCS Nachwuchs 22.11.2026 - nur I/L, Final 1+2 gemischt
    # ------------------------------------------------------------------
    print("=== Event 35 (22.11., BCCS Nachwuchs So) ===")
    r35 = RingBuilder(35)
    for cat in ("I", "L"):
        r35.run_block("agility", cat, 3, salas)
    for cat in ("I", "L"):
        r35.run_block("jumping", cat, 3, ismael)
    r35.rank_block("Rangverkündigung")
    for cat in ("I", "L"):
        r35.run_block("jumping", cat, 2, salas)
    for cat in ("I", "L"):
        r35.run_block("agility", cat, 2, ismael)
    r35.rank_block("Rangverkündigung")
    for cat in ("I", "L"):
        r35.run_block("agility", cat, 1, salas)
    for cat in ("I", "L"):
        r35.run_block("jumping", cat, 1, ismael)
    r35.rank_block("Rangverkündigung")
    r35.rank_block("Bekanntgabe der Finalisten", duration_minutes=70)
    r35.final_block("Jumping Finale Nachwuchs I/L", salas, 17)
    r35.final_block("Agility Finale Nachwuchs I/L", ismael, 17)
    r35.rank_block("Rangverkündigung")

    print("=== Zusammenfassung ===")
    for label, r in (("33", r33), ("34", r34), ("35", r35)):
        print(f"  Event {label}: {r.created_runs} Lauf-Bloecke, {r.created_ranks} Rang/Ansage-Bloecke, {r.created_finals} Final-Bloecke")

    if DRY_RUN:
        print("\nDRY RUN - keine Aenderungen gespeichert (rollback).")
        db.session.rollback()
    else:
        db.session.commit()
        print("\nCOMMIT - Aenderungen gespeichert.")
