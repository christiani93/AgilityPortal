"""Öffentliche Cup-Ranglisten und Finale (ohne Login)."""
from flask import Blueprint, abort, render_template

from app.models import Cup, CupFinal
from app.services.cup_standings import compute_standings


public_cups_bp = Blueprint("public_cups", __name__)


@public_cups_bp.get("/cups")
def cup_index():
    """Liste aller aktiven Cups."""
    cups = Cup.query.filter_by(is_active=True).order_by(Cup.season.desc(), Cup.name).all()
    return render_template("public/cups/index.html", cups=cups)


@public_cups_bp.get("/cups/<int:cup_id>")
def cup_standings(cup_id):
    """Öffentliche Qualifikations-Rangliste eines Cups."""
    cup = Cup.query.filter_by(id=cup_id, is_active=True).first_or_404()
    from app.services.cup_qualification import get_qualification
    qualification = get_qualification(cup)
    finals = CupFinal.query.filter_by(cup_id=cup_id, is_published=True).all()
    return render_template("public/cups/standings.html", cup=cup, qualification=qualification, finals=finals)


@public_cups_bp.get("/cups/<int:cup_id>/finals/<int:final_id>")
def cup_final_bracket(cup_id, final_id):
    """Öffentliches KO-Bracket eines Finales."""
    cup = Cup.query.filter_by(id=cup_id, is_active=True).first_or_404()
    final = CupFinal.query.filter_by(id=final_id, cup_id=cup_id, is_published=True).first_or_404()
    # Matchups nach Runde gruppieren
    from collections import defaultdict
    rounds = defaultdict(list)
    for m in sorted(final.matchups, key=lambda x: (x.round_no, x.matchup_no)):
        rounds[m.round_no].append(m)
    return render_template(
        "public/cups/final_bracket.html",
        cup=cup,
        final=final,
        rounds=dict(sorted(rounds.items())),
    )
