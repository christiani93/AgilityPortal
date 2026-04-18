import enum
import re
from datetime import datetime

from sqlalchemy import CheckConstraint, event
from sqlalchemy.orm import validates
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import UserMixin

from .extensions import db


class LicenseKind(enum.Enum):
    CH = "CH"
    FOREIGN = "FOREIGN"


class DogOwnerRole(enum.Enum):
    OWNER = "OWNER"
    CO_OWNER = "CO_OWNER"
    HANDLER = "HANDLER"


class AuthorizationStatus(enum.Enum):
    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


class RegistrationStatus(enum.Enum):
    PENDING = "PENDING"
    SUBMITTED = "SUBMITTED"
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"


class TkaMasterStatus(enum.Enum):
    PENDING = "PENDING"
    IN_EXPORT = "IN_EXPORT"
    OK = "OK"
    ISSUE = "ISSUE"
    NOT_REQUIRED = "NOT_REQUIRED"


class TkaExportType(enum.Enum):
    MASTER_CHECK = "MASTER_CHECK"
    EVENT_CHECK = "EVENT_CHECK"


class TkaFindingKind(enum.Enum):
    CLASS_OR_CATEGORY_MISMATCH = "CLASS_OR_CATEGORY_MISMATCH"
    LICENSE_UNKNOWN = "LICENSE_UNKNOWN"
    LICENSE_INVALID = "LICENSE_INVALID"
    UNKNOWN_FORMAT = "UNKNOWN_FORMAT"


class TkaEventCheckStatus(enum.Enum):
    PENDING = "PENDING"
    IN_EXPORT = "IN_EXPORT"
    OK = "OK"
    ISSUE = "ISSUE"
    CLASS_CHANGED = "CLASS_CHANGED"
    AUTO_OK = "AUTO_OK"


class TkaIssueType(enum.Enum):
    DATA_MISMATCH = "DATA_MISMATCH"
    LICENSE_UNKNOWN = "LICENSE_UNKNOWN"
    LICENSE_INVALID = "LICENSE_INVALID"
    PARSER_UNKNOWN_FORMAT = "PARSER_UNKNOWN_FORMAT"


class BillingMode(enum.Enum):
    PORTAL = "PORTAL"
    ORGANIZER = "ORGANIZER"


# ---------------------------------------------------------------------------
# Verein
# ---------------------------------------------------------------------------

