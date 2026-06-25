from flask import Blueprint, abort, current_app, render_template, request

from app.models import Event, EventFinalist, Registration, ScheduleBlock, StartNumber


public_events_bp = Blueprint("public_events", __name__)

_DIVISION_LABELS = {"sm": "SM", "nachwuchs": "Nachwuchs"}
_SOURCE_LABELS = {"agility": "Agility", "jumping": "Jumping",
                  "title_defender": "Titelverteidiger", "nachruecker": "Nachrücker"}


def _has_admin_key():
    expected = current_app.config.get("ADMIN_KEY")
    provided = request.args.get("key") or request.headers.get("X-Admin-Key")
    return expected and provided == expected


@public_events_bp.get("/events/<int:event_id>/schedule")
def public_schedule(event_id):
    event = Event.query.get_or_404(event_id)
    if not event.is_published and not _has_admin_key():
        abort(404)
    if not event.schedule_public and not _has_admin_key():
        abort(403)

    blocks = (
        ScheduleBlock.query.filter_by(event_id=event_id)
        .order_by(ScheduleBlock.sort_index, ScheduleBlock.start_at)
        .all()
    )
    return render_template("public/schedule.html", event=event, blocks=blocks)


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
    if not event.startlist_public and not _has_admin_key():
        abort(403)

    numbers = (
        StartNumber.query.filter_by(event_id=event_id)
        .order_by(StartNumber.start_no)
        .all()
    )
    rows = []
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

    return render_template(
        "public/startlist.html",
        event=event,
        rows=rows,
        has_numbers=bool(numbers),
    )
