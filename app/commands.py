"""
Flask-CLI-Befehle für Entwicklung und Tests.
"""
import click
from datetime import datetime
from flask.cli import with_appcontext
from app.extensions import db


_CATEGORY_MAP = {
    "L": "Large",
    "I": "Intermediate",
    "M": "Medium",
    "S": "Small",
}

_FIRST_NAMES = [
    "Anna", "Lea", "Sara", "Laura", "Nina", "Julia", "Maria", "Sandra",
    "Klaus", "Thomas", "Peter", "Stefan", "Markus", "Daniel", "Michael", "Andreas",
]
_LAST_NAMES = [
    "Müller", "Meier", "Schmid", "Fischer", "Weber", "Keller", "Huber",
    "Wolf", "Zimmermann", "Baumann", "Moser", "Frei", "Brunner", "Steiner",
]

_DOG_NAMES = [
    "Ace", "Bella", "Charlie", "Daisy", "Echo", "Finn", "Grace", "Hunter",
    "Ivy", "Jake", "Kira", "Leo", "Maya", "Neo", "Oreo", "Pepper",
    "Quinn", "Rex", "Sky", "Tara", "Uma", "Vega", "Wren", "Xena",
    "Yara", "Zeus", "Amber", "Bruno", "Cleo", "Duke",
]


def _test_external_id(event_id: int, n: int) -> str:
    return f"TEST_{event_id}_{n:04d}"


@click.command("seed-test-regs")
@click.argument("event_id", type=int)
@click.option("--count", "-n", default=5, show_default=True,
              help="Anzahl Testanmeldungen pro Lauf")
@with_appcontext
def seed_test_regs(event_id: int, count: int):
    """
    Erstellt Testanmeldungen für alle Läufe eines Turniers.

    Beispiel:
      flask seed-test-regs 3
      flask seed-test-regs 3 --count 10
    """
    from app.models import (Event, EventRun, Registration, RegistrationStatus,
                             Person, Dog, DogOwner, DogOwnerRole, LicenseKind,
                             TkaMasterStatus)

    event = db.session.get(Event, event_id)
    if not event:
        click.echo(f"Event {event_id} nicht gefunden.", err=True)
        return

    runs = db.session.execute(
        db.select(EventRun).filter_by(event_id=event_id)
    ).scalars().all()

    if not runs:
        click.echo("Keine Läufe für dieses Turnier definiert.", err=True)
        return

    # Höchste bereits vorhandene Testnummer ermitteln
    from sqlalchemy import like
    existing = db.session.execute(
        db.select(db.func.count(Person.id))
        .where(Person.external_id.like(f"TEST_{event_id}_%"))
    ).scalar() or 0

    created = 0
    n = existing

    for run in runs:
        category_code = _CATEGORY_MAP.get(run.category, run.category)
        for _ in range(count):
            n += 1
            ext_id = _test_external_id(event_id, n)

            first = _FIRST_NAMES[(n - 1) % len(_FIRST_NAMES)]
            last  = _LAST_NAMES[(n - 1) % len(_LAST_NAMES)]
            dog_name = _DOG_NAMES[(n - 1) % len(_DOG_NAMES)]

            # Person
            person = Person(
                first_name=first,
                last_name=last,
                email=f"test{n}@test.invalid",
                external_id=ext_id,
            )
            db.session.add(person)
            db.session.flush()

            # Hund (FOREIGN-Lizenz umgeht CH-Validierung)
            dog = Dog(
                name=dog_name,
                license_no=f"TST-{n:06d}",
                license_kind=LicenseKind.FOREIGN,
                category=run.category,
                class_level=run.class_level,
                tka_master_status=TkaMasterStatus.NOT_REQUIRED,
                external_id=f"TESTDOG_{event_id}_{n:04d}",
            )
            db.session.add(dog)
            db.session.flush()

            # Besitzer-Verknüpfung
            owner = DogOwner(dog_id=dog.id, person_id=person.id,
                             role=DogOwnerRole.OWNER)
            db.session.add(owner)

            # Anmeldung
            reg = Registration(
                event_id=event_id,
                dog_id=dog.id,
                handler_id=person.id,
                category_code=category_code,
                class_level=run.class_level,
                status=RegistrationStatus.CONFIRMED,
                external_id=f"TESTREG_{event_id}_{n:04d}",
            )
            db.session.add(reg)
            created += 1

    db.session.commit()
    click.echo(
        f"✓ {created} Testanmeldungen für Turnier «{event.name}» erstellt "
        f"({len(runs)} Läufe × {count} Starter)."
    )


