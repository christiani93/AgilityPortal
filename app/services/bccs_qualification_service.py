"""
BCCS-SM-Finalisten-Berechnung für das Portal.

Portiert die Qualifikationslogik aus AgilitySoftware (bccs_sm_qualification.py)
zur Berechnung der Finalisten pro Kategorie × Division. Diese Funktion wird
nach dem Import von Qualifikationsergebnissen aus der Software aufgerufen,
um die Finalisten für den Portal-Zeitplan zu berechnen (vor dem lokalen
Datenexport in die Software zurück).

Der Prozess:
1. load_event_for_qualification() — konvertiert Portal-Event zu Software-Format
2. calculate_bccs_sm_finalists() — ruft AgilitySoftware-Logik auf
3. save_finalists_to_event() — speichert Ergebnisse in DB (EventFinalist)
"""
import json
import math
from typing import Optional
from datetime import datetime, timezone

from app.extensions import db
from app.models import Event, EventRun, EventFinalist, Result


# === Konstanten (identisch zu AgilitySoftware bccs_sm_qualification.py) ===
CATEGORIES = ["Intermediate", "Large"]
DIVISIONS = {
    "sm":        {"label": "SM",        "classes": ["3"]},
    "nachwuchs": {"label": "Nachwuchs", "classes": ["1", "2"]},
}
QUALI_RUN_TYPES = ["Agility", "Jumping"]
QUOTA_PCT = 0.15
DIS_SENTINEL_FEHLER = 999.0
DIS_SENTINEL_ZEIT = 999.99


def calculate_bccs_finalists(event: Event) -> dict:
    """
    Berechnet die Finalisten für ein BCCS-SM-Event und speichert sie.

    Args:
        event: Portal-Event mit type="bccs_sm"

    Returns:
        dict mit "divisions" und "finalists" (Struktur wie aus SW calculate_bccs_sm_qualification)

    Raises:
        ValueError: wenn Event-Daten unzureichend sind
    """
    # Konvertiere Portal-Event zu Software-Format
    sw_event = _load_event_for_qualification(event)

    # Berechne Finalisten (nur SW-Logik, keine DB-Änderungen)
    result = _calculate_bccs_sm_qualification(sw_event)

    # Speichere Ergebnisse in EventFinalist
    _save_finalists_to_event(event, result)

    return result


def _load_event_for_qualification(event: Event) -> dict:
    """
    Konvertiert ein Portal-Event zu dem Format, das die SW-Qualifikationsfunktion erwartet.

    Erwartet:
    - Event mit type="bccs_sm"
    - EventRun-Einträge mit kategorie/klasse/laufart/is_final
    - Result-Einträge mit Fehler/Zeit/Rangplatz

    Returns: dict mit Struktur:
      {
        "runs": [
          {
            "kategorie": "Intermediate" | "Large",
            "klasse": "1" | "2" | "3",
            "laufart": "Agility" | "Jumping",
            "is_final": bool,
            "entries": [ {Lizenznummer, Hundename, fehler_total, ...} ]
          },
          ...
        ],
        "bccs_sm_config": {
          "quali_run_order": ["Agility", "Jumping"] | ["Jumping", "Agility"],
          "defending_champions": [ {license, dog_name, handler_name, category, division} ],
          "sm_licenses": [...] (optional)
        }
      }
    """
    # Sammle alle Läufe mit Ergebnissen
    runs_data = []
    for run in event.runs:
        # Konvertiere category code (S/M/I/L) zu vollständiger Form
        category_map = {"S": "Small", "M": "Medium", "I": "Intermediate", "L": "Large"}
        kategorie = category_map.get(run.category, run.category)

        # BCCS ist nur für Intermediate/Large
        if kategorie not in CATEGORIES:
            continue

        # BCCS akzeptiert nur Agility/Jumping
        laufart = run.run_type.capitalize()  # "agility" -> "Agility"
        if laufart not in QUALI_RUN_TYPES:
            continue

        # Sammle Ergebnisse für diesen Lauf
        entries = _collect_run_entries(event, run)

        if entries:  # Nur Läufe mit Ergebnissen einbeziehen
            runs_data.append({
                "kategorie": kategorie,
                "klasse": str(run.class_level),
                "laufart": laufart,
                "is_final": run.is_final,
                "entries": entries,
            })

    # Lade BCCS-Konfiguration (Titelverteidiger, Quali-Reihenfolge, etc.)
    config = _load_bccs_config(event)

    return {
        "runs": runs_data,
        "bccs_sm_config": config,
    }


