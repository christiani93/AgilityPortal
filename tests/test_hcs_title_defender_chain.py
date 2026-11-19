"""Verifiziert die Titelverteidiger-Kette über das Cup-System für den Halloween Cup:

Die KO-Final-Sieger eines Jahres (season N) werden als CupFinal/CupFinalResult
(final_rank=1) persistiert; das Folgejahr (season N+1) findet sie via
``detect_title_defenders`` automatisch als Vorjahressieger.

Entspricht dem realen Weg: AgilitySoftware exportiert ``cup_finals.json`` →
``_import_cup_finals`` schreibt diese Datensätze → Folgejahr-Abfrage.
"""
from app.extensions import db
from app.models import Cup, CupFinal, CupFinalParticipant, CupFinalResult
from app.services.cup_qualification import detect_title_defenders


# Die realen HCS-2026-Champions (KO-Final-Sieger je Kategorie), 31.10.2026.
HCS_2026_WINNERS = [
    ("Small",        "Carioca", "Tiphanie Mauroux",    "15736"),
    ("Medium",       "Kaja",    "Jana-Lorena Von Burg", "16132"),
    ("Intermediate", "Liv",     "Bettina Heiniger",    "15953"),
    ("Large",        "Youri",   "Roland Marro",        "14554"),
]


def _seed_hcs_2026_winners():
    """Legt Cup 2026 + die vier Final-Sieger an (wie beim resultexport-Import)."""
    cup = Cup(name="Halloween Cup 2026", season=2026,
              special_ruleset="halloween_cup", title_defender_spots=1)
    db.session.add(cup)
    db.session.flush()
    for category, dog, handler, lic in HCS_2026_WINNERS:
        final = CupFinal(cup_id=cup.id, group_label=category,
                         category_code=category, class_level=None,
                         is_published=True, notes="hcs2026_title_defender")
        db.session.add(final)
        db.session.flush()
        part = CupFinalParticipant(final_id=final.id, dog_name=dog,
                                   handler_name=handler, license_no=lic)
        db.session.add(part)
        db.session.flush()
        db.session.add(CupFinalResult(final_id=final.id,
                                      participant_id=part.id, final_rank=1))
    db.session.commit()
    return cup


def test_hcs_next_year_detects_previous_winners(app):
    with app.app_context():
        _seed_hcs_2026_winners()

        # Folgejahr-Cup (season 2027) — stellvertretend für HCS 2027.
        cup_2027 = Cup(name="Halloween Cup 2027", season=2027,
                       special_ruleset="halloween_cup", title_defender_spots=1)
        db.session.add(cup_2027)
        db.session.commit()

        defenders = detect_title_defenders(cup_2027)

        assert set(defenders.keys()) == {"Small", "Medium", "Intermediate", "Large"}
        assert defenders["Small"]["dog_name"] == "Carioca"
        assert defenders["Small"]["license_no"] == "15736"
        assert defenders["Large"]["handler_name"] == "Roland Marro"
        assert defenders["Intermediate"]["dog_name"] == "Liv"
        assert defenders["Medium"]["license_no"] == "16132"


def test_no_previous_cup_yields_no_defenders(app):
    """Ohne Vorjahres-Cup (season − 1) liefert die Abfrage nichts (kein Crash)."""
    with app.app_context():
        cup_2027 = Cup(name="Halloween Cup 2027", season=2027,
                       special_ruleset="halloween_cup", title_defender_spots=1)
        db.session.add(cup_2027)
        db.session.commit()
        assert detect_title_defenders(cup_2027) == {}
