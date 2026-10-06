# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-10-06

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

## Reservation mit mehreren Turnieren — ⏳ OFFEN (Handoff aus AdminPortal 2026-10-06)

**Ziel:** Eine AdminPortal-Reservation kann **mehrere** AgilityPortal-Turniere
umfassen (z.B. ein Veranstalter bucht die Zeitmessung für mehrere Turniere in
einer Anfrage). Heute ist die Verknüpfung 1 Event : 1 Reservation
(`event.reservation_id`), und `reservation_sync.py` schickt genau EIN
`portal_event_id`.

**AdminPortal-Seite — ✅ BEREITS ERLEDIGT (abwärtskompatibel):**
- `POST /api/reservations` UND `PATCH /api/reservations/<id>` akzeptieren jetzt
  zusätzlich ein Feld **`events`** (Liste):
  ```json
  "events": [
    {"portal_event_id": 14, "ais_turniernummer": 12345, "event_name": "...", "date_from": "2027-05-01"},
    {"portal_event_id": 15, "ais_turniernummer": 12346, "event_name": "...", "date_from": "2027-05-02"}
  ]
  ```
- Das **erste** Listenelement gilt als Haupt-Turnier (füllt weiter die Einzel-
  Spalten `portal_event_id`/`ais_turniernummer`, damit bestehende Links/Features
  laufen). Alle Events landen zusätzlich in der neuen Kindtabelle
  `reservation_event`; die Detailseite zeigt alle Turniere + TKAMO-Links.
- **Alt-Format bleibt gültig:** einzelnes `portal_event_id` ohne `events` →
  genau ein Turnier (wie bisher). Nichts bricht, solange AgilityPortal nichts ändert.
- **Wichtig:** Wird `events` bei PATCH mitgeschickt, ersetzt AdminPortal die
  **komplette** Turnier-Menge. AgilityPortal muss also immer ALLE Turniere einer
  Reservation zusammen senden, nicht inkrementell.

**AgilityPortal-Seite — ✅ Variante (a) UMGESETZT (2026-10-06):**
- [x] UX-Entscheid: **Variante (a)** gewählt — auf einem Event „zu bestehender
      Reservation hinzufügen" (Dropdown der Turniere mit Reservation, gleicher
      Veranstalter / Superadmin). Setzt `event.reservation_id` auf die Reservation
      des gewählten Turniers. Route `club.event_reservation_join`.
- [x] `services/reservation_sync.py` → `update_reservation` sendet jetzt bei JEDER
      Aktualisierung die **vollständige** `events`-Liste der Reservation
      (Haupt-Turnier = frühestes Datum zuerst, füllt die Einzel-Spalten),
      `estimated_participants` = Summe. Neu-Anfrage (`create_reservation`) bleibt
      Einzel-Format (abwärtskompatibel).
- [x] Detailseite zeigt bei Mehr-Turnier-Reservation alle beteiligten Turniere.
- [x] Tests: `tests/test_reservation_multi.py` (events-Array + Einzelfall).
- [x] **PROD-DEPLOYED 2026-10-06** (Commit `44bb7df`).

**Vorlagen-gesteuerte geteilte Reservation — ✅ UMGESETZT (2026-10-06, Vorschlag 1):**
- [x] `EventTemplate.reservation_shared` (Checkbox im Vorlagen-Formular): aus der
      Vorlage erzeugte Turniere teilen sich EINE Reservation.
