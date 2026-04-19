"""
VAR-Integration — Videoanzeigesystem für Agility-Wettkämpfe.

Routen:
  GET  /events/<id>/var/display   — Anzeigeseite (öffentlich, für Beamer/Fremdsoftware)
  GET  /events/<id>/var/control   — Steuerseite (Login erforderlich)
  GET  /events/<id>/var/state     — State lesen (öffentlich, JSON)
  POST /events/<id>/var/state     — State setzen (Login erforderlich)
  GET  /events/<id>/var/content   — Anzeigeinhalt im VAR-HTML-Format (öffentlich)
"""
import json as _json
import os

from flask import abort, jsonify, render_template, request, Response, current_app
from flask_login import login_required

from app.extensions import db
from app.models import Event, LiveUpdate, Result, ResultImport
from .routes import club_bp


# ── Hilfsfunktionen ──────────────────────────────────────────────────────────

def _var_state_path(event_id: int) -> str:
    return os.path.join(current_app.instance_path, f"var_state_{event_id}.json")


def _read_var_state(event_id: int) -> dict:
    try:
        path = _var_state_path(event_id)
        with open(path, encoding="utf-8") as f:
            return _json.load(f)
    except Exception:
        return {"ring": ""}


def _write_var_state(event_id: int, data: dict):
    path = _var_state_path(event_id)
    with open(path, "w", encoding="utf-8") as f:
        _json.dump(data, f, ensure_ascii=False)


# ── Anzeigeseite (öffentlich) ────────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/var/display")
def event_var_display(event_id):
    """VAR Anzeigeseite — öffentlich, für Beamer oder Fremdsoftware-Link."""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    return render_template("var/var_display.html", event=event)


# ── Steuerseite (Login) ──────────────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/var/control")
@login_required
def event_var_control(event_id):
    """VAR Steuerseite — Ring auswählen, Display-URL anzeigen. Nur für Club-Admins."""
    from .routes import _assert_event_access
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    _assert_event_access(event)

    # Aktive Ringe aus den letzten LiveUpdates ermitteln
    all_updates = (
        db.session.execute(
            db.select(LiveUpdate)
            .filter_by(event_id=event_id)
            .order_by(LiveUpdate.created_at.desc())
            .limit(200)
        ).scalars().all()
    )
    # Neuesten Update pro Ring sammeln
    live_rings: dict = {}
    for upd in all_updates:
        try:
            p = _json.loads(upd.payload_json or "{}")
        except Exception:
            continue
        ring = p.get("ring") or ""
        if ring and ring not in live_rings:
            sl   = p.get("startlist") or {}
            curr = sl.get("current_starter")
            nxt  = sl.get("next_starter")
            live_rings[ring] = {
                "ring":          ring,
                "run_name":      p.get("run_name") or "",
                "discipline":    p.get("discipline") or "",
                "category_code": p.get("category_code") or "",
                "class_level":   p.get("class_level") or 0,
                "current_dog":   curr.get("dog_name")     if curr else "",
                "current_handler": curr.get("handler_name") if curr else "",
                "next_dog":      nxt.get("dog_name")      if nxt  else "",
            }

    # Falls noch keine LiveUpdates → Ringe aus event.ring_count aufbauen
    if not live_rings:
        ring_count = event.ring_count or 1
        for i in range(1, ring_count + 1):
            r = f"Ring {i}"
            live_rings[r] = {"ring": r, "run_name": "—", "discipline": "",
                             "category_code": "", "class_level": 0,
                             "current_dog": "", "current_handler": "", "next_dog": ""}

    state = _read_var_state(event_id)
    return render_template(
        "var/var_control.html",
        event=event,
        live_rings=list(live_rings.values()),
        state=state,
    )


# ── State-API ────────────────────────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/var/state")
def event_var_state_get(event_id):
    """GET VAR-State — öffentlich, wird von der Anzeigeseite gepollt."""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    return jsonify(_read_var_state(event_id))


@club_bp.post("/events/<int:event_id>/var/state")
@login_required
def event_var_state_post(event_id):
    """POST VAR-State — setzt den aktiven Ring."""
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)
    data = request.get_json(force=True) or {}
    ring = data.get("ring", "")
    _write_var_state(event_id, {"ring": ring})
    return jsonify({"ok": True, "ring": ring})


# ── Content-Endpunkt (öffentlich) ────────────────────────────────────────────

@club_bp.get("/events/<int:event_id>/var/content")
def event_var_content(event_id):
    """
    Liefert den VAR-Anzeigeinhalt als vollständige HTML-Seite.
    CSS-Klassen entsprechen exakt dem VAR-Fremdsoftware-Format.
    Parameter: ?ring=Ring+1
    """
    event = db.session.get(Event, event_id)
    if not event:
        abort(404)

    ring = request.args.get("ring", "").strip()
    if not ring:
        return Response(
            "<html><body style='font-family:arial;font-size:20px;"
            "background:#dae5f4;display:flex;align-items:center;"
            "justify-content:center;height:100vh;'>"
            "<p>Kein Ring ausgewählt.</p></body></html>",
            content_type="text/html; charset=utf-8",
        )

    # Neuesten LiveUpdate für diesen Ring laden
    all_updates = (
        db.session.execute(
            db.select(LiveUpdate)
            .filter_by(event_id=event_id)
            .order_by(LiveUpdate.created_at.desc())
            .limit(200)
        ).scalars().all()
    )
    ring_data = None
    for upd in all_updates:
        try:
            p = _json.loads(upd.payload_json or "{}")
        except Exception:
            continue
        if p.get("ring") == ring:
            ring_data = p
            break

    # Ergebnisse für diesen Ring (neuester Import)
    latest_import = (
        db.session.execute(
            db.select(ResultImport)
            .filter_by(event_id=event_id)
            .order_by(ResultImport.created_at.desc())
        ).scalars().first()
    )
    result_rows = []
    result_run_name = ""
    if latest_import:
        all_results = (
            db.session.execute(
                db.select(Result)
                .filter_by(result_import_id=latest_import.id, ring=ring)
                .order_by(Result.discipline, Result.category_code,
                          Result.class_level, Result.rank)
            ).scalars().all()
        )
        # Nur die letzte Gruppe (aktuellster Lauf dieses Rings)
        if all_results:
            last = all_results[-1]
            result_run_name = (
                f"{(last.discipline or '').capitalize()} "
                f"{last.category_code} Kl.{last.class_level}"
            ).strip()
            result_rows = [
                r for r in all_results
                if r.discipline  == last.discipline
                and r.category_code == last.category_code
                and r.class_level   == last.class_level
            ]

    return render_template(
        "var/var_content.html",
        ring=ring,
        ring_data=ring_data,
        result_rows=result_rows,
        result_run_name=result_run_name,
    )
