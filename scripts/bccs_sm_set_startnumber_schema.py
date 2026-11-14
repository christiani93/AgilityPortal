#!/usr/bin/env python3
"""
Skript: BCCS-SM Events (33/34/35) mit Startnummern-Schemas konfigurieren.
Läuft lokal in .venv; setzt die startnumber_schema-Felder auf Prod via SSH.

Verwendung:
    python scripts/bccs_sm_set_startnumber_schema.py [--dry-run]
"""
import json
import sys
from pathlib import Path

# Lokale Dev-DB oder Prod via SSH?
DRY_RUN = "--dry-run" in sys.argv

BCCS_EVENTS = {
    33: "Abendmeeting 20.11.2026",
    34: "BCCS-SM 21.11.2026 (Sa)",
    35: "BCCS-SM 22.11.2026 (So)",
}

# Startnummern-Schema: pro Kategorie × Klasse
STARTNUMBER_SCHEMA = {
    "Intermediate-1": 101,
    "Intermediate-2": 111,
    "Intermediate-3": 121,
    "Large-1": 201,
    "Large-2": 211,
    "Large-3": 221,
}

def main():
    if DRY_RUN:
        print("[DRY-RUN] Keine Änderungen geschrieben.\n")

    schema_json = json.dumps(STARTNUMBER_SCHEMA)

    for event_id, event_name in BCCS_EVENTS.items():
        print(f"Event {event_id}: {event_name}")
        print(f"  Schema: {schema_json}")

        if not DRY_RUN:
            try:
                from app.extensions import db
                from app.models import Event

                # Nur lokal ausführbar; für Prod siehe Prod-DB-Zugriff
                event = db.session.get(Event, event_id)
                if event:
                    event.startnumber_schema = schema_json
                    db.session.commit()
                    print(f"  ✅ Gespeichert")
                else:
                    print(f"  ⚠️  Event nicht gefunden (lokale DB?)")
            except Exception as e:
                print(f"  ❌ Fehler: {e}", file=sys.stderr)
                return 1
        else:
            print(f"  [DRY] bereit zum Speichern")

    print("\nSQL-Alternative für Prod (über SSH):")
    for event_id in BCCS_EVENTS:
        print(f"UPDATE events SET startnumber_schema = '{schema_json}' WHERE id = {event_id};")

    return 0

if __name__ == "__main__":
    sys.exit(main())
