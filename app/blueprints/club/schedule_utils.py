"""
Zeitplan-Hilfsfunktionen für das AgilityPortal.
Adaptiert von AgilitySoftware/planner/schedule_planner.py
"""
from datetime import datetime, timedelta
import json

# ---------------------------------------------------------------------------
# Timing-Konstanten
# ---------------------------------------------------------------------------
SECONDS_PER_STARTER = {
    "agility": 65,
    "jumping": 60,
    "open":    65,
}
CHANGEOVER_SECONDS      = 1200   # 20 Min Umbau pro Disziplin-/Klassenwechsel
BRIEFING_MINUTES_PER_50 = 8      # 8 Min Briefing pro 50 Starter
BRIEFING_BLOCK_SIZE     = 50

CATEGORY_ORDER = ["Large", "Intermediate", "Medium", "Small"]
CATEGORY_SORT  = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}

DISCIPLINE_LABELS = {
    "agility": "Agility",
    "jumping": "Jumping",
    "open":    "Open",
}


def _round_to_minutes(dt: datetime, minutes: int) -> datetime:
    discard = timedelta(
        minutes=dt.minute % minutes,
        seconds=dt.second,
        microseconds=dt.microsecond,
    )
    dt -= discard
    if discard >= timedelta(minutes=minutes / 2):
        dt += timedelta(minutes=minutes)
    return dt


def _advance(current: datetime, seconds: int, round_minutes: int) -> tuple:
    """Gibt (start_str, end_str, new_current) zurück."""
    start = _round_to_minutes(current, round_minutes) if round_minutes else current
    end   = start + timedelta(seconds=seconds)
    if round_minutes:
        end = _round_to_minutes(end, round_minutes)
    return start.strftime("%H:%M"), end.strftime("%H:%M"), end


def _briefing_seconds(participant_count: int) -> int:
    """8 Min pro 50 Starter."""
    blocks = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    return blocks * BRIEFING_MINUTES_PER_50 * 60


def _secs_per_starter(discipline: str, run_time_config: dict | None) -> int:
    """Sekunden pro Starter für eine Disziplin (Event-Konfiguration oder Default)."""
    cfg = run_time_config or SECONDS_PER_STARTER
    return cfg.get((discipline or "agility").lower(),
                   SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65))


def estimate_block(discipline: str, participant_count: int,
                   run_time_config: dict | None = None) -> dict:
    """Geschätzte Dauer eines Lauf-Blocks (inkl. Umbau-Anteil)."""
    secs        = _secs_per_starter(discipline, run_time_config)
    run_seconds = participant_count * secs
    brief_secs  = _briefing_seconds(participant_count)
    total       = CHANGEOVER_SECONDS + brief_secs + run_seconds
    return {
        "participants":   participant_count,
        "changeover_sec": CHANGEOVER_SECONDS,
        "briefing_sec":   brief_secs,
        "run_sec":        run_seconds,
        "changeover_min": CHANGEOVER_SECONDS // 60,
        "briefing_min":   brief_secs // 60,
        "run_min":        run_seconds // 60,
        "total_min":      total // 60,
        "total_seconds":  total,
    }


def _group_key(block) -> tuple:
    """Gruppierschlüssel: gleiche Disziplin + gleiche Klasse = eine Gruppe."""
    return ((block.discipline or "").lower(), block.class_level or 0)


def _split_into_groups(sorted_blocks: list) -> list:
    """
    Teilt die Block-Liste in Gruppen auf.

    Aufeinanderfolgende Lauf-Blöcke mit gleicher Disziplin UND gleicher Klasse
    bilden eine Gruppe (ein Umbau, ein gemeinsames Briefing, Läufe in Folge).
    Bei Disziplin- oder Klassenwechsel beginnt eine neue Gruppe (→ neuer Umbau).
    Rangverkündigungen unterbrechen immer und stehen als Einzel-Element dazwischen.

    Rückgabe: Liste von (typ, inhalt)
      ('run_group', [block, ...])
      ('rank',      block)
    """
    groups      = []
    current_grp = []
    current_key = None

    for block in sorted_blocks:
        if getattr(block, "block_type", "run") == "rank_announcement":
            if current_grp:
                groups.append(("run_group", current_grp))
                current_grp = []
                current_key = None
            groups.append(("rank", block))
        else:
            key = _group_key(block)
            if current_key is not None and key != current_key:
                # Disziplin oder Klasse gewechselt → neue Gruppe
                groups.append(("run_group", current_grp))
                current_grp = []
            current_grp.append(block)
            current_key = key

    if current_grp:
        groups.append(("run_group", current_grp))

    return groups


