from functools import wraps
import io
import json as _json
import zipfile

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request, Response
from flask_login import login_required, current_user
from flask_babel import _

from app.extensions import db
from flask_mail import Message
from app.extensions import mail
from app.models import User, Club, Event, EventRun, EventJudge, Judge, PendingRequest, Person, Dog, DogOwner, DogOwnerRole, LicenseKind, Registration, RegistrationStatus, ScheduleBlock, LiveUpdate, Result, ResultImport
from .forms import AddUserForm, ChangePasswordForm, EventForm, EventRunForm, JudgeRequestForm, ClubRequestForm, DogForm, DogClassForm, EventRegistrationForm


def _send_notify(subject, body):
    """Sendet eine Benachrichtigungs-E-Mail an info@z-b.tech."""
    from flask import current_app
    try:
        if not current_app.config.get("MAIL_SERVER"):
            current_app.logger.warning("E-Mail: MAIL_SERVER nicht konfiguriert.")
            return
        notify_email = current_app.config.get("NOTIFY_EMAIL", "info@z-b.tech")
        msg = Message(subject=subject, recipients=[notify_email], body=body)
        mail.send(msg)
    except BaseException as e:
        current_app.logger.warning(f"E-Mail konnte nicht gesendet werden: {e}")

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
    # Superadmin: Vereinsübersicht
    if current_user.is_superadmin:
        clubs = db.session.execute(db.select(Club).order_by(Club.name)).scalars().all()
        events = _events_for_club(None)
        pending_count = db.session.execute(
            db.select(db.func.count()).select_from(PendingRequest).filter_by(status="pending")
        ).scalar()
        return render_template("club/superadmin_dashboard.html", clubs=clubs, events=events,
                               pending_count=pending_count)

    # Teilnehmer ohne Vereinszuordnung: offene Turniere + eigene Anmeldungen
    if not current_user.club_id:
        open_events = db.session.execute(
            db.select(Event)
            .filter_by(status="open", is_test=False)
            .order_by(Event.starts_at)
        ).scalars().all()
        # Eigene Anmeldungen (alle nicht-stornierten, neueste zuerst)
        my_registrations = []
        if current_user.person_id:
            my_registrations = db.session.execute(
                db.select(Registration)
                .filter_by(handler_id=current_user.person_id)
                .filter(Registration.status != RegistrationStatus.CANCELLED)
                .order_by(Registration.created_at.desc())
            ).scalars().all()
        return render_template("club/participant_dashboard.html",
                               open_events=open_events,
                               my_registrations=my_registrations)

    club = _club_for_user()
    events = _events_for_club(club)
    return render_template("club/dashboard.html", club=club, events=events)


# ---------------------------------------------------------------------------
# Superadmin: Server-Einstellungen (API-Keys einsehen)
# ---------------------------------------------------------------------------

@club_bp.get("/admin/settings")
@login_required
def admin_settings():
    """Superadmin-Seite: zeigt API-Keys und Sync-Status (empfangene Updates)."""
    if not current_user.is_superadmin:
        abort(403)
    from flask import current_app
    keys = {
        "LIVE_API_KEY":    current_app.config.get("LIVE_API_KEY", ""),
        "RESULTS_API_KEY": current_app.config.get("RESULTS_API_KEY", ""),
        "ADMIN_KEY":       current_app.config.get("ADMIN_KEY", ""),
    }
    # Letzte 10 Live-Updates (neueste zuerst) — mit geparstem Preview
    import json as _json2
    recent_live_raw = (
        db.session.execute(
            db.select(LiveUpdate).order_by(LiveUpdate.created_at.desc()).limit(10)
        ).scalars().all()
    )
    recent_live = []
    for upd in recent_live_raw:
        preview = ""
        try:
            p = _json2.loads(upd.payload_json or "{}")
            r = p.get("result") or {}
            dog = r.get("dog_name") or ""
            handler = r.get("handler_name") or ""
            run = p.get("run_name") or ""
            platz = r.get("platz")
            parts = []
            if run:
                parts.append(run)
            if dog:
                parts.append(dog)
            if handler:
                parts.append(f"/ {handler}")
            if platz:
                parts.append(f"Pl.{platz}")
            preview = " · ".join(parts)
        except Exception:
            pass
        recent_live.append({"upd": upd, "preview": preview})

    # Letzte 5 Result-Imports
    recent_imports = (
        db.session.execute(
            db.select(ResultImport).order_by(ResultImport.created_at.desc()).limit(5)
        ).scalars().all()
    )
    return render_template("club/admin_settings.html", keys=keys,
                           recent_live=recent_live, recent_imports=recent_imports)


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
            flash(_("Diese E-Mail-Adresse ist bereits registriert."), "danger")
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
            flash(_("Benutzer %(name)s wurde erstellt.", name=user.full_name), "success")
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
        flash(_("Du kannst deinen eigenen Account nicht deaktivieren."), "danger")
        return redirect(url_for("club.users"))
    if user.is_superadmin:
        flash(_("Superadmin-Accounts können nicht deaktiviert werden."), "danger")
        return redirect(url_for("club.users"))

    user.is_active = False
    db.session.commit()
    flash(_("%(name)s wurde deaktiviert.", name=user.full_name), "success")
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
    flash(_("%(name)s wurde aktiviert.", name=user.full_name), "success")
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
        flash(_("Passwort für %(name)s wurde geändert.", name=user.full_name), "success")
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


