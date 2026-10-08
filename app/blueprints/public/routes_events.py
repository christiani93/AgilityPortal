from flask import Blueprint, abort, current_app, render_template, request, url_for

from app.models import (Event, EventFinalist, EventRun, Registration,
                        RegistrationStatus, ResultImport, ScheduleBlock, StartNumber)


public_events_bp = Blueprint("public_events", __name__)

_DIVISION_LABELS = {"sm": "SM", "nachwuchs": "Nachwuchs"}
_SOURCE_LABELS = {"agility": "Agility", "jumping": "Jumping",
                  "title_defender": "Titelverteidiger", "nachruecker": "Nachrücker"}
_CATEGORY_ORDER = {"Small": 0, "Medium": 1, "Intermediate": 2, "Large": 3}
_RUN_TYPE_ORDER = {"agility": 0, "jumping": 1, "open": 2, "tunnel": 3}
_CATEGORY_CODE_ORDER = {"S": 0, "M": 1, "I": 2, "L": 3}


def _competitions_for_event(event):
    """Öffentliche Wettbewerbs-Übersicht: welche Disziplinen mit welchen
    Kategorien/Klassen das Turnier anbietet (keine privaten Daten).

    Rückgabe: Liste von {label, items:[{cat, cat_code, cls}]} je Disziplin.
    """
    by_type = {}
    for run in event.runs:
        by_type.setdefault(run.run_type, set()).add((run.category, run.class_level))
    competitions = []
    for run_type in sorted(by_type, key=lambda t: _RUN_TYPE_ORDER.get(t, 9)):
        combos = sorted(
            by_type[run_type],
            key=lambda ck: (_CATEGORY_CODE_ORDER.get(ck[0], 9), ck[1]),
        )
        competitions.append({
            "label": EventRun.RUN_TYPE_LABELS.get(run_type, run_type),
            "combos": [
                {"cat": EventRun.CATEGORY_LABELS.get(cat, cat), "cat_code": cat, "cls": cls}
                for cat, cls in combos
            ],
        })
    return competitions


def _has_admin_key():
    expected = current_app.config.get("ADMIN_KEY")
    provided = request.args.get("key") or request.headers.get("X-Admin-Key")
    return expected and provided == expected


@public_events_bp.get("/events")
def public_events_index():
    """Öffentliche, login-freie Liste aller publizierten Veranstaltungen."""
    from datetime import datetime

    events = (
        Event.query.filter_by(is_published=True, is_test=False)
        .order_by(Event.starts_at.is_(None), Event.starts_at)
        .all()
    )
    today = datetime.utcnow().date()
    upcoming, past = [], []
    for ev in events:
        ref = ev.ends_at or ev.starts_at
        if ref and ref.date() < today:
            past.append(ev)
        else:
            upcoming.append(ev)
    past.reverse()  # jüngste zuerst

    return render_template(
        "public/events_index.html", upcoming=upcoming, past=past,
    )


@public_events_bp.get("/events/<int:event_id>")
def public_overview(event_id):
    """Öffentliche, login-freie Event-Landingpage (Ziel des Website-Sync-Links)."""
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)

    has_finalists = (
        EventFinalist.query.filter_by(event_id=event_id).first() is not None
    )
    start_numbers_assigned = (
        StartNumber.query.filter_by(event_id=event_id).first() is not None
    )
    has_results = (
        ResultImport.query.filter_by(event_id=event_id).first() is not None
    )

    from datetime import datetime
    today = datetime.utcnow().date()
    start_date = event.starts_at.date() if event.starts_at else None
    end_date = (event.ends_at or event.starts_at)
    end_date = end_date.date() if end_date else None
    is_event_day = bool(start_date and end_date and start_date <= today <= end_date)

    type_label = None
    if event.type and event.type != "regular":
        type_label = Event.TYPE_LABELS.get(event.type, event.type)
    ruleset_label = None
    if event.special_ruleset:
        ruleset_label = Event.SPECIAL_RULESET_LABELS.get(
            event.special_ruleset, event.special_ruleset)

    competitions = _competitions_for_event(event)

    return render_template(
        "public/overview.html",
        event=event,
        type_label=type_label,
        ruleset_label=ruleset_label,
        has_finalists=has_finalists,
        start_numbers_assigned=start_numbers_assigned,
        has_results=has_results,
        is_event_day=is_event_day,
        competitions=competitions,
    )


