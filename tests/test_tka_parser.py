import pytest
from app.models import (
    Dog,
    LicenseKind,
    Registration,
    RegistrationStatus,
    TkaEventCheckStatus,
    TkaExportBatch,
    TkaExportRow,
    TkaExportType,
)
from app.extensions import db
from app.services.tka_service import apply_tka_import, parse_tka_text


def test_parse_class_mismatch_single_line():
    text = (
        "Falsche Klasse oder Kategorie auf Zeile 5, Lizenz 16897 Pac-Man. "
        "Klasse im Import: L1. Klasse im System: L2"
    )
    findings = parse_tka_text(text)
    assert len(findings) == 1
    finding = findings[0]
    assert finding["license_no"] == "16897"
    assert finding["import_category_code"] == "Large"
    assert finding["import_class_level"] == 1
    assert finding["system_category_code"] == "Large"
    assert finding["system_class_level"] == 2


def test_parse_class_mismatch_multiline():
    text = (
        "Falsche Klasse oder Kategorie auf Zeile 5, Lizenz 16897 Pac-Man.\n"
        "Klasse im Import: L1.\n"
        "Klasse im System: L2"
    )
    findings = parse_tka_text(text)
    assert len(findings) == 1
    assert findings[0]["license_no"] == "16897"


def test_parse_license_unknown_keywords():
    text = "Lizenz 99999 nicht bekannt im System."
    findings = parse_tka_text(text)
    assert len(findings) == 1
    assert findings[0]["license_no"] == "99999"
    assert findings[0]["finding_kind"].value == "LICENSE_UNKNOWN"


def test_parse_invalid_oldies_keywords():
    text = "Lizenz 12345 ist ung\u00fcltig (Oldies)."
    findings = parse_tka_text(text)
    assert len(findings) == 1
    assert findings[0]["license_no"] == "12345"
    assert findings[0]["finding_kind"].value == "LICENSE_INVALID"


def test_apply_ok_when_no_finding(app):
    with app.app_context():
        dog = Dog(name="Rex", license_no="12345", license_kind=LicenseKind.CH)
        registration = Registration(
            dog=dog,
            event_id=1,
            status=RegistrationStatus.SUBMITTED,
            class_level=1,
            category_code="Large",
            tka_event_check_status=TkaEventCheckStatus.PENDING,
        )
        batch = TkaExportBatch(export_type=TkaExportType.EVENT_CHECK, event_id=1)
        row = TkaExportRow(
            registration=registration,
            dog=dog,
            license_no=dog.license_no,
            category_code=registration.category_code,
            class_level=registration.class_level,
        )
        batch.rows.append(row)
        db.session.add_all([dog, registration, batch])
        db.session.commit()

        apply_tka_import(batch_id=batch.id, raw_text="", imported_by_user_id=1)
        db.session.commit()

        assert registration.tka_event_check_status == TkaEventCheckStatus.OK
        assert registration.tka_issue_message is None
