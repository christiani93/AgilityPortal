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
CHANGEOVER_SECONDS      = 1200   # 20 Min Umbau vor jedem Block
BRIEFING_MINUTES_PER_50 = 8      # 8 Min Briefing pro 50 Starter
BRIEFING_BLOCK_SIZE     = 50     # Briefing-Blöcke à 50 Starter
PREP_PAUSE_SECONDS      = 300    # 5 Min Pause bei nur 1 Briefing-Block

# Kategorie-Reihenfolge: Large → Intermediate → Medium → Small
CATEGORY_ORDER = ["Large", "Intermediate", "Medium", "Small"]
CATEGORY_SORT  = {cat: i for i, cat in enumerate(CATEGORY_ORDER)}

CATEGORY_LABELS = {
    "Large":        "Large (L)",
    "Intermediate": "Intermediate (I)",
    "Medium":       "Medium (M)",
    "Small":        "Small (S)",
}

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


def estimate_block(discipline: str, participant_count: int) -> dict:
    """Berechnet die geschätzte Dauer eines Lauf-Blocks."""
    secs             = SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65)
    run_seconds      = participant_count * secs
    blocks           = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    briefing_seconds = blocks * BRIEFING_MINUTES_PER_50 * 60
    prep_seconds     = PREP_PAUSE_SECONDS if blocks == 1 else 0
    total            = CHANGEOVER_SECONDS + briefing_seconds + prep_seconds + run_seconds
    return {
        "participants":   participant_count,
        "changeover_min": CHANGEOVER_SECONDS // 60,
        "briefing_min":   briefing_seconds // 60,
        "prep_min":       prep_seconds // 60,
        "run_min":        run_seconds // 60,
        "total_min":      total // 60,
        "total_seconds":  total,
    }


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict,
                     event_date_str: str, round_minutes: int = 0) -> dict:
    """
    Berechnet die Timeline pro Ring.

    blocks_by_ring  : {ring_name: [ScheduleBlock, ...]} (nach sort_index sortiert)
    ring_start_times: {"Ring 1": "08:00", ...}
    event_date_str  : "YYYY-MM-DD"
    round_minutes   : auf X Minuten runden (0 = kein Runden, 5 = 5-Min-Raster)

    Gibt zurück: {ring_name: [timeline_item, ...]}
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
            count = getattr(block, "_participant_count", 0)
            est   = estimate_block(block.discipline, count)

            start_dt = _round_to_minutes(current, round_minutes) if round_minutes else current
            end_dt   = start_dt + timedelta(seconds=est["total_seconds"])
            if round_minutes:
                end_dt = _round_to_minutes(end_dt, round_minutes)

            items.append({
                "block":      block,
                "start_time": start_dt.strftime("%H:%M"),
                "end_time":   end_dt.strftime("%H:%M"),
                **est,
            })
            current = end_dt if round_minutes else (current + timedelta(seconds=est["total_seconds"]))
        timeline[ring] = items
    return timeline


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
    """Sortierschlüssel für Kategorien: Large=0, Intermediate=1, Medium=2, Small=3."""
    return CATEGORY_SORT.get(category_code, 9)
