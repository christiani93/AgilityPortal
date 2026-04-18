from functools import wraps

from datetime import datetime

from flask import Blueprint, render_template, redirect, url_for, flash, abort, request
from flask_login import login_required, current_user
from flask_babel import _

from app.extensions import db
from flask_mail import Message
from app.extensions import mail
from app.models import User, Club, Event, EventRun, EventJudge, Judge, PendingRequest, Person, Dog, DogOwner, DogOwnerRole, LicenseKind, Registration, RegistrationStatus
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

    # Teilnehmer ohne Vereinszuordnung: offene Turniere anzeigen
    if not current_user.club_id:
        open_events = db.session.execute(
            db.select(Event)
            .filter_by(status="open")
            .order_by(Event.starts_at)
        ).scalars().all()
        return render_template("club/participant_dashboard.html", open_events=open_events)

    club = _club_for_user()
    events = _events_for_club(club)
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
# Teilnehmer: Event-Ansicht & Anmeldung
# ---------------------------------------------------------------------------

_CATEGORY_CODE_MAP = {"L": "Large", "I": "Intermediate", "M": "Medium", "S": "Small"}


@club_bp.get("/events/<int:event_id>/view")
@club_bp.post("/events/<int:event_id>/view")
@login_required
def event_view(event_id):
    event = db.session.get(Event, event_id)
    if not event or event.status not in ("open", "closed", "cancelled"):
        abort(404)
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
    return render_template("club/event_view.html", event=event, form=form,
                           dogs=dogs, dogs_data=dogs_data, my_registrations=my_registrations,
                           deadline_passed=deadline_passed)


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

# Startnummern-Schema identisch zur AgilitySoftware
_START_NUMBER_SCHEMA = {
    "Large-3": 1300, "Large-2": 1200, "Large-1": 1100,
    "Intermediate-3": 2300, "Intermediate-2": 2200, "Intermediate-1": 2100,
    "Medium-3": 3300, "Medium-2": 3200, "Medium-1": 3100,
    "Small-3": 4300, "Small-2": 4200, "Small-1": 4100,
}


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
    confirmed = db.session.execute(
        db.select(Registration)
        .filter_by(event_id=event_id, status=RegistrationStatus.CONFIRMED)
        .order_by(Registration.category_code, Registration.class_level,
                  Registration.handler_id)
    ).scalars().all()
    # Zähler pro Kategorie-Klasse aus dem Schema
    counters = {k: v for k, v in _START_NUMBER_SCHEMA.items()}
    for reg in confirmed:
        key = f"{reg.category_code}-{reg.class_level}"
        if key in counters:
            reg.start_number = counters[key]
            counters[key] += 1
        else:
            # Fallback: nächste freie Nummer ab 9000
            reg.start_number = 9000 + confirmed.index(reg)
    db.session.commit()
    flash(_("Startnummern wurden vergeben."), "success")
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