@club_bp.post("/events/create-test")
@login_required
def create_test_event_web():
    """Erstellt eine Testveranstaltung mit Standardläufen direkt aus dem Dashboard."""
    if not current_user.is_superadmin:
        abort(403)

    from datetime import date, timedelta
    from .schedule_utils import ring_names as _ring_names
    from app.models import (EventRun, Registration, RegistrationStatus,
                             Person, Dog, DogOwner, DogOwnerRole, LicenseKind,
                             TkaMasterStatus)

    name     = (request.form.get("name") or "Testturnier").strip()
    count    = max(1, min(50, request.form.get("count", 5, type=int)))
    club_id  = request.form.get("club_id", type=int) or None
    starts   = datetime.combine(date.today() + timedelta(days=7),
                                datetime.min.time())

    _CAT_MAP = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}
    _FIRST   = ["Anna","Lea","Sara","Laura","Nina","Julia","Maria","Sandra",
                "Klaus","Thomas","Peter","Stefan","Markus","Daniel","Michael","Andreas"]
    _LAST    = ["Müller","Meier","Schmid","Fischer","Weber","Keller","Huber",
                "Wolf","Zimmermann","Baumann","Moser","Frei","Brunner","Steiner"]
    _DOGS    = ["Ace","Bella","Charlie","Daisy","Echo","Finn","Grace","Hunter",
                "Ivy","Jake","Kira","Leo","Maya","Neo","Oreo","Pepper",
                "Quinn","Rex","Sky","Tara","Uma","Vega","Wren","Xena"]

    event = Event(
        name=name, starts_at=starts, ends_at=starts,
        status="open", is_test=True,
        organiser_club_id=club_id, type="regular", ring_count=1,
    )
    db.session.add(event)
    db.session.flush()

    # Alle Standard-Läufe anlegen (Agility + Jumping, alle Kategorien, Kl.1–3)
    run_count = 0
    for discipline in ("agility", "jumping"):
        for cat in ("L", "I", "M", "S"):
            for kl in (1, 2, 3):
                db.session.add(EventRun(event_id=event.id, run_type=discipline,
                                        category=cat, class_level=kl))
                run_count += 1
    db.session.flush()

    # Anmeldungen: eine pro (Kategorie, Klasse) — gilt für alle Disziplinen
    # (Agility + Jumping teilen sich denselben Teilnehmerkreis pro Kat./Klasse)
    n = 0
    for cat in ("L", "I", "M", "S"):
        for kl in (1, 2, 3):
            category_code = _CAT_MAP.get(cat, cat)
            for _i in range(count):
                n += 1
                person = Person(
                    first_name=_FIRST[(n - 1) % len(_FIRST)],
                    last_name=_LAST[(n - 1) % len(_LAST)],
                    email=f"test{n}@test.invalid",
                    external_id=f"TEST_{event.id}_{n:04d}",
                )
                db.session.add(person)
                db.session.flush()

                dog = Dog(
                    name=_DOGS[(n - 1) % len(_DOGS)],
                    license_no=f"TST-E{event.id:04d}N{n:05d}",
                    license_kind=LicenseKind.FOREIGN,
                    category=cat, class_level=kl,
                    tka_master_status=TkaMasterStatus.NOT_REQUIRED,
                    external_id=f"TESTDOG_{event.id}_{n:04d}",
                )
                db.session.add(dog)
                db.session.flush()

                db.session.add(DogOwner(dog_id=dog.id, person_id=person.id,
                                        role=DogOwnerRole.OWNER))
                db.session.add(Registration(
                    event_id=event.id, dog_id=dog.id, handler_id=person.id,
                    category_code=category_code, class_level=kl,
                    status=RegistrationStatus.CONFIRMED,
                    external_id=f"TESTREG_{event.id}_{n:04d}",
                ))

    db.session.commit()
    flash(_(
        "Testturnier «%(name)s» erstellt: %(runs)s Läufe, %(regs)s Anmeldungen.",
        name=name, runs=run_count, regs=n
    ), "success")
    return redirect(url_for("club.event_detail", event_id=event.id))


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
        close_at = (
            datetime.combine(form.registration_close_at.data, datetime.max.time().replace(microsecond=0))
            if form.registration_close_at.data else None
        )
        open_at = (
            datetime.combine(form.registration_open_at.data, datetime.min.time())
            if form.registration_open_at.data else None
        )
        event = Event(
            ais_turniernummer=form.ais_turniernummer.data or None,
            name=form.name.data.strip(),
            location=form.location.data.strip() if form.location.data else None,
            starts_at=starts,
            ends_at=ends,
            registration_open_at=open_at,
            registration_close_at=close_at,
            pruefungsleiter=form.pruefungsleiter.data.strip() if form.pruefungsleiter.data else None,
            max_participants=form.max_participants.data or None,
            entry_fee=form.entry_fee.data or None,
            allows_bitches_in_season=form.allows_bitches_in_season.data,
            bitches_in_season_start_last=form.bitches_in_season_start_last.data,
            notes_public=form.notes_public.data.strip() if form.notes_public.data else None,
            is_test=form.is_test.data,
            organiser_club_id=club_id,
            type="regular",
            status="draft",
        )
        db.session.add(event)
        db.session.commit()
        flash(_("Turnier «%(name)s» wurde erstellt.", name=event.name), "success")
        return redirect(url_for("club.event_detail", event_id=event.id))
    return render_template("club/event_form.html", form=form, event=None,
                           is_superadmin=current_user.is_superadmin)


_CATEGORY_SORT = {"L": 0, "I": 1, "M": 2, "S": 3}


