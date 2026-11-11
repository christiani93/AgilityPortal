"""
Flask-CLI-Befehle für Entwicklung und Tests.
"""
import click
from datetime import datetime, date
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

    # Eindeutige (Kategorie, Klasse)-Kombinationen — eine Anmeldung gilt
    # für alle Disziplinen (Agility + Jumping teilen denselben Teilnehmerkreis)
    seen = set()
    cat_class_combos = []
    for run in runs:
        key = (run.category, run.class_level)
        if key not in seen:
            seen.add(key)
            cat_class_combos.append((run.category, run.class_level))

    created = 0
    n = existing

    for cat, kl in cat_class_combos:
        category_code = _CATEGORY_MAP.get(cat, cat)
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
                category=cat,
                class_level=kl,
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
                class_level=kl,
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


# ---------------------------------------------------------------------------
# Saison-Turniere (Kalender H2 2026 – Feb 2027) als echte Events anlegen.
# Sichtbar (is_published=True), Anmeldung geschlossen (status="closed"), da
# die Anmeldung noch nicht über das Portal, sondern über AOA läuft.
# ---------------------------------------------------------------------------

# organiser = Name-Fragment zum Suchen des Veranstalter-Vereins (Club.name ILIKE).
_SEASON_EVENTS = [
    # Halloween Cup = 3 eigenständige Tagesevents (EventRun-Unique-Constraint
    # erlaubt kein 2. Agi/Jump je Kombination; Sa+So sind unabhängige Durchgänge).
    # Fr = nur Tunnellauf (keine offizielle AIS), Sa/So = Agility+Jumping mit AIS.
    {"ext": "SEASON_2627_halloween_fr", "name": "Halloween Cup 30.10.2026",
     "start": date(2026, 10, 30), "end": date(2026, 10, 30),
     "type": "regular", "ruleset": "halloween_cup", "organiser": "Seeland"},

    {"ext": "SEASON_2627_halloween_sa", "name": "Halloween Cup 31.10.2026",
     "start": date(2026, 10, 31), "end": date(2026, 10, 31),
     "type": "regular", "ruleset": "halloween_cup", "organiser": "Seeland"},

    {"ext": "SEASON_2627_halloween_so", "name": "Halloween Cup 01.11.2026",
     "start": date(2026, 11, 1), "end": date(2026, 11, 1),
     "type": "regular", "ruleset": "halloween_cup", "organiser": "Seeland"},

    {"ext": "SEASON_2627_wimesma_m1", "name": "WiMeSma 26/27 – Meeting 1",
     "start": date(2026, 11, 15), "end": date(2026, 11, 15),
     "type": "regular", "ruleset": None, "organiser": "Kiesen",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_seeland_abendmeeting", "name": "Abendmeeting 20.11.2026",
     "start": date(2026, 11, 20), "end": date(2026, 11, 20),
     "type": "regular", "ruleset": None, "organiser": "Seeland",
     "location": "Münsingen"},

    # BCCS-SM = 2 eigenständige Tagesevents (wie HCS: EventRun-Unique-Constraint
    # erlaubt kein 2. Agi/Jump je Kombination; Sa+So sind unabhängige Durchgänge).
    # Sa = SM (Klasse 3), So = Nachwuchs (Klasse 1-2). AIS wird wie bei HCS separat
    # auf Prod gesetzt (Sa 12323 / So 12324).
    {"ext": "SEASON_2627_bccs_sm_sa", "name": "BCCS-Schweizermeisterschaft 21.11.2026",
     "start": date(2026, 11, 21), "end": date(2026, 11, 21),
     "type": "bccs_sm", "ruleset": None, "organiser": "Seeland",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_bccs_sm_so", "name": "BCCS-Schweizermeisterschaft 22.11.2026",
     "start": date(2026, 11, 22), "end": date(2026, 11, 22),
     "type": "bccs_sm", "ruleset": None, "organiser": "Seeland",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_advent", "name": "Adventscup",
     "start": date(2026, 11, 27), "end": date(2026, 11, 29),
     "type": "regular", "ruleset": "advents_cup", "organiser": "LiTyWee"},

    # SKBS-SM + FMBB-WM-Quali am selben Wochenende (Sa 05.12 + So 06.12.2026):
    # pro Tag EIN kombiniertes Turnier mit denselben Läufen. type=skbs_sm bringt
    # das Finalisten-Feature; FMBB hat im Portal keine eigene Logik (nur Label),
    # die FMBB-Auswertung läuft in der AgilitySoftware aus denselben Läufen.
    # AIS je Tag kommt aus der AdminPortal-Reservation (noch nicht erfasst → das
    # Reservation-Gate überspringt beide, bis die Reservationen angelegt sind).
    {"ext": "SEASON_2627_skbs_fmbb_sa", "name": "SKBS-SM + FMBB-WM-Quali 05.12.2026",
     "start": date(2026, 12, 5), "end": date(2026, 12, 5),
     "type": "skbs_sm", "ruleset": None, "organiser": "Seeland",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_skbs_fmbb_so", "name": "SKBS-SM + FMBB-WM-Quali 06.12.2026",
     "start": date(2026, 12, 6), "end": date(2026, 12, 6),
     "type": "skbs_sm", "ruleset": None, "organiser": "Seeland",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_wimesma_m2", "name": "WiMeSma 26/27 – Meeting 2",
     "start": date(2026, 12, 12), "end": date(2026, 12, 12),
     "type": "regular", "ruleset": None, "organiser": "Kiesen",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_edelweiss", "name": "Edelweiss Challenge",
     "start": date(2027, 1, 8), "end": date(2027, 1, 10),
     "type": "regular", "ruleset": "edelweiss_challenge", "organiser": "LiTyWee"},

    {"ext": "SEASON_2627_wimesma_m3", "name": "WiMeSma 26/27 – Meeting 3",
     "start": date(2027, 1, 17), "end": date(2027, 1, 17),
     "type": "regular", "ruleset": None, "organiser": "Kiesen",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_daenzer_jan", "name": "Turnier Dänzer (Januar)",
     "start": date(2027, 1, 22), "end": date(2027, 1, 24),
     "type": "regular", "ruleset": None, "organiser": "Seeland"},

    {"ext": "SEASON_2627_wimesma_final", "name": "WiMeSma 26/27 – Meeting 4 + Finallauf",
     "start": date(2027, 2, 13), "end": date(2027, 2, 13),
     "type": "regular", "ruleset": None, "organiser": "Kiesen",
     "location": "Münsingen"},

    {"ext": "SEASON_2627_daenzer_feb", "name": "Turnier Dänzer (Februar)",
     "start": date(2027, 2, 19), "end": date(2027, 2, 21),
     "type": "regular", "ruleset": None, "organiser": "Seeland"},
]


