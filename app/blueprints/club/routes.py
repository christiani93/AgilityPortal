from functools import wraps

from flask import Blueprint, render_template, redirect, url_for, flash, abort
from flask_login import login_required, current_user

from app.extensions import db
from app.models import User, Club, Event
from .forms import AddUserForm, ChangePasswordForm

club_bp = Blueprint("club", __name__, url_prefix="/club")


def club_admin_required(f):
    """Decorator: nur club_admin darf diese Route aufrufen."""
    @wraps(f)
    @login_required
    def decorated(*args, **kwargs):
        if not current_user.is_club_admin:
            abort(403)
        return f(*args, **kwargs)
    return decorated


# ---------------------------------------------------------------------------
# Dashboard — für alle eingeloggten Vereinsbenutzer
# ---------------------------------------------------------------------------

@club_bp.get("/")
@login_required
def dashboard():
    club = current_user.club
    events = []
    if club:
        events = (
            db.session.execute(
                db.select(Event)
                .filter_by(organiser_club_id=club.id)
                .order_by(Event.starts_at.desc())
            )
            .scalars()
            .all()
        )
    return render_template("club/dashboard.html", club=club, events=events)


# ---------------------------------------------------------------------------
# Benutzerverwaltung — nur club_admin
# ---------------------------------------------------------------------------

@club_bp.get("/users")
@club_admin_required
def users():
    members = (
        db.session.execute(
            db.select(User)
            .filter_by(club_id=current_user.club_id)
            .order_by(User.last_name, User.first_name)
        )
        .scalars()
        .all()
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
                club_id=current_user.club_id,
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
    if not user or user.club_id != current_user.club_id:
        abort(404)
    if user.id == current_user.id:
        flash("Du kannst deinen eigenen Account nicht deaktivieren.", "danger")
        return redirect(url_for("club.users"))
    if user.is_club_admin:
        flash("Andere Club-Admins können nicht deaktiviert werden.", "danger")
        return redirect(url_for("club.users"))

    user.is_active = False
    db.session.commit()
    flash(f"{user.full_name} wurde deaktiviert.", "success")
    return redirect(url_for("club.users"))


@club_bp.post("/users/<int:user_id>/activate")
@club_admin_required
def activate_user(user_id):
    user = db.session.get(User, user_id)
    if not user or user.club_id != current_user.club_id:
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
    if not user or user.club_id != current_user.club_id:
        abort(404)

    form = ChangePasswordForm()
    if form.validate_on_submit():
        user.set_password(form.password.data)
        db.session.commit()
        flash(f"Passwort für {user.full_name} wurde geändert.", "success")
        return redirect(url_for("club.users"))

    return render_template("club/reset_password.html", form=form, member=user)
