from functools import wraps

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, Club, Event, EventRun, Judge
from .forms import AddUserForm, ChangePasswordForm, EventForm, EventRunForm

club_bp = Blueprint("club", __name__, url_prefix="/club")


def club_admin_required(f):
    """Decorator: nur club_admin oder superadmin darf diese Route aufrufen."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.can_manage_club:
            abort(403)
        return f(*args, **kwargs)
    return decorated


def _club_for_user():
    """Gibt den Club des aktuellen Users zurück, oder None bei superadmin."""
    if current_user.is_superadmin:
        return None
    return current_user.club


def _events_for_club(club):
    """Gibt Events für einen Club zurück, oder alle Events bei superadmin."""
    if current_user.is_superadmin:
        return (
            db.session.execute(
                db.select(Event).order_by(Event.starts_at.desc())
            ).scalars().all()
        )
    if not club:
        return []
    return (
        db.session.execute(
            db.select(Event)
            .filter_by(organiser_club_id=club.id)
            .order_by(Event.starts_at.desc())
        ).scalars().all()
    )


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@club_bp.get("/")
@login_required
def dashboard():
    club = _club_for_user()
    events = _events_for_club(club)

    # Superadmin: Vereinsübersicht statt einzelnem Vereins-Dashboard
    if current_user.is_superadmin:
        clubs = db.session.execute(
            db.select(Club).order_by(Club.name)
        ).scalars().all()
        return render_template("club/superadmin_dashboard.html", clubs=clubs, events=events)

    return render_template("club/dashboard.html", club=club, events=events)


# ---------------------------------------------------------------------------
# Benutzerverwaltung — club_admin oder superadmin
# ---------------------------------------------------------------------------

@club_bp.get("/users")
@club_admin_required
def users():
    if current_user.is_superadmin:
        # Superadmin sieht alle Benutzer
        members = (
            db.session.execute(
                db.select(User).order_by(User.last_name, User.first_name)
            ).scalars().all()
        )
    else:
        members = (
            db.session.execute(
                db.select(User)
                .filter_by(club_id=current_user.club_id)
                .order_by(User.last_name, User.first_name)
            ).scalars().all()
        )
    return render_template("club/users.html", members=members)


@club_bp.get("/users/add")
@club_bp.post("/users/add")
@club_admin_required
def add_user():
    form = AddUserForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()

        if existing:
            flash("Diese E-Mail-Adresse ist bereits registriert.", "danger")
        else:
            user = User(
                email=email,
                first_name=form.first_name.data.strip(),
                last_name=form.last_name.data.strip(),
                role=form.role.data,
                club_id=current_user.club_id,  # None bei superadmin
                is_active=True,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            flash(f"Benutzer {user.full_name} wurde erstellt.", "success")
            return redirect(url_for("club.users"))

    return render_template("club/add_user.html", form=form)


@club_bp.post("/users/<int:user_id>/deactivate")
@club_admin_required
def deactivate_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    # club_admin darf nur eigene Vereinsmitglieder verwalten
    if not current_user.is_superadmin and user.club_id != current_user.club_id:
        abort(404)
    if user.id == current_user.id:
        flash("Du kannst deinen eigenen Account nicht deaktivieren.", "danger")
        return redirect(url_for("club.users"))
    if user.is_superadmin:
        flash("Superadmin-Accounts können nicht deaktiviert werden.", "danger")
        return redirect(url_for("club.users"))

    user.is_active = False
    db.session.commit()
    flash(f"{user.full_name} wurde deaktiviert.", "success")
    return redirect(url_for("club.users"))


@club_bp.post("/users/<int:user_id>/activate")
@club_admin_required
def activate_user(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if not current_user.is_superadmin and user.club_id != current_user.club_id:
        abort(404)
    user.is_active = True
    db.session.commit()
    flash(f"{user.full_name} wurde aktiviert.", "success")
    return redirect(url_for("club.users"))


@club_bp.get("/users/<int:user_id>/password")
@club_bp.post("/users/<int:user_id>/password")
@club_admin_required
def reset_password(user_id):
    user = db.session.get(User, user_id)
    if not user:
        abort(404)
    if not current_user.is_superadmin and user.club_id != current_user.club_id:
        abort(404)

    form = ChangePasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(f"Passwort für {user.full_name} wurde geändert.", "success")
        return redirect(url_for("club.users"))

    return render_template("club/reset_password.html", form=form, member=user)


# ---------------------------------------------------------------------------
# Turnierverwaltung — alle angemeldeten Benutzer mit Club
# ---------------------------------------------------------------------------

def _assert_event_access(event):
    """Stellt sicher, dass der aktuelle User auf dieses Turnier zugreifen darf."""
    if current_user.is_superadmin:
        return
    if not current_user.club_id:
        abort(403)
    if event.organiser_club_id != current_user.club_id:
        abort(403)


def _fill_club_choices(form):
    """Befüllt form.club_id.choices für Superadmin."""
    clubs = db.session.execute(db.select(Club).order_by(Club.name)).scalars().all()
    form.club_id.choices = [(0, "— Verein wählen —")] + [(c.id, c.name) for c in clubs]


@club_bp.get("/events/new")
@club_bp.post("/events/new")
@login_required
def event_new():
    if not current_user.club_id and not current_user.is_superadmin:
        abort(403)
    form = EventForm()
    if current_user.is_superadmin:
        _fill_club_choices(form)
    else:
        del form.club_id  # Feld nicht anzeigen/validieren
    if form.validate_on_submit():
        if current_user.is_superadmin:
            club_id = form.club_id.data if form.club_id.data != 0 else None
        else:
            club_id = current_user.club_id
        starts = datetime.combine(form.starts_at.data, datetime.min.time())
        ends = (
            datetime.combine(form.ends_at.data, datetime.min.time())
            if form.ends_at.data else None
        )
        event = Event(
            ais_turniernummer=form.ais_turniernummer.data or None,
            name=form.name.data.strip(),
            location=form.location.data.strip() if form.location.data else None,
            starts_at=starts,
            ends_at=ends,
            organiser_club_id=club_id,
            type="regular",
            status="draft",
        )
        db.session.add(event)
        db.session.commit()
        flash(f"Turnier «{event.name}» wurde erstellt.", "success")
        return redirect(url_for("club.event_detail", event_id=event.id))
    return render_template("club/event_form.html", form=form, event=None,
                           is_superadmin=current_user.is_superadmin)


@club_bp.get("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    run_form = EventRunForm()
    judges = db.session.execute(
        db.select(Judge).order_by(Judge.last_name, Judge.first_name)
    ).scalars().all()
    return render_template("club/event_detail.html", event=event, run_form=run_form,
                           judges=judges)


@club_bp.get("/events/<int:event_id>/edit")
@club_bp.post("/events/<int:event_id>/edit")
@login_required
def event_edit(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    form = EventForm(obj=event)
    if current_user.is_superadmin:
        _fill_club_choices(form)
    else:
        del form.club_id
    # DateField erwartet date, nicht datetime
    if request.method == "GET":
        form.starts_at.data = event.starts_at.date() if event.starts_at else None
        form.ends_at.data = event.ends_at.date() if event.ends_at else None
        if current_user.is_superadmin:
            form.club_id.data = event.organiser_club_id or 0
    if form.validate_on_submit():
        event.ais_turniernummer = form.ais_turniernummer.data or None
        event.name = form.name.data.strip()
        event.location = form.location.data.strip() if form.location.data else None
        event.starts_at = datetime.combine(form.starts_at.data, datetime.min.time())
        event.ends_at = (
            datetime.combine(form.ends_at.data, datetime.min.time())
            if form.ends_at.data else None
        )
        if current_user.is_superadmin:
            event.organiser_club_id = form.club_id.data if form.club_id.data != 0 else None
        db.session.commit()
        flash("Turnier gespeichert.", "success")
        return redirect(url_for("club.event_detail", event_id=event.id))
    return render_template("club/event_form.html", form=form, event=event,
                           is_superadmin=current_user.is_superadmin)


@club_bp.post("/events/<int:event_id>/runs/add")
@login_required
def event_run_add(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    form = EventRunForm()
    if form.validate_on_submit():
        existing = db.session.execute(
            db.select(EventRun).filter_by(
                event_id=event_id,
                run_type=form.run_type.data,
                category=form.category.data,
                class_level=int(form.class_level.data),
            )
        ).scalar_one_or_none()
        if existing:
            flash("Dieser Lauf ist bereits vorhanden.", "warning")
        else:
            db.session.add(EventRun(
                event_id=event_id,
                run_type=form.run_type.data,
                category=form.category.data,
                class_level=int(form.class_level.data),
            ))
            db.session.commit()
            flash("Lauf hinzugefügt.", "success")
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/events/<int:event_id>/runs/<int:run_id>/judge")
@login_required
def event_run_set_judge(event_id, run_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    run = db.session.get(EventRun, run_id)
    if not run or run.event_id != event_id:
        abort(404)
    judge_id = request.form.get("judge_id", type=int)
    run.judge_id = judge_id if judge_id and judge_id != 0 else None
    db.session.commit()
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/events/<int:event_id>/runs/<int:run_id>/delete")
@login_required
def event_run_delete(event_id, run_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    run = db.session.get(EventRun, run_id)
    if not run or run.event_id != event_id:
        abort(404)
    db.session.delete(run)
    db.session.commit()
    flash("Lauf entfernt.", "success")
    return redirect(url_for("club.event_detail", event_id=event_id))