def _find_reservation_ais(spec_start: date):
    """Sucht die AIS-Turniernummer für ein Datum in der AdminPortal-Reservation
    (gleiche DB, andere App - kein eigenes Modell, daher raw SQL).

    Reihenfolge:
    1. `reservation_event`-Zeile mit exaktem `date_from`-Treffer (die saubere,
       pro-Tag aufgeschlüsselte Quelle - siehe Reservation #63 nach dem Fix
       vom 09.11.2026).
    2. Fallback: `reservation`-Haupttabelle, aber NUR wenn es ein echtes
       Eintages-Turnier ist (date_to NULL oder == date_from) - bei Mehrtage-
       Reservationen ohne `reservation_event`-Aufschlüsselung lässt sich die
       passende AIS-Nummer aus `ais_turniernummer_extra` (Komma-String) nicht
       verlässlich einem bestimmten Tag zuordnen, also kein Match.

    Gibt (ais_turniernummer, reservation_id) oder (None, None) zurück.
    `reservation`/`reservation_event` gehören zum AdminPortal-Schema - in
    Dev/Test-DBs ohne dessen Tabellen (z.B. die SQLite-Test-DB) existieren sie
    nicht; das wird wie "keine Reservation gefunden" behandelt, nicht als Fehler.
    """
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError

    try:
        row = db.session.execute(text("""
            SELECT re.portal_event_id, re.ais_turniernummer, re.reservation_id
            FROM reservation_event re
            JOIN reservation r ON r.id = re.reservation_id
            WHERE re.date_from = :d AND r.status = 'confirmed'
              AND re.ais_turniernummer IS NOT NULL
            LIMIT 1
        """), {"d": spec_start}).first()
        if row:
            return row.ais_turniernummer, row.reservation_id

        row = db.session.execute(text("""
            SELECT id, ais_turniernummer
            FROM reservation
            WHERE date_from = :d AND (date_to IS NULL OR date_to = date_from)
              AND status = 'confirmed' AND ais_turniernummer IS NOT NULL
            LIMIT 1
        """), {"d": spec_start}).first()
        if row:
            return row.ais_turniernummer, row.id
    except DBAPIError:
        db.session.rollback()
        return None, None

    return None, None


