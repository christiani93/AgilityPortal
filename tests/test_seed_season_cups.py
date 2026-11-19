"""seed-season-events legt pro TV-Serie automatisch einen Saison-Cup an
(Titelverteidiger-Speicher), idempotent und unabhängig vom Reservation-Gate
der Events.
"""
from app.commands import seed_season_events
from app.models import Cup


def test_seed_creates_halloween_cup(app):
    with app.app_context():
        runner = app.test_cli_runner()
        runner.invoke(seed_season_events, [])

        cups = Cup.query.filter_by(special_ruleset="halloween_cup").all()
        assert len(cups) == 1
        cup = cups[0]
        assert cup.season == 2026
        assert cup.name == "Halloween Cup 2026"
        assert cup.title_defender_spots == 1


def test_seed_cup_is_idempotent(app):
    with app.app_context():
        runner = app.test_cli_runner()
        runner.invoke(seed_season_events, [])
        runner.invoke(seed_season_events, [])
        assert Cup.query.filter_by(special_ruleset="halloween_cup").count() == 1


def test_dry_run_creates_nothing(app):
    with app.app_context():
        runner = app.test_cli_runner()
        runner.invoke(seed_season_events, ["--dry-run"])
        assert Cup.query.count() == 0