@click.command("clear-test-regs")
@click.argument("event_id", type=int)
@click.confirmation_option(prompt="Alle Testdaten für dieses Turnier löschen?")
@with_appcontext
def clear_test_regs(event_id: int):
    """
    Löscht alle Testanmeldungen, -hunde und -personen für ein Turnier.

    Beispiel:
      flask clear-test-regs 3
    """
    from app.models import Registration, Dog, Person, DogOwner

    # Registrierungen mit TEST-external_id
    regs = db.session.execute(
        db.select(Registration)
        .where(Registration.external_id.like(f"TESTREG_{event_id}_%"))
    ).scalars().all()

    dog_ids    = [r.dog_id    for r in regs]
    person_ids = [r.handler_id for r in regs if r.handler_id]

    for reg in regs:
        db.session.delete(reg)

    # Hunde löschen (cascade löscht DogOwner)
    for dog in db.session.execute(
        db.select(Dog).where(Dog.id.in_(dog_ids))
    ).scalars().all():
        db.session.delete(dog)

    # Personen löschen
    for person in db.session.execute(
        db.select(Person).where(Person.id.in_(person_ids))
    ).scalars().all():
        db.session.delete(person)

    db.session.commit()
    click.echo(
        f"✓ {len(regs)} Testanmeldungen, {len(dog_ids)} Hunde und "
        f"{len(person_ids)} Personen gelöscht."
    )


@click.command("create-test-event")
@click.option("--name", default="Testturnier", show_default=True, help="Turniername")
@click.option("--club-id", type=int, default=None, help="Verein-ID (optional)")
@click.option("--count", "-n", default=5, show_default=True, help="Starter pro Lauf")
@with_appcontext
def create_test_event(name: str, club_id: int, count: int):
    """
    Erstellt eine komplette Testveranstaltung (is_test=True) mit allen
    Standard-Läufen (Agility + Jumping, alle Kategorien, Klassen 1-3)
    und befüllt sie direkt mit Testanmeldungen.

    Beispiel:
      flask create-test-event
      flask create-test-event --name "Mein Testturnier" --count 8
    """
    from datetime import date, timedelta
    from app.models import (Event, EventRun, Registration, RegistrationStatus,
                             Person, Dog, DogOwner, DogOwnerRole, LicenseKind,
                             TkaMasterStatus)

    # Turnier anlegen
    starts = datetime.combine(date.today() + timedelta(days=7), datetime.min.time())
    event = Event(
        name=name,
        starts_at=starts,
        ends_at=starts,
        status="open",
        is_test=True,
        organiser_club_id=club_id,
        type="regular",
        ring_count=1,
    )
    db.session.add(event)
    db.session.flush()

    # Läufe: Agility + Jumping, alle 4 Kategorien, Klassen 1-3
    runs = []
    for discipline in ("agility", "jumping"):
        for cat in ("L", "I", "M", "S"):
            for kl in (1, 2, 3):
                run = EventRun(
                    event_id=event.id,
                    run_type=discipline,
                    category=cat,
                    class_level=kl,
                )
                db.session.add(run)
                runs.append((discipline, cat, kl))

    db.session.flush()

    # Testanmeldungen
    created = 0
    for n_global, (discipline, cat, kl) in enumerate(
        [(d, c, k) for d, c, k in runs for _ in range(count)], start=1
    ):
        category_code = _CATEGORY_MAP.get(cat, cat)
        ext_id = _test_external_id(event.id, n_global)

        first    = _FIRST_NAMES[(n_global - 1) % len(_FIRST_NAMES)]
        last     = _LAST_NAMES[(n_global - 1) % len(_LAST_NAMES)]
        dog_name = _DOG_NAMES[(n_global - 1) % len(_DOG_NAMES)]

        person = Person(
            first_name=first, last_name=last,
            email=f"test{n_global}@test.invalid",
            external_id=ext_id,
        )
        db.session.add(person)
        db.session.flush()

        dog = Dog(
            name=dog_name,
            license_no=f"TST-E{event.id:04d}N{n_global:05d}",
            license_kind=LicenseKind.FOREIGN,
            category=cat,
            class_level=kl,
            tka_master_status=TkaMasterStatus.NOT_REQUIRED,
            external_id=f"TESTDOG_{event.id}_{n_global:04d}",
        )
        db.session.add(dog)
        db.session.flush()

        db.session.add(DogOwner(dog_id=dog.id, person_id=person.id,
                                role=DogOwnerRole.OWNER))
        db.session.add(Registration(
            event_id=event.id, dog_id=dog.id, handler_id=person.id,
            category_code=category_code, class_level=kl,
            status=RegistrationStatus.CONFIRMED,
            external_id=f"TESTREG_{event.id}_{n_global:04d}",
        ))
        created += 1

    db.session.commit()
    click.echo(
        f"✓ Testturnier «{name}» (ID {event.id}) erstellt: "
        f"{len(runs)} Läufe, {created} Anmeldungen."
    )
    click.echo(f"  → Direkt aufrufen: /club/events/{event.id}/view")
