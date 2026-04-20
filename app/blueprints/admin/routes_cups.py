"""
Admin-Routen für die Cup-Verwaltung.

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie andere Admin-Routen)
"""
import json
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app

from app.extensions import db
from app.models import Cup, CupEvent, CupFinal, CupFinalParticipant, CupFinalMatchup, Event
from app.services.cup_standings import compute_standings


cups_admin_bp = Blueprint("cups_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def _admin_key():
    return request.args.get("key") or ""


# ── Liste aller Cups ───────────────────────────────────────────────────────────

@cups_admin_bp.get("/admin/cups")
@_require_admin_key
def cup_list():
    cups = Cup.query.order_by(Cup.season.desc(), Cup.name).all()
    return render_template("admin/cups/list.html", cups=cups, admin_key=_admin_key())


# ── Cup anlegen ────────────────────────────────────────────────────────────────

@cups_admin_bp.route("/admin/cups/new", methods=["GET", "POST"])
@_require_admin_key
def cup_new():
    if request.method == "POST":
        cup = _cup_from_form(Cup())
        db.session.add(cup)
        db.session.commit()
        flash(f"Cup «{cup.name}» wurde angelegt.", "success")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup.id, key=_admin_key()))
    return render_template("admin/cups/form.html", cup=None, admin_key=_admin_key())


# ── Cup-Detail + Standings ─────────────────────────────────────────────────────

@cups_admin_bp.get("/admin/cups/<int:cup_id>")
@_require_admin_key
def cup_detail(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    standings = compute_standings(cup)
    # Alle Events für Event-Verknüpfungs-Dropdown
    events = Event.query.order_by(Event.date_from.desc()).limit(200).all()
    # Finale dieses Cups
    finals = CupFinal.query.filter_by(cup_id=cup_id).order_by(CupFinal.group_label).all()
    return render_template(
        "admin/cups/detail.html",
        cup=cup,
        standings=standings,
        events=events,
        finals=finals,
        admin_key=_admin_key(),
    )


# ── Cup bearbeiten ─────────────────────────────────────────────────────────────

@cups_admin_bp.route("/admin/cups/<int:cup_id>/edit", methods=["GET", "POST"])
@_require_admin_key
def cup_edit(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    if request.method == "POST":
        _cup_from_form(cup)
        db.session.commit()
        flash("Cup gespeichert.", "success")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup.id, key=_admin_key()))
    return render_template("admin/cups/form.html", cup=cup, admin_key=_admin_key())


# ── Event zum Cup hinzufügen ───────────────────────────────────────────────────

@cups_admin_bp.post("/admin/cups/<int:cup_id>/events/add")
@_require_admin_key
def cup_event_add(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    event_id = request.form.get("event_id", type=int)
    meeting_no = request.form.get("meeting_no", type=int)

    if not event_id or not meeting_no:
        flash("Event und Meeting-Nummer sind Pflicht.", "danger")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    event = db.session.get(Event, event_id)
    if not event:
        flash("Event nicht gefunden.", "danger")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    # Prüfen ob bereits verknüpft
    existing = CupEvent.query.filter_by(cup_id=cup_id, event_id=event_id).first()
    if existing:
        flash(f"Event «{event.name}» ist bereits als Meeting {existing.meeting_no} verknüpft.", "warning")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    ce = CupEvent(cup_id=cup_id, event_id=event_id, meeting_no=meeting_no)
    db.session.add(ce)
    db.session.commit()
    flash(f"Meeting {meeting_no}: «{event.name}» hinzugefügt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


# ── Event aus Cup entfernen ────────────────────────────────────────────────────

@cups_admin_bp.post("/admin/cups/<int:cup_id>/events/<int:cup_event_id>/remove")
@_require_admin_key
def cup_event_remove(cup_id, cup_event_id):
    ce = db.get_or_404(CupEvent, cup_event_id)
    if ce.cup_id != cup_id:
        abort(404)
    db.session.delete(ce)
    db.session.commit()
    flash("Meeting entfernt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


# ── Hilfsfunktion: Formular → Cup ─────────────────────────────────────────────

# ── Finale verwalten ──────────────────────────────────────────────────────────

@cups_admin_bp.route("/admin/cups/<int:cup_id>/finals/new", methods=["GET", "POST"])
@_require_admin_key
def cup_final_new(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    standings = compute_standings(cup)

    if request.method == "POST":
        group_label = request.form.get("group_label", "").strip()
        category_code = request.form.get("category_code", "").strip()
        class_level = request.form.get("class_level", type=int) or None

        final = CupFinal(
            cup_id=cup_id,
            group_label=group_label,
            category_code=category_code,
            class_level=class_level,
        )
        db.session.add(final)
        db.session.flush()

        # Teilnehmer aus Qualifikation übernehmen
        dogs = standings.get(group_label, [])
        for rank, dog in enumerate(dogs, start=1):
            p = CupFinalParticipant(
                final_id=final.id,
                dog_name=dog.dog_name,
                handler_name=dog.handler_name,
                qualifying_points=dog.total_points,
                seeding_rank=rank,
            )
            db.session.add(p)

        db.session.commit()
        flash(f"Finale für «{group_label}» angelegt.", "success")
        return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final.id, key=_admin_key()))

    return render_template(
        "admin/cups/final_new.html",
        cup=cup,
        standings=standings,
        admin_key=_admin_key(),
    )


@cups_admin_bp.get("/admin/cups/<int:cup_id>/finals/<int:final_id>")
@_require_admin_key
def cup_final_detail(cup_id, final_id):
    cup = db.get_or_404(Cup, cup_id)
    final = db.get_or_404(CupFinal, final_id)
    if final.cup_id != cup_id:
        abort(404)
    return render_template(
        "admin/cups/final_detail.html",
        cup=cup,
        final=final,
        admin_key=_admin_key(),
    )


@cups_admin_bp.post("/admin/cups/<int:cup_id>/finals/<int:final_id>/publish")
@_require_admin_key
def cup_final_publish(cup_id, final_id):
    final = db.get_or_404(CupFinal, final_id)
    if final.cup_id != cup_id:
        abort(404)
    final.is_published = not final.is_published
    db.session.commit()
    status = "veröffentlicht" if final.is_published else "versteckt"
    flash(f"Finale {status}.", "success")
    return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/finals/<int:final_id>/draw")
@_require_admin_key
def cup_final_draw(cup_id, final_id):
    """Losnummern zufällig vergeben."""
    import random
    final = db.get_or_404(CupFinal, final_id)
    if final.cup_id != cup_id:
        abort(404)
    participants = final.participants
    numbers = list(range(1, len(participants) + 1))
    random.shuffle(numbers)
    for p, n in zip(participants, numbers):
        p.draw_number = n
    db.session.commit()
    flash(f"Losnummern für {len(participants)} Teilnehmer vergeben.", "success")
    return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/finals/<int:final_id>/bracket/generate")
@_require_admin_key
def cup_final_bracket_generate(cup_id, final_id):
    """Generiert das KO-Bracket basierend auf den Losnummern."""
    final = db.get_or_404(CupFinal, final_id)
    if final.cup_id != cup_id:
        abort(404)

    participants = [p for p in final.participants if p.draw_number is not None]
    if len(participants) < 2:
        flash("Mindestens 2 Teilnehmer mit Losnummern benötigt.", "danger")
        return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final_id, key=_admin_key()))

    # Bestehende Matchups löschen
    CupFinalMatchup.query.filter_by(final_id=final_id).delete()
    db.session.flush()

    # Sortiert nach Losnummer
    sorted_p = sorted(participants, key=lambda p: p.draw_number)
    n = len(sorted_p)

    # Runde 1: Höchste vs Tiefste (1 vs n, 2 vs n-1, …)
    matchup_no = 1
    matchups_r1 = []
    lo, hi = 0, n - 1
    while lo < hi:
        m = CupFinalMatchup(
            final_id=final_id,
            round_no=1,
            matchup_no=matchup_no,
            participant_a_id=sorted_p[hi].id,   # hohe Nummer
            participant_b_id=sorted_p[lo].id,    # tiefe Nummer
        )
        db.session.add(m)
        matchups_r1.append(m)
        lo += 1
        hi -= 1
        matchup_no += 1

    # Folgerunden werden manuell nach Eintrag der Ergebnisse erstellt
    db.session.commit()
    flash(f"Runde 1 mit {len(matchups_r1)} Duellen generiert.", "success")
    return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/finals/<int:final_id>/matchups/<int:matchup_id>/result")