def _collect_run_entries(event: Event, run: EventRun) -> list[dict]:
    """
    Sammelt alle Ergebnisse eines Laufs im Format, das die SW-Logik erwartet.
    """
    results = Result.query.filter_by(event_id=event.id, run_id=run.id).all()

    entries = []
    for result in results:
        # Normalisiere Ergebnis-Daten
        is_dns = (result.disqualification or "").strip() == "DNS"
        is_dis = (result.disqualification or "").strip() in ("DIS", "ABR", "DNS")
        fehler_total = float(result.total_faults or 0)

        if is_dis:
            fehler_total = DIS_SENTINEL_FEHLER

        entry = {
            "Lizenznummer": result.dog.license_no if result.dog else "",
            "Hundename": result.dog.name if result.dog else "",
            "Vorname": result.handler.first_name if result.handler else "",
            "Nachname": result.handler.last_name if result.handler else "",
            "handler_name": (
                f"{result.handler.first_name} {result.handler.last_name}".strip()
                if result.handler else ""
            ),
            "dog_name": result.dog.name if result.dog else "",
            "fehler_total": fehler_total,
            "fehler_parcours": int(result.course_faults or 0),
            "zeit_total": float(result.time_seconds or DIS_SENTINEL_ZEIT) if not is_dis else DIS_SENTINEL_ZEIT,
            "platz": result.placement,
            "disqualifikation": result.disqualification or "",
        }
        entries.append(entry)

    return entries


def _load_bccs_config(event: Event) -> dict:
    """
    Lädt BCCS-SM-spezifische Konfiguration aus dem Event.

    Fallback: Standard-Konfiguration wenn nicht gespeichert.
    """
    # TODO: Diese Felder sollten im Event gespeichert sein (JSON-Spalte)
    # Für MVP: Fallback auf Defaults

    return {
        "quali_run_order": ["Agility", "Jumping"],
        "defending_champions": [],  # TODO: aus Event laden wenn vorhanden
        "sm_licenses": None,  # Optional: Filter auf bestimmte Lizenzen
    }


def _calculate_bccs_sm_qualification(event: dict) -> dict:
    """
    Interne Implementierung der BCCS-SM-Qualifikation (portiert aus AgilitySoftware).

    Args:
        event: dict mit "runs" und "bccs_sm_config"

    Returns:
        dict mit "divisions" und "finalists"
    """
    config = event.get("bccs_sm_config") or {}
    quali_order = _resolve_quali_order(config.get("quali_run_order"))
    defenders = config.get("defending_champions") or []

    divisions = {}
    all_finalists = []

    for category in CATEGORIES:
        for div_key, div_def in DIVISIONS.items():
            qualified = set()
            div_finalists = []

            # Titelverteidiger
            defending = _find_defender(defenders, category, div_key)
            if defending and defending.get("license"):
                lic = defending["license"].strip()
                if _defender_started(event, category, div_def["classes"], lic):
                    div_finalists.append({
                        "license": lic,
                        "dog_name": defending.get("dog_name", ""),
                        "handler_name": defending.get("handler_name", ""),
                        "source": "title_defender",
                        "from_class": None,
                        "quali_rank": None,
                    })
                    qualified.add(lic)

            # Klassen der Division SEPARAT werten
            quota = {}
            open_spots = 0
            for cls in div_def["classes"]:
                res = _compute_class(
                    _collect_class(event, category, cls),
                    quali_order,
                    qualified
                )
                div_finalists.extend(res["finalists"])
                for la, q in res["quota"].items():
                    quota[la] = quota.get(la, 0) + q
                open_spots += res["open_spots"]

            for f in div_finalists:
                f["category"] = category
                f["division"] = div_key
                all_finalists.append(f)

            divisions[f"{category}/{div_key}"] = {
                "category": category,
                "division": div_key,
                "quota": quota,
                "finalists": div_finalists,
                "open_spots": open_spots,
            }

    return {"divisions": divisions, "finalists": all_finalists}


