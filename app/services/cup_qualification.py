"""
Cup-Qualifikations-Service – Halloween Cup Schlüssel.

Qualifikations-Logik pro Lauf:
  - Plätze können pro Kategorie (Large / Intermediate / Medium / Small) variieren
  - split_by_class=True → Klasse 1 / 2 / 3 werden separat ausgewertet (Agility, Jumping)
  - split_by_class=False → alle Klassen fliessen in eine gemeinsame Rangliste (Tunnellauf)
  - Doppelqualifikation: bereits qualifizierte Teams werden übersprungen,
    das nächste noch nicht qualifizierte Team rückt nach

Auffüller-Lauf:
  - Füllt jede Gruppe auf die nächste 2er-Potenz auf (2, 4, 8, 16, …)
  - Verwendet den konfigurierten Auffüller-Lauf und überspringt Bereits-Qualifizierte

Manuelle Einträge (Titelverteidiger, Wildcards/Beste Verkleidung):
  - Werden separat eingetragen und beim Berechnen berücksichtigt
"""
from __future__ import annotations

import math
import re
from collections import defaultdict

from app.extensions import db
from app.models import Cup, CupFinal, CupFinalResult, CupQualificationRun, CupQualifiedTeam, Registration, Result


CATEGORIES = ["Large", "Intermediate", "Medium", "Small"]


def _normalise(name: str) -> str:
    return re.sub(r'\s+', ' ', (name or '').strip().upper())


def next_power_of_two(n: int) -> int:
    """Nächste 2er-Potenz >= n. Minimum 2."""
    if n <= 2:
        return 2
    return 2 ** math.ceil(math.log2(n))


def _group_key(category_code: str, class_level: int | None) -> str:
    labels = {'Small': 'Small', 'Medium': 'Medium', 'Intermediate': 'Intermediate', 'Large': 'Large'}
    cat = labels.get(category_code, category_code)
    if class_level:
        return f"{cat} – Klasse {class_level}"
    return cat


# ---------------------------------------------------------------------------
# Hauptfunktion: Qualifikation berechnen + in DB speichern
# ---------------------------------------------------------------------------

def run_qualification(cup: Cup) -> dict[str, list[CupQualifiedTeam]]:
    """
    Berechnet die Qualifikationsliste für alle Gruppen des Cups neu.
    Bestehende auto-generierte Einträge (run/fillup) werden ersetzt.
    Manuelle Einträge (title_defender/wildcard) bleiben erhalten.
    """
    # Schritt 1: Auto-Einträge löschen
    CupQualifiedTeam.query.filter(
        CupQualifiedTeam.cup_id == cup.id,
        CupQualifiedTeam.qualification_source.in_(
            [CupQualifiedTeam.SOURCE_RUN, CupQualifiedTeam.SOURCE_FILLUP]
        )
    ).delete(synchronize_session=False)
    db.session.flush()

    # Schritt 2: Manuelle Teams sammeln → als bereits qualifiziert markieren
    # qualified[group_key] = {normalised_dog_name, ...}
    qualified: dict[str, set[str]] = defaultdict(set)

    manual = CupQualifiedTeam.query.filter(
        CupQualifiedTeam.cup_id == cup.id,
        CupQualifiedTeam.qualification_source.in_(
            [CupQualifiedTeam.SOURCE_TITLE_DEFENDER, CupQualifiedTeam.SOURCE_WILDCARD]
        )
    ).all()
    for qt in manual:
        # Manuelle Teams zählen als "qualifiziert" für Doppelqualifikationsprüfung
        # → ohne Klassen-Suffix, da sie in der Finalrangliste ohne Klasse stehen
        key = _group_key(qt.category_code, None)  # immer ohne Klasse für Doppelcheck
        qualified[key].add(_normalise(qt.dog_name))

    # Schritt 3: Qualifikationsläufe (nicht Auffüller) abarbeiten
    qual_runs = [qr for qr in cup.qualification_runs if not qr.is_fillup]
    fillup_runs = [qr for qr in cup.qualification_runs if qr.is_fillup]

    new_entries: list[CupQualifiedTeam] = []

    for qr in qual_runs:
        _process_run(cup, qr, qualified, new_entries)

    for entry in new_entries:
        db.session.add(entry)
    db.session.flush()
    new_entries_at_flush = list(new_entries)

    # Schritt 4: Auffüller
    if fillup_runs:
        _process_fillup(cup, fillup_runs[0], qualified, new_entries)

    db.session.commit()
    return get_qualification(cup)


