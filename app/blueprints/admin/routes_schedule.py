from datetime import datetime
from functools import wraps

from flask import Blueprint, abort, current_app, redirect, render_template, request, url_for

from app.models import Event
from app.services.schedule_service import (
    add_block,
    auto_generate_blocks_from_registrations,
    delete_block,
    list_blocks,
    lock_schedule,
    move_block,
    unlock_schedule,
    update_block,
)


schedule_admin_bp = Blueprint("schedule_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def _parse_datetime(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@schedule_admin_bp.get("/admin/events/<int:event_id>/schedule")
@_require_admin_key
def schedule_home(event_id):
    event = Event.query.get_or_404(event_id)
    blocks = list_blocks(event_id)
    return render_template(
        "admin/schedule.html",
        event=event,
        blocks=blocks,
        admin_key=request.args.get("key", ""),
    )


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/add")
@_require_admin_key
def schedule_add(event_id):
    data = {
        "ring": request.form.get("ring"),
        "start_at": _parse_datetime(request.form.get("start_at")),
        "discipline": request.form.get("discipline"),
        "category_code": request.form.get("category_code"),
        "class_level": request.form.get("class_level", type=int),
        "notes": request.form.get("notes"),
    }
    add_block(event_id, data)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/update")
@_require_admin_key
def schedule_update(event_id):
    block_id = request.form.get("block_id", type=int)
    data = {
        "ring": request.form.get("ring"),
        "start_at": _parse_datetime(request.form.get("start_at")),
        "discipline": request.form.get("discipline"),
        "category_code": request.form.get("category_code"),
        "class_level": request.form.get("class_level", type=int),
        "notes": request.form.get("notes"),
    }
    update_block(block_id, data)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/delete")
@_require_admin_key
def schedule_delete(event_id):
    block_id = request.form.get("block_id", type=int)
    delete_block(block_id)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/move")
@_require_admin_key
def schedule_move(event_id):
    block_id = request.form.get("block_id", type=int)
    direction = request.form.get("direction")
    move_block(block_id, direction)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/auto")
@_require_admin_key
def schedule_auto(event_id):
    auto_generate_blocks_from_registrations(event_id)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/lock")
@_require_admin_key
def schedule_lock(event_id):
    lock_schedule(event_id)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))


@schedule_admin_bp.post("/admin/events/<int:event_id>/schedule/unlock")
@_require_admin_key
def schedule_unlock(event_id):
    unlock_schedule(event_id)
    return redirect(url_for("schedule_admin.schedule_home", event_id=event_id, key=request.args.get("key")))
