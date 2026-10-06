"""
Reservation-Sync: AgilityPortal-Event → AdminPortal Reservation

Erstellt oder aktualisiert eine Reservationsanfrage im AdminPortal.
"""

import requests
from datetime import datetime
from flask import current_app


def _date_to(event):
    """date_to nur setzen, wenn Mehrtages-Event (sonst None wie bisher)."""
    if not event.starts_at:
        return None
    if event.ends_at and event.ends_at.date() != event.starts_at.date():
        return event.ends_at.date().isoformat()
    return None


def _event_entry(event) -> dict:
    """Ein Eintrag für das `events`-Array einer Mehr-Turnier-Reservation."""
    return {
        "portal_event_id": event.id,
        "ais_turniernummer": event.ais_turniernummer,
        "event_name": event.name,
        "date_from": event.starts_at.date().isoformat() if event.starts_at else None,
        "date_to": _date_to(event),
    }


def _reservation_events(reservation_id):
    """
    Alle Events, die sich diese Reservation teilen — nach Datum/ID sortiert.
    Das erste Element ist das Haupt-Turnier (füllt bei AdminPortal die Einzel-Spalten).
    """
    from app.models import Event
    return (Event.query
            .filter(Event.reservation_id == reservation_id)
            .order_by(Event.starts_at.asc().nullslast(), Event.id.asc())
            .all())


def _api_headers() -> dict:
    token = current_app.config.get("WEBSITE_API_TOKEN", "")
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }


def _base_url() -> str:
    return current_app.config.get("WEBSITE_API_URL", "").rstrip("/")


def _event_payload(event, contact_name: str, contact_email: str,
                   contact_phone: str = "", club: str = "",
                   notes: str = "",
                   option_special_eval: bool = False,
                   option_website: bool = False,
                   option_event_support: bool = False) -> dict:
    return {
        "portal_event_id": event.id,
        "event_name": event.name,
        "location": event.location or "",
        "date_from": event.starts_at.date().isoformat() if event.starts_at else None,
        "date_to": (event.ends_at.date().isoformat()
                    if event.ends_at and event.ends_at.date() != event.starts_at.date()
                    else None) if event.starts_at else None,
        "ais_turniernummer": event.ais_turniernummer,
        "estimated_participants": event.max_participants,
        "contact_name": contact_name,
        "contact_email": contact_email,
        "contact_phone": contact_phone,
        "club": club,
        "notes": notes,
        "option_special_eval": option_special_eval,
        "option_website": option_website,
        "option_event_support": option_event_support,
    }


def create_reservation(event, contact_name: str, contact_email: str,
                       contact_phone: str = "", club: str = "",
                       notes: str = "",
                       option_special_eval: bool = False,
                       option_website: bool = False,
                       option_event_support: bool = False) -> tuple[bool, str]:
    """
    Erstellt eine neue Reservationsanfrage im AdminPortal.
    Gibt (True, "") bei Erfolg oder (False, fehlermeldung) zurück.
    """
    url = _base_url()
    if not url or not current_app.config.get("WEBSITE_API_TOKEN"):
        return False, "WEBSITE_API_URL oder WEBSITE_API_TOKEN nicht konfiguriert."

    payload = _event_payload(event, contact_name, contact_email,
                             contact_phone, club, notes,
                             option_special_eval, option_website, option_event_support)
    try:
        resp = requests.post(f"{url}/api/reservations",
                             json=payload, headers=_api_headers(), timeout=15)
        resp.raise_for_status()
        data = resp.json()
        res_id = data.get("id")
        if res_id:
            event.reservation_id = int(res_id)
            event.reservation_synced_at = datetime.utcnow()
            return True, ""
        return False, f"Keine ID in Antwort: {data}"
    except requests.RequestException as e:
        return False, f"Netzwerkfehler: {e}"


def update_reservation(event) -> tuple[bool, str]:
    """
    Aktualisiert die verknüpfte Reservationsanfrage mit aktuellen Event-Daten.

    Teilen sich mehrere Events dieselbe Reservation (Mehr-Turnier-Reservation),
    wird IMMER die vollständige `events`-Liste gesendet — AdminPortal ersetzt bei
    PATCH die komplette Turnier-Menge. Das Haupt-Turnier (erstes Listenelement)
    füllt zusätzlich die Einzel-Spalten für abwärtskompatible Links/Features.
    """
    if not event.reservation_id:
        return False, "Keine Reservationsanfrage verknüpft."

    url = _base_url()
    if not url or not current_app.config.get("WEBSITE_API_TOKEN"):
        return False, "WEBSITE_API_URL oder WEBSITE_API_TOKEN nicht konfiguriert."

    group = _reservation_events(event.reservation_id)
    # Fallback, falls die Gruppe (z.B. durch Race) leer zurückkommt
    if not group:
        group = [event]
    main = group[0]

    payload = {
        "event_name": main.name,
        "location": main.location or "",
        "date_from": main.starts_at.date().isoformat() if main.starts_at else None,
        "date_to": _date_to(main),
        "ais_turniernummer": main.ais_turniernummer,
        "estimated_participants": sum(e.max_participants or 0 for e in group) or None,
        "events": [_event_entry(e) for e in group],
    }
    try:
        resp = requests.patch(
            f"{url}/api/reservations/{event.reservation_id}",
            json=payload, headers=_api_headers(), timeout=15,
        )
        resp.raise_for_status()
        now = datetime.utcnow()
        for e in group:
            e.reservation_synced_at = now
        return True, ""
    except requests.RequestException as e:
        return False, f"Netzwerkfehler: {e}"