@club_bp.get("/events/<int:event_id>")
@login_required
def event_detail(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    run_form = EventRunForm()
    # Läufe in Reihenfolge L→I→M→S sortieren
    sorted_runs = sorted(
        event.runs,
        key=lambda r: (r.run_type, _CATEGORY_SORT.get(r.category, 9), r.class_level)
    )
    # Alle verfügbaren Richter (für das Hinzufügen-Dropdown)
    present_judge_ids = {ej.judge_id for ej in event.event_judges}
    all_judges = db.session.execute(
        db.select(Judge).order_by(Judge.last_name, Judge.first_name)
    ).scalars().all()
    available_judges = [j for j in all_judges if j.id not in present_judge_ids]
    # Anmeldungen für Veranstalter
    registrations = db.session.execute(
        db.select(Registration).filter_by(event_id=event_id)
        .filter(Registration.status != RegistrationStatus.CANCELLED)
        .order_by(Registration.category_code, Registration.class_level)
    ).scalars().all() if not current_user.is_handler_role else []
    return render_template("club/event_detail.html", event=event, run_form=run_form,
                           sorted_runs=sorted_runs, available_judges=available_judges,
                           registrations=registrations)


@club_bp.post("/events/<int:event_id>/judges/add")
@login_required
def event_judge_add(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    judge_id = request.form.get("judge_id", type=int)
    if judge_id:
        existing = db.session.execute(
            db.select(EventJudge).filter_by(event_id=event_id, judge_id=judge_id)
        ).scalar_one_or_none()
        if not existing:
            db.session.add(EventJudge(event_id=event_id, judge_id=judge_id))
            db.session.commit()
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/events/<int:event_id>/judges/<int:judge_id>/remove")
@login_required
def event_judge_remove(event_id, judge_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    ej = db.session.execute(
        db.select(EventJudge).filter_by(event_id=event_id, judge_id=judge_id)
    ).scalar_one_or_none()
    if ej:
        # Läufe dieses Richters auf "nicht zugewiesen" setzen
        for run in event.runs:
            if run.judge_id == judge_id:
                run.judge_id = None
        db.session.delete(ej)
        db.session.commit()
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/events/<int:event_id>/delete")
@login_required
def event_delete(event_id):
    if not current_user.is_superadmin:
        abort(403)
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    # Manuell löschen was nicht via cascade abgedeckt ist
    db.session.execute(
        db.delete(Registration).where(Registration.event_id == event_id)
    )
    db.session.execute(
        db.delete(ScheduleBlock).where(ScheduleBlock.event_id == event_id)
    )
    name = event.name
    db.session.delete(event)   # cascaded: EventRun, EventJudge
    db.session.commit()
    flash(_("Turnier «%(name)s» wurde gelöscht.", name=name), "success")
    return redirect(url_for("club.dashboard"))


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
        form.registration_open_at.data = event.registration_open_at.date() if event.registration_open_at else None
        form.registration_close_at.data = event.registration_close_at.date() if event.registration_close_at else None
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
        event.registration_open_at = (
            datetime.combine(form.registration_open_at.data, datetime.min.time())
            if form.registration_open_at.data else None
        )
        event.registration_close_at = (
            datetime.combine(form.registration_close_at.data, datetime.max.time().replace(microsecond=0))
            if form.registration_close_at.data else None
        )
        event.pruefungsleiter = form.pruefungsleiter.data.strip() if form.pruefungsleiter.data else None
        event.max_participants = form.max_participants.data or None
        event.entry_fee = form.entry_fee.data or None
        event.allows_bitches_in_season = form.allows_bitches_in_season.data
        event.bitches_in_season_start_last = form.bitches_in_season_start_last.data
        event.notes_public = form.notes_public.data.strip() if form.notes_public.data else None
        event.is_test = form.is_test.data
        if current_user.is_superadmin:
            event.organiser_club_id = form.club_id.data if form.club_id.data != 0 else None
        db.session.commit()
        flash(_("Turnier gespeichert."), "success")
        return redirect(url_for("club.event_detail", event_id=event.id))
    return render_template("club/event_form.html", form=form, event=event,
                           is_superadmin=current_user.is_superadmin)


@club_bp.post("/events/<int:event_id>/status")
@login_required
def event_set_status(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    new_status = request.form.get("status")
    # Erlaubte Übergänge
    transitions = {
        "draft":     ["open", "cancelled"],
        "open":      ["closed", "cancelled"],
        "closed":    ["open", "cancelled"],
        "cancelled": ["draft"],
    }
    if new_status in transitions.get(event.status, []):
        event.status = new_status
        db.session.commit()
        labels = {"open": _("geöffnet"), "closed": _("geschlossen"),
                  "cancelled": _("abgesagt"), "draft": _("auf Entwurf zurückgesetzt")}
        flash(_("Turnier wurde %(status)s.", status=labels.get(new_status, new_status)), "success")
    else:
        flash(_("Ungültiger Statuswechsel."), "danger")
    return redirect(url_for("club.event_detail", event_id=event_id))


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
            flash(_("Dieser Lauf ist bereits vorhanden."), "warning")
        else:
            db.session.add(EventRun(
                event_id=event_id,
                run_type=form.run_type.data,
                category=form.category.data,
                class_level=int(form.class_level.data),
            ))
            db.session.commit()
            flash(_("Lauf hinzugefügt."), "success")
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
    flash(_("Lauf entfernt."), "success")
    return redirect(url_for("club.event_detail", event_id=event_id))


# ---------------------------------------------------------------------------
# Anfragen (neuer Richter / neuer Verein)
# ---------------------------------------------------------------------------

@club_bp.get("/requests/judge")
@club_bp.post("/requests/judge")
@login_required
def request_judge():
    """Club-Admin stellt Anfrage für neuen Richter."""
    if not current_user.can_manage_club:
        abort(403)
    form = JudgeRequestForm()
    if form.validate_on_submit():
        db.session.add(PendingRequest(
            request_type="judge",
            submitted_by_id=current_user.id,
            judge_ais_id=form.judge_ais_id.data or None,
            judge_first_name=form.judge_first_name.data.strip(),
            judge_last_name=form.judge_last_name.data.strip(),
            note=form.note.data.strip() if form.note.data else None,
        ))
        db.session.commit()
        _send_notify(
            subject="[z-b Portal] Neue Richter-Anfrage",
            body=(
                f"Neuer Richter beantragt von {current_user.full_name} ({current_user.email}):\n\n"
                f"Name: {form.judge_first_name.data} {form.judge_last_name.data}\n"
                f"AIS-Nr.: {form.judge_ais_id.data or '—'}\n"
                f"Bemerkung: {form.note.data or '—'}\n\n"
                f"Prüfen: portal.z-b.tech/club/requests"
            ),
        )
        flash(_("Anfrage wurde gesendet. Der Administrator wird sie prüfen."), "success")
        return redirect(url_for("club.dashboard"))
    return render_template("club/request_judge.html", form=form)


@club_bp.get("/requests/club")
@club_bp.post("/requests/club")
@login_required
def request_club():
    """Teilnehmer stellt Anfrage für neuen Verein."""
    form = ClubRequestForm()
    if form.validate_on_submit():
        db.session.add(PendingRequest(
            request_type="club",
            submitted_by_id=current_user.id,
            club_vereinsnummer=form.club_vereinsnummer.data.strip(),
            club_name=form.club_name.data.strip(),
            note=form.note.data.strip() if form.note.data else None,
        ))
        db.session.commit()
        _send_notify(
            subject="[z-b Portal] Neue Verein-Anfrage",
            body=(
                f"Neuer Verein beantragt von {current_user.full_name} ({current_user.email}):\n\n"
                f"Vereinsnummer: {form.club_vereinsnummer.data}\n"
                f"Name: {form.club_name.data}\n"
                f"Bemerkung: {form.note.data or '—'}\n\n"
                f"Prüfen: portal.z-b.tech/club/requests"
            ),
        )
        flash(_("Anfrage wurde gesendet. Der Administrator wird sie prüfen."), "success")
        return redirect(url_for("club.dashboard"))
    return render_template("club/request_club.html", form=form)


@club_bp.get("/requests")
@login_required
def pending_requests():
    """Superadmin: alle offenen Anfragen."""
    if not current_user.is_superadmin:
        abort(403)
    requests_pending = db.session.execute(
        db.select(PendingRequest)
        .filter_by(status="pending")
        .order_by(PendingRequest.created_at)
    ).scalars().all()
    requests_done = db.session.execute(
        db.select(PendingRequest)
        .filter(PendingRequest.status != "pending")
        .order_by(PendingRequest.created_at.desc())
        .limit(20)
    ).scalars().all()
    return render_template("club/pending_requests.html",
                           requests_pending=requests_pending,
                           requests_done=requests_done)


@club_bp.post("/requests/<int:req_id>/approve")
@login_required
def request_approve(req_id):
    if not current_user.is_superadmin:
        abort(403)
    req = db.session.get(PendingRequest, req_id)
    if not req or req.status != "pending":
        abort(404)
    if req.request_type == "judge":
        db.session.add(Judge(
            ais_judge_id=req.judge_ais_id,
            first_name=req.judge_first_name,
            last_name=req.judge_last_name,
        ))
    elif req.request_type == "club":
        db.session.add(Club(
            vereinsnummer=req.club_vereinsnummer,
            name=req.club_name,
        ))
    req.status = "approved"
    req.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(_("Anfrage genehmigt und %(type)s erstellt.",
            type=(_("Richter") if req.request_type == "judge" else _("Verein"))), "success")
    return redirect(url_for("club.pending_requests"))


@club_bp.get("/requests/test-mail")
@login_required
def test_mail():
    if not current_user.is_superadmin:
        abort(403)
    from flask import current_app
    server = current_app.config.get("MAIL_SERVER", "")
    if not server:
        flash(_("MAIL_SERVER ist nicht in der .env konfiguriert."), "danger")
        return redirect(url_for("club.pending_requests"))
    try:
        notify_email = current_app.config.get("NOTIFY_EMAIL", "info@z-b.tech")
        msg = Message(
            subject="[z-b Portal] Testmail",
            recipients=[notify_email],
            body=(
                "Dies ist eine Testmail vom z-b Vereinsportal.\n\n"
                f"MAIL_SERVER: {server}\n"
                f"MAIL_PORT: {current_app.config.get('MAIL_PORT')}\n"
                f"MAIL_USERNAME: {current_app.config.get('MAIL_USERNAME')}\n"
            ),
        )
        mail.send(msg)
        flash(_("✓ Testmail erfolgreich an %(email)s gesendet (Server: %(server)s).", email=notify_email, server=server), "success")
    except BaseException as e:
        flash(_("✗ Fehler beim Senden: %(error)s", error=str(e)), "danger")
    return redirect(url_for("club.pending_requests"))


# ---------------------------------------------------------------------------
# Teilnehmer: Hunde verwalten
# ---------------------------------------------------------------------------

@club_bp.get("/profile/dogs")
@club_bp.post("/profile/dogs")
@login_required
def profile_dogs():
    if not current_user.person:
        # Person erstellen falls noch nicht vorhanden
        p = Person(first_name=current_user.first_name or "", last_name=current_user.last_name or "", email=current_user.email)
        db.session.add(p)
        db.session.flush()
        current_user.person_id = p.id
        db.session.commit()
    form = DogForm()
    if form.validate_on_submit():
        try:
            license_kind = LicenseKind[form.license_kind.data]
            license_no = form.license_no.data.strip()
            Dog._validate_license_format(license_kind, license_no)
            existing = db.session.execute(db.select(Dog).filter_by(license_no=license_no)).scalar_one_or_none()
            if existing:
                # Prüfen ob bereits verknüpft
                already = db.session.execute(
                    db.select(DogOwner).filter_by(dog_id=existing.id, person_id=current_user.person_id)
                ).scalar_one_or_none()
                if already:
                    flash(_("Du bist bereits mit diesem Hund verknüpft."), "info")
                else:
                    db.session.add(DogOwner(dog_id=existing.id, person_id=current_user.person_id, role=DogOwnerRole.HANDLER))
                    db.session.commit()
                    flash(_("Hund «%(name)s» wurde deinem Profil als Hundeführer hinzugefügt.", name=existing.name), "success")
                return redirect(url_for("club.profile_dogs"))
            else:
                dog = Dog(name=form.name.data.strip())
                dog.license_kind = license_kind
                dog.license_no = license_no
                db.session.add(dog)
                db.session.flush()
                db.session.add(DogOwner(dog_id=dog.id, person_id=current_user.person_id, role=DogOwnerRole.OWNER))
                db.session.commit()
                flash(_("Hund «%(name)s» wurde hinzugefügt.", name=dog.name), "success")
                return redirect(url_for("club.profile_dogs"))
        except ValueError as e:
            flash(_("Ungültige Lizenznummer: %(error)s", error=str(e)), "danger")
    dogs = current_user.dogs
    # Klassen-Formulare je Hund (prefill)
    class_forms = {}
    for dog in dogs:
        cf = DogClassForm(prefix=f"dog_{dog.id}")
        cf.category.data = dog.category or "L"
        cf.class_level.data = dog.class_level or 1
        class_forms[dog.id] = cf
    return render_template("club/profile_dogs.html", form=form, dogs=dogs, class_forms=class_forms)


@club_bp.post("/profile/dogs/<int:dog_id>/class")
@login_required
def dog_update_class(dog_id):
    if not current_user.person:
        abort(403)
    dog = db.session.get(Dog, dog_id)
    if not dog:
        abort(404)
    # Nur der Eigentümer darf die Klasse ändern
    owner = db.session.execute(
        db.select(DogOwner).filter_by(dog_id=dog_id, person_id=current_user.person_id, role=DogOwnerRole.OWNER)
    ).scalar_one_or_none()
    if not owner:
        abort(403)
    form = DogClassForm(prefix=f"dog_{dog_id}")
    if form.validate_on_submit():
        dog.category = form.category.data
        dog.class_level = int(form.class_level.data)
        # Alle offenen Anmeldungen dieses Hundes aktualisieren
        category_full = _CATEGORY_CODE_MAP.get(dog.category, dog.category)
        open_regs = db.session.execute(
            db.select(Registration).filter_by(dog_id=dog_id)
            .filter(Registration.status.in_([RegistrationStatus.PENDING, RegistrationStatus.SUBMITTED]))
        ).scalars().all()
        for reg in open_regs:
            reg.category_code = category_full
            reg.class_level = dog.class_level
        db.session.commit()
        if open_regs:
            flash(_("Klasse/Kategorie gespeichert. %(n)s offene Anmeldung(en) wurden aktualisiert.", n=len(open_regs)), "success")
        else:
            flash(_("Klasse/Kategorie gespeichert."), "success")
    return redirect(url_for("club.profile_dogs"))


# ---------------------------------------------------------------------------
# Teilnehmer: Event-Übersicht (öffentlich verlinkbar, kein Schedule)
# ---------------------------------------------------------------------------

@club_bp.get("/events/<int:event_id>/info")
@login_required
def event_info(event_id):
    """Teilnehmer-Eventseite: Turnierdaten + eigene Anmeldung + Startnummer + Live-Ergebnisse."""
    event = db.session.get(Event, event_id)
    if not event or event.status not in ("open", "closed", "cancelled"):
        abort(404)
    if event.is_test and not current_user.is_superadmin:
        abort(404)

    my_registrations = []
    if current_user.person_id:
        my_registrations = db.session.execute(
            db.select(Registration)
            .filter_by(event_id=event_id, handler_id=current_user.person_id)
            .filter(Registration.status != RegistrationStatus.CANCELLED)
        ).scalars().all()

    deadline_passed = (
        event.registration_close_at and event.registration_close_at < datetime.utcnow()
    )
    has_start_numbers = event.start_numbers_generated_at is not None

    # Live-Ergebnisse aus gespeichertem Result-Import (aktuellster Import pro Event)
    result_classes = []
    latest_import = (
        db.session.execute(
            db.select(ResultImport)
            .filter_by(event_id=event_id)
            .order_by(ResultImport.created_at.desc())
        ).scalars().first()
    )
    if latest_import:
        results_rows = (
            db.session.execute(
                db.select(Result)
                .filter_by(result_import_id=latest_import.id)
                .order_by(Result.ring, Result.discipline, Result.category_code, Result.class_level, Result.rank)
            ).scalars().all()
        )
        # Gruppieren nach Ring / Disziplin / Kategorie / Klasse
        from itertools import groupby
        def _class_key(r):
            return (r.ring or "", r.discipline or "", r.category_code or "", r.class_level or 0)
        for key, group in groupby(results_rows, key=_class_key):
            ring, disc, cat, cls = key
            rows = list(group)
            result_classes.append({
                "ring": ring,
                "discipline": disc,
                "category_code": cat,
                "class_level": cls,
                "results": rows,
                "final": latest_import.final,
            })

    return render_template("club/event_info.html",
                           event=event,
                           my_registrations=my_registrations,
                           deadline_passed=deadline_passed,
                           has_start_numbers=has_start_numbers,
                           result_classes=result_classes,
                           latest_import=latest_import)


# ---------------------------------------------------------------------------
# Teilnehmer: Abmelden & Läufig melden
# ---------------------------------------------------------------------------

@club_bp.post("/registrations/<int:reg_id>/cancel-own")
@login_required
def registration_cancel_own(reg_id):
    """Teilnehmer meldet sich selbst ab."""
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    # Nur eigene Anmeldungen
    if reg.handler_id != current_user.person_id:
        abort(403)
    # Nur PENDING oder CONFIRMED, und Nennschluss nicht abgelaufen
    deadline_passed = (
        reg.event.registration_close_at and
        reg.event.registration_close_at < datetime.utcnow()
    )
    if deadline_passed:
        flash(_("Nennschluss ist abgelaufen — Abmeldung nicht mehr möglich."), "danger")
        return redirect(url_for("club.event_info", event_id=reg.event_id))
    if reg.status not in (RegistrationStatus.PENDING, RegistrationStatus.CONFIRMED):
        flash(_("Diese Anmeldung kann nicht mehr storniert werden."), "danger")
        return redirect(url_for("club.event_info", event_id=reg.event_id))

    reg.status = RegistrationStatus.CANCELLED
    db.session.commit()
    flash(_("Abmeldung für %(dog)s wurde erfolgreich gespeichert.", dog=reg.dog.name), "success")
    return redirect(url_for("club.event_info", event_id=reg.event_id))


@club_bp.post("/registrations/<int:reg_id>/toggle-in-season")
@login_required
def registration_toggle_in_season(reg_id):
    """Teilnehmer meldet Hündin als läufig (oder hebt es auf)."""
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    if reg.handler_id != current_user.person_id:
        abort(403)
    if reg.status not in (RegistrationStatus.PENDING, RegistrationStatus.CONFIRMED):
        abort(403)
    # Turnier muss läufige Hündinnen erlauben
    if not reg.event.allows_bitches_in_season:
        flash(_("Dieses Turnier erlaubt keine läufigen Hündinnen."), "danger")
        return redirect(url_for("club.event_info", event_id=reg.event_id))

    reg.is_in_season = not reg.is_in_season
    db.session.commit()

    if reg.is_in_season:
        flash(_("%(dog)s als läufig gemeldet.", dog=reg.dog.name), "info")
    else:
        flash(_("Läufig-Meldung für %(dog)s aufgehoben.", dog=reg.dog.name), "info")
    return redirect(url_for("club.event_info", event_id=reg.event_id))


# ---------------------------------------------------------------------------
# Teilnehmer: Event-Ansicht & Anmeldung (Superadmin-Zeitplanansicht)
# ---------------------------------------------------------------------------

_CATEGORY_CODE_MAP = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}


@club_bp.get("/events/<int:event_id>/view")
@club_bp.post("/events/<int:event_id>/view")
@login_required
def event_view(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.status not in ("open", "closed", "cancelled"):
        abort(404)
    # Teilnehmeransicht nur für Superadmin
    if not current_user.is_superadmin:
        abort(403)
    form = EventRegistrationForm()
    dogs = current_user.dogs if current_user.person else []
    form.dog_id.choices = [(d.id, d.name) for d in dogs]
    # Für JS-Vorausfüllung: Kategorie + Klasse je Hund
    dogs_data = {
        d.id: {"category": d.category or "", "class_level": d.class_level or 1}
        for d in dogs
    }
    # Bestehende Anmeldungen des Users für dieses Event
    my_registrations = []
    if current_user.person:
        my_registrations = db.session.execute(
            db.select(Registration).filter_by(event_id=event_id, handler_id=current_user.person_id)
        ).scalars().all()
    deadline_passed = (
        event.registration_close_at and event.registration_close_at < datetime.utcnow()
    )

    # Zeitplan für Teilnehmer-Ansicht
    from .schedule_utils import (compute_detailed_segments, parse_ring_start_times,
                                  ring_names as _ring_names, auto_title, sort_key_category)
    sched_blocks = db.session.execute(
        db.select(ScheduleBlock).filter_by(event_id=event_id)
        .order_by(ScheduleBlock.ring, ScheduleBlock.sort_index)
    ).scalars().all()
    counts = _participant_counts_for_event(event_id)
    for b in sched_blocks:
        b._participant_count = counts.get((b.category_code, b.class_level), 0)
        b._display_title = b.title or auto_title(b.discipline, b.category_code, b.class_level)
    rings = _ring_names(event.ring_count or 1)
    start_times = parse_ring_start_times(event.ring_start_times)
    for r in rings:
        start_times.setdefault(r, "08:00")
    sched_by_ring = {r: [] for r in rings}
    for b in sched_blocks:
        if b.ring in sched_by_ring:
            sched_by_ring[b.ring].append(b)
    has_start_numbers = event.start_numbers_generated_at is not None
    sched_timeline = (
        compute_detailed_segments(sched_by_ring, start_times,
                                  event.starts_at.strftime("%Y-%m-%d") if event.starts_at
                                  else datetime.utcnow().strftime("%Y-%m-%d"),
                                  round_minutes=5,
                                  run_time_config=_get_run_time_config(event))
        if has_start_numbers else {}
    )

    if form.validate_on_submit():
        if event.status != "open" or deadline_passed:
            flash(_("Anmeldungen sind nicht mehr offen."), "danger")
            return redirect(url_for("club.event_view", event_id=event_id))
        if not current_user.person:
            flash(_("Bitte füge zuerst einen Hund in deinem Profil hinzu."), "warning")
            return redirect(url_for("club.profile_dogs"))
        dog = db.session.get(Dog, form.dog_id.data)
        if not dog or not dog.category:
            flash(_("Bitte hinterlege zuerst die Kategorie für diesen Hund in deinem Profil."), "warning")
            return redirect(url_for("club.profile_dogs"))
        # Prüfen ob bereits angemeldet (gleicher Hund)
        existing = db.session.execute(
            db.select(Registration).filter_by(event_id=event_id, dog_id=form.dog_id.data)
        ).scalar_one_or_none()
        if existing:
            flash(_("Dieser Hund ist für dieses Turnier bereits angemeldet."), "warning")
        else:
            new_class = int(form.class_level.data)
            category_full = _CATEGORY_CODE_MAP.get(dog.category, dog.category)
            # Klasse im Profil + alle anderen offenen Anmeldungen aktualisieren
            if dog.class_level != new_class:
                dog.class_level = new_class
                other_regs = db.session.execute(
                    db.select(Registration)
                    .filter(Registration.dog_id == dog.id,
                            Registration.event_id != event_id,
                            Registration.status.in_([RegistrationStatus.PENDING, RegistrationStatus.SUBMITTED]))
                ).scalars().all()
                for r in other_regs:
                    r.class_level = new_class
            reg = Registration(
                event_id=event_id,
                dog_id=form.dog_id.data,
                handler_id=current_user.person_id,
                category_code=category_full,
                class_level=new_class,
                is_in_season=form.is_in_season.data,
                status=RegistrationStatus.PENDING,
            )
            db.session.add(reg)
            db.session.commit()
            flash(_("Anmeldung erfolgreich."), "success")
            return redirect(url_for("club.event_view", event_id=event_id))
    sorted_runs = sorted(
        event.runs,
        key=lambda r: (r.run_type, _CATEGORY_SORT.get(r.category, 9), r.class_level)
    )
    return render_template("club/event_view.html", event=event, form=form,
                           dogs=dogs, dogs_data=dogs_data, my_registrations=my_registrations,
                           deadline_passed=deadline_passed,
                           sched_by_ring=sched_by_ring, rings=rings,
                           sched_timeline=sched_timeline,
                           has_start_numbers=has_start_numbers,
                           sorted_runs=sorted_runs)


@club_bp.post("/registrations/<int:reg_id>/cancel")
@login_required
def registration_cancel(reg_id):
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    if not current_user.person or reg.handler_id != current_user.person_id:
        abort(403)
    if reg.status == RegistrationStatus.CANCELLED:
        flash(_("Anmeldung ist bereits storniert."), "info")
    else:
        reg.status = RegistrationStatus.CANCELLED
        db.session.commit()
        flash(_("Anmeldung wurde storniert."), "success")
    return redirect(url_for("club.event_view", event_id=reg.event_id))


# ---------------------------------------------------------------------------
# Anmeldungen bestätigen / ablehnen (Veranstalter)
# ---------------------------------------------------------------------------

# Standard-Startnummernschema (xx01 = erster Starter pro Block)
_START_NUMBER_SCHEMA_DEFAULT = {
    "Large-1": 1101, "Large-2": 1201, "Large-3": 1301,
    "Intermediate-1": 2101, "Intermediate-2": 2201, "Intermediate-3": 2301,
    "Medium-1": 3101, "Medium-2": 3201, "Medium-3": 3301,
    "Small-1": 4101, "Small-2": 4201, "Small-3": 4301,
}

# Standard-Laufzeit in Sekunden pro Starter
_RUN_TIME_CONFIG_DEFAULT = {"agility": 65, "jumping": 60, "open": 65}


def _get_startnumber_schema(event) -> dict:
    """Gibt das Event-spezifische Schema zurück, oder den Default."""
    import json as _j
    if event.startnumber_schema:
        try:
            return {k: int(v) for k, v in _j.loads(event.startnumber_schema).items()}
        except Exception:
            pass
    return dict(_START_NUMBER_SCHEMA_DEFAULT)


def _get_run_time_config(event) -> dict:
    """Gibt die Event-spezifische Laufzeit-Konfiguration zurück, oder den Default."""
    import json as _j
    if event.run_time_config:
        try:
            return {k: int(v) for k, v in _j.loads(event.run_time_config).items()}
        except Exception:
            pass
    return dict(_RUN_TIME_CONFIG_DEFAULT)


@club_bp.post("/registrations/<int:reg_id>/confirm")
@login_required
def registration_confirm(reg_id):
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    _assert_event_access(reg.event)
    if reg.status == RegistrationStatus.PENDING:
        reg.status = RegistrationStatus.CONFIRMED
        db.session.commit()
        flash(_("Anmeldung bestätigt."), "success")
    return redirect(url_for("club.event_detail", event_id=reg.event_id))


@club_bp.post("/registrations/<int:reg_id>/reject")
@login_required
def registration_reject(reg_id):
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    _assert_event_access(reg.event)
    if reg.status != RegistrationStatus.CANCELLED:
        reg.status = RegistrationStatus.CANCELLED
        db.session.commit()
        flash(_("Anmeldung abgelehnt."), "success")
    return redirect(url_for("club.event_detail", event_id=reg.event_id))


@club_bp.post("/events/<int:event_id>/confirm-all")
@login_required
def event_confirm_all(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)
    pending = db.session.execute(
        db.select(Registration).filter_by(event_id=event_id, status=RegistrationStatus.PENDING)
    ).scalars().all()
    for reg in pending:
        reg.status = RegistrationStatus.CONFIRMED
    db.session.commit()
    flash(_("%(n)s Anmeldungen bestätigt.", n=len(pending)), "success")
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/events/<int:event_id>/assign-startnumbers")
@login_required
def event_assign_startnumbers(event_id):
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    MIN_GAP = 20   # Mindest-Lücke zwischen zwei Hunden desselben Handlers

    # ── Alle bestätigten Anmeldungen ─────────────────────────────────────────
    confirmed = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id, status=RegistrationStatus.CONFIRMED)
    ).scalars().all()

    # ── Globale Block-Reihenfolge aus Ring 1 (sort_index) ────────────────────
    # Jeder unique (category_code, class_level) erscheint nur einmal.
    ring1_blocks = db.session.execute(
        db.select(ScheduleBlock)
        .filter_by(event_id=event_id, ring="Ring 1")
        .filter(ScheduleBlock.block_type == "run")
        .order_by(ScheduleBlock.sort_index)
    ).scalars().all()

    seen_keys: set = set()
    ordered_keys: list = []
    for b in ring1_blocks:
        if b.category_code and b.class_level:
            key = (b.category_code, b.class_level)
            if key not in seen_keys:
                seen_keys.add(key)
                ordered_keys.append(key)

    # ── Anmeldungen nach (category_code, class_level) gruppieren ─────────────
    from collections import defaultdict
    regs_by_key: dict = defaultdict(list)
    for reg in confirmed:
        regs_by_key[(reg.category_code, reg.class_level)].append(reg)

    # Blöcke die nicht in Ring 1 stehen → hinten, alphabetisch sortiert
    for key in sorted(set(regs_by_key.keys()) - seen_keys):
        ordered_keys.append(key)

    # ── Gap-bewusste Platzierung ─────────────────────────────────────────────
    # handler_last_global: letzte globale Position des Handlers (für Lücken-Prüfung)
    handler_last_global: dict = {}   # handler_id → int
    schema   = _get_startnumber_schema(event)
    fallback = 9001
    global_offset = 0

    for key in ordered_keys:
        regs = regs_by_key.get(key, [])
        if not regs:
            continue

        n        = len(regs)
        cat, cls = key

        # Handler mit mehreren Hunden zuerst verarbeiten (mehr Spielraum nötig)
        handler_count: dict = defaultdict(int)
        for reg in regs:
            if reg.handler_id:
                handler_count[reg.handler_id] += 1

        # Sortierung: läufige Hündinnen ans Ende, Mehrfach-Handler zuerst,
        # dann handler_id für Stabilität
        sorted_regs = sorted(regs, key=lambda r: (
            r.is_in_season,
            -(handler_count.get(r.handler_id, 1)),
            r.handler_id or 0,
            r.id,
        ))

        placed: list = [None] * n

        for reg in sorted_regs:
            hid        = reg.handler_id
            last_global = handler_last_global.get(hid, -(MIN_GAP * 100))

            # Ersten freien Slot suchen, der die Mindestlücke einhält
            placed_ok = False
            for p in range(n):
                if placed[p] is not None:
                    continue
                if global_offset + p - last_global >= MIN_GAP:
                    placed[p] = reg
                    handler_last_global[hid] = global_offset + p
                    placed_ok = True
                    break

            if not placed_ok:
                # Lücke nicht einzuhalten (zu wenig Starter) → best effort:
                # kleinsten Abstand wählen
                best_p, best_gap = None, -1
                for p in range(n):
                    if placed[p] is not None:
                        continue
                    gap = global_offset + p - last_global
                    if gap > best_gap:
                        best_gap, best_p = gap, p
                if best_p is not None:
                    placed[best_p] = reg
                    handler_last_global[hid] = global_offset + best_p

        # Startnummern aus Schema zuweisen
        schema_key = f"{cat}-{cls}"
        base_nr    = schema.get(schema_key)

        for p, reg in enumerate(placed):
            if reg is None:
                continue
            reg.start_number = (base_nr + p) if base_nr is not None else fallback
            if base_nr is None:
                fallback += 1

        global_offset += n

    event.start_numbers_generated_at = datetime.utcnow()
    db.session.commit()
    flash(_("Startnummern wurden vergeben."), "success")
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.get("/events/<int:event_id>/export.zip")
@login_required
def event_export_zip(event_id):
    """Export eines Turniers als ZIP für den Import in die AgilitySoftware."""
    if not current_user.is_superadmin:
        abort(403)
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    from .schedule_utils import parse_ring_start_times

    # ── Bestätigte Anmeldungen ────────────────────────────────────────────────
    confirmed = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id, status=RegistrationStatus.CONFIRMED)
        .order_by(Registration.category_code, Registration.class_level,
                  Registration.start_number)
    ).scalars().all()

    # ── Disziplinen aus den Turnierläufen ─────────────────────────────────────
    disciplines = sorted({r.run_type for r in event.runs}) if event.runs else ["agility"]

    # ── external_id sicherstellen (für Rück-Zuordnung beim Result-Export) ──────
    if not event.external_id:
        import uuid as _uuid
        event.external_id = _uuid.uuid4().hex
        db.session.commit()

    # ── manifest.json ─────────────────────────────────────────────────────────
    manifest = {"schema": "agility.exchange.eventexport.v1"}

    # ── event.json ────────────────────────────────────────────────────────────
    event_payload = {
        "event": {
            "external_id":  event.external_id,
            "name":         event.name or "",
            "date":         event.starts_at.strftime("%Y-%m-%d") if event.starts_at else "",
            "club_number":  event.organiser_club.vereinsnummer if event.organiser_club else "",
            "event_number": event.ais_turniernummer or "",
            "location":     event.location or "",
        }
    }

    # ── entities.json ─────────────────────────────────────────────────────────
    handlers_seen: set = set()
    handlers_list = []
    dogs_list     = []

    for reg in confirmed:
        if reg.handler_id and reg.handler_id not in handlers_seen:
            handlers_seen.add(reg.handler_id)
            p = reg.handler
            if p:
                handlers_list.append({
                    "external_id": str(reg.handler_id),
                    "firstname":   p.first_name or "",
                    "lastname":    p.last_name  or "",
                })
        if reg.dog and reg.dog.license_no:
            dogs_list.append({
                "license_no":          reg.dog.license_no,
                "dog_name":            reg.dog.name or "",
                "handler_external_id": str(reg.handler_id) if reg.handler_id else "",
                "category_code":       reg.category_code or "",
                "class_level":         str(reg.class_level),
            })

    entities = {"handlers": handlers_list, "dogs": dogs_list}

    # ── registrations.json ────────────────────────────────────────────────────
    # Eine Zeile pro (Anmeldung × Disziplin), damit AgilitySoftware
    # je einen Lauf pro (Disziplin, Kategorie, Klasse) anlegt.
    registrations = []
    for reg in confirmed:
        for disc in disciplines:
            registrations.append({
                "registration_external_id": f"{reg.id}_{disc}",
                "license_no":               reg.dog.license_no if reg.dog else "",
                "dog_name":                 reg.dog.name       if reg.dog else "",
                "handler_first_name":       reg.handler.first_name if reg.handler else "",
                "handler_last_name":        reg.handler.last_name  if reg.handler else "",
                "discipline":               disc.capitalize(),   # "Agility" / "Jumping"
                "category_code":            reg.category_code or "",
                "class_level":              str(reg.class_level),
                "is_in_season":             reg.is_in_season,
            })

    # ── start_numbers.json ────────────────────────────────────────────────────
    has_numbers = event.start_numbers_generated_at is not None
    sn_entries  = []
    if has_numbers:
        for reg in confirmed:
            if reg.start_number and reg.dog and reg.dog.license_no:
                sn_entries.append({
                    "license_no": reg.dog.license_no,
                    "start_no":   reg.start_number,
                })
    start_numbers_payload = {"locked": has_numbers, "start_numbers": sn_entries}

    # ── schedule.json ─────────────────────────────────────────────────────────
    sched_blocks = db.session.execute(
        db.select(ScheduleBlock).filter_by(event_id=event_id)
        .order_by(ScheduleBlock.ring, ScheduleBlock.sort_index)
    ).scalars().all()

    schedule_blocks_out = []
    for b in sched_blocks:
        # Ring-Nummer aus "Ring 1", "Ring 2" extrahieren
        ring_num = 1
        for part in (b.ring or "").split():
            if part.isdigit():
                ring_num = int(part)
                break

        blk: dict = {
            "ring":       ring_num,
            "sort_index": b.sort_index,
            "block_type": b.block_type,
            "notes":      b.notes or "",
        }
        if b.block_type == "run":
            blk.update({
                "discipline":    b.discipline    or "",
                "category_code": b.category_code or "",
                "class_level":   str(b.class_level) if b.class_level else "",
            })
        else:  # rank_announcement
            blk.update({
                "title":            b.title or "Rangverkündigung",
                "duration_minutes": b.duration_minutes or 5,
            })
        schedule_blocks_out.append(blk)

    schedule_payload = {"blocks": schedule_blocks_out}

    # ── ZIP zusammenbauen ─────────────────────────────────────────────────────
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        def _add(name, obj):
            zf.writestr(name, _json.dumps(obj, ensure_ascii=False, indent=2))

        _add("manifest.json",      manifest)
        _add("event.json",         event_payload)
        _add("entities.json",      entities)
        _add("registrations.json", {"registrations": registrations})
        _add("start_numbers.json", start_numbers_payload)
        _add("schedule.json",      schedule_payload)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in (event.name or "event"))
    filename   = f"eventexport_{event_id}_{safe_name}.zip"

    return Response(
        buf.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@club_bp.get("/events/<int:event_id>/startlist")
def event_startlist(event_id):
    """Öffentliche Startliste — kein Login nötig, direkt verlinkbar."""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    # Kategorie-Reihenfolge
    CAT_ORDER = {"Large": 0, "Intermediate": 1, "Medium": 2, "Small": 3}

    # Alle bestätigten Anmeldungen mit vergebener Startnummer
    regs = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id, status=RegistrationStatus.CONFIRMED)
        .filter(Registration.start_number.isnot(None))
        .order_by(Registration.category_code, Registration.class_level,
                  Registration.start_number)
    ).scalars().all()

    # Nach (Kategorie, Klasse) gruppieren — in definierter Reihenfolge
    from collections import defaultdict
    groups: dict = defaultdict(list)
    for reg in regs:
        groups[(reg.category_code, reg.class_level)].append(reg)

    sorted_groups = sorted(
        groups.items(),
        key=lambda kv: (CAT_ORDER.get(kv[0][0], 9), kv[0][1])
    )

    has_numbers = event.start_numbers_generated_at is not None

    return render_template(
        "club/startlist.html",
        event=event,
        sorted_groups=sorted_groups,
        has_numbers=has_numbers,
    )


