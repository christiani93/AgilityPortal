import enum
import re
from datetime import datetime

from sqlalchemy import CheckConstraint, event
from sqlalchemy.orm import validates

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


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(255), unique=True, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


class Person(db.Model):
    __tablename__ = "people"

    id = db.Column(db.Integer, primary_key=True)
    first_name = db.Column(db.String(100), nullable=False)
    last_name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(255))
    phone = db.Column(db.String(50))
    external_id = db.Column(db.String(64), unique=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
        self._validate_license_format(self.license_kind, value)
        if self.license_kind == LicenseKind.FOREIGN and value:
            self.foreign_country_code = value.split("-", 1)[0]
        return value

    @validates("license_kind")
    def _validate_license_kind(self, key, value):
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
    person = db.relationship("Person")


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
    __tablename__ = "events"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    location = db.Column(db.String(200))
    starts_at = db.Column(db.DateTime)
    ends_at = db.Column(db.DateTime)
    external_id = db.Column(db.String(64), unique=True)
    billing_mode = db.Column(
        db.Enum(BillingMode, name="billing_mode"),
        default=BillingMode.ORGANIZER,
        nullable=False,
    )
    billing_notes = db.Column(db.Text)
    is_completed = db.Column(db.Boolean, default=False, nullable=False)
    is_published = db.Column(db.Boolean, default=False, nullable=False)
    startlist_public = db.Column(db.Boolean, default=False, nullable=False)
    schedule_public = db.Column(db.Boolean, default=False, nullable=False)
    results_public = db.Column(db.Boolean, default=False, nullable=False)
    start_numbers_locked = db.Column(db.Boolean, default=False, nullable=False)
    start_numbers_generated_at = db.Column(db.DateTime)
    start_numbers_rule_set = db.Column(db.Text)
    schedule_locked = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)


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
