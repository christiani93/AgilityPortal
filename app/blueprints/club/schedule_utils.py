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


def estimate_block(discipline: str, participant_count: int) -> dict:
    """Berechnet die geschätzte Dauer eines Lauf-Blocks."""
    secs = SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65)
    run_seconds      = participant_count * secs
    blocks           = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    briefing_seconds = blocks * BRIEFING_MINUTES_PER_50 * 60
    prep_seconds     = PREP_PAUSE_SECONDS if blocks == 1 else 0
    total            = CHANGEOVER_SECONDS + briefing_seconds + prep_seconds + run_seconds
    return {
        "participants":    participant_count,
        "changeover_min":  CHANGEOVER_SECONDS // 60,
        "briefing_min":    briefing_seconds // 60,
        "prep_min":        prep_seconds // 60,
        "run_min":         run_seconds // 60,
        "total_min":       total // 60,
        "total_seconds":   total,
    }


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict, event_date_str: str) -> dict:
    """
    Berechnet die Timeline pro Ring.

    blocks_by_ring   : dict {ring_name: [ScheduleBlock, ...]} (bereits nach sort_index sortiert)
    ring_start_times : dict {"Ring 1": "08:00", ...}
    event_date_str   : "YYYY-MM-DD"

    Gibt zurück: dict {ring_name: [timeline_item, ...]}
    Jedes timeline_item hat: block, start_time, end_time, participants,
    changeover_min, briefing_min, prep_min, run_min, total_min, total_seconds
    """
    timeline = {}
    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
        sorted_blocks = sorted(blocks, key=lambda b: b.sort_index)
        for block in sorted_blocks:
            count = getattr(block, "_participant_count", 0)
            est   = estimate_block(block.discipline, count)
            items.append({
                "block":      block,
                "start_time": current.strftime("%H:%M"),
                "end_time":   (current + timedelta(seconds=est["total_seconds"])).strftime("%H:%M"),
                **est,
            })
            current += timedelta(seconds=est["total_seconds"])
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
    """Generiert einen lessbaren Blocktitel."""
    disc = {"agility": "Agility", "jumping": "Jumping", "open": "Open"}.get(
        (discipline or "").lower(), discipline or ""
    )
    cat_short = {"Small": "S", "Medium": "M", "Intermediate": "I", "Large": "L"}.get(
        category_code, category_code
    )
    return f"{disc} {cat_short} Kl. {class_level}"
