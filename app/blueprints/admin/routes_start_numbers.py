import json
from functools import wraps

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.extensions import db
from app.models import Event, Registration, StartNumber
from app.services.start_number_service import (
    generate_start_numbers,
    lock_start_numbers,
    set_start_number_manual,
    unlock_start_numbers,
)


start_numbers_admin_bp = Blueprint("start_numbers_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


@start_numbers_admin_bp.get("/admin/events/<int:event_id>/startnumbers")
@_require_admin_key
def start_numbers_home(event_id):
    event = Event.query.get_or_404(event_id)
    numbers = (
        StartNumber.query.filter_by(event_id=event_id)
        .order_by(StartNumber.start_no)
        .all()
    )
    rows = []
    for entry in numbers:
        registration = Registration.query.get(entry.registration_id)
        dog = registration.dog
        handler = registration.handler
        rows.append(
            {
                "start_no": entry.start_no,
                "registration_id": registration.id,
                "license_no": dog.license_no if dog else "",
                "dog_name": dog.name if dog else "",
                "handler_name": f"{handler.first_name} {handler.last_name}" if handler else "",
                "club_name": registration.club_name or "",
                "category_code": registration.category_code,
                "class_level": registration.class_level,
            }
        )

    rule_set = None
    if event.start_numbers_rule_set:
        try:
            rule_set = json.loads(event.start_numbers_rule_set)
        except json.JSONDecodeError:
            rule_set = event.start_numbers_rule_set

    return render_template(
        "admin/start_numbers.html",
        event=event,
        rows=rows,
        rule_set=rule_set,
        admin_key=request.args.get("key", ""),
    )


@start_numbers_admin_bp.post("/admin/events/<int:event_id>/startnumbers/generate")
@_require_admin_key
def start_numbers_generate(event_id):
    mode = request.form.get("mode", "RANDOM")
    club_name = request.form.get("club_name")
    random_club_first = request.form.get("random_club_first") == "on"
    seed = request.form.get("seed")
    club_prio = None
    if mode == "CLUB_PRIO":
        if random_club_first:
            club_prio = {"mode": "random_club_first"}
        else:
            club_prio = {"mode": "club_first", "club_name": club_name}
    generate_start_numbers(
        event_id=event_id,
        mode=mode,
        club_prio=club_prio,
        seed=int(seed) if seed else None,
    )
    return redirect(url_for("start_numbers_admin.start_numbers_home", event_id=event_id, key=request.args.get("key")))


@start_numbers_admin_bp.post("/admin/events/<int:event_id>/startnumbers/lock")
@_require_admin_key
def start_numbers_lock(event_id):
    lock_start_numbers(event_id)
    return redirect(url_for("start_numbers_admin.start_numbers_home", event_id=event_id, key=request.args.get("key")))


@start_numbers_admin_bp.post("/admin/events/<int:event_id>/startnumbers/unlock")
@_require_admin_key
def start_numbers_unlock(event_id):
    unlock_start_numbers(event_id)
    return redirect(url_for("start_numbers_admin.start_numbers_home", event_id=event_id, key=request.args.get("key")))


@start_numbers_admin_bp.post("/admin/events/<int:event_id>/startnumbers/set")
@_require_admin_key
def start_numbers_set(event_id):
    registration_id = request.form.get("registration_id", type=int)
    new_start_no = request.form.get("new_start_no", type=int)
    set_start_number_manual(event_id=event_id, registration_id=registration_id, new_start_no=new_start_no)
    return redirect(url_for("start_numbers_admin.start_numbers_home", event_id=event_id, key=request.args.get("key")))
