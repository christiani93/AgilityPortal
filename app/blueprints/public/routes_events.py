from flask import Blueprint, abort, current_app, render_template, request

from app.models import (Event, EventFinalist, Registration, RegistrationStatus,
                        ScheduleBlock, StartNumber)


public_events_bp = Blueprint("public_events", __name__)

_DIVISION_LABELS = {"sm": "SM", "nachwuchs": "Nachwuchs"}
_SOURCE_LABELS = {"agility": "Agility", "jumping": "Jumping",
                  "title_defender": "Titelverteidiger", "nachruecker": "Nachrücker"}
_CATEGORY_ORDER = {"Small": 0, "Medium": 1, "Intermediate": 2, "Large": 3}


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

    type_label = None
    if event.type and event.type != "regular":
        type_label = Event.TYPE_LABELS.get(event.type, event.type)
    ruleset_label = None
    if event.special_ruleset:
        ruleset_label = Event.SPECIAL_RULESET_LABELS.get(
            event.special_ruleset, event.special_ruleset)

    return render_template(
        "public/overview.html",
        event=event,
        type_label=type_label,
        ruleset_label=ruleset_label,
        has_finalists=has_finalists,
        start_numbers_assigned=start_numbers_assigned,
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


@public_events_bp.get("/events/<int:event_id>/startlist")
def public_startlist(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)
    # Meldeliste/Startliste ist für publizierte Events öffentlich sichtbar –
    # gleich wie für eingeloggte Nutzer (kein startlist_public-Gate mehr).

    numbers = (
        StartNumber.query.filter_by(event_id=event_id)
        .order_by(StartNumber.start_no)
        .all()
    )

    rows = []
    if numbers:
        # Startnummern vergeben → echte Startliste
        for entry in numbers:
            registration = Registration.query.get(entry.registration_id)
            if not registration:
                continue
            dog = registration.dog
            handler = registration.handler
            rows.append(
                {
                    "start_no": entry.start_no,
                    "dog_name": dog.name if dog else "",
                    "handler_name": f"{handler.first_name} {handler.last_name}" if handler else "",
                    "category_code": registration.category_code,
                    "class_level": registration.class_level,
                }
            )
    else:
        # Noch keine Startnummern → read-only Meldeliste aus den Anmeldungen
        registrations = (
            Registration.query.filter_by(event_id=event_id)
            .filter(Registration.status != RegistrationStatus.CANCELLED)
            .all()
        )
        for registration in registrations:
            dog = registration.dog
            handler = registration.handler
            rows.append(
                {
                    "start_no": None,
                    "dog_name": dog.name if dog else "",
                    "handler_name": f"{handler.first_name} {handler.last_name}" if handler else "",
                    "category_code": registration.category_code,
                    "class_level": registration.class_level,
                }
            )
        rows.sort(key=lambda r: (
            _CATEGORY_ORDER.get(r["category_code"], 99),
            r["class_level"] or 0,
            r["dog_name"].lower(),
        ))

    return render_template(
        "public/startlist.html",
        event=event,
        rows=rows,
        has_numbers=bool(numbers),
    )
