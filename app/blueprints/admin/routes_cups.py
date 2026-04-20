"""
Admin-Routen für die Cup-Verwaltung.

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie andere Admin-Routen)
"""
import json
from functools import wraps

from flask import Blueprint, abort, flash, redirect, render_template, request, url_for, current_app

from flask_login import current_user

from app.extensions import db
from app.models import (Club, Cup, CupAllowedOrganiser, CupEvent, CupFinal,
                        CupFinalParticipant, CupFinalMatchup,
                        CupQualificationRun, CupQualifiedTeam, Event)
from app.services.cup_qualification import (
    run_qualification, get_qualification,
    detect_title_defenders, already_has_title_defender,
)


cups_admin_bp = Blueprint("cups_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        # Eingeloggte Superadmins haben immer Zugriff
        if current_user.is_authenticated and getattr(current_user, 'is_superadmin', False):
            return func(*args, **kwargs)
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def _admin_key():
    """Key für URL-Parameter – leer wenn Superadmin eingeloggt."""
    if current_user.is_authenticated and getattr(current_user, 'is_superadmin', False):
        return ""
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
    clubs = Club.query.order_by(Club.name).all()
    if request.method == "POST":
        cup = _cup_from_form(Cup())
        db.session.add(cup)
        db.session.commit()
        flash(f"Cup «{cup.name}» wurde angelegt.", "success")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup.id, key=_admin_key()))
    return render_template("admin/cups/form.html", cup=None, clubs=clubs, admin_key=_admin_key())


# ── Cup-Detail + Standings ─────────────────────────────────────────────────────

