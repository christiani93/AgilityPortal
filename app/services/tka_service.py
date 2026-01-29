import re
from collections import defaultdict
from datetime import datetime

from sqlalchemy import desc

from app.models import (
    Dog,
    LicenseKind,
    Registration,
    RegistrationStatus,
    TkaEventCheckStatus,
    TkaExportBatch,
    TkaExportRow,
    TkaExportType,
    TkaFinding,
    TkaFindingKind,
    TkaImport,
    TkaIssueType,
    TkaMasterStatus,
)
from app.extensions import db

CATEGORY_CODE_MAP = {
    "S": "Small",
    "M": "Medium",
    "I": "Intermediate",
    "L": "Large",
}


def build_master_check_batch(created_by_user_id=None) -> TkaExportBatch:
    batch = TkaExportBatch(export_type=TkaExportType.MASTER_CHECK, created_by_user_id=created_by_user_id)
    dogs = Dog.query.filter(
        Dog.license_kind == LicenseKind.CH,
        Dog.tka_master_status.in_([TkaMasterStatus.PENDING, TkaMasterStatus.ISSUE]),
    ).all()

    for dog in dogs:
        registration = (
            Registration.query.filter_by(dog_id=dog.id)
            .order_by(desc(Registration.created_at))
            .first()
        )
        category_code = dog.tka_category_confirmed
        class_level = None
        if registration:
            category_code = category_code or registration.category_code
            class_level = registration.class_level

        if not category_code:
            dog.tka_master_status = TkaMasterStatus.ISSUE
            dog.tka_issue_message = "Kategorie fehlt"
            continue
        if class_level is None:
            dog.tka_master_status = TkaMasterStatus.ISSUE
            dog.tka_issue_message = "Klasse fehlt"
            continue

        row = TkaExportRow(
            dog_id=dog.id,
            license_no=dog.license_no,
            category_code=category_code,
            class_level=class_level,
        )
        batch.rows.append(row)
        dog.tka_master_status = TkaMasterStatus.IN_EXPORT
        dog.tka_issue_message = None

    db.session.add(batch)
    db.session.flush()
    return batch


def build_event_check_batch(event_id: int, created_by_user_id=None) -> TkaExportBatch:
    batch = TkaExportBatch(
        export_type=TkaExportType.EVENT_CHECK,
        event_id=event_id,
        created_by_user_id=created_by_user_id,
    )
    registrations = (
        Registration.query.join(Dog, Registration.dog_id == Dog.id)
        .filter(
            Registration.event_id == event_id,
            Dog.license_kind == LicenseKind.CH,
            Registration.status == RegistrationStatus.SUBMITTED,
            Registration.tka_event_check_status.in_(
                [
                    TkaEventCheckStatus.PENDING,
                    TkaEventCheckStatus.ISSUE,
                    TkaEventCheckStatus.CLASS_CHANGED,
                    TkaEventCheckStatus.IN_EXPORT,
                ]
            ),
        )
        .all()
    )

    for registration in registrations:
        row = TkaExportRow(
            registration_id=registration.id,
            dog_id=registration.dog_id,
            license_no=registration.dog.license_no,
            category_code=registration.category_code,
            class_level=registration.class_level,
        )
        batch.rows.append(row)
        registration.tka_event_check_status = TkaEventCheckStatus.IN_EXPORT
        registration.tka_issue_message = None
        registration.tka_issue_type = None

    db.session.add(batch)
    db.session.flush()
    return batch


def render_batch_to_csv(batch_id: int) -> str:
    batch = TkaExportBatch.query.get(batch_id)
    lines = ["Lizenznummer;Kategorie;Klasse"]
    for row in batch.rows:
        lines.append(f"{row.license_no};{row.category_code};{row.class_level}")
    return "\n".join(lines) + "\n"