def _resolve_quali_order(order: Optional[list]) -> list[str]:
    """Validiert die Quali-Lauf-Reihenfolge; Fallback ['Agility', 'Jumping']."""
    if isinstance(order, (list, tuple)) and set(order) == set(QUALI_RUN_TYPES):
        return list(order)
    return list(QUALI_RUN_TYPES)


def _find_defender(defenders: list[dict], category: str, div_key: str) -> Optional[dict]:
    """Sucht den Titelverteidiger für eine bestimmte Division."""
    for d in defenders:
        if (d.get("category") == category and d.get("division") == div_key
                and (d.get("license") or "").strip()):
            return d
    return None


def _collect_class(event: dict, category: str, cls: str) -> dict:
    """Sammelt Quali-Einträge einer (Kategorie × Klasse) je Laufart."""
    quali = {"Agility": [], "Jumping": []}
    for run in event.get("runs", []):
        if run.get("kategorie") != category or run.get("is_final"):
            continue
        if str(run.get("klasse") or "") != cls:
            continue
        laufart = run.get("laufart") or ""
        if laufart not in QUALI_RUN_TYPES:
            continue
        for e in run.get("entries", []):
            lic = (e.get("Lizenznummer") or "").strip()
            if not lic:
                continue
            ne = _normalise_entry(e)
            ne["from_class"] = int(cls) if cls.isdigit() else None
            quali[laufart].append(ne)
    return quali


def _defender_started(event: dict, category: str, classes: list[str], lic: str) -> bool:
    """True, wenn der Titelverteidiger in >=1 Quali-Lauf der Division gestartet ist."""
    for run in event.get("runs", []):
        if run.get("kategorie") != category or run.get("is_final"):
            continue
        if str(run.get("klasse") or "") not in classes:
            continue
        if run.get("laufart") not in QUALI_RUN_TYPES:
            continue
        for e in run.get("entries", []):
            if (e.get("Lizenznummer") or "").strip() == lic:
                return True
    return False


def _normalise_entry(entry: dict) -> dict:
    """Normalisiert einen Eintrag für die Qualifikationsberechnung."""
    license_no = (entry.get("Lizenznummer") or "").strip()
    dis_val = (entry.get("disqualifikation") or "").strip()
    fehler_total = entry.get("fehler_total", DIS_SENTINEL_FEHLER)
    is_dns = dis_val == "DNS"
    is_dis = (
        dis_val in ("DIS", "ABR", "DNS")
        or float(fehler_total) >= DIS_SENTINEL_FEHLER
    )

    # Handler-Name aus verschiedenen Quellen
    handler_name = entry.get("handler_name", "")
    if not handler_name:
        # Fallback: aus Vorname/Nachname zusammensetzen
        vorname = (entry.get("Vorname") or "").strip()
        nachname = (entry.get("Nachname") or "").strip()
        handler_name = f"{vorname} {nachname}".strip()

    return {
        "license": license_no,
        "dog_name": entry.get("dog_name", entry.get("Hundename") or ""),
        "handler_name": handler_name,
        "fehler_total": float(fehler_total) if not is_dis else DIS_SENTINEL_FEHLER,
        "fehler_parcours": int(entry.get("fehler_parcours", 0) or 0),
        "zeit": float(entry.get("zeit_total", DIS_SENTINEL_ZEIT)) if not is_dis else DIS_SENTINEL_ZEIT,
        "rang": entry.get("platz"),
        "dis": is_dis,
        "dns": is_dns,
    }


