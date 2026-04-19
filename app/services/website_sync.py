"""
Website-Sync: AgilityPortal-Event → AdminPortal/z-b.tech PublicEvent

Ablauf:
1. generate_body_md(event)  → Markdown-Text für body_md
2. sync_to_website(event)   → POST an AdminPortal-API, speichert website_event_id
"""

import re
import requests
from datetime import datetime, timedelta
from flask import current_app

WEEKDAYS_DE = {
    0: "Montag", 1: "Dienstag", 2: "Mittwoch", 3: "Donnerstag",
    4: "Freitag", 5: "Samstag", 6: "Sonntag",
}
MONTHS_DE = {
    1: "Januar", 2: "Februar", 3: "März", 4: "April",
    5: "Mai", 6: "Juni", 7: "Juli", 8: "August",
    9: "September", 10: "Oktober", 11: "November", 12: "Dezember",
}


def _fmt_date_long(dt) -> str:
    """DD. Monat YYYY aus datetime oder date."""
    if dt is None:
        return "—"
    d = dt.date() if hasattr(dt, "date") else dt
    return f"{d.day}. {MONTHS_DE[d.month]} {d.year}"


def _fmt_weekday(dt) -> str:
    if dt is None:
        return ""
    d = dt.date() if hasattr(dt, "date") else dt
    return WEEKDAYS_DE[d.weekday()]


def generate_body_md(event) -> str:
    """Erstellt den body_md-Text für den PublicEvent auf z-b.tech."""
    lines = []

    # ── Datum
    if event.starts_at:
        wd = _fmt_weekday(event.starts_at)
        date_str = _fmt_date_long(event.starts_at)
        if event.ends_at and event.ends_at.date() != event.starts_at.date():
            date_end = _fmt_date_long(event.ends_at)
            lines.append(f"🗓 **{wd}, {date_str} – {date_end}**")
        else:
            lines.append(f"🗓 **{wd}, {date_str}**")

    lines.append("")  # Leerzeile

    # ── Wettbewerbe / Disziplinen
    if event.tkamo_disciplines:
        lines.append(f"🥋 {event.tkamo_disciplines}")

    # ── Kategorien
    if event.tkamo_categories:
        lines.append(f"🏆 {event.tkamo_categories}")

    # ── Ringe
    if event.ring_count:
        lines.append(f"🏟 {event.ring_count} Ring(e)")

    # ── Läufige Hündinnen
    laeufig = "Ja" if event.allows_bitches_in_season else "Nein"
    lines.append(f"🐩 Läufige Hündinnen: {laeufig}")

    # ── Richter (falls vorhanden)
    if event.tkamo_judges:
        lines.append(f"👩‍⚖️ Richter: {event.tkamo_judges}")

    # ── Prüfungsleiter
    if event.pruefungsleiter:
        lines.append(f"📌 Prüfungsleiter: {event.pruefungsleiter}")

    # ── Freitext-Beschreibung
    if event.event_description_de and event.event_description_de.strip():
        lines.append("")
        lines.append(event.event_description_de.strip())

    lines.append("")  # Leerzeile vor Links

    # ── Anmeldelink
    portal_url = current_app.config.get("PORTAL_PUBLIC_URL", "").rstrip("/")
    if portal_url:
        reg_url = f"{portal_url}/events/{event.id}"
        lines.append(f"📝 [Zur Anmeldung]({reg_url})")

    # ── Meldeschluss
    if event.registration_close_at:
        lines.append(f"📅 Meldeschluss: {_fmt_date_long(event.registration_close_at)}")

    # ── TKAMO-Links (primäre + allfällige weitere AIS-Nummern)
    from app.services.tkamo_importer import tkamo_url_for
    ais_all = []
    if event.ais_turniernummer:
        ais_all.append(str(event.ais_turniernummer))
    if event.ais_turniernummer_extra:
        for part in event.ais_turniernummer_extra.split(","):
            p = part.strip()
            if p:
                ais_all.append(p)
    if len(ais_all) == 1:
        lines.append(f"📋 [TKAMO-Eintrag]({tkamo_url_for(ais_all[0])})")
    elif len(ais_all) > 1:
        for i, ais in enumerate(ais_all, 1):
            lines.append(f"📋 [TKAMO-Eintrag Tag {i}]({tkamo_url_for(ais)})")

    return "\n".join(lines)


def _make_slug(event) -> str:
    """Erzeugt einen URL-sicheren Slug aus Eventname und Datum."""
    name = event.name or "event"
    # Umlaute ersetzen
    for old, new in [("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("Ä", "Ae"),
                     ("Ö", "Oe"), ("Ü", "Ue"), ("ß", "ss")]:
        name = name.replace(old, new)
    name = re.sub(r'[^a-zA-Z0-9\s-]', '', name)
    name = re.sub(r'\s+', '-', name.strip()).lower()
    name = name[:40].rstrip('-')

    date_part = ""
    if event.starts_at:
        date_part = event.starts_at.strftime("-%Y-%m-%d")

    # Eindeutigkeit via AIS-Nr oder Event-ID
    uid = f"-ais{event.ais_turniernummer}" if event.ais_turniernummer else f"-id{event.id}"
    return f"{name}{date_part}{uid}"


def sync_to_website(event) -> tuple[bool, str]:
    """
    Synchronisiert den Event mit dem AdminPortal.

    Gibt (True, "") bei Erfolg zurück,
    oder (False, fehlermeldung) bei Fehler.
    """
    api_url = current_app.config.get("WEBSITE_API_URL", "").rstrip("/")
    api_token = current_app.config.get("WEBSITE_API_TOKEN", "")

    if not api_url or not api_token:
        return False, "WEBSITE_API_URL oder WEBSITE_API_TOKEN nicht konfiguriert."

    body_md = generate_body_md(event)

    # Datum für PublicEvent
    date_from = None
    date_to = None
    visible_until = None
    if event.starts_at:
        date_from = event.starts_at.date().isoformat()
        end_d = event.ends_at.date() if event.ends_at else event.starts_at.date()
        if end_d != event.starts_at.date():
            date_to = end_d.isoformat()
        visible_until = (end_d + timedelta(days=7)).isoformat()

    payload = {
        "public_event_id": event.website_event_id,  # None = neu anlegen
        "title": event.name,
        "slug": _make_slug(event),
        "date_from": date_from,
        "date_to": date_to,
        "location": event.location,
        "body_md": body_md,
        "website_url": (
            f"https://www.tkamo.ch/?lang=de&n0=agenda&n1=&detail={event.ais_turniernummer}"
            if event.ais_turniernummer else None
        ),
        "visible_until": visible_until,
        "status": "published",
        # Beschreibung für Rücklink (optionales Extra-Feld)
        "portal_event_id": event.id,
    }

    try:
        resp = requests.post(
            f"{api_url}/api/events/sync",
            json=payload,
            headers={
                "Authorization": f"Bearer {api_token}",
                "Content-Type": "application/json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()
        new_id = data.get("id")
        if new_id:
            event.website_event_id = int(new_id)
            event.website_synced_at = datetime.utcnow()
            return True, ""
        return False, f"API-Antwort enthielt keine ID: {data}"
    except requests.RequestException as e:
        return False, f"Netzwerkfehler: {e}"
    except Exception as e:
        return False, f"Fehler: {e}"