@public_events_bp.get("/events/<int:event_id>/schedule")
def public_schedule(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)
    if not event.schedule_public and not _has_admin_key():
        abort(403)

    # Gleiche Ablaufplan-Darstellung wie in der eingeloggten Teilnehmer-Ansicht
    # (club/event_view.html): Segment-Timeline mit Umbau/Briefing/Vorbereitungs-
    # pause/Rangverkündigung und Zeiten, sobald Startnummern vergeben sind –
    # sonst nur die Reihenfolge.
    from datetime import datetime

    from app.blueprints.club.routes import (_effective_participant_count,
                                            _get_run_time_config,
                                            _participant_counts_for_event)
    from app.blueprints.club.schedule_utils import (auto_title,
                                                    compute_detailed_segments,
                                                    parse_ring_start_times,
                                                    ring_names)

    blocks = (
        ScheduleBlock.query.filter_by(event_id=event_id)
        .order_by(ScheduleBlock.ring, ScheduleBlock.sort_index)
        .all()
    )
    counts = _participant_counts_for_event(event_id)
    for b in blocks:
        b._participant_count = _effective_participant_count(b, counts)
        b._display_title = b.title or auto_title(
            b.discipline, b.category_code, b.class_level)

    rings = ring_names(event.ring_count or 1)
    start_times = parse_ring_start_times(event.ring_start_times)
    for r in rings:
        start_times.setdefault(r, "08:00")
    sched_by_ring = {r: [] for r in rings}
    for b in blocks:
        if b.ring in sched_by_ring:
            sched_by_ring[b.ring].append(b)

    has_start_numbers = event.start_numbers_generated_at is not None
    sched_timeline = (
        compute_detailed_segments(
            sched_by_ring, start_times,
            event.starts_at.strftime("%Y-%m-%d") if event.starts_at
            else datetime.utcnow().strftime("%Y-%m-%d"),
            round_minutes=5,
            run_time_config=_get_run_time_config(event))
        if has_start_numbers else {}
    )

    return render_template(
        "public/schedule.html", event=event, rings=rings,
        sched_by_ring=sched_by_ring, sched_timeline=sched_timeline,
        has_start_numbers=has_start_numbers,
    )


@public_events_bp.get("/events/<int:event_id>/finalists")
def public_finalists(event_id):
    """Öffentliche Finalisten-Liste (SKBS-SM flach, BCCS-SM nach Kategorie+Division)."""
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)

    finalists = (
        EventFinalist.query.filter_by(event_id=event_id)
        .order_by(EventFinalist.category, EventFinalist.division, EventFinalist.position)
        .all()
    )
    if not finalists:
        abort(404)

    from collections import OrderedDict
    groups = OrderedDict()
    for f in finalists:
        groups.setdefault((f.category or "", f.division or ""), []).append(f)

    return render_template(
        "public/finalists.html", event=event, groups=groups,
        division_labels=_DIVISION_LABELS, source_labels=_SOURCE_LABELS,
    )


def _row_from_registration(registration, start_no):
    dog = registration.dog
    handler = registration.handler
    return {
        "start_no": start_no,
        "dog_name": dog.name if dog else "",
        "breed": (dog.breed if dog else "") or "",
        "handler_name": f"{handler.first_name} {handler.last_name}" if handler else "",
        "category_code": registration.category_code,
        "class_level": registration.class_level,
        "club_name": registration.club_display_name or "",
    }


def _collect_startlist_rows(event_id):
    """Sammelt Startlisten-Zeilen für ein Event (dreistufig):

    1. StartNumber-Tabelle befüllt (Rücksync aus der AgilitySoftware) → deren
       Nummern haben Vorrang, denn das ist der massgebliche Event-Tag-Stand.
    2. sonst bestätigte Anmeldungen mit portal-intern vergebener Startnummer
       (``Registration.start_number``) → echte Startliste, nach Nummer sortiert.
    3. sonst → vorläufige Meldeliste (alle offenen Anmeldungen, nach
       Kategorie/Klasse/Hund).

    Rückgabe: (rows, has_numbers)
    """
    numbers = (
        StartNumber.query.filter_by(event_id=event_id)
        .order_by(StartNumber.start_no)
        .all()
    )
    if numbers:
        rows = []
        for entry in numbers:
            registration = Registration.query.get(entry.registration_id)
            if registration:
                rows.append(_row_from_registration(registration, entry.start_no))
        return rows, True

    confirmed_numbered = (
        Registration.query.filter_by(
            event_id=event_id, status=RegistrationStatus.CONFIRMED
        )
        .filter(Registration.start_number.isnot(None))
        .order_by(Registration.start_number)
        .all()
    )
    if confirmed_numbered:
        rows = [_row_from_registration(r, r.start_number) for r in confirmed_numbered]
        return rows, True

    registrations = (
        Registration.query.filter_by(event_id=event_id)
        .filter(Registration.status != RegistrationStatus.CANCELLED)
        .all()
    )
    rows = [_row_from_registration(r, None) for r in registrations]
    rows.sort(key=lambda r: (
        _CATEGORY_ORDER.get(r["category_code"], 99),
        r["class_level"] or 0,
        r["dog_name"].lower(),
    ))
    return rows, False