@club_bp.post("/events/<int:event_id>/reset-startnumbers")
@login_required
def event_reset_startnumbers(event_id):
    """Alle Startnummern löschen (nur Superadmin)."""
    if not current_user.is_superadmin:
        abort(403)
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    db.session.execute(
        db.update(Registration)
        .where(Registration.event_id == event_id)
        .values(start_number=None)
    )
    event.start_numbers_generated_at = None
    db.session.commit()
    flash(_("Startnummern wurden zurückgesetzt."), "warning")
    return redirect(url_for("club.event_detail", event_id=event_id))


@club_bp.post("/registrations/<int:reg_id>/startnumber")
@login_required
def registration_set_startnumber(reg_id):
    reg = db.session.get(Registration, reg_id)
    if not reg:
        abort(404)
    _assert_event_access(reg.event)
    new_nr = request.form.get("start_number", type=int)
    if new_nr and new_nr > 0:
        reg.start_number = new_nr
        db.session.commit()
    return redirect(url_for("club.event_detail", event_id=reg.event_id))


@club_bp.post("/requests/<int:req_id>/reject")
@login_required
def request_reject(req_id):
    if not current_user.is_superadmin:
        abort(403)
    req = db.session.get(PendingRequest, req_id)
    if not req or req.status != "pending":
        abort(404)
    req.status = "rejected"
    req.admin_note = request.form.get("admin_note", "").strip() or None
    req.resolved_at = datetime.utcnow()
    db.session.commit()
    flash(_("Anfrage abgelehnt."), "info")
    return redirect(url_for("club.pending_requests"))