@_require_admin_key
def cup_final_matchup_result(cup_id, final_id, matchup_id):
    """Ergebnis eines Duells eintragen."""
    matchup = db.get_or_404(CupFinalMatchup, matchup_id)
    if matchup.final_id != final_id:
        abort(404)

    def _get_float(name):
        v = request.form.get(name, "").strip()
        try:
            return float(v) if v else None
        except ValueError:
            return None

    # Rückzug prüfen
    forfeit = request.form.get("forfeit", "")
    if forfeit == "a":
        matchup.forfeit_participant_id = matchup.participant_a_id
    elif forfeit == "b":
        matchup.forfeit_participant_id = matchup.participant_b_id
    else:
        matchup.forfeit_participant_id = None

    # Zeiten und Fehler nur setzen wenn kein Rückzug
    if not matchup.forfeit_participant_id:
        matchup.a_time1 = _get_float("a_time1")
        matchup.a_time2 = _get_float("a_time2")
        matchup.a_faults = request.form.get("a_faults", type=int) or 0
        matchup.a_refusals = request.form.get("a_refusals", type=int) or 0
        matchup.a_disqualified = bool(request.form.get("a_disqualified"))

        matchup.b_time1 = _get_float("b_time1")
        matchup.b_time2 = _get_float("b_time2")
        matchup.b_faults = request.form.get("b_faults", type=int) or 0
        matchup.b_refusals = request.form.get("b_refusals", type=int) or 0
        matchup.b_disqualified = bool(request.form.get("b_disqualified"))

    # Gewinner automatisch berechnen
    matchup.winner_id = matchup.computed_winner_id

    db.session.commit()
    flash("Ergebnis gespeichert.", "success")
    return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final_id, key=_admin_key()))


# ── Hilfsfunktion: Formular → Cup ─────────────────────────────────────────────

def _cup_from_form(cup: Cup) -> Cup:
    cup.name = request.form.get("name", "").strip()
    cup.season = request.form.get("season", type=int) or 2026
    cup.special_ruleset = request.form.get("special_ruleset") or None
    cup.description = request.form.get("description", "").strip() or None
    cup.is_active = bool(request.form.get("is_active"))
    cup.count_best_meetings = request.form.get("count_best_meetings", type=int) or None
    cup.split_by_class = bool(request.form.get("split_by_class"))
    cup.split_by_run_type = bool(request.form.get("split_by_run_type"))

    # Punktetabelle: kommagetrennte Zahlen → JSON
    points_raw = request.form.get("point_system", "").strip()
    if points_raw:
        try:
            points = [int(x.strip()) for x in points_raw.split(",") if x.strip()]
            cup.point_system_json = json.dumps(points)
        except ValueError:
            cup.point_system_json = None
    else:
        cup.point_system_json = None  # Default verwenden
    return cup
