"""Reglement-Corpus-Zugriff + Tier-1-Volltextsuche (ohne LLM, deterministisch).

Liest die Content-Baseline (manifest.json + extrahierte Volltexte), die separat
aufgebaut/gepflegt wird (siehe ClaudeSync\\reglement_corpus bzw. den Reglement-Monitor
im AdminPortal). Diese Suche ist nur LESEND — sie lädt/aktualisiert nichts.

Pfad kommt aus ``current_app.config['REGLEMENT_CORPUS_DIR']`` (Default im App-Setup).
Fehlt der Corpus, liefern die Funktionen einen sauberen Fehlerstatus statt zu crashen.
"""
from __future__ import annotations

import json
import os
import re
from functools import lru_cache

from flask import current_app

MANIFEST_NAME = "manifest.json"


def corpus_dir() -> str:
    return current_app.config.get("REGLEMENT_CORPUS_DIR", "")


def _manifest_path(cdir: str) -> str:
    return os.path.join(cdir, MANIFEST_NAME)


@lru_cache(maxsize=8)
def _load_manifest_cached(manifest_path: str, mtime: float) -> dict:
    """Manifest laden; über (Pfad, mtime) gecached, lädt also nur neu wenn die Datei
    sich ändert (mtime ist Teil des Cache-Keys)."""
    with open(manifest_path, encoding="utf-8") as fh:
        return json.load(fh)


def load_manifest() -> dict | None:
    cdir = corpus_dir()
    mpath = _manifest_path(cdir)
    if not cdir or not os.path.exists(mpath):
        return None
    return _load_manifest_cached(mpath, os.path.getmtime(mpath))


def corpus_status() -> dict:
    """Übersicht für die UI: ist der Corpus da, wie viele Dokumente, wann gebaut."""
    cdir = corpus_dir()
    man = load_manifest()
    if man is None:
        return {"ok": False, "corpus_dir": cdir,
                "error": "Kein Reglement-Corpus gefunden (manifest.json fehlt). "
                         "REGLEMENT_CORPUS_DIR prüfen bzw. Baseline aufbauen."}
    docs = man.get("documents", [])
    years = sorted({d.get("year") for d in docs if d.get("year")}, reverse=True)
    modules = sorted({m for d in docs for m in d.get("affects_modules", [])})
    return {
        "ok": True,
        "corpus_dir": cdir,
        "created_utc": man.get("created_utc"),
        "document_count": man.get("document_count", len(docs)),
        "years": years,
        "modules": modules,
        "source_page": man.get("source_page"),
    }


def _read_text(cdir: str, rel_path: str) -> list[str]:
    path = os.path.join(cdir, rel_path.replace("/", os.sep))
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def search(query: str, *, year=None, doc=None, module=None, context: int = 1,
           max_docs: int = 40, max_hits_per_doc: int = 40, max_total_hits: int = 400) -> dict:
    """Tier-1-Volltextsuche. Mehrere Begriffe = UND pro Zeile (alle müssen in der
    Zeile vorkommen). Case-insensitive, Teilstring (kein Regex vom Nutzer).

    Rückgabe:
      {ok, corpus_dir, error, query, terms, total_hits, doc_count,
       documents: [ {filename, category, year, source, modules,
                     hits: [ {line, context:[{n,text,match}]} ]} ],
       truncated: bool }
    """
    man = load_manifest()
    cdir = corpus_dir()
    terms = [t for t in (query or "").split() if t]
    if man is None:
        return {"ok": False, "corpus_dir": cdir, "error": "Kein Reglement-Corpus gefunden.",
                "query": query, "terms": terms, "total_hits": 0, "documents": [], "doc_count": 0}
    if not terms:
        return {"ok": True, "corpus_dir": cdir, "error": None, "query": query, "terms": [],
                "total_hits": 0, "documents": [], "doc_count": 0, "truncated": False}

    patterns = [re.compile(re.escape(t), re.IGNORECASE) for t in terms]
    docs = man.get("documents", [])
    if year:
        docs = [d for d in docs if str(d.get("year")) == str(year)]
    if doc:
        docs = [d for d in docs if doc.lower() in d.get("filename", "").lower()]
    if module:
        docs = [d for d in docs if any(module.lower() in m for m in d.get("affects_modules", []))]

    out_docs = []
    total_hits = 0
    truncated = False
    for d in docs:
        if total_hits >= max_total_hits or len(out_docs) >= max_docs:
            truncated = True
            break
        lines = _read_text(cdir, d.get("text_file", ""))
        if not lines:
            continue
        hit_lines = [i for i, ln in enumerate(lines) if all(p.search(ln) for p in patterns)]
        if not hit_lines:
            continue
        hits = []
        for i in hit_lines[:max_hits_per_doc]:
            lo, hi = max(0, i - context), min(len(lines), i + context + 1)
            ctx = [{"n": j + 1, "text": lines[j].rstrip(), "match": (j == i)} for j in range(lo, hi)]
            hits.append({"line": i + 1, "context": ctx})
        total_hits += len(hit_lines[:max_hits_per_doc])
        if len(hit_lines) > max_hits_per_doc:
            truncated = True
        out_docs.append({
            "filename": d.get("filename"),
            "category": d.get("category"),
            "year": d.get("year"),
            "source": d.get("source"),
            "modules": d.get("affects_modules", []),
            "url": d.get("url"),
            "hits": hits,
            "hit_count": len(hit_lines),
        })

    return {
        "ok": True, "corpus_dir": cdir, "error": None,
        "query": query, "terms": terms,
        "total_hits": total_hits, "doc_count": len(out_docs),
        "documents": out_docs, "truncated": truncated,
    }
