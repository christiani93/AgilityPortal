"""Registrierung verknüpft bestehende Teilnehmer-Person (gleiche E-Mail+Name,
ohne Account) statt ein Duplikat anzulegen."""
from app.extensions import db
from app.models import User, Person


def _register(client, email, first="Max", last="Muster", pw="geheim123"):
    return client.post(
        "/auth/register",
        data={
            "first_name": first,
            "last_name": last,
            "email": email,
            "password": pw,
            "password2": pw,
        },
        follow_redirects=False,
    )


def test_register_links_existing_participant(app):
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with app.app_context():
        # Importierter Teilnehmer ohne Account (z.B. aus AOA-Import),
        # E-Mail in GROSSBUCHSTABEN → case-insensitiver Abgleich muss greifen.
        p = Person(first_name="Max", last_name="Muster",
                   email="MAX@example.com", account_user_id=None)
        db.session.add(p)
        db.session.commit()
        pid = p.id

    resp = _register(client, "max@example.com")
    assert resp.status_code in (302, 303)

    with app.app_context():
        # Keine zweite Person angelegt
        people = db.session.execute(db.select(Person)).scalars().all()
        assert len(people) == 1, [(x.id, x.email) for x in people]
        linked = db.session.get(Person, pid)
        user = db.session.execute(db.select(User)).scalars().one()
        assert linked.account_user_id == user.id
        assert user.person_id == pid


def test_register_fresh_email_creates_person(app):
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    resp = _register(client, "neu@example.com", first="Erika", last="Neu")
    assert resp.status_code in (302, 303)
    with app.app_context():
        people = db.session.execute(db.select(Person)).scalars().all()
        assert len(people) == 1
        user = db.session.execute(db.select(User)).scalars().one()
        assert user.person_id == people[0].id
        assert people[0].account_user_id == user.id


def test_register_does_not_steal_person_with_account(app):
    """Person mit gleicher Mail+Name, aber bereits einem anderen Account
    zugeordnet, darf NICHT übernommen werden → neue Person entsteht."""
    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()
    with app.app_context():
        other = User(email="other@example.com", first_name="Max",
                     last_name="Muster", role="handler", is_active=True)
        other.set_password("whatever1")
        db.session.add(other)
        db.session.flush()
        p = Person(first_name="Max", last_name="Muster",
                   email="max@example.com", account_user_id=other.id)
        db.session.add(p)
        db.session.commit()
        taken_pid = p.id

    resp = _register(client, "max@example.com")
    assert resp.status_code in (302, 303)
    with app.app_context():
        people = db.session.execute(db.select(Person)).scalars().all()
        assert len(people) == 2  # bestehende (fremde) + neue eigene
        new_user = db.session.execute(
            db.select(User).filter_by(email="max@example.com")
        ).scalars().one()
        assert new_user.person_id != taken_pid