def _decode_code(code: str):
    if not code or len(code) < 2:
        return None, None
    category = CATEGORY_CODE_MAP.get(code[0].upper())
    try:
        class_level = int(code[1:])
    except ValueError:
        class_level = None
    return category, class_level


def parse_tka_text(raw_text: str):
    findings = []
    if not raw_text:
        return findings

    mismatch_pattern = re.compile(
        r"Falsche Klasse oder Kategorie.*?Lizenz\s*(\d+).*?Import:\s*([A-Z]\d).*?System:\s*([A-Z]\d)",
        re.IGNORECASE | re.DOTALL,
    )

    remaining_text = raw_text
    for match in mismatch_pattern.finditer(raw_text):
        license_no, import_code, system_code = match.groups()
        import_category, import_class = _decode_code(import_code)
        system_category, system_class = _decode_code(system_code)
        findings.append(
            {
                "finding_kind": TkaFindingKind.CLASS_OR_CATEGORY_MISMATCH,
                "license_no": license_no,
                "import_category_code": import_category,
                "import_class_level": import_class,
                "system_category_code": system_category,
                "system_class_level": system_class,
                "raw_message": match.group(0).strip(),
            }
        )
        remaining_text = remaining_text.replace(match.group(0), "")

    lines = [line.strip() for line in re.split(r"\r?\n", remaining_text) if line.strip()]
    for line in lines:
        if "Lizenz" in line and re.search(r"unbekannt|nicht bekannt|nicht vorhanden", line, re.IGNORECASE):
            license_no = _extract_license(line)
            findings.append(
                {
                    "finding_kind": TkaFindingKind.LICENSE_UNKNOWN,
                    "license_no": license_no,
                    "raw_message": line,
                }
            )
            continue
        if re.search(r"ung\u00fcltig|Oldies|Oldie", line, re.IGNORECASE):
            license_no = _extract_license(line)
            if license_no:
                findings.append(
                    {
                        "finding_kind": TkaFindingKind.LICENSE_INVALID,
                        "license_no": license_no,
                        "raw_message": line,
                    }
                )
            else:
                findings.append(
                    {
                        "finding_kind": TkaFindingKind.UNKNOWN_FORMAT,
                        "license_no": None,
                        "raw_message": line,
                    }
                )
            continue
        if "Lizenz" in line:
            findings.append(
                {
                    "finding_kind": TkaFindingKind.UNKNOWN_FORMAT,
                    "license_no": _extract_license(line),
                    "raw_message": line,
                }
            )

    return findings


def _extract_license(text: str):
    match = re.search(r"\b(\d+)\b", text)
    if match:
        return match.group(1)
    return None


def apply_tka_import(batch_id: int, raw_text: str, imported_by_user_id=None) -> TkaImport:
    batch = TkaExportBatch.query.get(batch_id)
    tka_import = TkaImport(
        batch_id=batch_id,
        imported_by_user_id=imported_by_user_id,
        raw_text=raw_text,
    )
    db.session.add(tka_import)

    parsed = parse_tka_text(raw_text)
    findings_by_license = defaultdict(list)

    for finding in parsed:
        finding_row = TkaFinding(
            tka_import=tka_import,
            license_no=finding.get("license_no"),
            finding_kind=finding["finding_kind"],
            issue_type=_finding_to_issue_type(finding["finding_kind"]),
            import_category_code=finding.get("import_category_code"),
            import_class_level=finding.get("import_class_level"),
            system_category_code=finding.get("system_category_code"),
            system_class_level=finding.get("system_class_level"),
            raw_message=finding.get("raw_message"),
            message=finding.get("raw_message"),
        )
        db.session.add(finding_row)
        if finding.get("license_no"):
            findings_by_license[finding["license_no"]].append(finding)

    for row in batch.rows:
        if row.license_no is None:
            continue
        if batch.export_type == TkaExportType.MASTER_CHECK:
            _apply_master_row(row, findings_by_license.get(row.license_no, []))
        if batch.export_type == TkaExportType.EVENT_CHECK:
            _apply_event_row(row, findings_by_license.get(row.license_no, []))

    db.session.commit()
    return tka_import


