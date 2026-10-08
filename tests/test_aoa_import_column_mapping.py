"""Spalten-Mapping-Tests für AOA-/TKAMO-Importer.

Kein App-Context nötig — testet nur die Hilfsfunktionen.
"""
import io

from app.blueprints.admin.routes_aoa_import import (
    _coerce_cell, _decode_text, _detect_columns, _parse_csv, _parse_xlsx,
    _read_upload, _unescape)


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

# Reales AOA-/SportyDog-Export-Format (mit " AOA"-Suffix, Stand 2026)
REAL_AOA_HEADERS = [
    "A Datum", "A ID Turnier", "HF Name AOA", "HF Vorname AOA", "HF Strasse AOA",
    "HF PLZ AOA", "HF Ort AOA", "HF Land AOA", "HF Sprache AOA", "HF Telefon AOA",
    "HF Email AOA", "HF Vereinnr AOA", "Hf Verein", "H Lizenz AOA", "H Kategorie AOA",
    "H Klasse AOA", "H Name AOA", "H Rasse AOA", "H SHSB AOA", "H Chip",
]


def _resolve_cols(headers):
    return _detect_columns(headers)


def test_aoa_original_headers_all_mapped():
    cols = _resolve_cols(AOA_HEADERS)
    # breed ist optional (AOA-Original hat keine Rasse-Spalte)
    required = {k: v for k, v in cols.items() if k != "breed"}
    assert all(required.values()), f"Unmapped: {[k for k,v in required.items() if not v]}"
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


def test_real_aoa_export_headers_all_mapped():
    """Reales AOA-Export-Format mit ' AOA'-Suffix (vorher gar nicht erkannt →
    0 Importe). 'Hf Verein' hat kein Suffix, wird case-insensitiv gematcht."""
    cols = _resolve_cols(REAL_AOA_HEADERS)
    required = ["license", "dog_name", "category", "class",
                "first_name", "last_name", "email", "club", "club_no", "breed"]
    assert all(cols[k] for k in required), \
        f"Unmapped: {[k for k in required if not cols[k]]}"
    assert cols["license"] == "H Lizenz AOA"
    assert cols["dog_name"] == "H Name AOA"
    assert cols["last_name"] == "HF Name AOA"
    assert cols["first_name"] == "HF Vorname AOA"
    assert cols["club"] == "Hf Verein"
    assert cols["club_no"] == "HF Vereinnr AOA"
    assert cols["breed"] == "H Rasse AOA"


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


def test_unescape_removes_dbisam_backslash_escaping():
    # SportyDog/AOA-Export escaped Apostrophe/Anführungszeichen (DBISAM-Eigenart)
    assert _unescape("Cypat\\'Agil") == "Cypat'Agil"
    assert _unescape("Les Cabot\\'ins") == "Les Cabot'ins"
    assert _unescape("Djinn\\' Tomic Folly") == "Djinn' Tomic Folly"
    assert _unescape('Les "Cabot\\"ins"') == 'Les "Cabot"ins"'


def test_unescape_leaves_plain_text_unchanged():
    assert _unescape("Rocky") == "Rocky"
    assert _unescape("") == ""
    assert _unescape(None) is None


# ── Upload-Lesen: xlsx + Encoding-Fallback ──────────────────────────────────

class _FakeUpload:
    def __init__(self, filename, data: bytes):
        self.filename = filename
        self._data = data

    def read(self):
        return self._data


def _build_xlsx() -> bytes:
    import openpyxl
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["H Lizenz AOA", "H Name AOA", "H Kategorie AOA", "H Klasse AOA",
               "HF Name AOA", "HF Vorname AOA", "Hf Verein", "H Rasse AOA"])
    # Umlaute + ganzzahlige Zahlwerte (openpyxl liefert 1.0 → muss "1" werden)
    ws.append([15333, "Mac", "Large", 1, "Brönnimann", "Christiane", "SKBS",
               "Altdeutscher Schäferhund"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_coerce_cell_integer_float_and_none():
    assert _coerce_cell(None) == ""
    assert _coerce_cell(1.0) == "1"      # Klasse soll "1" bleiben, nicht "1.0"
    assert _coerce_cell(15333) == "15333"
    assert _coerce_cell("Mac") == "Mac"


def test_parse_xlsx_preserves_umlauts_and_strings():
    rows, headers = _parse_xlsx(_build_xlsx())
    cols = _detect_columns(headers)
    assert len(rows) == 1
    row = rows[0]
    assert row[cols["license"]] == "15333"
    assert row[cols["class"]] == "1"             # kein "1.0"
    assert row[cols["last_name"]] == "Brönnimann"  # Umlaut intakt
    assert row[cols["breed"]] == "Altdeutscher Schäferhund"


def test_read_upload_dispatches_xlsx_by_extension_and_magic():
    data = _build_xlsx()
    rows, _ = _read_upload(_FakeUpload("export.xlsx", data))
    assert len(rows) == 1
    # Auch ohne passende Endung über ZIP-Magic ('PK') erkannt
    rows2, _ = _read_upload(_FakeUpload("export.bin", data))
    assert len(rows2) == 1


def test_decode_text_falls_back_to_cp1252_for_excel_csv():
    # Excel "Speichern als CSV" auf DE-Windows schreibt cp1252 (ö = 0xF6)
    cp1252 = "Nachname;Vorname\r\nBrönnimann;Christiane\r\n".encode("cp1252")
    text = _decode_text(cp1252)
    assert "Brönnimann" in text  # kein � mehr
    # UTF-8-Eingabe bleibt ebenfalls korrekt
    assert _decode_text("Köniz".encode("utf-8")) == "Köniz"


def test_read_upload_csv_cp1252_roundtrip():
    cp1252 = "H Lizenz;H Name;H Kategorie;H Kl Eingabe\r\n13852;Füchsli;Large;1\r\n".encode("cp1252")
    rows, headers = _read_upload(_FakeUpload("export.csv", cp1252))
    cols = _detect_columns(headers)
    assert rows[0][cols["dog_name"]] == "Füchsli"
