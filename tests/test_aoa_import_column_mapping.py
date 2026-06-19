"""Spalten-Mapping-Tests für AOA-/TKAMO-Importer.

Kein App-Context nötig — testet nur die Hilfsfunktionen.
"""
from app.blueprints.admin.routes_aoa_import import _find_column, _parse_csv


# AOA-Original-Header (kein Präfix)
AOA_HEADERS = [
    "Lizenz", "Hundename", "Kategorie", "Klasse",
    "Vorname", "Nachname", "Email", "Telefon", "Verein", "Vereinsnummer",
]

# TKAMO/SportyDog-Variante (mit H und HF Präfixen, siehe TKAMO-Mail-Export)
TKAMO_HEADERS = [
    "Datum", "A ID Turnier",
    "HF Name", "HF Vorname", "HF Strasse", "HF PLZ", "HF Ort", "HF Land",
    "HF Sprache", "HF Telefon", "HF Email", "HF Vereinnr", "HF Verein",
    "H Lizenz", "H Kategorie", "H Kl Eingabe", "H Name", "H Rasse", "H SHSB", "H Chip",
]


def _resolve_cols(headers):
    return {
        "license":    _find_column(headers, "Lizenz", "LicenseNo", "License", "Lizenznummer", "H Lizenz"),
        "dog_name":   _find_column(headers, "Hundename", "DogName", "Hund", "Name Hund", "H Name"),
        "category":   _find_column(headers, "Kategorie", "Category", "Kat", "H Kategorie"),
        "class":      _find_column(headers, "Klasse", "Class", "KL", "Kl", "H Kl Eingabe", "H Klasse"),
        "first_name": _find_column(headers, "Vorname", "FirstName", "Fname", "HF Vorname"),
        "last_name":  _find_column(headers, "Nachname", "LastName", "Lname", "Name", "HF Name"),
        "email":      _find_column(headers, "Email", "E-Mail", "EMail", "HF Email"),
        "phone":      _find_column(headers, "Telefon", "Phone", "Tel", "Mobile", "HF Telefon"),
        "club":       _find_column(headers, "Verein", "Club", "ClubName", "HF Verein"),
        "club_no":    _find_column(headers, "Vereinsnummer", "ClubNo", "VereinsNr", "HF Vereinnr"),
    }


def test_aoa_original_headers_all_mapped():
    cols = _resolve_cols(AOA_HEADERS)
    assert all(cols.values()), f"Unmapped: {[k for k,v in cols.items() if not v]}"
    assert cols["license"] == "Lizenz"
    assert cols["dog_name"] == "Hundename"


def test_tkamo_h_hf_prefix_headers_all_mapped():
    cols = _resolve_cols(TKAMO_HEADERS)
    assert all(cols.values()), f"Unmapped: {[k for k,v in cols.items() if not v]}"
    # Korrekte Disambiguierung: "HF Name" → last_name, "H Name" → dog_name
    assert cols["license"] == "H Lizenz"
    assert cols["dog_name"] == "H Name"
    assert cols["last_name"] == "HF Name"
    assert cols["first_name"] == "HF Vorname"
    assert cols["class"] == "H Kl Eingabe"
    assert cols["club_no"] == "HF Vereinnr"


def test_tkamo_csv_parses_with_real_format():
    """Roher CSV-Parse mit TKAMO-Header-Reihe."""
    csv_content = (
        "Datum;A ID Turnier;HF Name;HF Vorname;HF Telefon;HF Email;HF Vereinnr;HF Verein;"
        "H Lizenz;H Kategorie;H Kl Eingabe;H Name;H Rasse\r\n"
        "18.05.2025;11342;Diserens;Mary;797381664;m@e.ch;222;Bex;13852;Intermediate;1;Rocky;Border collie\r\n"
    )
    rows, headers = _parse_csv(csv_content)
    assert len(rows) == 1
    cols = _resolve_cols(headers)
    row = rows[0]
    assert row[cols["license"]] == "13852"
    assert row[cols["dog_name"]] == "Rocky"
    assert row[cols["category"]] == "Intermediate"
    assert row[cols["class"]] == "1"
    assert row[cols["first_name"]] == "Mary"
    assert row[cols["last_name"]] == "Diserens"
