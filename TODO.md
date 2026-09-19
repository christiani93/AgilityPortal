# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-08-16

## Turnier-Vorlagen — ✅ UMGESETZT (2026-09-19)

Umgesetzt als benannte **`EventTemplate`-Bibliothek** (nicht „Duplizieren") im Admin-Bereich
(`/admin/templates`, nur Superadmin). Vorlage traegt stabile Felder + Laeufe + Config +
Reservations-Kontakt/Optionen + Webseiten-Text; „Turnier erzeugen" fragt nur Datum + AIS
(eine AIS-Nummer pro Turniertag via `day_count`) und kann Website-/Reservation-Sync optional
direkt anstossen. Migrationen `33d169664153` + `febf1477c166`.

> Historischer Handoff-Kontext (Brief aus AdminPortal-Session, 2026-09-19):

**Ziel:** Jaehrlich wiederkehrende Turniere schneller anlegen, ohne AIS-Nummer,
Veranstalter, Kontaktdaten, Laeufe & Config jedes Mal neu einzutippen.

**Architektur-Entscheid (wichtig):** Das Feature gehoert INS AGILITYPORTAL, wo das
Event die Quelle ist — NICHT ins AdminPortal via `anmeldung`-Bind cross-DB
schreiben (umgeht Event-Erstelllogik/Laeufe/Config + die Sync-Services →
fragil, doppeltes Schema). Reservation + Webseiten-Event entstehen bereits ueber
die bestehenden Push-Syncs vom Event aus:
- `app/services/website_sync.py` → `POST admin.z-b.tech/api/events/sync` → PublicEvent (z-b.tech), merkt `website_event_id`.
- `app/services/reservation_sync.py` → `POST admin.z-b.tech/api/reservations` → Reservation im AdminPortal, merkt `reservation_id`.
(Beide AdminPortal-Gegenstellen existieren: `reservation_create`, `event_sync`.)

**Empfohlener Ansatz — „Turnier duplizieren" (minimal, kein neues Schema):**
- [ ] Knopf „Als neues Turnier duplizieren" auf einem bestehenden Event.
- [ ] Kopiert die STABILEN Felder inkl. **Laeufe (`EventRun`)** + Config
      (`run_time_config`, `startnumber_schema`, Ring-Config, `entry_fee`,
      `pruefungsleiter`, `organiser_club_id`, `max_participants`, Huendinnen-Flags,
      `notes_public`, `type`). Das Kopieren der Laeufe/Config ist der groesste
      Zeitgewinn.
- [ ] Laesst die JAEHRLICH wechselnden Felder LEER: `ais_turniernummer` (+`_extra`),
      `starts_at`/`ends_at`, `registration_open_at`/`_close_at`. Status = `draft`.
      `external_id`, `website_event_id`, `reservation_id`, `*_synced_at`, Ergebnisse
      NICHT mitkopieren.
- [ ] Danach fuellt der User nur AIS + Daten, dann die bestehenden Sync-Knoepfe
      (→ Webseite, → Reservation).

**Relevante Stellen:** `app/models.py` Event (ab Z.265), `app/blueprints/club/routes.py`
`event_new` (ab Z.402) als Feld-Referenz, `services/website_sync.py`,
`services/reservation_sync.py` (Reservation braucht Kontakt Name/E-Mail/Verein +
`option_*` — bei benannter Vorlagen-Bibliothek muesste die Vorlage die tragen).

**Offene Entscheidungen (User-Empfehlung war):**
1. Duplizieren (empfohlen) vs. benannte `EventTemplate`-Tabelle. Duplizieren
   deckt den Bedarf, kein Migrations-/UI-Overhead.
2. „Veroeffentlichen"-Knopf die 2 Syncs verketten ODER getrennt lassen
   (mehr Kontrolle pro Turnier). User tendiert noch nicht festgelegt.

## WiMeSma-Cup (Deadline 15.11.2026 — 1. von 4 Meetings)

- [ ] Reglement klären: Cup-Punkte pro Klasse getrennt oder Small/Medium kombiniert werten (`split_by_class`)?
- [ ] Reglement klären: „beste-N" Meetings-Regel bestätigen (wie viele der 4 Meetings zählen?)
- [ ] Reglement klären: Final-Modus (Open-Lauf, umgekehrte Startreihenfolge)
- [ ] Echten Test-Cup mit den 4 Meetings anlegen (15.11./12.12.2026, 17.01./13.02.2027) und öffentliche Rangliste prüfen

## Adventscup (Deadline 27.–29.11.2026)

- [ ] Regelwerk klären: reicht das Halloween-Muster (KO-Bracket) 1:1, oder eigene Regel nötig?

## KO-Final / „American"-Format (Cup-Finals allgemein, betrifft Halloween Cup + ggf. Adventscup)

- [ ] Runde 2+ (Viertelfinale/Halbfinale/Finale) automatisch aus den Vorrunden-Siegern generieren
      (aktuell generiert `cup_final_bracket_generate` nur Runde 1)
- [ ] Halbfinale-Sonderregel implementieren: beide Verlierer → Spiel um Platz 3
- [ ] Schlussrangliste befüllen (`CupFinalResult` wird aktuell nirgends geschrieben)

## SKBS-SM + FMBB-Quali Münsingen (Deadline 05.–06.12.2026)

- [ ] Bestehenden Dezember-Plan + FMBB-Plan abarbeiten (siehe `DEV_PLAN.md` + Memory `project_implementation_plan_dec2026`)

## Edelweiss Challenge (Deadline 08.–10.01.2027)

- [ ] Reglement besorgen/klären (u.a.: ist Klasse 3 auch ein Quali-Lauf?)

## BCCS-SM — ✅ ERLEDIGT (2026-08-16)

Implementiert, deployed, 1:1 gegen echte 2025-Referenzdaten validiert (bis Commit `bf659da`).
Offen bleibt nur ein manueller Klicktest der Dashboard-UI durch Chris (serverseitige Logik
bereits verifiziert).

## Crashguard-Rollout — ✅ ERLEDIGT (2026-08-16)

`CRASHGUARD_URL` + `CRASHGUARD_TOKEN` sind in `~/apps/agilityportal/.env` gesetzt, Dienst
läuft, Collector (AdminPortal) empfängt Reports (verifiziert). Debug-Tools auf Prod aus
(`ENABLE_DEBUG_TOOLS` nicht gesetzt).

Anleitung: `~/.claude/playbooks/crashguard-deploy.md`

## Architektur-Notiz

- Wird vom AdminPortal verwaltet (Subdomain portal.z-b.tech, Port 8020)
- Sister-Projekt: AgilitySoftware (Online-Offline-Pair, `_related/AgilitySoftware/` falls Cross-Link gesetzt)
- Folgt TKAMO-Reglemente: https://www.tkamo.ch/de/agility/reglemente.html
- Deploy: `supervisorctl restart agilityportal` (AdminPortal-managed)