# ---------------------------------------------------------------------------
# Zeitplan
# ---------------------------------------------------------------------------

def _participant_counts_for_event(event_id):
    """Gibt {(category_code, class_level): count} für PENDING/CONFIRMED-Anmeldungen zurück."""
    from sqlalchemy import func
    rows = db.session.execute(
        db.select(Registration.category_code, Registration.class_level, func.count())
        .filter(
            Registration.event_id == event_id,
            Registration.status.in_([RegistrationStatus.PENDING, RegistrationStatus.CONFIRMED])
        )
        .group_by(Registration.category_code, Registration.class_level)
    ).all()
    return {(r[0], r[1]): r[2] for r in rows}


@club_bp.get("/events/<int:event_id>/schedule")
@login_required
def event_schedule(event_id):
    import json as _json
    from .schedule_utils import compute_timeline, parse_ring_start_times, ring_names, auto_title

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    rings = ring_names(event.ring_count or 1)
    start_times = parse_ring_start_times(event.ring_start_times)
    for r in rings:
        start_times.setdefault(r, "08:00")

    # Alle ScheduleBlocks für dieses Event, sortiert
    all_blocks = db.session.execute(
        db.select(ScheduleBlock).filter_by(event_id=event_id)
        .order_by(ScheduleBlock.ring, ScheduleBlock.sort_index)
    ).scalars().all()

    # Teilnehmerzahlen pro Kategorie+Klasse
    counts = _participant_counts_for_event(event_id)
    for block in all_blocks:
        block._participant_count = counts.get((block.category_code, block.class_level), 0)
        if not block.title:
            block._display_title = auto_title(block.discipline, block.category_code, block.class_level)
        else:
            block._display_title = block.title

    # Blocks nach Ring gruppieren
    blocks_by_ring = {r: [] for r in rings}
    for block in all_blocks:
        if block.ring in blocks_by_ring:
            blocks_by_ring[block.ring].append(block)

    # Event-Konfiguration laden
    run_time_cfg   = _get_run_time_config(event)
    startnr_schema = _get_startnumber_schema(event)

    # Timeline berechnen
    event_date = event.starts_at.strftime("%Y-%m-%d") if event.starts_at else datetime.utcnow().strftime("%Y-%m-%d")
    timeline = compute_timeline(blocks_by_ring, start_times, event_date,
                                run_time_config=run_time_cfg)

    # Noch nicht eingeplante EventRuns — sortiert nach L→I→M→S, dann Klasse
    scheduled_keys = {
        (b.discipline, b.category_code, b.class_level) for b in all_blocks
    }
    unscheduled_runs = sorted(
        [r for r in event.runs
         if (r.run_type, _CATEGORY_CODE_MAP.get(r.category, r.category), r.class_level)
         not in scheduled_keys],
        key=lambda r: (r.run_type, _CATEGORY_SORT.get(r.category, 9), r.class_level)
    )

    # Richter des Turniers für den Dropdown
    event_judges = [ej.judge for ej in event.event_judges]

    return render_template(
        "club/schedule.html",
        event=event,
        rings=rings,
        start_times=start_times,
        blocks_by_ring=blocks_by_ring,
        timeline=timeline,
        unscheduled_runs=unscheduled_runs,
        event_judges=event_judges,
        run_time_cfg=run_time_cfg,
        startnr_schema=startnr_schema,
        sn_defaults=_START_NUMBER_SCHEMA_DEFAULT,
        rt_defaults=_RUN_TIME_CONFIG_DEFAULT,
    )