def get_qualification(cup: Cup) -> dict[str, list[CupQualifiedTeam]]:
    """Gibt die gespeicherte Qualifikationsliste gruppiert zurück."""
    all_teams = (
        CupQualifiedTeam.query
        .filter_by(cup_id=cup.id)
        .order_by(CupQualifiedTeam.category_code, CupQualifiedTeam.id)
        .all()
    )
    result: dict[str, list[CupQualifiedTeam]] = defaultdict(list)
    for qt in all_teams:
        key = _group_key(qt.category_code, None)  # Finals sind pro Kategorie, nicht pro Klasse
        result[key].append(qt)
    # Sortieren: Large → Intermediate → Medium → Small
    order = {c: i for i, c in enumerate(CATEGORIES)}
    return dict(sorted(result.items(), key=lambda kv: order.get(kv[0], 99)))


# ---------------------------------------------------------------------------
# Verarbeitung eines Qualifikationslaufs
# ---------------------------------------------------------------------------

def _process_run(
    cup: Cup,
    qr: CupQualificationRun,
    qualified: dict[str, set[str]],
    new_entries: list[CupQualifiedTeam],
):
    """
    Vergibt Qualifikationsplätze für einen Lauf.

    Wenn split_by_class=True: Klasse 1, 2, 3 werden separat ausgewertet.
    Wenn split_by_class=False: alle Klassen fliessen zusammen (Tunnellauf).

    Pro Kategorie werden die konfigurierten Plätze vergeben.
    Bereits qualifizierte Teams werden übersprungen.
    """
    results = (
        Result.query
        .filter_by(event_id=qr.event_id, discipline=qr.discipline)
        .all()
    )
    if not results:
        return

    # Ergebnisse nach (category, class_level_or_None) gruppieren
    by_group: dict[tuple, list[Result]] = defaultdict(list)
    for r in results:
        cls = r.class_level if qr.split_by_class else None
        key = (r.category_code or '', cls)
        by_group[key].append(r)

    for (cat_code, cls), group_results in by_group.items():
        # Sortieren: nicht-DQ zuerst, dann nach Rang
        group_results.sort(key=lambda r: (
            1 if r.eliminated else 0,
            r.rank if r.rank else 9999,
        ))

        spots = qr.spots_for_category(cat_code)
        if spots <= 0:
            continue

        # Doppelqualifikation wird gegen die Kategorie-Gruppe geprüft (ohne Klasse)
        cat_key = _group_key(cat_code, None)
        spots_given = 0

        # Cache: registration_external_id → license_no (für Titelverteidiger-Erkennung)
        ext_to_license: dict[str, str] = {}

        for r in group_results:
            if spots_given >= spots:
                break
            if r.eliminated:
                continue
            dog_key = _normalise(r.dog_name or '')
            if not dog_key:
                continue
            if dog_key in qualified[cat_key]:
                # Doppelqualifikation: überspringen, nächstes Team rückt nach
                continue
            # Lizenz nachschlagen (via Registration → Dog)
            license_no: str | None = None
            ext_id = r.registration_external_id or ''
            if ext_id:
                if ext_id not in ext_to_license:
                    reg = Registration.query.filter_by(
                        event_id=qr.event_id,
                        external_id=ext_id,
                    ).first()
                    ext_to_license[ext_id] = (reg.dog.license_no if reg and reg.dog else '') or ''
                license_no = ext_to_license[ext_id] or None
            # Qualifiziert!
            qualified[cat_key].add(dog_key)
            spots_given += 1
            new_entries.append(CupQualifiedTeam(
                cup_id=cup.id,
                category_code=cat_code,
                class_level=cls,  # merken aus welcher Klasse qualifiziert
                dog_name=r.dog_name or '',
                handler_name=r.handler_name or '',
                license_no=license_no,
                qualification_source=CupQualifiedTeam.SOURCE_RUN,
                qual_run_id=qr.id,
                qualified_rank=r.rank,
            ))