@cups_admin_bp.get("/admin/cups/<int:cup_id>")
@_require_admin_key
def cup_detail(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    qualification = get_qualification(cup)
    events = Event.query.order_by(Event.date_from.desc()).limit(200).all()
    finals = CupFinal.query.filter_by(cup_id=cup_id).order_by(CupFinal.group_label).all()
    clubs = Club.query.order_by(Club.name).all()
    return render_template(
        "admin/cups/detail.html",
        cup=cup,
        qualification=qualification,
        events=events,
        finals=finals,
        clubs=clubs,
        admin_key=_admin_key(),
    )


# ── Qualifikationsläufe konfigurieren ─────────────────────────────────────────

@cups_admin_bp.post("/admin/cups/<int:cup_id>/qual-runs/add")
@_require_admin_key
def cup_qual_run_add(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    event_id = request.form.get("event_id", type=int)
    discipline = request.form.get("discipline", "").strip()
    spots = request.form.get("spots", type=int) or 3
    run_order = request.form.get("run_order", type=int)
    is_fillup = bool(request.form.get("is_fillup"))
    label = request.form.get("label", "").strip() or None

    if not event_id or not discipline:
        flash("Event und Disziplin sind Pflicht.", "danger")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    # Veranstalter-Einschränkung prüfen (Superadmin darf immer)
    is_superadmin = current_user.is_authenticated and getattr(current_user, 'is_superadmin', False)
    qual_event = db.session.get(Event, event_id)
    if not is_superadmin and qual_event and not cup.allows_club(qual_event.organiser_club_id):
        allowed_names = ", ".join(ao.club.name for ao in cup.allowed_organisers)
        club_name = qual_event.organiser_club.name if qual_event.organiser_club else "kein Verein"
        flash(
            f"Der Veranstalter «{club_name}» darf diesen Cup nicht durchführen. "
            f"Erlaubte Vereine: {allowed_names}.",
            "danger",
        )
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    # Automatische run_order wenn nicht angegeben
    if not run_order:
        existing = CupQualificationRun.query.filter_by(cup_id=cup_id).count()
        run_order = existing + 1

    # Plätze pro Kategorie aus Formular lesen
    spots_large = request.form.get("spots_large", type=int) or 1
    spots_intermediate = request.form.get("spots_intermediate", type=int) or 1
    spots_medium = request.form.get("spots_medium", type=int) or 1
    spots_small = request.form.get("spots_small", type=int) or 1
    split_by_class = bool(request.form.get("split_by_class"))

    spots_map = {
        "Large": spots_large,
        "Intermediate": spots_intermediate,
        "Medium": spots_medium,
        "Small": spots_small,
    }
    # Falls alle gleich: spots_json weglassen und nur spots setzen
    all_same = len(set(spots_map.values())) == 1
    spots_json_val = None if all_same else json.dumps(spots_map)
    spots_default = spots_large  # einheitlicher Wert

    qr = CupQualificationRun(
        cup_id=cup_id,
        event_id=event_id,
        discipline=discipline,
        spots=spots_default,
        spots_json=spots_json_val,
        split_by_class=split_by_class,
        run_order=run_order,
        is_fillup=is_fillup,
        label=label,
    )
    db.session.add(qr)
    db.session.commit()
    flash(f"Qualifikationslauf «{qr.display_label}» hinzugefügt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/qual-runs/<int:qr_id>/remove")
@_require_admin_key
def cup_qual_run_remove(cup_id, qr_id):
    qr = db.get_or_404(CupQualificationRun, qr_id)
    if qr.cup_id != cup_id:
        abort(404)
    db.session.delete(qr)
    db.session.commit()
    flash("Qualifikationslauf entfernt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/qualify/run")
@_require_admin_key
def cup_run_qualification(cup_id):
    """Qualifikation neu berechnen und in DB speichern."""
    cup = db.get_or_404(Cup, cup_id)
    result = run_qualification(cup)
    total = sum(len(v) for v in result.values())
    flash(f"Qualifikation berechnet: {total} Teams qualifiziert.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/qualify/add-manual")
@_require_admin_key
def cup_qualify_add_manual(cup_id):
    """Manuellen Eintrag hinzufügen (Titelverteidiger / Wildcard)."""
    cup = db.get_or_404(Cup, cup_id)
    source = request.form.get("source", "wildcard")
    if source not in (CupQualifiedTeam.SOURCE_TITLE_DEFENDER, CupQualifiedTeam.SOURCE_WILDCARD):
        source = CupQualifiedTeam.SOURCE_WILDCARD

    dog_name = request.form.get("dog_name", "").strip()
    handler_name = request.form.get("handler_name", "").strip()
    category_code = request.form.get("category_code", "").strip()
    class_level = request.form.get("class_level", type=int) or None
    note = request.form.get("note", "").strip() or None

    if not dog_name or not handler_name or not category_code:
        flash("Hund, Hundeführer und Kategorie sind Pflicht.", "danger")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    qt = CupQualifiedTeam(
        cup_id=cup_id,
        category_code=category_code,
        class_level=class_level if cup.split_by_class else None,
        dog_name=dog_name,
        handler_name=handler_name,
        qualification_source=source,
        seeding_note=note,
    )
    db.session.add(qt)
    db.session.commit()
    label = CupQualifiedTeam.SOURCE_LABELS.get(source, source)
    flash(f"{label} «{dog_name}» hinzugefügt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


@cups_admin_bp.post("/admin/cups/<int:cup_id>/qualify/<int:qt_id>/remove")
@_require_admin_key
def cup_qualify_remove(cup_id, qt_id):
    qt = db.get_or_404(CupQualifiedTeam, qt_id)
    if qt.cup_id != cup_id:
        abort(404)
    db.session.delete(qt)
    db.session.commit()
    flash("Eintrag entfernt.", "success")
    return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))


# ── Cup bearbeiten ─────────────────────────────────────────────────────────────

@cups_admin_bp.route("/admin/cups/<int:cup_id>/edit", methods=["GET", "POST"])
@_require_admin_key
def cup_edit(cup_id):
    cup = db.get_or_404(Cup, cup_id)
    clubs = Club.query.order_by(Club.name).all()
    if request.method == "POST":
        _cup_from_form(cup)
        db.session.commit()
        flash("Cup gespeichert.", "success")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup.id, key=_admin_key()))
    return render_template("admin/cups/form.html", cup=cup, clubs=clubs, admin_key=_admin_key())


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

    # Veranstalter-Einschränkung prüfen (Superadmin darf immer)
    is_superadmin = current_user.is_authenticated and getattr(current_user, 'is_superadmin', False)
    if not is_superadmin and not cup.allows_club(event.organiser_club_id):
        allowed_names = ", ".join(ao.club.name for ao in cup.allowed_organisers)
        club_name = event.organiser_club.name if event.organiser_club else "kein Verein"
        flash(
            f"Der Veranstalter «{club_name}» darf diesen Cup nicht durchführen. "
            f"Erlaubte Vereine: {allowed_names}.",
            "danger",
        )
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
    qualification = get_qualification(cup)

    if request.method == "POST":
        group_label = request.form.get("group_label", "").strip()
        category_code = request.form.get("category_code", "").strip()

        final = CupFinal(
            cup_id=cup_id,
            group_label=group_label,
            category_code=category_code,
            class_level=None,
        )
        db.session.add(final)
        db.session.flush()

        # Teilnehmer aus Qualifikationsliste übernehmen
        teams = qualification.get(group_label, [])
        for rank, qt in enumerate(teams, start=1):
            p = CupFinalParticipant(
                final_id=final.id,
                dog_name=qt.dog_name,
                handler_name=qt.handler_name,
                qualifying_points=0,
                seeding_rank=rank,
            )
            db.session.add(p)

        db.session.commit()
        flash(f"Finale für «{group_label}» mit {len(teams)} Teilnehmern angelegt.", "success")
        return redirect(url_for("cups_admin.cup_final_detail", cup_id=cup_id, final_id=final.id, key=_admin_key()))

    return render_template(
        "admin/cups/final_new.html",
        cup=cup,
        qualification=qualification,
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


# ── Titelverteidiger automatisch ermitteln ────────────────────────────────────

@cups_admin_bp.route("/admin/cups/<int:cup_id>/title-defender/detect", methods=["GET", "POST"])
@_require_admin_key
def cup_detect_title_defender(cup_id):
    """Vorjahressieger ermitteln und als Titelverteidiger eintragen."""
    cup = db.get_or_404(Cup, cup_id)
    candidates = detect_title_defenders(cup)

    if request.method == "POST":
        added = 0
        for group_key, info in candidates.items():
            cat = info["category_code"]
            # Nur eintragen wenn noch kein Titelverteidiger für diese Kategorie
            if already_has_title_defender(cup, cat):
                continue
            selected = request.form.get(f"add_{group_key}")
            if selected != "1":
                continue
            qt = CupQualifiedTeam(
                cup_id=cup.id,
                category_code=cat,
                class_level=None,
                dog_name=info["dog_name"],
                handler_name=info["handler_name"],
                license_no=info.get("license_no"),
                qualification_source=CupQualifiedTeam.SOURCE_TITLE_DEFENDER,
                seeding_note=f"Vorjahressieger {cup.season - 1}",
            )
            db.session.add(qt)
            added += 1
        db.session.commit()
        if added:
            flash(f"{added} Titelverteidiger eingetragen.", "success")
        else:
            flash("Keine neuen Titelverteidiger eingetragen (bereits vorhanden oder nicht ausgewählt).", "warning")
        return redirect(url_for("cups_admin.cup_detail", cup_id=cup_id, key=_admin_key()))

    # GET: Vorschau anzeigen
    existing_defenders = {
        qt.category_code
        for qt in CupQualifiedTeam.query.filter_by(
            cup_id=cup_id,
            qualification_source=CupQualifiedTeam.SOURCE_TITLE_DEFENDER,
        ).all()
    }
    return render_template(
        "admin/cups/title_defender_detect.html",
        cup=cup,
        candidates=candidates,
        existing_defenders=existing_defenders,
        admin_key=_admin_key(),
    )


# ── Hilfsfunktion: Formular → Cup ─────────────────────────────────────────────

def _cup_from_form(cup: Cup) -> Cup:
    cup.name = request.form.get("name", "").strip()
    cup.season = request.form.get("season", type=int) or 2026
    cup.special_ruleset = request.form.get("special_ruleset", "").strip() or None
    cup.description = request.form.get("description", "").strip() or None
    cup.is_active = bool(request.form.get("is_active"))
    cup.title_defender_spots = request.form.get("title_defender_spots", type=int) or 1
    cup.wildcard_spots = request.form.get("wildcard_spots", type=int) or 0
    cup.split_by_class = bool(request.form.get("split_by_class"))

    # Erlaubte Veranstalter-Vereine
    selected_club_ids = {int(v) for v in request.form.getlist("allowed_club_ids") if v.isdigit()}
    # Bestehende löschen und neu setzen
    cup.allowed_organisers.clear()
    for club_id in selected_club_ids:
        club = db.session.get(Club, club_id)
        if club:
            cup.allowed_organisers.append(CupAllowedOrganiser(club_id=club_id))

    return cup
