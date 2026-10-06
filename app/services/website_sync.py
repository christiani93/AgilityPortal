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


def _as_date(dt):
    """datetime/date → date (oder None)."""
    if dt is None:
        return None
    return dt.date() if hasattr(dt, "date") else dt


def generate_body_md(event) -> str:
    """Erstellt den body_md-Text für den PublicEvent auf z-b.tech.

    Spiegelt bewusst den Generator der AdminPortal-Seite
    (``_generate_event_body``), damit im AdminPortal erstellte und aus dem
    Portal synchronisierte Events identisch lesen: ein Abschnitt pro
    Turniertag mit Infozeilen + Fliesstext.

    Wo vorhanden, füllen die TKAMO-Felder (Wettbewerbe, Kategorien, Richter)
    die Infozeilen — sonst greifen die gleichen Standardtexte wie im
    AdminPortal. Deshalb vor dem Sync den TKAMO-Import ausführen.
    """
    start = _as_date(event.starts_at)
    if not start:
        return ""
    end = _as_date(event.ends_at) or start
    if end < start:
        end = start

    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)

    title = event.name or "unserem Turnier"
    venue = (event.location or "").strip() or "Indoor"
    disciplines = (event.tkamo_disciplines or "").strip() or "Agility & Jumping"
    categories = ((event.tkamo_categories or "").strip()
                  or "gemäss offizieller Ausschreibung (S, M, I, L – 1–3)")
    judges = (event.tkamo_judges or "").strip()
    multi = len(days) > 1

    sections = []
    for i, day in enumerate(days):
        wd = WEEKDAYS_DE[day.weekday()]
        datum = day.strftime("%d.%m.%Y")
        tag = f" – Turniertag {i + 1}" if multi else ""
        sec = f"📅 {wd} {datum}{tag}\n\n"
        sec += f"🐕 Disziplinen: {disciplines}\n"
        sec += f"🏅 Kategorien: {categories}\n"
        if judges:
            sec += f"👩‍⚖️ Richter: {judges}\n"
        sec += f"🏟 Austragung: {venue}\n"
        sec += ("📋 Wertung: Offizielles TKAMO-Turnier\n" if i == 0
                else "📋 Fortsetzung des offiziellen Turniers\n")
        sec += ("🐾 Läufigkeit erlaubt\n" if event.allows_bitches_in_season
                else "🐾 Läufige Hündinnen: nicht erlaubt\n")
        sec += "\n**Eventbeschreibung**\n\n"
        if i == 0:
            sec += (
                f"Der erste Turniertag von {title} steht ganz im Zeichen von sportlicher "
                f"Präzision und Dynamik. Teams aus der ganzen Schweiz treffen sich in der {venue}, "
                "um sich in anspruchsvollen Parcours zu messen.\n\n"
                "Ob ambitioniertes Nachwuchsteam oder erfahrene Wettkämpfer – dieses Event bietet "
                "optimale Bedingungen für fairen und hochklassigen Agility-Sport.\n"
            )
        else:
            sec += (
                f"Am {i + 1}. Tag von {title} geht das Turnier in die nächste Runde. "
                "Noch einmal gilt es, Konzentration, Tempo und Teamwork perfekt aufeinander abzustimmen.\n\n"
                "Mit professioneller Organisation und spannenden Läufen verspricht dieses Wochenende "
                "ein echtes Highlight im Schweizer Agility-Kalender zu werden.\n"
            )
        sections.append(sec)

    body = "🇩🇪 Deutsch\n\n" + "\n".join(sections)

    # ── Freitext-Beschreibung (optionaler Zusatz des Veranstalters)
    if event.event_description_de and event.event_description_de.strip():
        body += "\n" + event.event_description_de.strip() + "\n"

    # ── Anmelde-Footer (echte Portal-Daten statt Platzhalter)
    portal_url = current_app.config.get("PORTAL_PUBLIC_URL", "").rstrip("/")
    if portal_url:
        body += f"\n👉 [Anmeldung & Details]({portal_url}/events/{event.id})\n"
    else:
        body += "\n👉 Anmeldung & Details: über TKAMO\n"
    if event.registration_close_at:
        body += f"📅 Meldeschluss: {_fmt_date_long(event.registration_close_at)}\n"
    else:
        body += "📅 Meldeschluss: gemäss offizieller Agenda\n"

    return body


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
