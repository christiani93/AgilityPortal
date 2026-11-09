"""Admin: Reglement-Volltextsuche (Tier 1) über die Content-Baseline.

Durchsucht die archivierten TKAMO- + event-spezifischen Reglemente (manifest.json +
extrahierte Volltexte) und zeigt pro Treffer Dokument, Zeile, Kontext und die vom
Manifest hinterlegte Modul-Zuordnung. Rein lesend, kein LLM, deterministisch.

Gated wie die übrigen Admin-Routen über ``?key=<ADMIN_KEY>``.
"""
from functools import wraps

from flask import Blueprint, abort, current_app, render_template, request
from flask_login import current_user

from app.services import reglement_corpus

reglement_admin_bp = Blueprint("reglement_admin", __name__)


def _require_admin_key(func):
    """Hybrid-Gate wie aoa_import: eingeloggter Superadmin ODER ``?key=<ADMIN_KEY>``."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
            return func(*args, **kwargs)
        expected = current_app.config.get("ADMIN_KEY")
        provided = request.args.get("key") or request.headers.get("X-Admin-Key")
        if not expected or provided != expected:
            abort(403)
        return func(*args, **kwargs)

    return wrapper


def _admin_key():
    if current_user.is_authenticated and getattr(current_user, "is_superadmin", False):
        return ""
    return request.args.get("key") or ""


@reglement_admin_bp.get("/admin/reglement")
@_require_admin_key
def reglement_search():
    query = (request.args.get("q") or "").strip()
    year = (request.args.get("year") or "").strip() or None
    module = (request.args.get("module") or "").strip() or None
    doc = (request.args.get("doc") or "").strip() or None
    try:
        context = max(0, min(5, int(request.args.get("context", 1))))
    except (TypeError, ValueError):
        context = 1

    status = reglement_corpus.corpus_status()
    results = None
    if query:
        results = reglement_corpus.search(query, year=year, module=module, doc=doc, context=context)

    return render_template(
        "admin/reglement/search.html",
        admin_key=_admin_key(),
        status=status,
        results=results,
        query=query,
        year=year or "",
        module=module or "",
        doc=doc or "",
        context=context,
    )