@club_bp.post("/events/<int:event_id>/schedule/rings")
@login_required
def schedule_save_rings(event_id):
    import json as _json
    from .schedule_utils import ring_names

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    ring_count = max(1, min(4, request.form.get("ring_count", 1, type=int)))
    event.ring_count = ring_count

    rings = ring_names(ring_count)
    times = {}
    for r in rings:
        key = f"start_{r.replace(' ', '_')}"
        val = (request.form.get(key) or "08:00").strip()
        try:
            datetime.strptime(val, "%H:%M")
        except ValueError:
            val = "08:00"
        times[r] = val
    event.ring_start_times = _json.dumps(times)
    db.session.commit()
    flash(_("Ringkonfiguration gespeichert."), "success")
    return redirect(url_for("club.event_schedule", event_id=event_id))


@club_bp.post("/events/<int:event_id>/schedule/settings")
@login_required
def schedule_save_settings(event_id):
    """Speichert Startnummern-Schema und Laufzeit-Konfiguration."""
    import json as _json

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    # ── Startnummern-Schema ────────────────────────────────────────────────
    schema = {}
    for cat in ("Large", "Intermediate", "Medium", "Small"):
        for kl in (1, 2, 3):
            key  = f"{cat}-{kl}"
            val  = request.form.get(f"sn_{cat}_{kl}", type=int)
            base = _START_NUMBER_SCHEMA_DEFAULT[key]
            schema[key] = val if val and val > 0 else base
    event.startnumber_schema = _json.dumps(schema)

    # ── Laufzeit pro Disziplin ─────────────────────────────────────────────
    run_cfg = {}
    for disc in ("agility", "jumping", "open"):
        val = request.form.get(f"rt_{disc}", type=int)
        default = _RUN_TIME_CONFIG_DEFAULT[disc]
        run_cfg[disc] = val if val and val > 0 else default
    event.run_time_config = _json.dumps(run_cfg)

    db.session.commit()
    flash(_("Einstellungen gespeichert."), "success")
    return redirect(url_for("club.event_schedule", event_id=event_id))