- [x] `Event.source_template_id` (Provenienz-FK) — merkt, aus welcher Vorlage ein
      Turnier stammt (um die „zuletzt erzeugte" Reservation der Serie zu finden).
- [x] `template_create_event`: bei aktivem `reservation_shared` + „Reservationsanfrage"
      hängt sich das 2./3. Turnier via `update_reservation` an die Reservation des
      zuletzt erzeugten Turniers an, statt eine neue anzulegen (erstes Turnier = Anker).
- [x] Migration `a9b0c1d2e3f4` (chained auf `f7a8b9c0d1e2`); MySQL-SQL geprüft (offline).
- [x] Tests: `tests/test_template_shared_reservation.py` (shared vs. unshared).
- [x] **PROD-DEPLOYED 2026-10-06** (Commit `44bb7df`, Migration `a9b0c1d2e3f4` gelaufen).

**Relevante Stellen:** `app/services/reservation_sync.py` (Payload-Bau, erledigt),
`routes_website_sync.py::event_reservation_join`, `event_detail.html` (Reservations-
Karte), `admin/routes_templates.py::template_create_event` + `templates/admin/templates/form.html`.

## Website-Sync-Text — ✅ UMGESETZT (2026-10-06)

Inserat-Text wie AdminPortal-Prosa + TKAMO-zuerst-Hinweis live (Commit `4fc0957`,
`website_sync.generate_body_md`). Keine Migration (Alembic-Head weiterhin `a9b0c1d2e3f4`).
AdminPortal-seitiges PublicEvent-Dedup-Gegenstück bleibt als ToDo in AdminPortal/TODO.md offen.

## Hotfix: NULLS LAST — ✅ BEHOBEN (2026-10-06)

`.nullslast()` crashte MariaDB (1064) auf `/club/events/<id>` (Commit `47989b8`, durch
portablen `case()`-Sort ersetzt). Behebt Crashes #99–104 aus dem Mehr-Turnier-Reservation-
Deploy (`44bb7df`). SQLite-Tests hatten den Bug nicht gefangen (MySQL-only-Syntaxfehler).

## Jump Into Fall (09.–11.10.2026) — Events 9/10/11, AIS 11338/11339/11340

- [x] Publiziert, Richter pro Lauf zugeordnet + anwesend, Starterzahlen genullt
- [x] Mit Reservation #42 verknüpft (ohne Sync)
- [x] TKAMO-Import gemacht
- [ ] Chris trägt Mi/Do (07./08.10.) Teilnehmer ein

## Halloween Cup KO-System (30.10.–01.11.2026)

Architektur entschieden (06.10.): **Variante B** — KO läuft offline in AgilitySoftware mit
TIMY (siehe AgilitySoftware `TODO.md`, Branch `feature/ko-cup`). Portal-Rolle ist nur:

- [ ] Read-only Live-Anzeige für den KO-Bracket (2 Ringserver-PCs speisen)
- [ ] Finalisten-Empfang via `eventexport.v1` inkl. Startnummer (für Ring-Zuteilung)

> Die bisherigen Portal-seitigen Punkte unten („Runde 2+ generieren", Halbfinale-Sonderregel,
> `CupFinalResult`) sind durch diese Architekturentscheidung für den Halloween Cup
> **gegenstandslos** — die Bracket-Logik liegt jetzt in AgilitySoftware. Bleiben relevant nur
> falls Adventscup das 1:1 im Portal statt in der Software umsetzen soll (siehe unten, offen).

## WiMeSma-Cup (Deadline 15.11.2026 — 1. von 4 Meetings)

- [ ] Reglement klären: Cup-Punkte pro Klasse getrennt oder Small/Medium kombiniert werten (`split_by_class`)?
- [ ] Reglement klären: „beste-N" Meetings-Regel bestätigen (wie viele der 4 Meetings zählen?)
- [ ] Reglement klären: Final-Modus (Open-Lauf, umgekehrte Startreihenfolge)
- [ ] Echten Test-Cup mit den 4 Meetings anlegen (15.11./12.12.2026, 17.01./13.02.2027) und öffentliche Rangliste prüfen

## Adventscup (Deadline 27.–29.11.2026)

- [ ] Regelwerk klären: reicht das Halloween-Muster (KO-Bracket) 1:1, oder eigene Regel nötig?

## KO-Final / „American"-Format (Portal-seitige Bracket-Logik — siehe Hinweis oben)

- [ ] Runde 2+ (Viertelfinale/Halbfinale/Finale) automatisch aus den Vorrunden-Siegern generieren
      (aktuell generiert `cup_final_bracket_generate` nur Runde 1)
- [ ] Halbfinale-Sonderregel implementieren: beide Verlierer → Spiel um Platz 3
- [ ] Schlussrangliste befüllen (`CupFinalResult` wird aktuell nirgends geschrieben)

## SKBS-SM + FMBB-Quali Münsingen (Deadline 05.–06.12.2026)

- [ ] Bestehenden Dezember-Plan + FMBB-Plan abarbeiten (siehe `DEV_PLAN.md` + Memory `project_implementation_plan_dec2026`)

## Edelweiss Challenge (Deadline 08.–10.01.2027)

- [ ] Reglement besorgen/klären (u.a.: ist Klasse 3 auch ein Quali-Lauf?)
- [x] Team-Challenge (2er-Teams) Reglement bestätigt (DIS-Team hinter Nicht-DIS via Sentinel
      999, Zeitfehler normal eingerechnet); Software P1+2 + Portal P5 fertig & getestet
      (2026-10-06), Portal-Teil **noch nicht prod-deployed**; P3/P4/P6 (Sync, EventRuns,
      Ranglisten) erst Januar — siehe AgilitySoftware `TODO.md`

## AOA-Anmeldelink-Vorlage

- [ ] `external_registration_link` als Vorlage bauen: URL-Muster
      `…/Turnierdetails_view.php?editid1=<AIS>` — nur `editid1` (= `ais_turniernummer`) variiert

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
