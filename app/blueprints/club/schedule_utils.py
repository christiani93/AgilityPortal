"""
Zeitplan-Hilfsfunktionen für das AgilityPortal.
Adaptiert von AgilitySoftware/planner/schedule_planner.py
"""
from datetime import datetime, timedelta
import json

# ---------------------------------------------------------------------------
# Timing-Konstanten (identisch mit AgilitySoftware-Defaults)
# ---------------------------------------------------------------------------
SECONDS_PER_STARTER = {
    "agility": 65,
    "jumping": 60,
    "open":    65,
}
CHANGEOVER_SECONDS      = 1200   # 20 Min Umbau pro Klassen-/Laufwechsel
BRIEFING_MINUTES_PER_50 = 8      # 8 Min Briefing pro 50 Starter
BRIEFING_BLOCK_SIZE     = 50     # Briefing-Blöcke à 50 Starter

CATEGORY_ORDER = ["Large", "Intermediate", "Medium", "Small"]
CATEGORY_SORT  = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}

DISCIPLINE_LABELS = {
    "agility": "Agility",
    "jumping": "Jumping",
    "open":    "Open",
}


def _round_to_minutes(dt: datetime, minutes: int) -> datetime:
    """Rundet eine Zeit auf das nächste Vielfache von `minutes`."""
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
    """Briefing-Dauer: 8 Min pro 50 Starter."""
    blocks = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    return blocks * BRIEFING_MINUTES_PER_50 * 60


def estimate_block(discipline: str, participant_count: int) -> dict:
    """Geschätzte Dauer eines Lauf-Blocks inkl. Umbau und Briefing."""
    secs         = SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65)
    run_seconds  = participant_count * secs
    brief_secs   = _briefing_seconds(participant_count)
    total        = CHANGEOVER_SECONDS + brief_secs + run_seconds
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


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict,
                     event_date_str: str, round_minutes: int = 0) -> dict:
    """
    Timeline (ein Item pro Block) für den Zeitplan-Editor.
    Jeder Lauf-Block erhält eigenen Umbau + Briefing + Lauf.
    Rangverkündigungen sind rein informative Marker ohne Zeitverbrauch.
    """
    timeline = {}
    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
        for block in sorted(blocks, key=lambda b: b.sort_index):
            btype = getattr(block, "block_type", "run")
            count = getattr(block, "_participant_count", 0)

            if btype == "rank_announcement":
                # Informativer Marker – verbraucht keine Zeit
                t  = _round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "block":          block,
                    "start_time":     ts,
                    "end_time":       ts,
                    "participants":   0,
                    "total_min":      0,
                    "changeover_min": 0,
                    "briefing_min":   0,
                    "run_min":        0,
                })
            else:
                est = estimate_block(block.discipline or "agility", count)
                s, e, current = _advance(current, est["total_seconds"], round_minutes)
                items.append({"block": block, "start_time": s, "end_time": e, **est})

        timeline[ring] = items
    return timeline


def compute_detailed_segments(blocks_by_ring: dict, ring_start_times: dict,
                               event_date_str: str, round_minutes: int = 5) -> dict:
    """
    Detaillierte Segment-Timeline für die Teilnehmer-Ansicht.

    Pro Lauf-Block: Umbau → Briefing → Lauf
      (jeder Klassen-/Laufwechsel löst einen neuen Umbau aus)

    Briefing end_time = Start des nächsten Briefings (= Kurspazier-Fenster
      für die Teilnehmer, bis das nächste Briefing beginnt).

    Rangverkündigung: informativer Marker ohne Zeitverbrauch, kein Umbau.
    """
    segments_by_ring = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
        for block in sorted(blocks, key=lambda b: b.sort_index):
            btype = getattr(block, "block_type", "run")
            title = getattr(block, "_display_title", None) or block.title or ""
            count = getattr(block, "_participant_count", 0)

            if btype == "rank_announcement":
                # Informativer Marker – verbraucht keine Zeit, kein Umbau
                t  = _round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "segment":    "rank_announcement",
                    "label":      title or "Rangverkündigung",
                    "block":      block,
                    "start_time": ts,
                    "end_time":   ts,
                    "participants": 0,
                })

            else:
                secs_s  = SECONDS_PER_STARTER.get((block.discipline or "agility").lower(), 65)
                run_s   = count * secs_s
                brief_s = _briefing_seconds(count)

                # ── Umbau (jeder Klassen-/Laufwechsel) ───────────────────
                s, e, current = _advance(current, CHANGEOVER_SECONDS, round_minutes)
                items.append({
                    "segment":    "changeover",
                    "label":      "Umbau",
                    "block":      block,
                    "start_time": s,
                    "end_time":   e,
                    "participants": 0,
                })

                # ── Briefing ──────────────────────────────────────────────
                if brief_s > 0:
                    s, e, current = _advance(current, brief_s, round_minutes)
                    items.append({
                        "segment":    "briefing",
                        "label":      f"Briefing – {title}",
                        "block":      block,
                        "start_time": s,
                        "end_time":   e,   # wird unten auf nächstes Briefing ausgedehnt
                        "participants": count,
                    })

                # ── Lauf ──────────────────────────────────────────────────
                s, e, current = _advance(current, max(run_s, 60), round_minutes)
                items.append({
                    "segment":    "run",
                    "label":      title,
                    "block":      block,
                    "start_time": s,
                    "end_time":   e,
                    "participants": count,
                })

        # ── Briefing-Fenster ausdehnen: end_time = Start nächstes Briefing ──
        # Teilnehmer sehen: «Briefing ab HH:MM – du hast Zeit bis HH:MM»
        briefing_idx = [i for i, it in enumerate(items) if it["segment"] == "briefing"]
        for j, idx in enumerate(briefing_idx):
            if j + 1 < len(briefing_idx):
                # Bis zum Start des nächsten Briefings
                items[idx]["end_time"] = items[briefing_idx[j + 1]]["start_time"]
            else:
                # Letztes Briefing: bis zum Ende des letzten Laufs
                last_run = next(
                    (it for it in reversed(items) if it["segment"] == "run"), None
                )
                if last_run:
                    items[idx]["end_time"] = last_run["end_time"]

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
    """Generiert einen lesbaren Blocktitel mit vollständigem Kategorienamen."""
    disc = DISCIPLINE_LABELS.get((discipline or "").lower(), discipline or "")
    cat  = category_code or ""
    return f"{disc} {cat} Kl. {class_level}"


def sort_key_category(category_code: str) -> int:
    return CATEGORY_SORT.get(category_code, 9)
