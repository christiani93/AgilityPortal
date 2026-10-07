"""
Test für die Self-Service-Seite "Meine Angaben" (club.profile_edit):
Name/Telefon bearbeiten, synchron zwischen User und Person (Person ist das,
was eventexport.v1 an die AgilitySoftware schickt und letztlich im
TKAMO-Export als Hundefuehrer landet).
"""
from app.extensions import db
from app import models as M


def _login(client, user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = str(user_id)
        sess["_fresh"] = True


def test_profile_edit_creates_person_and_syncs_name(app):
    with app.app_context():
        app.config["WTF_CSRF_ENABLED"] = False
        user = M.User(email="h@test.ch", role="handler",
                      first_name="Alt", last_name="Name")
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        client = app.test_client()
        _login(client, user_id)

        resp = client.post("/club/profile", data={
            "first_name": "Neu",
            "last_name": "Nachname",
            "phone": "079 123 45 67",
        })
        assert resp.status_code == 302

        updated = db.session.get(M.User, user_id)
        assert updated.first_name == "Neu"
        assert updated.last_name == "Nachname"
        assert updated.person is not None
        assert updated.person.first_name == "Neu"
        assert updated.person.last_name == "Nachname"
        assert updated.person.phone == "079 123 45 67"
