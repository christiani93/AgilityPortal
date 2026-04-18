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
CHANGEOVER_SECONDS      = 1200   # 20 Min Umbau pro Gruppe
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


def estimate_block(discipline: str, participant_count: int) -> dict:
    """Geschätzte Dauer eines Lauf-Blocks (inkl. Umbau-Anteil)."""
    secs        = SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65)
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


def _split_into_groups(sorted_blocks: list) -> list:
    """
    Teilt die Block-Liste in Gruppen auf.
    Jede Gruppe ist eine Folge aufeinanderfolgender Lauf-Blöcke.
    Rangverkündigungen stehen als eigene Einzel-Elemente dazwischen.
    Rückgabe: Liste von (typ, inhalt)
      typ == 'run_group'  → inhalt = [block, ...]
      typ == 'rank'       → inhalt = block
    """
    groups = []
    run_group = []
    for block in sorted_blocks:
        if getattr(block, "block_type", "run") == "rank_announcement":
            if run_group:
                groups.append(("run_group", run_group))
                run_group = []
            groups.append(("rank", block))
        else:
            run_group.append(block)
    if run_group:
        groups.append(("run_group", run_group))
    return groups


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict,
                     event_date_str: str, round_minutes: int = 0) -> dict:
    """
    Timeline für den Zeitplan-Editor (ein Item pro Block).
    Gruppenmodell: ein Umbau pro Gruppe → alle Briefings → alle Läufe.
    Rangverkündigungen sind informative Marker ohne Zeitverbrauch.
    """
    timeline = {}
    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
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
                run_group = content

                # Umbau einmalig für die Gruppe (dem ersten Block zugeordnet)
                co_start = _round_to_minutes(current, round_minutes) if round_minutes else current
                current  = co_start + timedelta(seconds=CHANGEOVER_SECONDS)
                if round_minutes:
                    current = _round_to_minutes(current, round_minutes)

                # Alle Briefings in Folge
                briefing_times = {}
                for b in run_group:
                    count  = getattr(b, "_participant_count", 0)
                    brief_s = _briefing_seconds(count)
                    s, e, current = _advance(current, brief_s, round_minutes)
                    briefing_times[b.id] = (s, e)

                # Alle Läufe in Folge
                run_times = {}
                for b in run_group:
                    count = getattr(b, "_participant_count", 0)
                    secs  = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                    run_s = max(count * secs, 60)
                    s, e, current = _advance(current, run_s, round_minutes)
                    run_times[b.id] = (s, e)

                # Items: Start = Briefing-Start, Ende = Lauf-Ende
                first = True
                for b in run_group:
                    count   = getattr(b, "_participant_count", 0)
                    brief_s = _briefing_seconds(count)
                    secs    = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                    run_s   = count * secs

                    b_start, _ = briefing_times[b.id]
                    _, r_end   = run_times[b.id]

                    items.append({
                        "block":          b,
                        "start_time":     co_start.strftime("%H:%M") if first else b_start,
                        "end_time":       r_end,
                        "participants":   count,
                        "changeover_min": CHANGEOVER_SECONDS // 60 if first else 0,
                        "briefing_min":   brief_s // 60,
                        "run_min":        run_s // 60,
                        "total_min":      (
                            (CHANGEOVER_SECONDS if first else 0) + brief_s + run_s
                        ) // 60,
                    })
                    first = False

        timeline[ring] = items
    return timeline


def compute_detailed_segments(blocks_by_ring: dict, ring_start_times: dict,
                               event_date_str: str, round_minutes: int = 5) -> dict:
    """
    Detaillierte Segment-Timeline für die Teilnehmer-Ansicht.

    Gruppenmodell pro Gruppe aufeinanderfolgender Lauf-Blöcke:
      1× Umbau
      Briefing Kl.1  (end_time = Start nächstes Briefing)
      Briefing Kl.2  (end_time = Start nächstes Briefing)
      …
      Lauf Kl.1
      Lauf Kl.2
      …

    Rangverkündigung: informativer Marker, kein Umbau, kein Zeitverbrauch.
    Eine Rangverkündigung bricht die Gruppe: danach beginnt eine neue Gruppe
    mit eigenem Umbau.
    """
    segments_by_ring = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
        groups = _split_into_groups(sorted(blocks, key=lambda b: b.sort_index))

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
                run_group = content

                # ── 1× Umbau für die ganze Gruppe ────────────────────────
                s, e, current = _advance(current, CHANGEOVER_SECONDS, round_minutes)
                items.append({
                    "segment":    "changeover",
                    "label":      "Umbau",
                    "block":      run_group[0],
                    "start_time": s,
                    "end_time":   e,
                    "participants": 0,
                })

                # ── Alle Briefings in Folge ───────────────────────────────
                briefing_item_indices = []
                for b in run_group:
                    title  = getattr(b, "_display_title", None) or b.title or ""
                    count  = getattr(b, "_participant_count", 0)
                    brief_s = _briefing_seconds(count)
                    s, e, current = _advance(current, brief_s, round_minutes)
                    briefing_item_indices.append(len(items))
                    items.append({
                        "segment":    "briefing",
                        "label":      f"Briefing – {title}",
                        "block":      b,
                        "start_time": s,
                        "end_time":   e,   # wird unten korrigiert
                        "participants": count,
                    })

                # ── Alle Läufe in Folge ───────────────────────────────────
                for b in run_group:
                    title  = getattr(b, "_display_title", None) or b.title or ""
                    count  = getattr(b, "_participant_count", 0)
                    secs_s = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
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

                # ── Briefing-Fenster: end_time = Start nächstes Briefing ──
                # Letztes Briefing der Gruppe → bis zum ersten Lauf der Gruppe
                for j, idx in enumerate(briefing_item_indices):
                    if j + 1 < len(briefing_item_indices):
                        # Nächstes Briefing in der Gruppe
                        items[idx]["end_time"] = items[briefing_item_indices[j + 1]]["start_time"]
                    else:
                        # Letztes Briefing → bis zum Start des ersten Laufs der Gruppe
                        first_run = next(
                            (it for it in items[idx:] if it["segment"] == "run"), None
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
