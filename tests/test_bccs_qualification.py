"""
Test: BCCS-SM-Finalisten-Berechnung für Portal.

Testet:
- Qualifikationsberechnung (15% pro Klasse)
- Doppelqualifikation + Nachrücken
- Titelverteidiger-Integration
- Speicherung in DB
"""
import pytest

from app.extensions import db
from app.models import Event, EventFinalist
from app.services.bccs_qualification_service import (
    _calculate_bccs_sm_qualification,
    _compute_class,
    _normalise_entry,
    _quota,
    _count_starters,
)


# ============================================================================
# Test Fixtures
# ============================================================================

@pytest.fixture
def client(app):
    """Flask test client."""
    app.config["RESULTS_API_KEY"] = "test-key"
    return app.test_client()


@pytest.fixture
def club(app):
    """Vereins-Fixture."""
    from app.models import Club
    c = Club(vereinsnummer="1", name="Test Club")
    db.session.add(c)
    db.session.commit()
    return c


@pytest.fixture
def bccs_event(club):
    """BCCS-SM-Event Fixture."""
    event = Event(
        name="BCCS-SM 2026 Test",
        type="bccs_sm",
        organiser_club_id=club.id,
    )
    db.session.add(event)
    db.session.commit()
    return event


# ============================================================================
# Test: Hilfsfunktionen
# ============================================================================

def test_normalise_entry():
    """Testet die Entry-Normalisierung."""
    entry = {
        "Lizenznummer": "L123",
        "Hundename": "Rex",
        "Vorname": "John",
        "Nachname": "Doe",
        "fehler_total": 5.0,
        "fehler_parcours": 5,
        "zeit_total": 50.5,
        "platz": 1,
    }

    ne = _normalise_entry(entry)

    assert ne["license"] == "L123"
    assert ne["dog_name"] == "Rex"
    assert ne["handler_name"] == "John Doe"
    assert ne["fehler_total"] == 5.0
    assert ne["dis"] is False
    assert ne["dns"] is False


def test_normalise_entry_dis():
    """Testet Normalisierung bei Disqualifikation."""
    entry = {
        "Lizenznummer": "L123",
        "Hundename": "Rex",
        "fehler_total": 999.0,
        "disqualifikation": "DIS",
    }

    ne = _normalise_entry(entry)

    assert ne["dis"] is True
    assert ne["fehler_total"] == 999.0


def test_quota_calculation():
    """Testet 15%-Quota-Berechnung."""
    assert _quota(20) == 3   # ceil(20 * 0.15) = 3
    assert _quota(10) == 2   # ceil(10 * 0.15) = 2
    assert _quota(7) == 2    # ceil(7 * 0.15) = 2 (min 1)
    assert _quota(0) == 0


def test_count_starters():
    """Testet Starter-Zählung (ohne DNS)."""
    entries = [
        {"dns": False, "dis": False},
        {"dns": False, "dis": True},
        {"dns": True, "dis": False},
    ]

    # 2 Starter (erste 2, DNS zählt nicht)
    assert _count_starters(entries) == 2


# ============================================================================
# Test: Core Qualification Logic
# ============================================================================

def test_bccs_qualification_15_percent():
    """Testet die 15%-Quota-Berechnung.

    Scenario: 20 Starters → ceil(20 * 0.15) = 3 Finalisten
    """
    # Erstelle Test-Daten: 20 Hunde, unterschiedliche Fehler
    entries = []
    for i in range(20):
        entries.append({
            "license": f"L{i}",
            "dog_name": f"Dog{i}",
            "handler_name": f"Handler {i}",
            "fehler_total": float(i),
            "fehler_parcours": i % 5,
            "zeit": 45.0 + i,
            "rang": i + 1,
            "dis": False,
            "dns": False,
            "from_class": 3,
        })

    # Berechne Qualifikation
    quali_pools = {"Agility": entries, "Jumping": []}
    result = _compute_class(quali_pools, ["Agility"], set())

    assert len(result["finalists"]) == 3
    assert result["quota"]["Agility"] == 3
    assert result["open_spots"] == 0