@click.command("seed-season-events")
@click.option("--dry-run", is_flag=True,
              help="Nur anzeigen, was angelegt würde – ohne zu schreiben.")
@with_appcontext
def seed_season_events(dry_run: bool):
    """
    Legt die Saison-Turniere (Kalender H2 2026 – Feb 2027) als echte Events an.

    Sichtbar (is_published=True), Anmeldung geschlossen (status="closed").
    Idempotent über external_id: ein zweiter Aufruf legt nichts doppelt an.
    Veranstalter werden per Namensfragment (Club.name ILIKE) zugeordnet.

    Legt ein Turnier nur an, wenn für dessen Datum bereits eine BESTÄTIGTE
    AdminPortal-Reservation mit AIS-Turniernummer existiert (siehe
    _find_reservation_ais) - ohne das wird übersprungen und eine Warnung
    ausgegeben, statt ein Turnier ohne AIS-Nummer anzulegen (Lehre aus
    Reservation #63, die nie mit den Events verknüpft wurde).

    Beispiel:
      flask seed-season-events --dry-run
      flask seed-season-events
    """
    from app.models import Event, Club

    def combine(d: date) -> datetime:
        return datetime.combine(d, datetime.min.time())

    club_cache: dict = {}

    def find_club(hint: str):
        if hint not in club_cache:
            club_cache[hint] = db.session.execute(
                db.select(Club).where(Club.name.ilike(f"%{hint}%"))
            ).scalars().first()
        return club_cache[hint]

    created = skipped = missing_reservation = 0
    warnings: list[str] = []

    for spec in _SEASON_EVENTS:
        existing = db.session.execute(
            db.select(Event).filter_by(external_id=spec["ext"])
        ).scalars().first()
        if existing:
            skipped += 1
            click.echo(f"  = vorhanden: {spec['name']} (ID {existing.id})")
            continue

        ais, reservation_id = _find_reservation_ais(spec["start"])
        if ais is None:
            missing_reservation += 1
            click.echo(
                f"  ! übersprungen (keine bestätigte Reservation mit AIS-Nummer "
                f"für {spec['start']}): {spec['name']}"
            )
            continue

        club = find_club(spec["organiser"]) if spec.get("organiser") else None
        if spec.get("organiser") and club is None:
            warnings.append(
                f"Veranstalter «{spec['organiser']}» für «{spec['name']}» "
                f"nicht gefunden - ohne Verein angelegt."
            )

        event = Event(
            external_id=spec["ext"],
            name=spec["name"],
            location=spec.get("location"),
            starts_at=combine(spec["start"]),
            ends_at=combine(spec["end"]),
            type=spec["type"],
            special_ruleset=spec.get("ruleset"),
            status="closed",
            is_published=True,
            organiser_club_id=club.id if club else None,
            ais_turniernummer=ais,
            reservation_id=reservation_id,
            reservation_synced_at=datetime.utcnow(),
        )
        db.session.add(event)
        created += 1
        club_label = club.name if club else "- (kein Verein)"
        click.echo(f"  + {spec['start']} {spec['name']} -> {club_label} (AIS {ais})")

    for w in warnings:
        click.echo(f"  ! {w}", err=True)

    if dry_run:
        db.session.rollback()
        click.echo(
            f"\n[DRY-RUN] {created} neu, {skipped} vorhanden, "
            f"{missing_reservation} ohne Reservation übersprungen - nichts geschrieben."
        )
    else:
        db.session.commit()
        click.echo(
            f"\n[OK] {created} Turniere angelegt, {skipped} bereits vorhanden, "
            f"{missing_reservation} ohne Reservation übersprungen."
        )