def _compute_class(quali_pools: dict, quali_order: list[str], qualified: set) -> dict:
    """
    Qualifikation EINER (Kategorie × Klasse): 15%-Direktquote pro Lauf,
    Doppelqualifikation überspringen, alternierendes Nachrücken.
    """
    finalists = []

    # Direkt-Qualifikation pro Lauf
    run_quota = {}
    run_sorted = {}
    for la in quali_order:
        pool = quali_pools.get(la, [])
        quota = _quota(_count_starters(pool))
        placed = _performance_sorted(pool)
        run_quota[la] = quota
        run_sorted[la] = placed

        given = 0
        for idx, e in enumerate(placed):
            if given >= quota:
                break
            if e["license"] in qualified:
                given += 1
                continue
            qualified.add(e["license"])
            finalists.append({
                "license": e["license"],
                "dog_name": e["dog_name"],
                "handler_name": e["handler_name"],
                "source": la.lower(),
                "from_class": e["from_class"],
                "quali_rank": idx + 1,
            })
            given += 1

    # Nachrücken für offene Plätze
    target = sum(run_quota.values())
    remaining = max(0, target - len(finalists))

    if remaining > 0:
        pointers = {la: 0 for la in quali_order}
        exhausted = {la: False for la in quali_order}
        while remaining > 0 and not all(exhausted.values()):
            progressed = False
            for la in quali_order:
                if remaining <= 0:
                    break
                placed = run_sorted[la]
                p = pointers[la]
                while p < len(placed) and placed[p]["license"] in qualified:
                    p += 1
                pointers[la] = p
                if p >= len(placed):
                    exhausted[la] = True
                    continue
                e = placed[p]
                qualified.add(e["license"])
                pointers[la] = p + 1
                progressed = True
                finalists.append({
                    "license": e["license"],
                    "dog_name": e["dog_name"],
                    "handler_name": e["handler_name"],
                    "source": "nachruecker",
                    "from_class": e["from_class"],
                    "quali_rank": p + 1,
                })
                remaining -= 1
            if not progressed:
                break

    return {
        "quota": dict(run_quota),
        "finalists": finalists,
        "open_spots": remaining,
    }


def _quota(num_starters: int) -> int:
    """Reglement 3.1: erste 15% der gestarteten SM-Hunde, aufgerundet."""
    if num_starters <= 0:
        return 0
    return math.ceil(num_starters * QUOTA_PCT)


def _performance_sorted(entries: list[dict]) -> list[dict]:
    """Nur platzierte Einträge, gerankt nach: Gesamtfehler → Parcoursfehler → Zeit."""
    valid = [e for e in entries if not e["dis"]]
    return sorted(valid, key=lambda e: (e["fehler_total"], e["fehler_parcours"], e["zeit"]))


def _count_starters(pool: list[dict]) -> int:
    """Gestartete Teams = alle ausser DNS."""
    starters = sum(1 for e in pool if not e["dns"])
    return starters if starters > 0 else len(pool)


def _save_finalists_to_event(event: Event, result: dict) -> None:
    """
    Speichert berechnete Finalisten in der EventFinalist-Tabelle.

    Ersetzt bestehende Einträge (idempotent).
    """
    # Lösche bestehende Finalisten für dieses Event
    EventFinalist.query.filter_by(event_id=event.id).delete(synchronize_session=False)

    # Füge neue Finalisten ein
    finalists = result.get("finalists") or []
    for pos, f in enumerate(finalists, start=1):
        db.session.add(EventFinalist(
            event_id=event.id,
            license=(f.get("license") or "")[:50],
            dog_name=(f.get("dog_name") or "")[:120],
            handler_name=(f.get("handler_name") or "")[:120],
            source=(f.get("source") or "")[:30],
            from_class=f.get("from_class"),
            quali_rank=f.get("quali_rank"),
            category=(f.get("category") or None) and f.get("category")[:20],
            division=(f.get("division") or None) and f.get("division")[:20],
            position=pos,
            imported_at=datetime.now(timezone.utc),
        ))

    db.session.commit()