# ---------------------------------------------------------------------------
# Auffüller-Lauf: auf nächste 2er-Potenz auffüllen
# ---------------------------------------------------------------------------

def _process_fillup(
    cup: Cup,
    fillup_run: CupQualificationRun,
    qualified: dict[str, set[str]],
    new_entries: list[CupQualifiedTeam],
):
    """Füllt jede Gruppe auf die nächste 2er-Potenz auf."""
    results = (
        Result.query
        .filter_by(event_id=fillup_run.event_id, discipline=fillup_run.discipline)
        .all()
    )
    if not results:
        return

    # Aktuelle Anzahl qualifizierter Teams pro Kategorie
    current_counts: dict[str, int] = defaultdict(int)
    existing = CupQualifiedTeam.query.filter_by(cup_id=cup.id).all()
    for qt in existing:
        key = _group_key(qt.category_code, None)
        current_counts[key] += 1
    for entry in new_entries:
        key = _group_key(entry.category_code, None)
        current_counts[key] += 1

    # Ergebnisse nach Kategorie gruppieren (Klassen zusammen für Auffüller)
    by_cat: dict[str, list[Result]] = defaultdict(list)
    for r in results:
        by_cat[r.category_code or ''].append(r)

    for cat_code, cat_results in by_cat.items():
        cat_key = _group_key(cat_code, None)
        current = current_counts.get(cat_key, 0)
        target = next_power_of_two(current)

        if current >= target:
            continue

        cat_results.sort(key=lambda r: (1 if r.eliminated else 0, r.rank if r.rank else 9999))

        for r in cat_results:
            current = current_counts.get(cat_key, 0)
            if current >= target:
                break
            if r.eliminated:
                continue
            dog_key = _normalise(r.dog_name or '')
            if not dog_key or dog_key in qualified[cat_key]:
                continue
            qualified[cat_key].add(dog_key)
            current_counts[cat_key] = current + 1
            entry = CupQualifiedTeam(
                cup_id=cup.id,
                category_code=cat_code,
                class_level=None,
                dog_name=r.dog_name or '',
                handler_name=r.handler_name or '',
                qualification_source=CupQualifiedTeam.SOURCE_FILLUP,
                qual_run_id=fillup_run.id,
                qualified_rank=r.rank,
            )
            db.session.add(entry)
            new_entries.append(entry)


# ---------------------------------------------------------------------------
# Titelverteidiger-Erkennung: Vorjahressieger ermitteln
# ---------------------------------------------------------------------------

def detect_title_defenders(cup: Cup) -> dict[str, dict]:
    """
    Ermittelt die Vorjahressieger aus dem Cup der vorherigen Saison.

    Sucht nach einem Cup mit gleichem special_ruleset und season = cup.season - 1.
    Gibt pro Kategorie die Informationen des Finalsiegers zurück.

    Rückgabe: {group_key: {"dog_name": ..., "handler_name": ..., "license_no": ...}}
    """
    if not cup.special_ruleset:
        return {}

    prev_cup = Cup.query.filter_by(
        special_ruleset=cup.special_ruleset,
        season=cup.season - 1,
    ).first()
    if not prev_cup:
        return {}

    # Alle Finale des Vorjahres-Cups laden
    prev_finals = CupFinal.query.filter_by(cup_id=prev_cup.id).all()
    if not prev_finals:
        return {}

    result: dict[str, dict] = {}

    for final in prev_finals:
        # Sieger = Rank 1 in CupFinalResult
        winner_result = (
            CupFinalResult.query
            .filter_by(final_id=final.id, final_rank=1)
            .first()
        )
        if not winner_result or not winner_result.participant:
            continue

        p = winner_result.participant
        group = final.group_label or final.category_code or ''
        result[group] = {
            "dog_name": p.dog_name,
            "handler_name": p.handler_name,
            "license_no": p.license_no,
            "category_code": final.category_code,
        }

    return result


def already_has_title_defender(cup: Cup, category_code: str) -> bool:
    """Prüft ob für diese Kategorie bereits ein Titelverteidiger eingetragen ist."""
    return CupQualifiedTeam.query.filter_by(
        cup_id=cup.id,
        category_code=category_code,
        qualification_source=CupQualifiedTeam.SOURCE_TITLE_DEFENDER,
    ).count() > 0
