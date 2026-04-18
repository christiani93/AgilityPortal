from flask import Blueprint, render_template, redirect, url_for, flash, request
from flask_login import login_user, logout_user, login_required, current_user
from flask_babel import _
from app.extensions import db
from app.models import User, Person
from .forms import LoginForm, RegisterForm

auth_bp = Blueprint("auth", __name__, url_prefix="/auth")


@auth_bp.get("/login")
@auth_bp.post("/login")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("club.dashboard"))

    form = LoginForm()
    if form.validate_on_submit():
        user = db.session.execute(
            db.select(User).filter_by(email=form.email.data.strip().lower())
        ).scalar_one_or_none()

        if user and user.is_active and user.check_password(form.password.data):
            login_user(user, remember=form.remember.data)
            next_page = request.args.get("next")
            return redirect(next_page or url_for("club.dashboard"))

        flash(_("E-Mail oder Passwort ungültig."), "danger")

    return render_template("auth/login.html", form=form)


@auth_bp.get("/register")
@auth_bp.post("/register")
def register():
    if current_user.is_authenticated:
        return redirect(url_for("club.dashboard"))
    form = RegisterForm()
    if form.validate_on_submit():
        email = form.email.data.strip().lower()
        existing = db.session.execute(
            db.select(User).filter_by(email=email)
        ).scalar_one_or_none()
        if existing:
            flash(_("Diese E-Mail-Adresse ist bereits registriert."), "danger")
        else:
            user = User(
                email=email,
                first_name=form.first_name.data.strip(),
                last_name=form.last_name.data.strip(),
                role="handler",
                is_active=True,
            )
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.flush()
            person = Person(
                first_name=form.first_name.data.strip(),
                last_name=form.last_name.data.strip(),
                email=email,
            )
            db.session.add(person)
            db.session.flush()  # get person.id
            user.person_id = person.id
            db.session.commit()
            login_user(user)
            flash(_("Willkommen, %(name)s! Dein Konto wurde erstellt.", name=user.first_name), "success")
            return redirect(url_for("club.dashboard"))
    return render_template("auth/register.html", form=form)


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
