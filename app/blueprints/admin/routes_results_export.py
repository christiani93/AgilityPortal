"""Serverseitiger TKAMO-Ergebnis-Export (Nachbau der AgilitySoftware-Funktion
`routes_print.tkamo_export`).

Erzeugt aus den im Portal gespeicherten Ergebnissen (neuester Result-Import des
Events) eine reglementskonforme TKAMO-CSV (semikolon-getrennt, Komma als
Dezimaltrennzeichen), Spaltenreihenfolge identisch zur offiziellen TKAMO-Vorlage
inkl. der (leeren) ASMV-Spalten.

Grenzen der Portal-Datenlage: Die Resultat-Austauschschnittstelle
(agility.exchange.resultexport.v1) überträgt KEINE Parcours-Geometrie. Daher
bleiben `Geschwindigkeit`, `Parcourslaenge`, `Geraetezahl`, `Standardzeit` und
`Maximalzeit` leer — diese Werte liegen nur in der AgilitySoftware vor.
"""
import csv
import io
from functools import wraps

from flask import Blueprint, Response, abort, current_app, request

from app.models import Event, EventRun, Judge, Registration, Result, ResultImport


results_export_admin_bp = Blueprint("results_export_admin", __name__)

# Result.category_code hält das volle Label ("Large"), EventRun.category den Code ("L").
_CAT_CODE = {"Small": "S", "Medium": "M", "Intermediate": "I", "Large": "L"}
# Result.discipline ("Agility") -> EventRun.run_type ("agility")
_RUN_TYPE = {"Agility": "agility", "Jumping": "jumping", "Open": "open"}
_CAT_SORT = {"Large": 0, "Intermediate": 1, "Medium": 2, "Small": 3}

HEADER = [
    "Turniernummer", "Lizenznummer", "Hundename", "Hundefuehrer", "Club",
    "Kategorie", "Klasse", "Rang", "Laufzeit", "Geschwindigkeit", "Fehler",
    "Verweigerung", "Zeitfehler", "Gesamtfehler", "Disqualifiziert", "Lauf",
    "Richter", "Parcourslaenge", "Geraetezahl", "Standardzeit", "Maximalzeit",
    "Datum", "ASMV Rang", "ASMV Team", "ASMV Punkte",
]


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def _num(value, decimals=2):
    """Zahl mit Komma-Dezimaltrennzeichen, oder '' bei None."""
    if value is None:
        return ""
    return f"{float(value):.{decimals}f}".replace(".", ",")


def _norm_lic(value):
    if value is None:
        return ""
    return "".join(ch for ch in str(value) if ch.isalnum()).upper()


def _judge_map(event_id):
    """(run_type, category_code, class_level) -> AIS-Richternummer."""
    out = {}
    for run in EventRun.query.filter_by(event_id=event_id).all():
        if run.judge_id is None:
            continue
        judge = Judge.query.get(run.judge_id)
        if not judge:
            continue
        out[(run.run_type, run.category, run.class_level)] = judge.ais_judge_id
    return out


def _club_map(event_id):
    """normalisierte Lizenznummer -> Vereinsname (aus den Anmeldungen)."""
    out = {}
    regs = (
        Registration.query.filter_by(event_id=event_id)
        .join(Registration.dog)
        .all()
    )
    for reg in regs:
        lic = reg.verified_license_no or (reg.dog.license_no if reg.dog else None)
        if lic:
            out.setdefault(_norm_lic(lic), reg.club_name or "")
    return out


def build_tkamo_csv(event):
    li = (
        ResultImport.query.filter_by(event_id=event.id)
        .order_by(ResultImport.id.desc())
        .first()
    )
    rows = (
        Result.query.filter_by(result_import_id=li.id).all() if li else []
    )
    judges = _judge_map(event.id)
    clubs = _club_map(event.id)
    datum = event.starts_at.strftime("%d.%m.%Y") if event.starts_at else ""
    turniernummer = event.ais_turniernummer or ""

    def sort_key(r):
        return (
            _CAT_SORT.get(r.category_code, 9),
            r.discipline or "",
            r.class_level or 0,
            r.rank if r.rank is not None else 10 ** 9,
        )

    output = io.StringIO()
    writer = csv.writer(output, delimiter=";")
    writer.writerow(HEADER)

    for r in sorted(rows, key=sort_key):
        # DNS kommt in der offiziellen TKAMO-Liste nicht vor
        if (r.status or "").upper() == "DNS":
            continue

        is_dis = bool(r.eliminated) or (r.status or "").upper() in ("DIS", "ABR")
        cat_code = _CAT_CODE.get(r.category_code, r.category_code)
        run_type = _RUN_TYPE.get(r.discipline, (r.discipline or "").lower())
        richter = judges.get((run_type, cat_code, r.class_level), "")
        club = clubs.get(_norm_lic(r.registration_external_id), "")

        if is_dis:
            # Wie in der offiziellen Vorlage: nur Identität + DIS-Marker,
            # keine (ohnehin als 999er-Sentinel gespeicherten) Ergebniswerte.
            writer.writerow([
                turniernummer, r.registration_external_id or "", r.dog_name or "",
                r.handler_name or "", club, r.category_code or "", r.class_level or "",
                "", "", "", "", "", "", "", "DIS", r.discipline or "",
                richter, "", "", "", "", datum, "", "", "",
            ])
            continue

        faults = int(r.faults or 0)
        refusals = int(r.refusals or 0)
        total_faults = r.total_faults if r.total_faults is not None else 0.0
        zeitfehler = max(0.0, round(total_faults - 5 * (faults + refusals), 2))
        writer.writerow([
            turniernummer,
            r.registration_external_id or "",
            r.dog_name or "",
            r.handler_name or "",
            club,
            r.category_code or "",
            r.class_level or "",
            r.rank if r.rank is not None else "",
            _num(r.time_s),
            "",                       # Geschwindigkeit: Parcourslänge nicht im Portal
            faults * 5,
            refusals * 5,
            _num(zeitfehler),
            _num(total_faults),
            "",                       # Disqualifiziert
            r.discipline or "",
            richter,
            "", "", "", "",           # Parcourslaenge / Geraetezahl / Standardzeit / Maximalzeit
            datum,
            "", "", "",               # ASMV Rang / Team / Punkte
        ])

    output.seek(0)
    return output.getvalue()


@results_export_admin_bp.get("/admin/events/<int:event_id>/tkamo_export")
@_require_admin_key
def tkamo_export(event_id):
    event = Event.query.get_or_404(event_id)
    csv_data = build_tkamo_csv(event)
    filename = f"tkamo_export_event_{event_id}.csv"
    return Response(
        csv_data,
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )
