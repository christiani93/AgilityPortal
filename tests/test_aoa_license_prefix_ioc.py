"""
SWG-M-05 / SWG-R-10: Ausländische Lizenzen tragen einen IOC-Ländercode.
Der AOA-Import normalisiert Kurzpräfixe auf IOC (nicht ISO): D→GER, NL→NED,
CH→SUI; FRA/AUT/BEL/ITA/ESP sind in beiden gleich.
"""
from app.blueprints.admin.routes_aoa_import import _normalize_license


def test_german_prefix_maps_to_ioc_ger():
    assert _normalize_license("D-123") == "GER-123"


def test_netherlands_prefix_maps_to_ioc_ned():
    assert _normalize_license("NL-9") == "NED-9"


def test_switzerland_prefix_maps_to_ioc_sui():
    assert _normalize_license("CH-5") == "SUI-5"


def test_unchanged_codes_stay():
    assert _normalize_license("F-1") == "FRA-1"
    assert _normalize_license("A-2") == "AUT-2"
    assert _normalize_license("B-3") == "BEL-3"


def test_numeric_ch_license_unchanged():
    assert _normalize_license("55501") == "55501"


def test_already_ioc_prefix_passthrough():
    # Bereits dreistelliger Code ohne Eintrag in der Map bleibt (nur Uppercase).
    assert _normalize_license("ger-7") == "GER-7"
    assert _normalize_license("FIN-7") == "FIN-7"
