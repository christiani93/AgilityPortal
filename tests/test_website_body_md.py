"""
Tests für den Inserat-Text-Generator (website_sync.generate_body_md).

Der Text spiegelt bewusst den AdminPortal-Generator (_generate_event_body):
ein Abschnitt pro Turniertag mit Infozeilen + Fliesstext. TKAMO-Felder füllen
– wo vorhanden – die Infozeilen, sonst greifen die Standardtexte.
"""
from datetime import datetime

from app.services.website_sync import generate_body_md


def test_single_day_uses_prose_and_defaults(app):
    with app.app_context():
        from app.models import Event
        ev = Event(name="Testturnier", location="Sporthalle Muster",
                   starts_at=datetime(2026, 5, 2))
        body = generate_body_md(ev)

    assert body.startswith("🇩🇪 Deutsch")
    assert "📅 Samstag 02.05.2026" in body
    assert "Turniertag 1" not in body          # Einzeltag → kein Tages-Suffix
    assert "🐕 Disziplinen: Agility & Jumping" in body
    assert "gemäss offizieller Ausschreibung" in body
    assert "Der erste Turniertag von Testturnier" in body
    assert "Sporthalle Muster" in body


def test_multi_day_has_section_per_day(app):
    with app.app_context():
        from app.models import Event
        ev = Event(name="Sommer Cup", location="Arena",
                   starts_at=datetime(2026, 6, 6), ends_at=datetime(2026, 6, 7))
        body = generate_body_md(ev)

    assert "📅 Samstag 06.06.2026 – Turniertag 1" in body
    assert "📅 Sonntag 07.06.2026 – Turniertag 2" in body
    assert "📋 Wertung: Offizielles TKAMO-Turnier" in body
    assert "📋 Fortsetzung des offiziellen Turniers" in body
    assert "Am 2. Tag von Sommer Cup" in body


def test_tkamo_fields_fill_info_lines(app):
    with app.app_context():
        from app.models import Event
        ev = Event(name="TKAMO Turnier", location="Halle",
                   starts_at=datetime(2026, 7, 4),
                   tkamo_disciplines="Nur Agility",
                   tkamo_categories="S, M (Kl. 2+3)",
                   tkamo_judges="Max Muster")
        body = generate_body_md(ev)

    assert "🐕 Disziplinen: Nur Agility" in body
    assert "🏅 Kategorien: S, M (Kl. 2+3)" in body
    assert "👩‍⚖️ Richter: Max Muster" in body


def test_no_start_date_returns_empty(app):
    with app.app_context():
        from app.models import Event
        ev = Event(name="Ohne Datum")
        assert generate_body_md(ev) == ""


def test_registration_footer_uses_portal_link(app):
    with app.app_context():
        from app.models import Event
        app.config["PORTAL_PUBLIC_URL"] = "https://portal.z-b.tech"
        from app.extensions import db
        ev = Event(name="Footer Turnier", starts_at=datetime(2026, 8, 1),
                   registration_close_at=datetime(2026, 7, 15))
        db.session.add(ev)
        db.session.commit()
        body = generate_body_md(ev)

    assert f"https://portal.z-b.tech/events/{ev.id}" in body
    assert "📅 Meldeschluss: 15. Juli 2026" in body