def _briefing_label(run_group: list) -> str:
    """
    Beschriftung für das gemeinsame Briefing einer Gruppe.
    Beispiel: 'Briefing Agility Kl.1'
    """
    b    = run_group[0]
    disc = DISCIPLINE_LABELS.get((b.discipline or "").lower(), b.discipline or "")
    kl   = b.class_level or ""
    return f"Briefing {disc} Kl.{kl}"


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict,
                     event_date_str: str, round_minutes: int = 0,
                     run_time_config: dict | None = None) -> dict:
    """
    Timeline für den Zeitplan-Editor (ein Item pro Block).
    Gruppenmodell: Umbau + Briefing (gesamt) + Läufe in Folge.
    Rangverkündigungen sind informative Marker ohne Zeitverbrauch.
    """
    timeline = {}
    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items  = []
        groups = _split_into_groups(sorted(blocks, key=lambda b: b.sort_index))

        for gtype, content in groups:
            if gtype == "rank":
                t  = _round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "block":          content,
                    "start_time":     ts,
                    "end_time":       ts,
                    "participants":   0,
                    "total_min":      0,
                    "changeover_min": 0,
                    "briefing_min":   0,
                    "run_min":        0,
                })
            else:
                run_group    = content
                total_count  = sum(getattr(b, "_participant_count", 0) for b in run_group)
                brief_s      = _briefing_seconds(total_count)

                # Umbau (einmalig für die Gruppe)
                co_start = _round_to_minutes(current, round_minutes) if round_minutes else current
                current  = co_start + timedelta(seconds=CHANGEOVER_SECONDS)
                if round_minutes:
                    current = _round_to_minutes(current, round_minutes)

                # Gemeinsames Briefing
                _bs, briefing_end_str, current = _advance(current, brief_s, round_minutes)

                # Läufe in Folge
                run_times = {}
                for b in run_group:
                    count = getattr(b, "_participant_count", 0)
                    secs  = _secs_per_starter(b.discipline, run_time_config)
                    run_s = max(count * secs, 60)
                    s, e, current = _advance(current, run_s, round_minutes)
                    run_times[b.id] = (s, e)

                # Ein Item pro Block
                first = True
                for b in run_group:
                    count  = getattr(b, "_participant_count", 0)
                    secs   = _secs_per_starter(b.discipline, run_time_config)
                    run_s  = count * secs
                    _, r_end = run_times[b.id]

                    items.append({
                        "block":          b,
                        "start_time":     co_start.strftime("%H:%M") if first else briefing_end_str,
                        "end_time":       r_end,
                        "participants":   count,
                        "changeover_min": CHANGEOVER_SECONDS // 60 if first else 0,
                        "briefing_min":   brief_s // 60 if first else 0,
                        "run_min":        run_s // 60,
                        "total_min":      (
                            (CHANGEOVER_SECONDS + brief_s if first else 0) + run_s
                        ) // 60,
                    })
                    first = False

        timeline[ring] = items
    return timeline