@club_bp.post("/events/<int:event_id>/schedule/add")
@login_required
def schedule_block_add(event_id):
    from .schedule_utils import auto_title

    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    block_type = request.form.get("block_type", "run")
    ring       = request.form.get("ring", "Ring 1")
    judge_id   = request.form.get("judge_id", type=int) or None
    title      = (request.form.get("title") or "").strip() or None

    max_idx = db.session.execute(
        db.select(db.func.max(ScheduleBlock.sort_index))
        .filter_by(event_id=event_id, ring=ring)
    ).scalar() or 0

    if block_type == "rank_announcement":
        block = ScheduleBlock(
            event_id=event_id,
            ring=ring,
            block_type="rank_announcement",
            discipline=None,
            category_code=None,
            class_level=None,
            duration_minutes=None,
            title=title or "Rangverkündigung",
            sort_index=max_idx + 10,
        )
    else:
        run_type    = request.form.get("run_type", "agility")
        category    = request.form.get("category", "L")
        class_level = request.form.get("class_level", 1, type=int)
        category_code = _CATEGORY_CODE_MAP.get(category, category)

        # Doppelt eintragen verhindern
        existing = db.session.execute(
            db.select(ScheduleBlock).filter_by(
                event_id=event_id, discipline=run_type,
                category_code=category_code, class_level=class_level
            )
        ).scalar_one_or_none()
        if existing:
            flash(_("Dieser Lauf ist bereits im Zeitplan."), "warning")
            return redirect(url_for("club.event_schedule", event_id=event_id))

        block = ScheduleBlock(
            event_id=event_id,
            ring=ring,
            block_type="run",
            discipline=run_type,
            category_code=category_code,
            class_level=class_level,
            judge_id=judge_id,
            title=title,
            sort_index=max_idx + 10,
        )

    db.session.add(block)
    db.session.commit()
    return redirect(url_for("club.event_schedule", event_id=event_id))