class Club(db.Model):
    """SKG-Verein. vereinsnummer ist die offizielle SKG-Nummer."""
    __tablename__ = "clubs"

    id = db.Column(db.Integer, primary_key=True)
    vereinsnummer = db.Column(db.String(20), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    phone = db.Column(db.String(50), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    users = db.relationship("User", back_populates="club")

    def __repr__(self):
        return f"<Club {self.vereinsnummer} {self.name}>"


# ---------------------------------------------------------------------------
# Benutzer (Portal-Login)
# ---------------------------------------------------------------------------

class User(UserMixin, db.Model):
    """
    Portal-Benutzer.
    role: 'club_admin' = Vereins-Admin, 'handler' = Hundeführer, None = allgemein
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    role = db.Column(db.String(20), nullable=True)        # club_admin / handler
    first_name = db.Column(db.String(100), nullable=True)
    last_name = db.Column(db.String(100), nullable=True)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    club = db.relationship("Club", back_populates="users")

    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=True)
    person = db.relationship("Person", foreign_keys=[person_id])

    @property
    def dogs(self):
        if not self.person:
            return []
        return [owner.dog for owner in self.person.owners]

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash or "", password)

    @property
    def full_name(self):
        if self.first_name or self.last_name:
            return f"{self.first_name or ''} {self.last_name or ''}".strip()
        return self.email

    @property
    def is_superadmin(self):
        return self.role == "superadmin"

    @property
    def is_club_admin(self):
        return self.role in ("club_admin", "superadmin")

    @property
    def can_manage_club(self):
        """True wenn der User Turniere verwalten darf (club_admin oder superadmin)."""
        return self.role in ("club_admin", "superadmin")

    @property
    def is_handler_role(self):
        return self.role == "handler"


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    external_id = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owners = db.relationship("DogOwner", back_populates="person")


class Dog(db.Model):
    __tablename__ = "dogs"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    license_no = db.Column(db.String(50), unique=True, nullable=False)
    license_kind = db.Column(db.Enum(LicenseKind, name="license_kind"), nullable=False)
    foreign_country_code = db.Column(db.String(3))
    external_id = db.Column(db.String(64), unique=True)
    tka_master_status = db.Column(
        db.Enum(TkaMasterStatus, name="tka_master_status"),
        default=TkaMasterStatus.PENDING,
        nullable=False,
    )
    tka_category_confirmed = db.Column(db.String(20))
    tka_master_checked_at = db.Column(db.DateTime)
    tka_issue_message = db.Column(db.Text)
    category = db.Column(db.String(1), nullable=True)   # L / I / M / S
    class_level = db.Column(db.Integer, nullable=True)  # 1 / 2 / 3
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    owners = db.relationship("DogOwner", back_populates="dog", cascade="all, delete-orphan")
    authorizations = db.relationship(
        "DogAuthorization", back_populates="dog", cascade="all, delete-orphan"
    )

    @staticmethod
    def _validate_license_format(license_kind, license_no):
        if license_kind == LicenseKind.CH:
            if not re.fullmatch(r"\d+", license_no or ""):
                raise ValueError("CH license number must contain digits only.")
        if license_kind == LicenseKind.FOREIGN:
            if not re.fullmatch(r"[A-Z]{3}-[A-Za-z0-9]+", license_no or ""):
                raise ValueError("FOREIGN license number must match AAA-... format.")

    def apply_license_kind_defaults(self):
        if self.license_kind == LicenseKind.FOREIGN:
            self.tka_master_status = TkaMasterStatus.NOT_REQUIRED
        elif self.license_kind == LicenseKind.CH:
            if self.tka_master_status is None or self.tka_master_status == TkaMasterStatus.NOT_REQUIRED:
                self.tka_master_status = TkaMasterStatus.PENDING

    @validates("license_no")
    def _validate_license_no(self, key, value):
        if self.license_kind is not None:
            self._validate_license_format(self.license_kind, value)
        if self.license_kind == LicenseKind.FOREIGN and value:
            self.foreign_country_code = value.split("-", 1)[0]
        return value

    @validates("license_kind")
    def _validate_license_kind(self, key, value):
        if self.license_no is not None:
            self._validate_license_format(value, self.license_no)
        if value == LicenseKind.FOREIGN and self.license_no:
            self.foreign_country_code = self.license_no.split("-", 1)[0]
        self.apply_license_kind_defaults()
        return value


class DogOwner(db.Model):
    __tablename__ = "dog_owners"

    id = db.Column(db.Integer, primary_key=True)
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    role = db.Column(db.Enum(DogOwnerRole, name="dog_owner_role"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="owners")
    person = db.relationship("Person", back_populates="owners")


class DogAuthorization(db.Model):
    __tablename__ = "dog_authorizations"

    id = db.Column(db.Integer, primary_key=True)
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    status = db.Column(
        db.Enum(AuthorizationStatus, name="authorization_status"),
        default=AuthorizationStatus.PENDING,
        nullable=False,
    )
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    dog = db.relationship("Dog", back_populates="authorizations")
    person = db.relationship("Person")


class Event(db.Model):
    """
    Agility-Turnier/Veranstaltung.

    type:
        regular        — normales Vereinsturnier
        sm             — Schweizermeisterschaft Einzel
        asmv_quali     — ASMV-Qualifikation
        asmv_final     — ASMV-Final
        eo_quali       — EO-Qualifikation
        wm_quali       — WM-Qualifikation
        sao_quali      — SAO-Qualifikation
        jao_quali      — JAO-Qualifikation

    special_ruleset: Spezialturniere mit Zusatzreglement
        halloween_cup, advents_cup, edelweiss_challenge, ...

    status:
        draft    — in Vorbereitung
        open     — Anmeldungen offen
        closed   — Anmeldungen geschlossen
        cancelled — abgesagt

    TKAMO-Fristen (automatisch prüfen):
        -14 Tage: Richterangaben vollständig → sonst gesperrt
        -3 Tage:  Zeitplan für Teilnehmer publiziert
        +0 Tage:  Lizenz-Check + Resultate gleichentags einreichen
    """
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    external_id = db.Column(db.String(64), unique=True)

    # TKAMO-Felder
    ais_turniernummer = db.Column(db.Integer, unique=True, nullable=True)
    type = db.Column(db.String(20), default="regular", nullable=False)
    special_ruleset = db.Column(db.String(50), nullable=True)
    status = db.Column(db.String(20), default="draft", nullable=False)
    organiser_club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"), nullable=True)
    pruefungsleiter = db.Column(db.String(255), nullable=True)
    judge_id = db.Column(db.Integer, db.ForeignKey("judges.id"), nullable=True)
    judge2_id = db.Column(db.Integer, db.ForeignKey("judges.id"), nullable=True)
    allows_bitches_in_season = db.Column(db.Boolean, default=False, nullable=False)
    is_breed_restricted = db.Column(db.Boolean, default=False, nullable=False)
    registration_open_at = db.Column(db.DateTime, nullable=True)
    registration_close_at = db.Column(db.DateTime, nullable=True)
    lizenzcheck_done_at = db.Column(db.DateTime, nullable=True)
    results_submitted_at = db.Column(db.DateTime, nullable=True)

    # Billing
    billing_mode = db.Column(
        db.Enum(BillingMode, name="billing_mode"),
        default=BillingMode.ORGANIZER,
        nullable=False,
    )
    billing_notes = db.Column(db.Text)

    # Sichtbarkeits-Flags
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    startlist_public = db.Column(db.Boolean, default=False, nullable=False)
    schedule_public = db.Column(db.Boolean, default=False, nullable=False)
    results_public = db.Column(db.Boolean, default=False, nullable=False)

    # Sperr-Flags
    start_numbers_locked = db.Column(db.Boolean, default=False, nullable=False)
    start_numbers_generated_at = db.Column(db.DateTime)
    start_numbers_rule_set = db.Column(db.Text)
    schedule_locked = db.Column(db.Boolean, default=False, nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    organiser_club = db.relationship("Club", foreign_keys=[organiser_club_id])
    judge = db.relationship("Judge", foreign_keys=[judge_id])
    judge2 = db.relationship("Judge", foreign_keys=[judge2_id])
    event_judges = db.relationship(
        "EventJudge",
        back_populates="event",
        order_by="EventJudge.id",
        cascade="all, delete-orphan",
    )
    runs = db.relationship(
        "EventRun",
        back_populates="event",
        order_by="EventRun.run_type, EventRun.category, EventRun.class_level",
        cascade="all, delete-orphan",
    )

    TYPE_LABELS = {
        "regular": "Reguläres Turnier",
        "sm": "Schweizermeisterschaft",
        "asmv_quali": "ASMV-Qualifikation",
        "asmv_final": "ASMV-Final",
        "eo_quali": "EO-Qualifikation",
        "wm_quali": "WM-Qualifikation",
        "sao_quali": "SAO-Qualifikation",
        "jao_quali": "JAO-Qualifikation",
    }

    SPECIAL_RULESET_LABELS = {
        "halloween_cup": "Halloween Cup",
        "advents_cup": "Advents Cup",
        "edelweiss_challenge": "Edelweiss Challenge",
    }

    @property
    def is_qualifier(self):
        return self.type in {"sm", "asmv_quali", "asmv_final",
                             "eo_quali", "wm_quali", "sao_quali", "jao_quali"}


# ---------------------------------------------------------------------------
# Läufe (Runs) eines Turniers
# ---------------------------------------------------------------------------

class EventRun(db.Model):
    """
    Ein einzelner Lauf innerhalb eines Turniers.

    run_type: agility | jumping | open
    category: S | M | I | L  (Small / Medium / Intermediate / Large)
    class_level: 1 | 2 | 3
    """
    __tablename__ = "event_runs"
    __table_args__ = (
        db.UniqueConstraint("event_id", "run_type", "category", "class_level",
                            name="uq_event_run"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    run_type = db.Column(db.String(20), nullable=False)   # agility / jumping / open
    category = db.Column(db.String(5), nullable=False)    # S / M / I / L
    class_level = db.Column(db.Integer, nullable=False)   # 1 / 2 / 3
    judge_id = db.Column(db.Integer, db.ForeignKey("judges.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    event = db.relationship("Event", back_populates="runs")
    judge = db.relationship("Judge")

    RUN_TYPE_LABELS = {
        "agility": "Agility",
        "jumping": "Jumping",
        "open": "Open",
    }

    CATEGORY_LABELS = {
        "S": "Small",
        "M": "Medium",
        "I": "Intermediate",
        "L": "Large",
    }

    @property
    def label(self):
        type_label = self.RUN_TYPE_LABELS.get(self.run_type, self.run_type)
        cat_label = self.CATEGORY_LABELS.get(self.category, self.category)
        return f"{type_label} – {cat_label} – Klasse {self.class_level}"


# ---------------------------------------------------------------------------
# Anwesende Richter eines Turniers
# ---------------------------------------------------------------------------

class EventJudge(db.Model):
    """Welche Richter sind an einem Turnier anwesend."""
    __tablename__ = "event_judges"
    __table_args__ = (
        db.UniqueConstraint("event_id", "judge_id", name="uq_event_judge"),
    )

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    judge_id = db.Column(db.Integer, db.ForeignKey("judges.id"), nullable=False)

    event = db.relationship("Event", back_populates="event_judges")
    judge = db.relationship("Judge")


# ---------------------------------------------------------------------------
# Anfragen (neuer Richter / neuer Verein)
# ---------------------------------------------------------------------------

class PendingRequest(db.Model):
    """
    Anfrage eines Benutzers an den Superadmin.
    request_type: 'judge' | 'club'
    status: 'pending' | 'approved' | 'rejected'
    """
    __tablename__ = "pending_requests"

    id = db.Column(db.Integer, primary_key=True)
    request_type = db.Column(db.String(10), nullable=False)   # judge / club
    status = db.Column(db.String(10), default="pending", nullable=False)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Richter-Felder
    judge_ais_id = db.Column(db.Integer, nullable=True)
    judge_first_name = db.Column(db.String(100), nullable=True)
    judge_last_name = db.Column(db.String(100), nullable=True)

    # Verein-Felder
    club_vereinsnummer = db.Column(db.String(20), nullable=True)
    club_name = db.Column(db.String(255), nullable=True)

    # Notizen
    note = db.Column(db.Text, nullable=True)          # Einreicher
    admin_note = db.Column(db.Text, nullable=True)    # Superadmin

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    resolved_at = db.Column(db.DateTime, nullable=True)

    submitted_by = db.relationship("User")

    @property
    def display_title(self):
        if self.request_type == "judge":
            return f"Richter: {self.judge_first_name} {self.judge_last_name}"
        return f"Verein: {self.club_vereinsnummer} {self.club_name}"


class Registration(db.Model):
    __tablename__ = "registrations"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"), nullable=False)
    handler_id = db.Column(db.Integer, db.ForeignKey("people.id"))
    external_id = db.Column(db.String(64), unique=True)
    club_name = db.Column(db.String(200))
    status = db.Column(
        db.Enum(RegistrationStatus, name="registration_status"),
        default=RegistrationStatus.PENDING,
        nullable=False,
    )
    class_level = db.Column(db.Integer, nullable=False)
    category_code = db.Column(db.String(20), nullable=False)
    tka_event_check_status = db.Column(
        db.Enum(TkaEventCheckStatus, name="tka_event_check_status"),
        default=TkaEventCheckStatus.PENDING,
        nullable=False,
    )
    verified_license_no = db.Column(db.String(50))
    verified_category_code = db.Column(db.String(20))
    verified_class_level = db.Column(db.Integer)
    verified_dog_name = db.Column(db.String(120))
    tka_issue_type = db.Column(db.Enum(TkaIssueType, name="tka_issue_type"))
    tka_issue_message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    event = db.relationship("Event")
    dog = db.relationship("Dog")
    handler = db.relationship("Person")

    __table_args__ = (
        CheckConstraint("class_level in (1, 2, 3)", name="ck_registrations_class_level"),
        CheckConstraint(
            "category_code in ('Small','Medium','Intermediate','Large')",
            name="ck_registrations_category_code",
        ),
    )

    def apply_license_kind_defaults(self):
        if self.dog and self.dog.license_kind == LicenseKind.FOREIGN:
            self.tka_event_check_status = TkaEventCheckStatus.AUTO_OK


class TkaExportBatch(db.Model):
    __tablename__ = "tka_export_batches"

    id = db.Column(db.Integer, primary_key=True)
    export_type = db.Column(db.Enum(TkaExportType, name="tka_export_type"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    exported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    rows = db.relationship("TkaExportRow", back_populates="batch", cascade="all, delete-orphan")


class TkaExportRow(db.Model):
    __tablename__ = "tka_export_rows"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("tka_export_batches.id"), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey("registrations.id"))
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"))
    license_no = db.Column(db.String(50), nullable=False)
    category_code = db.Column(db.String(20), nullable=False)
    class_level = db.Column(db.Integer, nullable=False)
    payload = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    batch = db.relationship("TkaExportBatch", back_populates="rows")
    registration = db.relationship("Registration")
    dog = db.relationship("Dog")


class TkaImport(db.Model):
    __tablename__ = "tka_imports"

    id = db.Column(db.Integer, primary_key=True)
    batch_id = db.Column(db.Integer, db.ForeignKey("tka_export_batches.id"), nullable=False)
    imported_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    imported_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    raw_text = db.Column(db.Text)
    source = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    findings = db.relationship("TkaFinding", back_populates="tka_import", cascade="all, delete-orphan")


class TkaFinding(db.Model):
    __tablename__ = "tka_findings"

    id = db.Column(db.Integer, primary_key=True)
    tka_import_id = db.Column(db.Integer, db.ForeignKey("tka_imports.id"), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey("registrations.id"))
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"))
    license_no = db.Column(db.String(50))
    finding_kind = db.Column(db.Enum(TkaFindingKind, name="tka_finding_kind"), nullable=False)
    issue_type = db.Column(db.Enum(TkaIssueType, name="tka_issue_type"), nullable=False)
    import_category_code = db.Column(db.String(20))
    import_class_level = db.Column(db.Integer)
    system_category_code = db.Column(db.String(20))
    system_class_level = db.Column(db.Integer)
    raw_message = db.Column(db.Text)
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    tka_import = db.relationship("TkaImport", back_populates="findings")
    registration = db.relationship("Registration")
    dog = db.relationship("Dog")


class ExchangeExportLog(db.Model):
    __tablename__ = "exchange_export_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    export_type = db.Column(db.String(50), nullable=False)
    schema = db.Column(db.String(100), nullable=False)
    file_path = db.Column(db.String(255))
    sha256 = db.Column(db.String(64))
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class LiveUpdate(db.Model):
    __tablename__ = "live_updates"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    event_external_id = db.Column(db.String(64), index=True, nullable=False)
    source_system = db.Column(db.String(100), nullable=False)
    source_version = db.Column(db.String(50))
    source_device = db.Column(db.String(100), index=True, nullable=False)
    sent_at = db.Column(db.DateTime)
    sequence_no = db.Column(db.Integer, nullable=False)
    payload_json = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint(
            "event_external_id",
            "source_device",
            "sequence_no",
            name="uq_live_updates_event_device_seq",
        ),
    )


class ResultImport(db.Model):
    __tablename__ = "result_imports"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    schema = db.Column(db.String(100), nullable=False)
    exported_at = db.Column(db.DateTime)
    final = db.Column(db.Boolean, default=False, nullable=False)
    zip_path = db.Column(db.String(255))
    sha256 = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Result(db.Model):
    __tablename__ = "results"

    id = db.Column(db.Integer, primary_key=True)
    result_import_id = db.Column(db.Integer, db.ForeignKey("result_imports.id"), nullable=False)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"))
    ring = db.Column(db.String(50))
    discipline = db.Column(db.String(100))
    category_code = db.Column(db.String(20))
    class_level = db.Column(db.Integer)
    run_no = db.Column(db.Integer)
    registration_external_id = db.Column(db.String(64), index=True)
    start_no = db.Column(db.Integer)
    rank = db.Column(db.Integer)
    time_s = db.Column(db.Float)
    faults = db.Column(db.Integer)
    refusals = db.Column(db.Integer)
    eliminated = db.Column(db.Boolean)
    status = db.Column(db.String(50))
    dog_name = db.Column(db.String(120))
    handler_name = db.Column(db.String(120))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Document(db.Model):
    __tablename__ = "documents"

    id = db.Column(db.Integer, primary_key=True)
    result_import_id = db.Column(db.Integer, db.ForeignKey("result_imports.id"), nullable=False)
    kind = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(255), nullable=False)
    path = db.Column(db.String(255), nullable=False)
    sha256 = db.Column(db.String(64))
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class StartNumber(db.Model):
    __tablename__ = "start_numbers"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False)
    registration_id = db.Column(db.Integer, db.ForeignKey("registrations.id"), nullable=False)
    start_no = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        db.UniqueConstraint("event_id", "registration_id", name="uq_start_numbers_event_reg"),
        db.UniqueConstraint("event_id", "start_no", name="uq_start_numbers_event_start_no"),
    )


class ScheduleBlock(db.Model):
    __tablename__ = "schedule_blocks"

    id = db.Column(db.Integer, primary_key=True)
    event_id = db.Column(db.Integer, db.ForeignKey("events.id"), nullable=False, index=True)
    ring = db.Column(db.String(50), default="Ring 1", nullable=False)
    start_at = db.Column(db.DateTime, index=True)
    discipline = db.Column(db.String(20), nullable=False)
    category_code = db.Column(db.String(20), nullable=False)
    class_level = db.Column(db.Integer, nullable=False)
    notes = db.Column(db.Text)
    sort_index = db.Column(db.Integer, index=True, nullable=False, default=0)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        CheckConstraint("class_level in (1, 2, 3)", name="ck_schedule_blocks_class_level"),
        CheckConstraint(
            "category_code in ('Small','Medium','Intermediate','Large')",
            name="ck_schedule_blocks_category_code",
        ),
    )


@event.listens_for(Dog, "before_insert")
@event.listens_for(Dog, "before_update")
def _apply_dog_license_kind_defaults(mapper, connection, target):
    if target.license_kind and target.license_no:
        Dog._validate_license_format(target.license_kind, target.license_no)
    target.apply_license_kind_defaults()


# ---------------------------------------------------------------------------
# Richter
# ---------------------------------------------------------------------------

class Judge(db.Model):
    """TKAMO-Richter. ais_judge_id ist die offizielle AIS-Richternummer."""
    __tablename__ = "judges"

    id = db.Column(db.Integer, primary_key=True)
    ais_judge_id = db.Column(db.Integer, unique=True, nullable=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"

    def __repr__(self):
        return f"<Judge {self.ais_judge_id} {self.full_name}>"


# ---------------------------------------------------------------------------
# ASMV-Stafette (vorbereitet — wird aktiviert wenn normale Turniere laufen)
# ---------------------------------------------------------------------------

class AsmvTeam(db.Model):
    """
    ASMV-Mannschaft für die Stafette.
    team_id ist die offizielle TKAMO ASMV-Mannschaftsnummer.
    """
    __tablename__ = "asmv_teams"

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    club_id = db.Column(db.Integer, db.ForeignKey("clubs.id"), nullable=True)
    kategorie = db.Column(db.String(20), nullable=False)  # Large/Medium/Small
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    club = db.relationship("Club")
    members = db.relationship("AsmvTeamMember", back_populates="team",
                              cascade="all, delete-orphan")

    def __repr__(self):
        return f"<AsmvTeam {self.team_id} {self.name}>"


class AsmvTeamMember(db.Model):
    """Mitglied einer ASMV-Mannschaft (Person + Hund)."""
    __tablename__ = "asmv_team_members"
    __table_args__ = (
        db.UniqueConstraint("team_id", "person_id", name="uq_asmv_team_person"),
    )

    id = db.Column(db.Integer, primary_key=True)
    team_id = db.Column(db.Integer, db.ForeignKey("asmv_teams.id"), nullable=False)
    person_id = db.Column(db.Integer, db.ForeignKey("people.id"), nullable=False)
    dog_id = db.Column(db.Integer, db.ForeignKey("dogs.id"), nullable=True)
    is_substitute = db.Column(db.Boolean, default=False, nullable=False)

    team = db.relationship("AsmvTeam", back_populates="members")
    person = db.relationship("Person")
    dog = db.relationship("Dog")

    def __repr__(self):
        return f"<AsmvTeamMember team={self.team_id} person={self.person_id}>"