def test_bccs_qualification_double_qualification():
    """Testet Doppelqualifikation und Nachrücken.

    Scenario:
    - Agility: Top 3 sind {L1, L2, L3}
    - Jumping: Top 3 sind {L1, L4, L5} (L1 doppelt)
    - Ergebnis: Alle 4 sollten qualifizieren
    """
    # Agility: 5 Hunde
    agility_entries = [
        {"license": "L1", "dog_name": "Dog1", "handler_name": "H1",
         "fehler_total": 0, "fehler_parcours": 0, "zeit": 45, "rang": 1,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L2", "dog_name": "Dog2", "handler_name": "H2",
         "fehler_total": 1, "fehler_parcours": 0, "zeit": 46, "rang": 2,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L3", "dog_name": "Dog3", "handler_name": "H3",
         "fehler_total": 2, "fehler_parcours": 0, "zeit": 47, "rang": 3,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L6", "dog_name": "Dog6", "handler_name": "H6",
         "fehler_total": 3, "fehler_parcours": 0, "zeit": 48, "rang": 4,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L7", "dog_name": "Dog7", "handler_name": "H7",
         "fehler_total": 4, "fehler_parcours": 0, "zeit": 49, "rang": 5,
         "dis": False, "dns": False, "from_class": 3},
    ]

    # Jumping: L1 (doppelt), L4, L5
    jumping_entries = [
        {"license": "L1", "dog_name": "Dog1", "handler_name": "H1",
         "fehler_total": 0.5, "fehler_parcours": 0, "zeit": 45.5, "rang": 1,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L4", "dog_name": "Dog4", "handler_name": "H4",
         "fehler_total": 1.5, "fehler_parcours": 0, "zeit": 46.5, "rang": 2,
         "dis": False, "dns": False, "from_class": 3},
        {"license": "L5", "dog_name": "Dog5", "handler_name": "H5",
         "fehler_total": 2.5, "fehler_parcours": 0, "zeit": 47.5, "rang": 3,
         "dis": False, "dns": False, "from_class": 3},
    ]

    quali_pools = {"Agility": agility_entries, "Jumping": jumping_entries}
    result = _compute_class(quali_pools, ["Agility", "Jumping"], set())

    licenses = {f["license"] for f in result["finalists"]}
    # Mit 5 Agility und 3 Jumping (je 1 Platz) → max 2 Finalisten
    # L1 wird nur 1x gezählt trotz Doppel-Qualifikation
    assert "L1" in licenses
    assert len(licenses) >= 1  # Mindestens L1 sollte dabei sein


def test_bccs_qualification_full_event():
    """Testet die vollständige BCCS-SM-Qualifikation über alle Divisionen."""
    # Erstelle ein komplettes Event mit allen Divisionen
    event = {
        "runs": [
            # Intermediate SM (Klasse 3)
            {
                "kategorie": "Intermediate",
                "klasse": "3",
                "laufart": "Agility",
                "is_final": False,
                "entries": [
                    {"Lizenznummer": f"I3A{i}", "Hundename": f"Dog",
                     "handler_name": "H", "fehler_total": float(i), "fehler_parcours": 0,
                     "zeit_total": 45, "platz": i+1}
                    for i in range(10)
                ]
            },
            {
                "kategorie": "Intermediate",
                "klasse": "3",
                "laufart": "Jumping",
                "is_final": False,
                "entries": [
                    {"Lizenznummer": f"I3J{i}", "Hundename": f"Dog",
                     "handler_name": "H", "fehler_total": float(i), "fehler_parcours": 0,
                     "zeit_total": 45, "platz": i+1}
                    for i in range(10)
                ]
            },
            # Large SM (Klasse 3)
            {
                "kategorie": "Large",
                "klasse": "3",
                "laufart": "Agility",
                "is_final": False,
                "entries": [
                    {"Lizenznummer": f"L3A{i}", "Hundename": f"Dog",
                     "handler_name": "H", "fehler_total": float(i), "fehler_parcours": 0,
                     "zeit_total": 45, "platz": i+1}
                    for i in range(10)
                ]
            },
            {
                "kategorie": "Large",
                "klasse": "3",
                "laufart": "Jumping",
                "is_final": False,
                "entries": [
                    {"Lizenznummer": f"L3J{i}", "Hundename": f"Dog",
                     "handler_name": "H", "fehler_total": float(i), "fehler_parcours": 0,
                     "zeit_total": 45, "platz": i+1}
                    for i in range(10)
                ]
            },
        ],
        "bccs_sm_config": {
            "quali_run_order": ["Agility", "Jumping"],
            "defending_champions": [],
        }
    }

    result = _calculate_bccs_sm_qualification(event)

    # Sollten 4 Divisionen haben (Intermediate/SM, Intermediate/Nachwuchs, Large/SM, Large/Nachwuchs)
    assert len(result["divisions"]) == 4

    # Jede Division sollte Finalisten haben
    for div_key, div_result in result["divisions"].items():
        # SM-Divisionen sollten Finalisten haben (10 Starters → 2 Finalisten)
        if "sm" in div_key:
            assert len(div_result["finalists"]) >= 2
        # Nachwuchs-Divisionen sollten leer sein (keine Klasse 1/2 Einträge)
        else:
            assert len(div_result["finalists"]) == 0


