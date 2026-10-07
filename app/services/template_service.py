"""
Turnier aus einer EventTemplate-Vorlage erzeugen.

Wird sowohl von den Admin-Routen (routes_templates.py, ADMIN_KEY/Superadmin)
als auch von den Club-Routen (club/routes.py, Veranstalter-Self-Service)
verwendet, damit die Erzeugungslogik an einer Stelle gepflegt wird.
"""
from datetime import datetime

from app.extensions import db
from app.models import Event, EventRun


def _parse_int(raw):
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def create_event_from_template(tpl, form):
    """
    Erzeugt ein Event aus einer Vorlage.

    `form` ist ein request.form-artiges Mapping (name, starts_at, ends_at,
    ais_1..ais_N, do_website, do_reservation, contact_*).

    Gibt (event, messages) zurück. `event` ist None, wenn die Eingabe
    ungültig war (z.B. fehlendes Startdatum) — dann enthält `messages`
    den Fehlergrund. `messages` ist eine Liste von (text, flash_category).
    """
    messages = []
    name = (form.get("name") or tpl.default_event_name or tpl.name).strip()
    starts_raw = form.get("starts_at")
    ends_raw = form.get("ends_at")
    try:
        starts_at = datetime.strptime(starts_raw, "%Y-%m-%d") if starts_raw else None
    except ValueError:
        starts_at = None
    try:
        ends_at = datetime.strptime(ends_raw, "%Y-%m-%d") if ends_raw else None
    except ValueError:
        ends_at = None

    if not starts_at:
        return None, [("Startdatum ist erforderlich.", "danger")]

    # AIS-Nummern: Feld ais_1 = Haupttag, ais_2.. = Folgetage (kommagetrennt)
    ais_values = []
    for i in range(1, tpl.day_count + 1):
        v = (form.get(f"ais_{i}") or "").strip()
        if v:
            ais_values.append(v)
    ais_haupt = _parse_int(ais_values[0]) if ais_values else None
    ais_extra = ",".join(ais_values[1:]) if len(ais_values) > 1 else None

    event = Event(
        name=name,
        location=tpl.location,
        starts_at=starts_at,
        ends_at=ends_at or starts_at,
        type=tpl.type,
        special_ruleset=tpl.special_ruleset,
        status="draft",
        organiser_club_id=tpl.organiser_club_id,
        pruefungsleiter=tpl.pruefungsleiter,
        entry_fee=tpl.entry_fee,
        max_participants=tpl.max_participants,
        allows_bitches_in_season=tpl.allows_bitches_in_season,
        bitches_in_season_start_last=tpl.bitches_in_season_start_last,
        ring_count=tpl.ring_count,
        notes_public=tpl.notes_public,
        event_description_de=tpl.event_description_de,
        registration_external=tpl.registration_external,
        registration_url=tpl.registration_url,
        startnumber_schema=tpl.startnumber_schema,
        run_time_config=tpl.run_time_config,
        ring_start_times=tpl.ring_start_times,
        ais_turniernummer=ais_haupt,
        ais_turniernummer_extra=ais_extra,
        source_template_id=tpl.id,
    )
    db.session.add(event)
    db.session.flush()

    for r in tpl.runs:
        db.session.add(EventRun(
            event_id=event.id, run_type=r.run_type, category=r.category,
            class_level=r.class_level, is_final=r.is_final))

    db.session.commit()
    messages.append((f"Turnier «{event.name}» aus Vorlage erstellt (Status: Entwurf).", "success"))

    if form.get("do_website"):
        try:
            from app.services.website_sync import sync_to_website
            ok, err = sync_to_website(event)
            if ok:
                db.session.commit()
                messages.append(("Webseiten-Event erstellt.", "success"))
            else:
                messages.append((f"Webseiten-Sync übersprungen: {err}", "warning"))
        except Exception as e:
            db.session.rollback()
            messages.append((f"Webseiten-Sync fehlgeschlagen: {e}", "warning"))

    if form.get("do_reservation"):
        # Geteilte Reservation: an das zuletzt aus dieser Vorlage erzeugte
        # Turnier mit Reservation anhängen, statt eine neue anzulegen.
        prior = None
        if tpl.reservation_shared:
            prior = (Event.query
                     .filter(Event.source_template_id == tpl.id,
                             Event.reservation_id.isnot(None),
                             Event.id != event.id)
                     .order_by(Event.id.desc())
                     .first())
        if prior:
            event.reservation_id = prior.reservation_id
            db.session.flush()
            try:
                from app.services.reservation_sync import update_reservation
                ok, err = update_reservation(event)
                if ok:
                    db.session.commit()
                    messages.append((f"An bestehende Reservation #{event.reservation_id} angehängt.", "success"))
                else:
                    db.session.rollback()
                    messages.append((f"Anhängen an Reservation übersprungen: {err}", "warning"))
            except Exception as e:
                db.session.rollback()
                messages.append((f"Anhängen an Reservation fehlgeschlagen: {e}", "warning"))
        else:
            contact_name = (form.get("contact_name") or tpl.contact_name or "").strip()
            contact_email = (form.get("contact_email") or tpl.contact_email or "").strip()
            if not contact_name or not contact_email:
                messages.append(("Reservationsanfrage übersprungen: Kontakt-Name und E-Mail fehlen.", "warning"))
            else:
                try:
                    from app.services.reservation_sync import create_reservation
                    ok, err = create_reservation(
                        event, contact_name, contact_email,
                        (form.get("contact_phone") or tpl.contact_phone or "").strip(),
                        tpl.organiser_club.name if tpl.organiser_club else "",
                        tpl.reservation_notes or "",
                        tpl.option_special_eval, tpl.option_website, tpl.option_event_support,
                    )
                    if ok:
                        db.session.commit()
                        messages.append(("Reservationsanfrage gesendet.", "success"))
                    else:
                        messages.append((f"Reservationsanfrage übersprungen: {err}", "warning"))
                except Exception as e:
                    db.session.rollback()
                    messages.append((f"Reservationsanfrage fehlgeschlagen: {e}", "warning"))

    return event, messages
