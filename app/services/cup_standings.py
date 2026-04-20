"""
Cup-Ranglisten-Berechnung.

Für jeden Cup werden aus den importierten Resultaten Punkte pro Hund und
Meeting berechnet. Die Gesamtrangliste ergibt sich aus der Summe der
besten N Meetings (oder aller Meetings, falls nicht konfiguriert).

Gruppierungsschlüssel pro Lauf:
  - category_code  (Small / Medium / Intermediate / Large)
  - class_level    (1 / 2 / 3) — nur wenn split_by_class=True
  - discipline     (agility / jumping / open) — nur für Punktevergabe pro Lauf,
                   Meeting-Score ist immer die Summe aller Läufe

Hundeidentifikation über (dog_name normiert, category_code) — da über
mehrere Events keine gemeinsame externe ID existiert.
"""
from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.models import Cup, CupEvent, Result


def _normalise_name(name: str) -> str:
    """Normalisiert einen Hundenamen für den Vergleich."""
    return re.sub(r'\s+', ' ', (name or '').strip().upper())


@dataclass
class MeetingScore:
    meeting_no: int
    event_name: str
    event_date: str
    points: int
    run_details: list[dict] = field(default_factory=list)  # [{discipline, rank, points}, ...]


@dataclass
class DogStanding:
    dog_name: str
    handler_name: str
    category_code: str
    class_level: int | None          # None wenn split_by_class=False
    meeting_scores: dict[int, MeetingScore] = field(default_factory=dict)  # meeting_no → score
    total_points: int = 0
    counted_meetings: int = 0

    @property
    def sort_key(self):
        return (-self.total_points, _normalise_name(self.dog_name))


def compute_standings(cup: Cup) -> dict[str, list[DogStanding]]:
    """
    Berechnet die Ranglisten für alle Gruppen eines Cups.

    Rückgabe: Dict  Gruppenname → sortierte Liste DogStanding
    Beispiel-Schlüssel: "Small – Klasse 1" oder "Small" (je nach Konfiguration)
    """
    if not cup.cup_events:
        return {}

    # dog_key → group_key → DogStanding
    standings: dict[str, dict[str, DogStanding]] = defaultdict(dict)

    for cup_event in cup.cup_events:
        event = cup_event.event
        if not event:
            continue

        # Alle finalen Resultate für dieses Event laden
        results = (
            Result.query
            .filter_by(event_id=event.id)
            .all()
        )
        if not results:
            continue

        event_date = event.date_from.strftime('%d.%m.%Y') if event.date_from else '–'

        # Resultate nach Gruppe und Hund gruppieren
        # Gruppe: (category_code, class_level_or_None)
        # Innerhalb Gruppe: Rangliste pro Lauf → Punkte
        # Für jeden Hund: Punkte über alle Läufe des Meetings summieren

        # Zuerst alle Gruppen sammeln, die in diesem Meeting vorkommen
        # Pro Gruppe: {dog_key: [points_per_run]}
        group_dog_runs: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))

        for r in results:
            cat = r.category_code or 'Unbekannt'
            cls = r.class_level if cup.split_by_class else None
            group_key = (cat, cls)

            dog_key = _normalise_name(r.dog_name or '')
            if not dog_key:
                continue

            pts = 0 if r.eliminated else cup.points_for_rank(r.rank)
            group_dog_runs[group_key][dog_key].append({
                'discipline': r.discipline or '–',
                'rank': r.rank,
                'eliminated': r.eliminated,
                'points': pts,
                'dog_name': r.dog_name or '',
                'handler_name': r.handler_name or '',
            })

        # Meeting-Scores berechnen
        for (cat, cls), dog_runs in group_dog_runs.items():
            group_label = _group_label(cat, cls)
            for dog_key, runs in dog_runs.items():
                meeting_pts = sum(r['points'] for r in runs)
                first = runs[0]

                if dog_key not in standings[group_label]:
                    standings[group_label][dog_key] = DogStanding(
                        dog_name=first['dog_name'],
                        handler_name=first['handler_name'],
                        category_code=cat,
                        class_level=cls,
                    )

                standings[group_label][dog_key].meeting_scores[cup_event.meeting_no] = MeetingScore(
                    meeting_no=cup_event.meeting_no,
                    event_name=event.name,
                    event_date=event_date,
                    points=meeting_pts,
                    run_details=runs,
                )

    # Gesamtpunkte berechnen (ggf. nur die besten N Meetings)
    result: dict[str, list[DogStanding]] = {}
    for group_label, dog_dict in standings.items():
        for dog_standing in dog_dict.values():
            scores = sorted(dog_standing.meeting_scores.values(), key=lambda s: s.points, reverse=True)
            if cup.count_best_meetings:
                scores = scores[:cup.count_best_meetings]
            dog_standing.total_points = sum(s.points for s in scores)
            dog_standing.counted_meetings = len(scores)
        result[group_label] = sorted(dog_dict.values(), key=lambda d: d.sort_key)

    return dict(sorted(result.items()))


def _group_label(category_code: str, class_level: int | None) -> str:
    labels = {
        'Small': 'Small',
        'Medium': 'Medium',
        'Intermediate': 'Intermediate',
        'Large': 'Large',
    }
    cat = labels.get(category_code, category_code)
    if class_level is not None:
        return f"{cat} – Klasse {class_level}"
    return cat