def _group_startlist_rows(rows, only_cat=None, only_cls=None):
    """Gruppiert Startlisten-Zeilen zu je einem Block pro (Kategorie, Klasse) –
    wie die Startliste der AgilitySoftware (ein Block = ein Lauf-Startliste).

    only_cat/only_cls filtern optional auf genau einen Block (für Einzel-PDF).
    Rückgabe: Liste von {category_code, class_level, rows, count}, sortiert nach
    Kategorie (S-M-I-L) und Klasse."""
    from collections import OrderedDict
    groups = OrderedDict()
    for row in rows:
        cat = row["category_code"]
        cls = row["class_level"]
        if only_cat is not None and cat != only_cat:
            continue
        if only_cls is not None and (cls or 0) != only_cls:
            continue
        groups.setdefault((cat, cls), []).append(row)

    ordered = sorted(
        groups.items(),
        key=lambda kv: (_CATEGORY_ORDER.get(kv[0][0], 99), kv[0][1] or 0),
    )
    result = []
    for (cat, cls), block_rows in ordered:
        block_rows.sort(key=lambda r: (
            r["start_no"] if r["start_no"] is not None else 10_000,
            r["dog_name"].lower(),
        ))
        result.append({
            "category_code": cat,
            "class_level": cls,
            "rows": block_rows,
            "count": len(block_rows),
        })
    return result


def _event_logo_urls(event):
    """(event_logo_url, club_logo_url) für die öffentliche Logo-Serve-Route."""
    event_logo_url = (
        url_for("club.event_logo_serve", event_id=event.id, logo_type="event_logo")
        if event.event_logo_filename else None
    )
    club_logo_url = (
        url_for("club.event_logo_serve", event_id=event.id, logo_type="club_logo")
        if event.club_logo_filename else None
    )
    return event_logo_url, club_logo_url


def _event_logo_paths(event):
    """(event_logo_path, club_logo_path) als Dateipfade für die PDF-Einbettung,
    oder None wenn kein Logo hinterlegt ist."""
    import os
    from app.blueprints.club.routes import LOGO_UPLOAD_FOLDER

    base = os.path.join(current_app.instance_path, LOGO_UPLOAD_FOLDER, str(event.id))

    def _path(fname):
        if not fname:
            return None
        p = os.path.join(base, fname)
        return p if os.path.exists(p) else None

    return _path(event.event_logo_filename), _path(event.club_logo_filename)


@public_events_bp.get("/events/<int:event_id>/startlist")
def public_startlist(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)
    # Meldeliste/Startliste ist für publizierte Events öffentlich sichtbar –
    # gleich wie für eingeloggte Nutzer (kein startlist_public-Gate mehr).

    # ?cat=&cls= blendet auf genau eine Klasse/Kategorie ein → direkt verlinkbar.
    only_cat = request.args.get("cat") or None
    only_cls = request.args.get("cls", type=int)

    rows, has_numbers = _collect_startlist_rows(event_id)
    groups = _group_startlist_rows(rows, only_cat=only_cat, only_cls=only_cls)

    return render_template(
        "public/startlist.html",
        event=event,
        groups=groups,
        rows=rows,
        has_numbers=has_numbers,
        single_block=bool(only_cat or only_cls),
    )


@public_events_bp.get("/events/<int:event_id>/startlist/print")
def public_startlist_print(event_id):
    """Druckfertige, login-freie Startliste/Meldeliste mit Logo-Kopf.

    Je ein Block pro (Kategorie, Klasse), Layout wie in der AgilitySoftware.
    Ohne Filter: alle Blöcke mit Seitenumbruch (Sammeldruck). Mit ?cat=&cls=
    genau ein Block → eine Druckseite = ein PDF pro Klasse/Kategorie beim
    „Als PDF speichern"."""
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)

    only_cat = request.args.get("cat") or None
    only_cls = request.args.get("cls", type=int)

    rows, has_numbers = _collect_startlist_rows(event_id)
    groups = _group_startlist_rows(rows, only_cat=only_cat, only_cls=only_cls)
    event_logo_url, club_logo_url = _event_logo_urls(event)

    return render_template(
        "public/startlist_print.html",
        event=event,
        groups=groups,
        has_numbers=has_numbers,
        event_logo_url=event_logo_url,
        club_logo_url=club_logo_url,
    )