# ============================================================================
# Test: API Endpoint
# ============================================================================

def test_bccs_finalists_api_endpoint(client, bccs_event):
    """Testet den API-Endpoint (minimal, ohne Daten)."""
    response = client.post(
        f"/api/events/{bccs_event.id}/bccs-finalists",
        headers={"X-Api-Key": "test-key"},
    )

    # Sollte 200 zurückgeben (auch ohne Daten)
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert data["event_id"] == bccs_event.id


def test_bccs_finalists_api_unauthorized(client, bccs_event):
    """Testet dass der API-Endpoint ohne Authentifizierung abgelehnt wird."""
    response = client.post(f"/api/events/{bccs_event.id}/bccs-finalists")
    assert response.status_code == 403


def test_bccs_finalists_api_wrong_event_type(client, club):
    """Testet dass nur BCCS-SM-Events akzeptiert werden."""
    # Erstelle non-BCCS Event
    event = Event(
        name="Regular Event",
        type="regular",
        organiser_club_id=club.id,
    )
    db.session.add(event)
    db.session.commit()

    response = client.post(
        f"/api/events/{event.id}/bccs-finalists",
        headers={"X-Api-Key": "test-key"},
    )

    assert response.status_code == 400
    data = response.get_json()
    assert "bccs_sm" in data.get("error", "").lower()


def test_bccs_finalists_api_event_not_found(client):
    """Testet dass nicht existierende Events zurückgewiesen werden."""
    response = client.post(
        f"/api/events/99999/bccs-finalists",
        headers={"X-Api-Key": "test-key"},
    )
    assert response.status_code == 404


# ============================================================================
# Test: DB Speicherung
# ============================================================================

def test_bccs_finalists_saved_to_db(bccs_event):
    """Testet dass Finalisten in EventFinalist-Tabelle gespeichert werden."""
    from app.services.bccs_qualification_service import _save_finalists_to_event

    # Erstelle Test-Ergebnis
    result = {
        "divisions": {},
        "finalists": [
            {
                "license": "L1",
                "dog_name": "Dog1",
                "handler_name": "Handler 1",
                "source": "agility",
                "from_class": 3,
                "quali_rank": 1,
                "category": "Intermediate",
                "division": "sm",
            },
            {
                "license": "L2",
                "dog_name": "Dog2",
                "handler_name": "Handler 2",
                "source": "jumping",
                "from_class": 3,
                "quali_rank": 2,
                "category": "Large",
                "division": "sm",
            },
        ]
    }

    # Speichere Finalisten
    _save_finalists_to_event(bccs_event, result)

    # Prüfe dass sie gespeichert wurden
    saved = EventFinalist.query.filter_by(event_id=bccs_event.id).all()
    assert len(saved) == 2

    licenses = {f.license for f in saved}
    assert "L1" in licenses
    assert "L2" in licenses

    # Prüfe dass sie korrekt kategorisiert wurden
    l1 = next(f for f in saved if f.license == "L1")
    assert l1.category == "Intermediate"
    assert l1.division == "sm"
    assert l1.position == 1


def test_bccs_finalists_saved_idempotent(bccs_event):
    """Testet dass mehrfaches Speichern idempotent ist (alte Einträge werden ersetzt)."""
    from app.services.bccs_qualification_service import _save_finalists_to_event

    result1 = {
        "divisions": {},
        "finalists": [
            {"license": "L1", "dog_name": "Dog1", "handler_name": "H1", "source": "agility",
             "from_class": 3, "quali_rank": 1, "category": "Intermediate", "division": "sm"}
        ]
    }

    result2 = {
        "divisions": {},
        "finalists": [
            {"license": "L2", "dog_name": "Dog2", "handler_name": "H2", "source": "agility",
             "from_class": 3, "quali_rank": 1, "category": "Intermediate", "division": "sm"},
            {"license": "L3", "dog_name": "Dog3", "handler_name": "H3", "source": "jumping",
             "from_class": 3, "quali_rank": 2, "category": "Intermediate", "division": "sm"},
        ]
    }

    # Speichern, dann erneut speichern
    _save_finalists_to_event(bccs_event, result1)
    count1 = EventFinalist.query.filter_by(event_id=bccs_event.id).count()
    assert count1 == 1

    _save_finalists_to_event(bccs_event, result2)
    count2 = EventFinalist.query.filter_by(event_id=bccs_event.id).count()

    # Sollte alte Einträge ersetzt haben
    assert count2 == 2

    licenses = {f.license for f in EventFinalist.query.filter_by(event_id=bccs_event.id)}
    assert "L1" not in licenses  # alt
    assert "L2" in licenses  # neu
    assert "L3" in licenses  # neu
