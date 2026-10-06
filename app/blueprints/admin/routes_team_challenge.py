"""
Admin-Routen für die Team-Challenge (2er-Team-Sonderformat).

Hier bildet der Veranstalter die Teams aus bereits erfassten Registrations:
je 2 Starter derselben Grössenkategorie, einer läuft Agility, der andere
Jumping. Level (soft = Kl. 1+2 / expert = Kl. 3) ergibt sich aus den Klassen
der beiden Mitglieder.

Die so gebildeten Teams reisen später (Sync-Phase P3/P4, noch offen) im
Event-Paket zur AgilitySoftware, die am Turniertag führend ist. Abgeglichen
wird über `Team.external_id`.

Zugriff: via ADMIN_KEY (gleiche Authentifizierung wie die übrigen Admin-Routen).
Konzept: KONZEPT_Team-Challenge.md (§3, §7).
"""
from functools import wraps

from flask import (Blueprint, abort, flash, redirect, render_template,
                   request, url_for, current_app)
from flask_login import current_user

from app.extensions import db
from app.models import Event, Registration, Team


team_admin_bp = Blueprint("team_admin", __name__)


def _require_admin_key(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
            return func(*args, **kwargs)
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)
    return wrapper


def _admin_key():
    if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
        return ""
    return request.args.get("key") or ""


# ── Helfer ──────────────────────────────────────────────────────────────────

def _registration_label(reg: Registration) -> str:
    dog = reg.dog
    handler = reg.handler
    handler_name = (
        f"{handler.first_name} {handler.last_name}".strip() if handler else ""
    )
    dog_name = dog.name if dog else ""
    license_no = dog.license_no if dog else ""
    return f"{handler_name} mit {dog_name} ({license_no})".strip()


def _used_registration_ids(event_id: int, exclude_team_id: int | None = None) -> set:
    """IDs aller Registrations, die schon in einem Team dieses Events stecken."""
    q = Team.query.filter_by(event_id=event_id)
    if exclude_team_id is not None:
        q = q.filter(Team.id != exclude_team_id)
    used = set()
    for t in q.all():
        used.add(t.member_agility_registration_id)
        used.add(t.member_jumping_registration_id)
    used.discard(None)
    return used


def _eligible_registrations(event_id: int, category_code: str, level: str,
                            exclude_team_id: int | None = None) -> list:
    """Registrations, die zu (Grösse, Level) passen und noch frei sind."""
    allowed = Team.CLASS_LEVELS_BY_LEVEL.get(level, [])
    if not allowed:
        return []
    used = _used_registration_ids(event_id, exclude_team_id)
    regs = (
        Registration.query
        .filter_by(event_id=event_id, category_code=category_code)
        .filter(Registration.class_level.in_(allowed))
        .all()
    )
    regs = [r for r in regs if r.id not in used]
    regs.sort(key=lambda r: _registration_label(r).lower())
    return regs


def _validate_team(event_id, category_code, level, agi_id, jump_id,
                   exclude_team_id=None) -> str | None:
    if category_code not in Team.CATEGORIES:
        return "Ungültige Grössenkategorie."
    if level not in Team.LEVELS:
        return "Ungültiges Level."
    if not agi_id or not jump_id:
        return "Beide Mitglieder (Agility + Jumping) sind Pflicht."
    if agi_id == jump_id:
        return "Die beiden Teammitglieder müssen unterschiedliche Starter sein."

    allowed = Team.CLASS_LEVELS_BY_LEVEL.get(level, [])
    used = _used_registration_ids(event_id, exclude_team_id)
    for reg_id, role in ((agi_id, "Agility"), (jump_id, "Jumping")):
        reg = db.session.get(Registration, reg_id)
        if reg is None or reg.event_id != event_id:
            return f"Starter ({role}) gehört nicht zu diesem Event."
        if reg_id in used:
            return f"Starter ({role}) ist bereits einem anderen Team zugeordnet."
        if reg.category_code != category_code:
            return (f"Starter ({role}, {reg.category_code}) passt nicht zur "
                    f"Grösse {category_code}.")
        if reg.class_level not in allowed:
            return (f"Starter ({role}, Klasse {reg.class_level}) passt nicht zu "
                    f"Level {level} (Kl. {'/'.join(str(c) for c in allowed)}).")
    return None


# ── Routen ────────────────────────────────────────────────────────────────

@team_admin_bp.get("/admin/events/<int:event_id>/teams")
@_require_admin_key
def team_config(event_id):
    event = db.get_or_404(Event, event_id)

    teams = (
        Team.query.filter_by(event_id=event_id)
        .order_by(Team.category_code, Team.level, Team.id)
        .all()
    )
    # Teams gruppiert für die 8 Blöcke (Grösse × Level)
    grouped = {}
    for t in teams:
        grouped.setdefault((t.category_code, t.level), []).append(t)
    ordered_groups = [
        (cat, lvl) for cat in Team.CATEGORIES for lvl in Team.LEVELS
    ]

    # Freie Registrations je (Grösse, Level) als JSON fürs Formular (JS-Filter)
    eligible_json = {
        f"{cat}|{lvl}": [
            {"id": r.id, "label": _registration_label(r)}
            for r in _eligible_registrations(event_id, cat, lvl)
        ]
        for cat in Team.CATEGORIES for lvl in Team.LEVELS
    }

    return render_template(
        "admin/team_challenge/config.html",
        event=event,
        teams=teams,
        grouped=grouped,
        ordered_groups=ordered_groups,
        eligible_json=eligible_json,
        categories=Team.CATEGORIES,
        levels=Team.LEVELS,
        level_labels=Team.LEVEL_LABELS,
        registration_label=_registration_label,
        admin_key=_admin_key(),
    )


@team_admin_bp.post("/admin/events/<int:event_id>/teams/add")
@_require_admin_key
def team_add(event_id):
    event = db.get_or_404(Event, event_id)
    category_code = (request.form.get("category_code") or "").strip()
    level = (request.form.get("level") or "").strip()
    agi_id = request.form.get("member_agility_registration_id", type=int)
    jump_id = request.form.get("member_jumping_registration_id", type=int)
    name = (request.form.get("name") or "").strip() or None

    error = _validate_team(event_id, category_code, level, agi_id, jump_id)
    if error:
        flash(error, "danger")
    else:
        team = Team(
            event_id=event_id,
            name=name,
            category_code=category_code,
            level=level,
            member_agility_registration_id=agi_id,
            member_jumping_registration_id=jump_id,
            source="portal",
        )
        db.session.add(team)
        db.session.commit()
        flash("Team hinzugefügt.", "success")
    return redirect(url_for("team_admin.team_config", event_id=event_id, key=_admin_key()))


@team_admin_bp.post("/admin/events/<int:event_id>/teams/<int:team_id>/delete")
@_require_admin_key
def team_delete(event_id, team_id):
    team = db.session.get(Team, team_id)
    if team and team.event_id == event_id:
        db.session.delete(team)
        db.session.commit()
        flash("Team entfernt.", "info")
    return redirect(url_for("team_admin.team_config", event_id=event_id, key=_admin_key()))