def compute_detailed_segments(blocks_by_ring: dict, ring_start_times: dict,
                               event_date_str: str, round_minutes: int = 5,
                               run_time_config: dict | None = None) -> dict:
    """
    Detaillierte Segment-Timeline für die Teilnehmer-Ansicht.

    Gruppenmodell (Disziplin + Klasse):
      Umbau
      Briefing [Disziplin] Kl.[X]   (ein gemeinsames Briefing für alle Kategorien)
      Lauf Large Kl.[X]
      Lauf Intermediate Kl.[X]
      Lauf Medium Kl.[X]
      Lauf Small Kl.[X]

    Bei Disziplin- oder Klassenwechsel: neuer Umbau + neues Briefing.
    Rangverkündigung: informativer Marker, kein Umbau, kein Zeitverbrauch.

    Briefing end_time = Start des nächsten Briefings (Kurspazier-Fenster).
    """
    segments_by_ring = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items  = []
        groups = _split_into_groups(sorted(blocks, key=lambda b: b.sort_index))

        briefing_item_indices = []   # Indizes aller Briefing-Items (für Fenster-Korrektur)

        for gtype, content in groups:
            if gtype == "rank":
                t  = _round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                label = (getattr(content, "_display_title", None)
                         or content.title or "Rangverkündigung")
                items.append({
                    "segment":    "rank_announcement",
                    "label":      label,
                    "block":      content,
                    "start_time": ts,
                    "end_time":   ts,
                    "participants": 0,
                })

            else:
                run_group   = content
                total_count = sum(getattr(b, "_participant_count", 0) for b in run_group)
                brief_s     = _briefing_seconds(total_count)

                # ── Umbau ─────────────────────────────────────────────────
                s, e, current = _advance(current, CHANGEOVER_SECONDS, round_minutes)
                items.append({
                    "segment":    "changeover",
                    "label":      "Umbau",
                    "block":      run_group[0],
                    "start_time": s,
                    "end_time":   e,
                    "participants": 0,
                })

                # ── Gemeinsames Briefing für die Gruppe ───────────────────
                s, e, current = _advance(current, brief_s, round_minutes)
                briefing_item_indices.append(len(items))
                items.append({
                    "segment":    "briefing",
                    "label":      _briefing_label(run_group),
                    "block":      run_group[0],
                    "start_time": s,
                    "end_time":   e,   # wird unten auf nächstes Briefing ausgedehnt
                    "participants": total_count,
                })

                # ── Läufe in Folge (alle Kategorien der Gruppe) ───────────
                for b in run_group:
                    title  = getattr(b, "_display_title", None) or b.title or ""
                    count  = getattr(b, "_participant_count", 0)
                    secs_s = _secs_per_starter(b.discipline, run_time_config)
                    run_s  = max(count * secs_s, 60)
                    s, e, current = _advance(current, run_s, round_minutes)
                    items.append({
                        "segment":    "run",
                        "label":      title,
                        "block":      b,
                        "start_time": s,
                        "end_time":   e,
                        "participants": count,
                    })

        # ── Briefing-Fenster: end_time = Start nächstes Briefing ──────────
        # Teilnehmer sehen den gesamten Zeitraum, den sie zum Kursspazieren haben.
        for j, idx in enumerate(briefing_item_indices):
            if j + 1 < len(briefing_item_indices):
                # Bis zum Start des nächsten Briefings
                items[idx]["end_time"] = items[briefing_item_indices[j + 1]]["start_time"]
            else:
                # Letztes Briefing: bis zum Start des ersten Laufs dieser Gruppe
                first_run = next(
                    (it for it in items[idx + 1:] if it["segment"] == "run"), None
                )
                if first_run:
                    items[idx]["end_time"] = first_run["start_time"]

        segments_by_ring[ring] = items
    return segments_by_ring


def parse_ring_start_times(json_str: str) -> dict:
    if not json_str:
        return {}
    try:
        return json.loads(json_str)
    except Exception:
        return {}


def ring_names(ring_count: int) -> list:
    return [f"Ring {i}" for i in range(1, max(1, ring_count or 1) + 1)]


def auto_title(discipline: str, category_code: str, class_level: int) -> str:
    disc = DISCIPLINE_LABELS.get((discipline or "").lower(), discipline or "")
    cat  = category_code or ""
    return f"{disc} {cat} Kl. {class_level}"


def sort_key_category(category_code: str) -> int:
    return CATEGORY_SORT.get(category_code, 9)
