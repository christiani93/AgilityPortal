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
CHANGEOVER_SECONDS      = 1200   # 20 Min Umbau pro Gruppe
BRIEFING_MINUTES_PER_50 = 8      # 8 Min Briefing pro 50 Starter
BRIEFING_BLOCK_SIZE     = 50     # Briefing-Blöcke à 50 Starter
PREP_PAUSE_SECONDS      = 300    # 5 Min Pause bei nur 1 Briefing-Block (TKAMO-Modus)
RANK_ANNOUNCEMENT_DEFAULT_MINUTES = 5

# Kategorie-Reihenfolge: Large → Intermediate → Medium → Small
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
    """Berechnet die Briefing-Dauer für eine Klasse (8 Min pro 50 Starter)."""
    blocks = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    return blocks * BRIEFING_MINUTES_PER_50 * 60


def estimate_block(discipline: str, participant_count: int) -> dict:
    """Berechnet die geschätzte Dauer eines Lauf-Blocks (inkl. eigenem Umbau)."""
    secs             = SECONDS_PER_STARTER.get((discipline or "agility").lower(), 65)
    run_seconds      = participant_count * secs
    briefing_seconds = _briefing_seconds(participant_count)
    blocks           = (participant_count // BRIEFING_BLOCK_SIZE) + 1
    prep_seconds     = PREP_PAUSE_SECONDS if blocks == 1 else 0
    total            = CHANGEOVER_SECONDS + briefing_seconds + prep_seconds + run_seconds
    return {
        "participants":      participant_count,
        "changeover_sec":    CHANGEOVER_SECONDS,
        "briefing_sec":      briefing_seconds,
        "prep_sec":          prep_seconds,
        "run_sec":           run_seconds,
        "changeover_min":    CHANGEOVER_SECONDS // 60,
        "briefing_min":      briefing_seconds // 60,
        "prep_min":          prep_seconds // 60,
        "run_min":           run_seconds // 60,
        "total_min":         total // 60,
        "total_seconds":     total,
    }


def compute_timeline(blocks_by_ring: dict, ring_start_times: dict,
                     event_date_str: str, round_minutes: int = 0,
                     per_block_changeover: bool = False) -> dict:
    """
    Timeline (ein Item pro Block) für den Zeitplan-Editor.
    Standard: ein Umbau pro Gruppe aufeinanderfolgender Lauf-Blöcke.
    per_block_changeover=True: TKAMO-Modus, jeder Block erhält eigenen Umbau.
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

        i = 0
        while i < len(sorted_blocks):
            block = sorted_blocks[i]
            btype = getattr(block, "block_type", "run")

            if btype == "rank_announcement":
                # Rangverkündigung ist rein informativ, verbraucht keine Zeit
                t = _round_to_minutes(current, round_minutes) if round_minutes else current
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
                i += 1
            else:
                # Aufeinanderfolgende Lauf-Blöcke sammeln
                run_group = []
                while i < len(sorted_blocks) and getattr(sorted_blocks[i], "block_type", "run") == "run":
                    run_group.append(sorted_blocks[i])
                    i += 1

                if per_block_changeover:
                    # TKAMO: jeder Block bekommt eigenen Umbau+Briefing+Lauf
                    for b in run_group:
                        count = getattr(b, "_participant_count", 0)
                        est   = estimate_block(b.discipline or "agility", count)
                        s, e, current = _advance(current, est["total_seconds"], round_minutes)
                        items.append({"block": b, "start_time": s, "end_time": e, **est})
                else:
                    # Standard: ein Umbau, dann alle Briefings, dann alle Läufe
                    # Umbau einmalig auf den ersten Block "buchen"
                    co_start = _round_to_minutes(current, round_minutes) if round_minutes else current
                    current  = co_start + timedelta(seconds=CHANGEOVER_SECONDS)
                    if round_minutes:
                        current = _round_to_minutes(current, round_minutes)

                    # Briefing pro Block
                    briefing_ends = {}
                    for b in run_group:
                        count  = getattr(b, "_participant_count", 0)
                        brief_s = _briefing_seconds(count)
                        s, e, current = _advance(current, brief_s, round_minutes)
                        briefing_ends[b.id] = (s, e)

                    # Läufe pro Block
                    run_starts = {}
                    for b in run_group:
                        count = getattr(b, "_participant_count", 0)
                        secs  = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                        run_s = count * secs
                        s, e, current = _advance(current, run_s, round_minutes)
                        run_starts[b.id] = (s, e)

                    # Items zusammenbauen (ein Item pro Block, Start = Briefing-Start)
                    first = True
                    for b in run_group:
                        count  = getattr(b, "_participant_count", 0)
                        brief_s = _briefing_seconds(count)
                        secs   = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                        run_s  = count * secs

                        b_start, b_end = briefing_ends[b.id]
                        r_start, r_end = run_starts[b.id]

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
                               event_date_str: str, round_minutes: int = 5,
                               per_block_changeover: bool = False) -> dict:
    """
    Detaillierte Segment-Timeline für die Teilnehmer-Ansicht.

    Standard-Modus (per_block_changeover=False):
      Gruppe aufeinanderfolgender Lauf-Blöcke:
        → 1× Umbau (20 Min)
        → Briefing Klasse 1 (8 Min / 50 Starter)
        → Briefing Klasse 2 …
        → Lauf Klasse 1
        → Lauf Klasse 2 …

    TKAMO-Modus (per_block_changeover=True):
      Jeder Block: Umbau → Briefing → Lauf

    rank_announcement-Blöcke unterbrechen Gruppen und erhalten einen eigenen Eintrag.
    """
    segments_by_ring = {}

    for ring, blocks in blocks_by_ring.items():
        start_str = ring_start_times.get(ring, "08:00")
        try:
            current = datetime.strptime(f"{event_date_str} {start_str}", "%Y-%m-%d %H:%M")
        except Exception:
            current = datetime.now().replace(hour=8, minute=0, second=0, microsecond=0)

        items = []
        sorted_blocks = sorted(blocks, key=lambda b: b.sort_index)

        i = 0
        while i < len(sorted_blocks):
            block = sorted_blocks[i]
            btype = getattr(block, "block_type", "run")

            if btype == "rank_announcement":
                # Rangverkündigung ist rein informativ, verbraucht keine Zeit
                t  = _round_to_minutes(current, round_minutes) if round_minutes else current
                ts = t.strftime("%H:%M")
                items.append({
                    "segment":    "rank_announcement",
                    "label":      getattr(block, "_display_title", None) or block.title or "Rangverkündigung",
                    "block":      block,
                    "start_time": ts,
                    "end_time":   ts,
                    "participants": 0,
                })
                i += 1

            else:
                # Aufeinanderfolgende Lauf-Blöcke sammeln
                run_group = []
                while i < len(sorted_blocks) and getattr(sorted_blocks[i], "block_type", "run") == "run":
                    run_group.append(sorted_blocks[i])
                    i += 1

                if per_block_changeover:
                    # TKAMO: Umbau + Briefing + Lauf je Block
                    for b in run_group:
                        title  = getattr(b, "_display_title", None) or b.title or ""
                        count  = getattr(b, "_participant_count", 0)
                        secs_s = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                        run_s  = count * secs_s
                        brief_s = _briefing_seconds(count)
                        blocks_n = (count // BRIEFING_BLOCK_SIZE) + 1
                        prep_s  = PREP_PAUSE_SECONDS if blocks_n == 1 else 0

                        s, e, current = _advance(current, CHANGEOVER_SECONDS, round_minutes)
                        items.append({"segment": "changeover", "label": "Umbau",
                                      "block": b, "start_time": s, "end_time": e, "participants": 0})
                        if brief_s > 0:
                            s, e, current = _advance(current, brief_s, round_minutes)
                            items.append({"segment": "briefing", "label": f"Briefing – {title}",
                                          "block": b, "start_time": s, "end_time": e, "participants": count})
                        if prep_s > 0:
                            s, e, current = _advance(current, prep_s, round_minutes)
                            items.append({"segment": "prep", "label": "Prep-Pause",
                                          "block": b, "start_time": s, "end_time": e, "participants": 0})
                        if run_s > 0:
                            s, e, current = _advance(current, run_s, round_minutes)
                            items.append({"segment": "run", "label": title,
                                          "block": b, "start_time": s, "end_time": e, "participants": count})

                else:
                    # ── 1 Umbau für die ganze Gruppe ──────────────────────────
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
                    for b in run_group:
                        title  = getattr(b, "_display_title", None) or b.title or ""
                        count  = getattr(b, "_participant_count", 0)
                        brief_s = _briefing_seconds(count)
                        if brief_s > 0:
                            s, e, current = _advance(current, brief_s, round_minutes)
                            items.append({
                                "segment":    "briefing",
                                "label":      f"Briefing – {title}",
                                "block":      b,
                                "start_time": s,
                                "end_time":   e,
                                "participants": count,
                            })

                    # ── Alle Läufe in Folge ───────────────────────────────────
                    for b in run_group:
                        title  = getattr(b, "_display_title", None) or b.title or ""
                        count  = getattr(b, "_participant_count", 0)
                        secs_s = SECONDS_PER_STARTER.get((b.discipline or "agility").lower(), 65)
                        run_s  = count * secs_s
                        if run_s > 0 or count == 0:
                            s, e, current = _advance(
                                current, max(run_s, 60), round_minutes
                            )
                            items.append({
                                "segment":    "run",
                                "label":      title,
                                "block":      b,
                                "start_time": s,
                                "end_time":   e,
                                "participants": count,
                            })

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