def _finding_to_issue_type(finding_kind: TkaFindingKind) -> TkaIssueType:
    mapping = {
        TkaFindingKind.CLASS_OR_CATEGORY_MISMATCH: TkaIssueType.DATA_MISMATCH,
        TkaFindingKind.LICENSE_UNKNOWN: TkaIssueType.LICENSE_UNKNOWN,
        TkaFindingKind.LICENSE_INVALID: TkaIssueType.LICENSE_INVALID,
        TkaFindingKind.UNKNOWN_FORMAT: TkaIssueType.PARSER_UNKNOWN_FORMAT,
    }
    return mapping[finding_kind]


def _apply_master_row(row: TkaExportRow, findings):
    dog = Dog.query.get(row.dog_id)
    if not dog or dog.license_kind == LicenseKind.FOREIGN:
        return
    now = datetime.utcnow()
    if not findings:
        dog.tka_master_status = TkaMasterStatus.OK
        dog.tka_master_checked_at = now
        dog.tka_issue_message = None
        return
    finding = findings[0]
    if finding["finding_kind"] == TkaFindingKind.CLASS_OR_CATEGORY_MISMATCH:
        system_category = finding.get("system_category_code")
        dog.tka_master_status = TkaMasterStatus.OK
        dog.tka_master_checked_at = now
        if system_category:
            dog.tka_category_confirmed = system_category
        dog.tka_issue_message = None
        return
    if finding["finding_kind"] == TkaFindingKind.LICENSE_UNKNOWN:
        dog.tka_master_status = TkaMasterStatus.ISSUE
        dog.tka_issue_message = "Lizenz unbekannt"
    elif finding["finding_kind"] == TkaFindingKind.LICENSE_INVALID:
        dog.tka_master_status = TkaMasterStatus.ISSUE
        dog.tka_issue_message = "Lizenz ung\u00fcltig/Oldies"
    else:
        dog.tka_master_status = TkaMasterStatus.ISSUE
        dog.tka_issue_message = "TKAMO Antwort unklar"
    dog.tka_master_checked_at = now


def _apply_event_row(row: TkaExportRow, findings):
    registration = Registration.query.get(row.registration_id)
    if not registration or registration.dog.license_kind == LicenseKind.FOREIGN:
        return
    if not findings:
        registration.tka_event_check_status = TkaEventCheckStatus.OK
        registration.tka_issue_type = None
        registration.tka_issue_message = None
        return
    finding = findings[0]
    if finding["finding_kind"] == TkaFindingKind.CLASS_OR_CATEGORY_MISMATCH:
        registration.verified_class_level = finding.get("system_class_level")
        registration.verified_category_code = finding.get("system_category_code")
        registration.tka_event_check_status = TkaEventCheckStatus.CLASS_CHANGED
        registration.tka_issue_type = TkaIssueType.DATA_MISMATCH
        registration.tka_issue_message = finding.get("raw_message")
        return
    if finding["finding_kind"] == TkaFindingKind.LICENSE_UNKNOWN:
        registration.tka_event_check_status = TkaEventCheckStatus.ISSUE
        registration.tka_issue_type = TkaIssueType.LICENSE_UNKNOWN
        registration.tka_issue_message = finding.get("raw_message")
        return
    if finding["finding_kind"] == TkaFindingKind.LICENSE_INVALID:
        registration.tka_event_check_status = TkaEventCheckStatus.ISSUE
        registration.tka_issue_type = TkaIssueType.LICENSE_INVALID
        registration.tka_issue_message = finding.get("raw_message")
        return
    registration.tka_event_check_status = TkaEventCheckStatus.ISSUE
    registration.tka_issue_type = TkaIssueType.PARSER_UNKNOWN_FORMAT
    registration.tka_issue_message = finding.get("raw_message")
