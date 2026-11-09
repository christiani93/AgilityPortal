"""Admin-Reglement-Suche (Tier 1): Route-Gating, Corpus-Status, Volltextsuche.

Nutzt einen Mini-Corpus in einem Temp-Ordner (unabhängig von der echten Baseline),
damit der Test deterministisch + portabel ist.
"""
import json
import os

import pytest


def _make_corpus(tmp_path):
    (tmp_path / "text").mkdir()
    (tmp_path / "text" / "Agility_Reglement_SM_Einzel_2025_DE.txt").write_text(
        "3.4 Qualifikation\n"
        "Die Kombinationsrangliste wird aus den Resultaten der Qualifikationslaeufe errechnet.\n"
        "Massgeblich sind die Gesamtfehlerpunkte.\n",
        encoding="utf-8",
    )
    manifest = {
        "schema": "reglement-corpus/1",
        "created_utc": "2026-11-08T00:00:00Z",
        "source_page": "https://www.tkamo.ch/de/agility/reglemente.html",
        "document_count": 1,
        "documents": [{
            "filename": "Agility_Reglement_SM_Einzel_2025_DE.pdf",
            "source": "tkamo-seite",
            "url": "https://www.tkamo.ch/media/files/Agility_Reglement_SM_Einzel_2025_DE.pdf",
            "category": "reglement", "year": 2025,
            "text_file": "text/Agility_Reglement_SM_Einzel_2025_DE.txt",
            "affects_modules": ["kombirangliste", "sm-quali-rechenkern"],
        }],
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return str(tmp_path)


@pytest.fixture()
def client_with_corpus(app, tmp_path):
    app.config["REGLEMENT_CORPUS_DIR"] = _make_corpus(tmp_path)
    return app.test_client()


def test_requires_admin_key(client_with_corpus):
    assert client_with_corpus.get("/admin/reglement").status_code == 403
    assert client_with_corpus.get("/admin/reglement?key=wrong").status_code == 403


def test_search_home_renders(client_with_corpus):
    r = client_with_corpus.get("/admin/reglement?key=dev-admin-key")
    assert r.status_code == 200
    assert "Reglement-Suche" in r.get_data(as_text=True)
    assert "1 Dokumente" in r.get_data(as_text=True)


def test_search_finds_term(client_with_corpus):
    r = client_with_corpus.get("/admin/reglement?key=dev-admin-key&q=Kombinationsrangliste")
    body = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "Treffer" in body
    assert "Agility_Reglement_SM_Einzel_2025_DE.pdf" in body
    assert "kombirangliste" in body            # Modul-Badge


def test_search_no_hits(client_with_corpus):
    r = client_with_corpus.get("/admin/reglement?key=dev-admin-key&q=Giraffe")
    assert "Keine Treffer" in r.get_data(as_text=True)


def test_filter_by_module(client_with_corpus):
    r = client_with_corpus.get("/admin/reglement?key=dev-admin-key&q=Gesamtfehlerpunkte&module=kombirangliste")
    assert r.status_code == 200
    assert "Treffer" in r.get_data(as_text=True)


def test_missing_corpus_shows_warning(app):
    app.config["REGLEMENT_CORPUS_DIR"] = os.path.join(os.sep, "nonexistent_corpus_dir_xyz")
    c = app.test_client()
    r = c.get("/admin/reglement?key=dev-admin-key")
    assert r.status_code == 200
    assert "Kein Reglement-Corpus" in r.get_data(as_text=True)