@club_bp.post("/events/<int:event_id>/schedule/blocks/<int:block_id>/delete")
@login_required
def schedule_block_delete(event_id, block_id):
    block = db.session.get(ScheduleBlock, block_id)
    if not block or block.event_id != event_id:
        abort(404)
    _assert_event_access(db.session.get(Event, event_id))
    db.session.delete(block)
    db.session.commit()
    return redirect(url_for("club.event_schedule", event_id=event_id))


@club_bp.post("/events/<int:event_id>/schedule/blocks/<int:block_id>/move")
@login_required
def schedule_block_move(event_id, block_id):
    block = db.session.get(ScheduleBlock, block_id)
    if not block or block.event_id != event_id:
        abort(404)
    _assert_event_access(db.session.get(Event, event_id))

    direction = request.form.get("direction", "down")
    ring_blocks = db.session.execute(
        db.select(ScheduleBlock)
        .filter_by(event_id=event_id, ring=block.ring)
        .order_by(ScheduleBlock.sort_index)
    ).scalars().all()

    idx = next((i for i, b in enumerate(ring_blocks) if b.id == block_id), None)
    if idx is None:
        return redirect(url_for("club.event_schedule", event_id=event_id))

    if direction == "up" and idx > 0:
        swap = ring_blocks[idx - 1]
        block.sort_index, swap.sort_index = swap.sort_index, block.sort_index
    elif direction == "down" and idx < len(ring_blocks) - 1:
        swap = ring_blocks[idx + 1]
        block.sort_index, swap.sort_index = swap.sort_index, block.sort_index

    db.session.commit()
    return redirect(url_for("club.event_schedule", event_id=event_id))


@club_bp.post("/events/<int:event_id>/schedule/order")
@login_required
def schedule_block_reorder(event_id):
    """AJAX: Speichert neue Reihenfolge nach Drag & Drop."""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    data = request.get_json(silent=True) or {}
    for ring_data in data.get("order", []):
        ring_name = ring_data.get("ring", "Ring 1")
        for idx, bid in enumerate(ring_data.get("blocks", [])):
            blk = db.session.get(ScheduleBlock, int(bid))
            if blk and blk.event_id == event_id:
                blk.ring       = ring_name
                blk.sort_index = idx * 10
    db.session.commit()
    return {"ok": True}
