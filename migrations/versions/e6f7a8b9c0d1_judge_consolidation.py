"""Richter-Konsolidierung: Block->Lauf-Referenz, tote Event-Richterfelder weg

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-10-05

Vereinheitlicht die Richter-Speicherung auf zwei Konzepte:
  (1) anwesend  -> EventJudge (unverändert)
  (2) richtet Lauf -> EventRun.judge_id (einzige Quelle)

Änderungen:
  * schedule_blocks.event_run_id (FK -> event_runs, ON DELETE SET NULL):
    Ersetzt den fragilen Composite-Key-Match (discipline+category+class_level,
    der is_final nicht unterscheiden konnte). Der Richter wird aus dem
    verknüpften Lauf abgeleitet.
  * Backfill: bestehende schedule_blocks mit passendem EventRun verknüpfen;
    block.judge_id -> run.judge_id übernehmen, wenn der Lauf noch keinen
    Richter hat (bewahrt das bisherige effektive Verhalten run.judge OR block.judge).
    Fehlt der passende Lauf, obwohl der Block einen Richter trägt, wird der Lauf
    angelegt, damit der Richter nicht verloren geht.
  * schedule_blocks.judge_id entfernt (Richter nur noch am Lauf).
  * events.judge_id / events.judge2_id entfernt (tot: nirgends gelesen/geschrieben).
"""
from datetime import datetime

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e6f7a8b9c0d1'
down_revision = 'd5e6f7a8b9c0'
branch_labels = None
depends_on = None


_CODE_MAP = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}


def _backfill(bind):
    """schedule_blocks mit EventRun verknüpfen und Richter auf den Lauf heben."""
    runs = bind.execute(sa.text(
        "SELECT id, event_id, run_type, category, class_level, judge_id, is_final "
        "FROM event_runs"
    )).mappings().all()

    # Nur reguläre Läufe (keine Finals) für die Zeitplan-Zuordnung indexieren.
    run_idx = {}
    for r in runs:
        if r["is_final"]:
            continue
        key = (r["event_id"], (r["run_type"] or "").lower(),
               _CODE_MAP.get(r["category"], r["category"]), r["class_level"])
        run_idx[key] = dict(r)

    blocks = bind.execute(sa.text(
        "SELECT id, event_id, discipline, category_code, class_level, judge_id "
        "FROM schedule_blocks WHERE block_type = 'run'"
    )).mappings().all()

    for b in blocks:
        key = (b["event_id"], (b["discipline"] or "").lower(),
               b["category_code"], b["class_level"])
        run = run_idx.get(key)

        if run is None:
            # Kein passender Lauf. Nur anlegen, wenn der Block einen Richter trägt
            # (sonst würde die reine Verknüpfung keinen Mehrwert bringen).
            if b["judge_id"] is None:
                continue
            category = {v: k for k, v in _CODE_MAP.items()}.get(
                b["category_code"], b["category_code"])
            run_type = (b["discipline"] or "").lower()   # EventRun-Konvention: lowercase
            bind.execute(sa.text(
                "INSERT INTO event_runs "
                "(event_id, run_type, category, class_level, is_final, judge_id, created_at) "
                "VALUES (:e, :rt, :cat, :cl, :fin, :j, :ts)"
            ), {"e": b["event_id"], "rt": run_type, "cat": category,
                "cl": b["class_level"], "fin": False, "j": b["judge_id"],
                "ts": datetime.utcnow()})
            new_id = bind.execute(sa.text(
                "SELECT id FROM event_runs WHERE event_id=:e AND run_type=:rt "
                "AND category=:cat AND class_level=:cl AND is_final=:fin"
            ), {"e": b["event_id"], "rt": run_type, "cat": category,
                "cl": b["class_level"], "fin": False}).scalar()
            run = {"id": new_id, "judge_id": b["judge_id"]}
            run_idx[key] = run
        else:
            # Richter nur übernehmen, wenn der Lauf noch keinen hat (run.judge gewinnt).
            if run["judge_id"] is None and b["judge_id"] is not None:
                bind.execute(sa.text(
                    "UPDATE event_runs SET judge_id=:j WHERE id=:id"
                ), {"j": b["judge_id"], "id": run["id"]})
                run["judge_id"] = b["judge_id"]

        bind.execute(sa.text(
            "UPDATE schedule_blocks SET event_run_id=:rid WHERE id=:bid"
        ), {"rid": run["id"], "bid": b["id"]})


def upgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    # 1) event_run_id + Index + FK anlegen
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('event_run_id', sa.Integer(), nullable=True))
        batch_op.create_index('ix_schedule_blocks_event_run_id', ['event_run_id'])
        batch_op.create_foreign_key(
            'fk_schedule_blocks_event_run', 'event_runs',
            ['event_run_id'], ['id'], ondelete='SET NULL')

    # 2) Daten übertragen
    _backfill(bind)

    # 3) schedule_blocks.judge_id entfernen (FK ist benannt: fk_schedule_blocks_judge)
    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        if dialect != 'sqlite':
            batch_op.drop_constraint('fk_schedule_blocks_judge', type_='foreignkey')
        batch_op.drop_column('judge_id')

    # 4) events.judge_id / judge2_id entfernen. Deren FKs sind unbenannt (inline im
    #    initial_schema) -> auf MySQL zur Laufzeit reflektieren und droppen.
    if dialect != 'sqlite':
        insp = sa.inspect(bind)
        for fk in insp.get_foreign_keys('events'):
            cols = set(fk.get('constrained_columns') or [])
            if cols & {'judge_id', 'judge2_id'} and fk.get('name'):
                op.drop_constraint(fk['name'], 'events', type_='foreignkey')
    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.drop_column('judge_id')
        batch_op.drop_column('judge2_id')


def downgrade():
    bind = op.get_bind()
    dialect = bind.dialect.name

    with op.batch_alter_table('events', schema=None) as batch_op:
        batch_op.add_column(sa.Column('judge_id', sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column('judge2_id', sa.Integer(), nullable=True))
        if dialect != 'sqlite':
            batch_op.create_foreign_key(
                'fk_events_judge', 'judges', ['judge_id'], ['id'])
            batch_op.create_foreign_key(
                'fk_events_judge2', 'judges', ['judge2_id'], ['id'])

    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('judge_id', sa.Integer(), nullable=True))
        if dialect != 'sqlite':
            batch_op.create_foreign_key(
                'fk_schedule_blocks_judge', 'judges', ['judge_id'], ['id'])

    # Richter aus dem verknüpften Lauf zurückschreiben, dann Verknüpfung entfernen.
    bind.execute(sa.text(
        "UPDATE schedule_blocks SET judge_id = ("
        "  SELECT er.judge_id FROM event_runs er WHERE er.id = schedule_blocks.event_run_id"
        ") WHERE event_run_id IS NOT NULL"
    ))

    with op.batch_alter_table('schedule_blocks', schema=None) as batch_op:
        if dialect != 'sqlite':
            batch_op.drop_constraint('fk_schedule_blocks_event_run', type_='foreignkey')
        batch_op.drop_index('ix_schedule_blocks_event_run_id')
        batch_op.drop_column('event_run_id')
