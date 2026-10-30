"""TKAMO-CSV-Import: Erweiterungen am AOA-Importer für TKAMO-Exporte
(SM/WM-Quali). Deckt die drei Kernänderungen ab:
- csv.Sniffer scheitert an TKAMO-Dateien → Fallback auf ';' (sonst kein Import)
- Spalten-Aliasse: 'Vereins-Nr.' (club_no), 'Mobile' (phone2), 'Geschlecht' (sex)
- Geschlecht 'Weiblich'/'Männlich' → Dog.sex 'F'/'M'
"""
import csv

import pytest

from app.blueprints.admin.routes_aoa_import import (
    _detect_columns, _normalize_sex, _parse_csv,
)

# Echte TKAMO-Kopfzeile (Spaltenreihenfolge weicht von AOA ab)
TKAMO_HEADER = ("Lizenznummer;Rufname;Hundename;Rasse;Geschlecht;Wurfdatum;"
                "Kategorie;Klasse;SHSB;Vereins-Nr.;Verein;Chip-Nr.;Vorname;Name;"
                "Strasse;PLZ;Ort;Telefon;Mobile;E-Mail;Sprache;Land;ACR-Rang;"
                "ACR-Punkte;Geburtsdatum;")
TKAMO_ROW = ("16105;Nayhra;O Nayhra from Elly (FCI);Border Collie;Weiblich;"
             "2022-04-25;Large;3;789716;439;Agility-Team Ennetsee;756098502053689;"
             "Annette;Ogierman;Wesmeristrasse 11;6221;Rickenbach;;+4179 337 27 16;"
             "annette@example.com;d;SUI;55;1401;1987-03-27;")


def test_normalize_sex():
    assert _normalize_sex("Weiblich") == "F"
    assert _normalize_sex("Männlich") == "M"
    assert _normalize_sex("W") == "F"
    assert _normalize_sex("M") == "M"
    assert _normalize_sex("") is None
    assert _normalize_sex(None) is None


def test_detect_columns_tkamo_header():
    cols = _detect_columns(TKAMO_HEADER.split(";"))
    assert cols["license"] == "Lizenznummer"
    assert cols["dog_name"] == "Hundename"
    assert cols["category"] == "Kategorie"
    assert cols["class"] == "Klasse"
    assert cols["first_name"] == "Vorname"
    assert cols["last_name"] == "Name"
    assert cols["email"] == "E-Mail"
    assert cols["club"] == "Verein"
    assert cols["breed"] == "Rasse"
    # Neu abgedeckte TKAMO-Spalten
    assert cols["club_no"] == "Vereins-Nr."
    assert cols["phone"] == "Telefon"
    assert cols["phone2"] == "Mobile"
    assert cols["sex"] == "Geschlecht"


def test_parse_csv_delimiter_fallback_when_sniffer_fails(monkeypatch):
    """Wenn der Sniffer scheitert (wie bei echten TKAMO-Dateien), muss _parse_csv
    auf das häufigste Trennzeichen der Kopfzeile (';') zurückfallen statt zu
    crashen."""
    def _boom(self, *a, **k):
        raise csv.Error("Could not determine delimiter")
    monkeypatch.setattr(csv.Sniffer, "sniff", _boom)

    content = TKAMO_HEADER + "\n" + TKAMO_ROW + "\n"
    rows, headers = _parse_csv(content)
    assert len(headers) >= 25
    assert "Lizenznummer" in headers
    assert len(rows) == 1
    assert rows[0]["Lizenznummer"] == "16105"
    assert rows[0]["Geschlecht"] == "Weiblich"
    assert rows[0]["Vereins-Nr."] == "439"


def test_parse_and_normalize_sex_end_to_end(monkeypatch):
    """Zusammenspiel: parsen (mit Fallback) + Spalten erkennen + Geschlecht
    normalisieren."""
    monkeypatch.setattr(csv.Sniffer, "sniff",
                        lambda self, *a, **k: (_ for _ in ()).throw(csv.Error("x")))
    rows, headers = _parse_csv(TKAMO_HEADER + "\n" + TKAMO_ROW + "\n")
    cols = _detect_columns(headers)
    assert _normalize_sex(rows[0][cols["sex"]]) == "F"
