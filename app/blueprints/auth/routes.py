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
            first = form.first_name.data.strip()
            last = form.last_name.data.strip()
            # Existiert diese E-Mail bereits als Teilnehmer (Person) OHNE eigenen
            # Account (z.B. aus AOA-Import/Anmeldung), übernehmen wir den
            # bestehenden Datensatz, statt ein Duplikat anzulegen — so bleiben
            # Hunde/Anmeldungen am Konto hängen. Abgleich über E-Mail + Name
            # (case-insensitive), damit bei einer Familien-Sammelmail der/die
            # Registrierende die EIGENE Person trifft und nicht die eines
            # Angehörigen.
            existing_person = db.session.execute(
                db.select(Person).filter(
                    db.func.lower(Person.email) == email,
                    db.func.lower(Person.first_name) == first.lower(),
                    db.func.lower(Person.last_name) == last.lower(),
                    Person.account_user_id.is_(None),
                ).order_by(Person.id)
            ).scalars().first()
            if existing_person:
                existing_person.account_user_id = user.id
                person = existing_person
                _linked = True
            else:
                person = Person(
                    first_name=first,
                    last_name=last,
                    email=email,
                    account_user_id=user.id,
                )
                db.session.add(person)
                db.session.flush()  # get person.id
                _linked = False
            user.person_id = person.id
            db.session.commit()
            login_user(user)
            if _linked:
                flash(_("Willkommen, %(name)s! Dein Konto wurde mit deinem "
                        "bestehenden Teilnehmer-Profil verknüpft.",
                        name=user.first_name), "success")
            else:
                flash(_("Willkommen, %(name)s! Dein Konto wurde erstellt.",
                        name=user.first_name), "success")
            return redirect(url_for("club.dashboard"))
    return render_template("auth/register.html", form=form)


@auth_bp.get("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("auth.login"))
