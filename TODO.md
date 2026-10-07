# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-10-07

## Session 2026-10-07 (Teil 8) — TKAMO-Name + Verein-Name + Rasse + Zeitplan-Renderfix — ⏳ LOKAL FERTIG, UNCOMMITTED

112/112 Tests grün, **noch NICHT committed/deployed** (Prod-Head bleibt `e3f4g5h6i7j8`).
Details in Memory `project_local_20261007_tkaname_verein_schedulefix`.
- [x] **`Dog.tka_name`** (neue Migration `f6a7b8c9d0e1`, down `e3f4g5h6i7j8`, additiv add_column):
      Lizenzcheck (`_parse_and_apply_tkamo`) schreibt offiziellen TKAMO-Namen in `tka_name`
      statt `dog.name`; TKAMO-CSV (`event_lizenzcheck_csv`) nutzt `tka_name or name`.
      AOA-Name bleibt auf allen normalen Listen. (User-Entscheid: Zusatzfeld, Fallback AOA.)
- [x] **Verein als Name statt Nummer** (nur Anzeige): Property `Registration.club_display_name`
      löst numerische `club_name` (=Vereinsnummer) über `Club.vereinsnummer` zum Namen auf;
      Gastverein ohne Portal-Account / Freitext → Rohwert bleibt. `club_name`-Feld UNVERÄNDERT
      (TKAMO-CSV braucht Nummer). User: Namen NICHT importieren, nur anzeigen.
- [x] **Rasse-Spalte** (`Dog.breed`) in club/startlist.html, public/startlist.html,
      public/startlist_print.html; `_collect_startlist_rows` liefert breed + club_name.
- [x] **Zeitplan-Startzeiten-Renderfix** `schedule_utils.py::compute_timeline`: Folgezeilen
      einer Gruppe zeigten alle das Briefing-Ende als Start; jetzt eigene fortlaufende
      Lauf-Startzeit (`run_times[b.id][0]`). Nur Editor-Ansicht betroffen, nicht
      compute_detailed_segments. Verifiziert 16:30→16:45→16:48→16:50→16:54.
### Handler-Gap-Verteilung — NEU umgesetzt 2026-10-07 (Details Memory `project_startnumber_gap_algorithm`)
- [x] **MIN_GAP ENTFERNT**, neue Soll-Lücke je **Spreizung** `n/own_count` (N=eigene Hunde im Block):
      `n/own_count >= 20` → `Block/N` (gleichmässig); sonst → `Block/(N-1)` (Extreme spreizen,
      grösstmöglicher Abstand). Einzelhund → keine Lücke. In `event_assign_startnumbers`.
      6/6 `tests/test_club_startnumbers.py` grün (neu: tight→Extreme, roomy→Block/N).
- [x] **VERWORFEN — gleichmässige even-Formel** (alt): an Turnier-16-Daten Regression.
      Die neue Block/(N-1)-Spreizung senkt NICHTS unter ein Minimum → nicht dasselbe.
- [x] **Nebenbefund behoben:** die alte (deployte) MIN_GAP-Logik liess in gesättigten kleinen
      Blöcken eine Registration komplett ohne Startnummer (Best-effort-Loop); NEU platziert alle.
- [!] **Physikalisch unlösbar bei kleinen Blöcken bleibt:** Handler mit vielen Hunden in
      kurzem Block → Pause unvermeidbar knapp. Nummernvergabe kann das nicht heilen.
- [ ] **OPTIONAL — erkennen & melden** statt lösen — nach „Startnummern vergeben" dem
      Veranstalter die Handler mit Startabstand < X min anzeigen (zeitbasiert via
      compute_detailed_segments). Mit User abstimmen + bauen.

### AOA-Import Handler-E-Mail-Merge-Bug — GEFIXT 2026-10-07 (Memory `project_aoa_import_handler_email_merge_bug`)
- [x] **Person-Matching: Name vor E-Mail.** Verschiedene Personen mit gemeinsamer Familien-
      E-Mail (Océane + Pascal Mauroux, beide kudelski.irene@bluewin.ch) wurden auf einen
      Handler gemappt → verfälschte Startnummern-Gaps. Fix in `routes_aoa_import.py`
      (`aoa_import_execute`) + Regressionstest `tests/test_aoa_import_handler_merge.py`.
      **Muss vor dem echten Event-9-Import (09.10.) live sein** (Event 9 hat aktuell 0 Regs).
- [ ] **Account↔Person-Verknüpfung** (vom User angestossen, SPÄTER): wie werden importierte
      Personen mit bestehenden Portal-Accounts/Lizenzen verbunden? Siehe AdminPortal-Gap-Memory.

## Session 2026-10-07 (Teil 7) — Testkopie + Anmelde-Guard + Bundle-Deploy — ✅ DEPLOYED

Commit `d461ac1` live, **NEUER Prod-Alembic-Head `e3f4g5h6i7j8`** (additiv, nur Tabelle
`special_ruleset_allowed_clubs`). DB-Backup `~/backups/agilityportal_xahizivi_main_20261007_164354.sql`.
Verifiziert: alle Routen 200, Wettbewerbe-Karte rendert, keine Logfehler. 112/112 Tests grün.
- [x] **Testkopie-Funktion** `club.event_duplicate_as_test` (POST /club/events/<id>/duplicate-as-test)
      + Button „🧪 Testkopie" auf event_detail. Kopiert Läufe/Richter/Zeitplan/Anmeldungen,
      is_test=True, AIS/external_id geleert, Startnummern NICHT kopiert.
- [x] **Anmelde-Guard** in `event_view`: Selbst-Anmeldung nur in angebotene (category,class).
      (Vorher KEINE Prüfung — man konnte sich in jede Kl.1-3 anmelden.)
- [x] **Testevent-Sicht**: `event_info` zeigt Testevents auch dem Veranstalter des eigenen Vereins.
- [x] **Wettbewerbe-Infokarte** in public/overview.html (Disziplinen/Kategorien/Klassen).
- [x] Gebündelt mitdeployed: Spezialturnier-Freigabe + Vorlagen-Self-Service + „Meine Angaben"
      (siehe Teil 5 unten — ist damit erledigt/live).

### ⏳ OFFEN — Test-Startliste von Event 9 (Dry-Run)
Event 9 = „Jump Into Fall – Vendredi 09.10.2026" (AIS **11338**, Club **295**=LyTiWee, 1 Ring,
**24 Läufe, 24 Zeitplan-Blöcke, 1 Richter, 0 Anmeldungen**, 0 Startnummern). Struktur ist da,
aber **0 Teilnehmer** → reine Kopie hätte leere Startliste. **Entscheid beim User offen:**
(A) Testkopie + Dummy-Teilnehmer (Default 8/Klasse, `TEST_`/`TST-`-Lizenzen wie
create_test_event_web) → Startnummern + Startliste als Dry-Run; (B) warten auf echten Import.

### ⏳ OFFEN — Multi-Club-Mitgliedschaft (als Nächstes, local-first)
4 Design-Entscheide vom User beantwortet (2026-10-07): (1) Auto-Mitgliedschaft = **manuell**
(Teilnehmer trägt sich bei Verein ein; TKAMO-Lizenzkontrolle liefert ab 2027 Verein-Abgleich),
(2) `User.club_id` als Hauptverein **behalten**, (3) Verein-Picker bei event_new **ja**,
(4) Promotion member→admin bleibt **über AdminPortal**. Umbau: M:N `ClubMembership(user_id,
club_id, role)`. User-Freigabe: **jetzt bauen, aber local-first testen, nur Claude selbst.**

## Session 2026-10-07 (Teil 6) — event_info-Ausbau + externe Anmeldung — ✅ DEPLOYED

Drei Deploys live, keine Migration (Head bleibt `d1e2f3a4b5c6`), keine neuen Crashes:
- [x] **event_info** TKAMO-Agenda-Link + Ablaufplan + Richter (`67ce554`)
- [x] „Nennschluss"→„Anmeldeschluss"; TKAMO-Karte = nur Link (**Kontaktmail raus**, Spam);
      Meldeliste/Startliste-Link (`58e81fc`)
- [x] Infokarte-Felder Veranstalter/Meldebeginn/Max.Teilnehmer/Anzahl Ringe; **externe
      Anmeldung**: bei `registration_external` externer Link statt Self-Registration auf
      event_info+event_view, POST lehnt ab, Veranstalter-Manuell-Add unberührt (`1d840df`)

### ⏳ OFFEN — Multi-Club-Mitgliedschaft (Wunsch 2026-10-07, Design)
Handler in mehreren Vereinen → Auto-Mitgliederrolle; Superadmin promotet zu Club-Admin
(darf Events eröffnen). Braucht M:N `ClubMembership(user_id, club_id, role)` statt
`User.club_id`. **4 Entscheide offen beim User**: (1) Auto-Mitgliedschaft-Trigger
(Lizenz-Vereinsnr / Event-Teilnahme / manuell), (2) club_id als Hauptverein behalten?,
(3) Verein-Picker bei event_new, (4) Promotion-UI Portal vs AdminPortal. DB-Migration
local-first, NICHT am Jump-Into-Fall-Wochenende.

## Session 2026-10-07 (Teil 5) — Spezialturnier-Freigabe + Self-Service — ✅ DEPLOYED (im Bundle Teil 7)

Live via `d461ac1`, **Prod-Alembic-Head `e3f4g5h6i7j8`** (Migration `special_ruleset_allowed_clubs`).
Verhaltensneutral solange Allowlist leer (`special_ruleset_restricts()`=False).

- [x] **Spezialturnier-Freigabe** (`SpecialRulesetAllowedClub`, Migration `e3f4g5h6i7j8`):
      eigenständige Allowlist Ruleset↔Verein, unabhängig vom Cup-System. Model-Helper
      `Event.special_ruleset_allows_club/_restricts/_allowed_club_ids`. Admin-UI
      `/admin/special-ruleset-assignments` (+ `/<ruleset>/edit`), verlinkt von Vorlagen-Liste.
      Durchsetzung club-seitig: `EventForm.special_ruleset`-Choices in `event_new`/`event_edit`
      serverseitig gefiltert (nicht nur UI). Edge-Case: nachträglich entzogener, bereits
      gesetzter Wert blockiert nicht das ganze Formular (`keep_value` in
      `_filter_special_ruleset_choices`).
- [x] **Vorlagen-Self-Service für Veranstalter** (der „Grundstein"): `/club/templates` +
      `/club/templates/<id>/create-event` — nur Veranstalter-Verein der Vorlage (oder
      Superadmin). Erzeugungslogik aus `routes_templates.py` nach
      `app/services/template_service.py::create_event_from_template` extrahiert (Admin + Club
      teilen sie). Nav-Link „Turnier-Vorlagen" ergänzt.
- [x] **`Dog.breed` im Self-Service** (`DogForm` / `/club/profile/dogs`): Rasse-Feld fehlte,
      obwohl Spalte seit AOA-Migration existiert — ergänzt (Formular + Anzeige in Hundekarte).
- [x] **Neue Seite „Meine Angaben"** (`/club/profile`, `club.profile_edit`): erster
      Self-Service-Ort für eigenen Namen/Telefon (vorher nur bei `/auth/register`). Hält
      `User.*name` und `Person.*name` synchron. E-Mail bewusst NICHT editierbar (Login-Identität).
      Nav-Link „Mein Profil → Meine Angaben" für ALLE eingeloggten Rollen.
- [ ] Committen + beim nächsten Portal-Deploy mitnehmen (Migration `e3f4g5h6i7j8` dann laufen).

**TKAMO-Export-Recherche (Befund, kein Code nötig):** Der echte TKAMO-Ergebnis-Export
(`routes_results_export.py::build_tkamo_csv`) braucht pro Zeile nur Lizenznr+Hundename (Dog),
`Hundefuehrer` (Namens-String via `eventexport.v1` → Software → `resultexport` zurück),
Club (`Registration.club_name`), Kategorie/Klasse, Richter-AIS-ID. **Adresse/Telefon sind
für TKAMO irrelevant** (Vorlage kennt die Spalten nicht) → „Meine Angaben" deckt den
TKAMO-Bedarf (Name) vollständig ab.

**Verwandte offene Wünsche (eigene Memory-Files, noch nicht umgesetzt):**
- [ ] AdminPortal: Account↔Lizenz-Verknüpfung (`club_user_add` legt immer neuen Account mit
      PW an; `dog_edit` zeigt Owner nur read-only) — eigenes Repo, eigene Session nötig.
- [ ] Team-CSV/XLSX-Import (Teamname+2 Lizenzen) für `/admin/events/<id>/teams`.

## Session 2026-10-07 (Teil 4) — Live-Seite Top5/Letzte5 + Team-Button — ✅ DEPLOYED

- [x] **Live-Seite pro Ring: Top 5 + Letzte 5 Ergebnisse** (Commit `82f215d`, prod live).
      Pro Ring-Card unter der Startliste: Top 5 (nach Rang aus `result_classes`, gematcht über
      Ring+Disziplin+Kategorie+Klasse, lowercase-normalisiert) + Letzte 5 gespeicherte Ergebnisse
      (aus LiveUpdate-Strom, **ohne DNS**, neueste zuerst, dedupliziert nach Lizenz, auf 5 gedeckelt).
      `event_live_json` (routes.py) + `event_live.html::renderRings`. In-Memory-Smoke-Test + 94 Tests grün.
- [x] **Team-Challenge-Button** auf Event-Detail (Superadmin + `special_ruleset=edelweiss_challenge`)
      → `/admin/events/<id>/teams`. Vorher gab es KEINEN Link dorthin.
- [x] **`special_ruleset` im Event-Edit** (`EventForm` Dropdown + `event_edit` + `event_form.html`):
      beliebige Turniere als Spezialformat (halloween_cup/advents_cup/edelweiss_challenge) markierbar.
      Hinweis: Team-Challenge ist NICHT ans Cup-/CupAllowedOrganiser-Freigabesystem gekoppelt.
- [x] Keine Migration (`special_ruleset` existiert seit Initial-Schema). 0 offene Crashes nach Deploy.
- [ ] **Wochenend-Live-Test (noch offen):** (a) Ring-Monitor (AgilitySoftware) aktualisiert sich pro
      Ring-PC beim Speichern eines Ergebnisses — Code vorhanden (`ring_monitor.html` joint
      `event:<id>:ring:<n>`, `save_result` emittiert ring-spezifisch + 20 s-Polling), nur Mehrring-
      Realtest fehlt. (b) Portal-Live-Seite Top5/Letzte5 mit echten Live-Daten verifizieren
      (braucht beide API-Keys: Top 5 aus Result-Export, Letzte 5 aus Live-Updates).
- [ ] Prüfen, ob Edelweiss-Testevent **ID 15** `special_ruleset=edelweiss_challenge` gesetzt hat
      (sonst im Edit-Dropdown nachziehen, damit der Button erscheint). Direkt-URL `/admin/events/15/teams`
      funktioniert unabhängig.

## Session 2026-10-07 (Teil 3) — Rangliste-Layout + Live-Link + Prod-Vorlagen

**UNCOMMITTED — am Ende der Session noch NICHT committed/deployed:**
- [ ] **Portal (`main`, lokal uncommitted):** öffentliche Event-Landingpage
      `app/templates/public/overview.html` + `app/blueprints/public/routes_events.py`
      (`public_overview`) — am **Event-Tag** (`is_event_day`: starts≤heute≤ends) erscheint
      jetzt eine rote „🔴 Live"-Karte → `club.event_live`. + FR/EN-Übersetzung des neuen
      Strings „Aktuelle Startliste und Ranglisten" (`.mo` neu kompiliert). 94 Tests grün.
      → committen + beim nächsten Portal-Deploy mitnehmen.
- [ ] **Software (`feature/ko-cup`, lokal uncommitted):** Rangliste-Upload-PDF
      `web_app/templates/print_ranking_pdf.html` an SportyDog-Vorlage angeglichen
      (2×3-Laufvorgaben-Box, Spalten Liz/Rasse/Verein/Kl/m/s, kompaktere Zeilen,
      Statistik mit %); `web_app/blueprints/routes_live.py` refactored
      (`_render_ranking_pdf_html` + neue Preview-Route `/live/preview_ranking_pdf`).
      12 Tests grün. Details+Quirks: Memory `project_design_pdf_siegerehrung`.
      → committen; kommt mit dem feature/ko-cup→main-Merge + EXE-Rebuild.

**ERLEDIGT auf Prod (kein Deploy nötig, Feature war live):**
- [x] Turnier-Vorlagen **Halloween Cup** (EventTemplate ID 2) + **Edelweiss Challenge**
      (ID 3) auf portal.z-b.tech angelegt; Club 295 = **LyTiWee**. HCS: Fr Tunnellauf /
      Sa A+J+Final / So A+J. Edelweiss: tägl. A+J + So Final. ⚠️ Platzhalter-Annahmen
      (Tunnellauf-Lauf category=L/class=1, Finale=Agility/Kl.3, Ring-Anzahl, Entry-Fee)
      vor echtem Event-Erzeugen im Admin-UI gegenchecken. Memory
      `project_prod_deploy_20261007_templates_teamdemo`.
- [x] **Edelweiss-Team-Challenge-Demo** auf Prod: Testevent **ID 15** (`is_test`),
      24 Dummy-Anmeldungen (pro Kat. 2×Kl.1 + 2×Kl.2 „soft" + 2×Kl.3 „expert").
      Veranstalter-Pick-UI: `/admin/events/15/teams`. Teilnehmer-Selbstauswahl erst
      zukünftig (wenn Anmeldung übers Portal läuft, dann P3+).

**OFFEN (Folge):**
- [ ] AIS-ID↔Lauf-Zuordnung: A+J zwingend pro AIS-ID (Memory `project_ais_turnier_id_pairing`);
      beim Event-Erzeugen aus Vorlage prüfen; HCS-Fr (nur Tunnel) eigene AIS-Nr? Reglement klären.

## Offen aus Session 2026-10-07 (Druck/i18n/Tunnellauf/AOA)

Erledigt (Software `feature/ko-cup`): Drucken-Buttons auf allen Druckseiten (geteilter
Partial `print/_print_button.html`); Einweiserliste L-I-M-S + Laufvorgaben-Tabelle (TKAMO);
EN als 3. Drucksprache + FR komplettiert; Tunnellauf-Ring-Schnellbutton in `/plan_schedule`.
Erledigt (Portal `main`): AOA-„nur Stammdaten"-Import `/admin/aoa-import/stammdaten`;
Drucken-Button in `club/startlist.html`.

Session 2026-10-07 (Teil 2) — Fortschritt an den 4 User-Punkten:
- [x] **Punkt 1 — Public Startliste als PDF mit Logos:** FERTIG. Neue Druckseite
      `GET /events/<id>/startlist/print` + `public/startlist_print.html` (A4, Event-+Vereinslogo-
      Kopf wie Software, Druck-Button → Browser „Als PDF speichern"), Button in `public/startlist.html`.
      Portal `main` Commit `d937db5` (NICHT deployed). Memory `public-startlist-print`.
      Offen/optional: echter Ein-Klick-`.pdf`-Download bräuchte reportlab (kein PDF-Engine da) — mit User klären.
- [x] **Punkt 3 — Zeitplan zu viele Briefings/Umbauten:** FERTIG (Software `feature/ko-cup`
      Commit `1636e88`). `schedule_planner._compute_timeline_for_ring` gruppiert jetzt pro
      (Disziplin, Laufformat, Klasse) → 1 Umbau+1 Briefing+Läufe statt pro Kategorie. +2 Tests.
      Memory `schedule-briefing-grouping-fix`. Offen: Portal-Flags skip_changeover/skip_briefing/
      force_new_group werden nicht exportiert → Software kann sie nicht honorieren (Follow-up).
- [x] **Punkt 2 — Portal-Tunnellauf:** FERTIG (Portal `main` `9a37642`, Software
      `feature/ko-cup` `40c485b`). **60 Sek/Starter** (User-Entscheid: inkl. Ringwechsel).
      KEINE Migration. Export mappt `tunnel → "Tunnellauf"` in BEIDEN Export-Pfaden
      (club-Route `event_export_zip` UND `services/exchange_service`!), Software
      `_normalize_timing_run_type` liefert „tunnellauf". Neuer `discipline_label`-Jinja-
      Filter. Tests beidseitig grün (Portal 94 / Software 149). Memory `tunnellauf-portal-plan`.
      NICHT deployed (kommt mit ko-cup-Merge + Portal-Deploy).
- [x] **Punkt 4 — Portal FR+EN komplett:** FERTIG (Portal `main` `bd276a7`, NICHT deployed).
      Alle öffentlichen Templates (`public/*` inkl. `cups/`) + Superadmin-Nav gewrappt; Katalog
      556→621 msgids, FR+EN komplett (115 Einträge, 0 leer/0 fuzzy, `.mo` committed). Sprach-
      Umschalter existierte schon (base.html + `/lang/<code>`). 94 Tests grün. Memory `portal-i18n`.
      **Quirk:** `pybabel extract` mit Root `.` (nicht `app`!), sonst 0 Treffer + Übersetzungs-
      verlust in `#~`-Obsolet. Rest-Lücke: `club/*`-Veranstalter-UI teils noch DE (niedrige Prio).
- [ ] **Teilnehmer-Startliste „fehlt komplett":** `public/startlist.html` `is_published`-Gate
      klären (nur unveröffentlicht oder echter Bug).
- [x] Toten Code löschen (Software): `print_marshall_list.html`, `startlist_print*.html`
      — GELÖSCHT (`feature/ko-cup` `bc9ac1d`, repo-weit null Referenzen).
- [ ] Restliche Druck-Listen: Logo-Übergabe + `position:fixed`-Overlap-Fix (Einzel-Review).
- [ ] `feature/ko-cup` → `main` mergen + EXE-Rebuild + Deploy (bringt Datenverlust-Fix 6d57db4,
      Zeitplan-Fix 1636e88, Tunnellauf 40c485b, **CDN-Vendoring 07ead9b** etc.). EXE-Rebuild
      zwingend für die vendored Assets.


## Rangliste Software → Portal (offizielle Ergebnisse) — ⏳ OFFEN, MUST-DO (User 2026-10-07)

**Ziel (User-Zitat):** „die Rangliste aus der Software ins Portal (die Offiziellen)" —
offizielle End-Ranglisten aus AgilitySoftware ins Portal publizieren und öffentlich anzeigen.
Das ist der `resultexport`-Rücksync-Pfad (Software → Portal), NICHT der Event-Export.

**Status/Kontext (noch zu planen, kein Code):**
- Es existiert bereits ein PDF-Weg: Software lädt `print_ranking_pdf.html` via
  `/live/upload_ranking_pdf/<event>/<run>` → Portal `POST /api/resultpdf` (Header `X-Api-Key`).
  Das ist nur ein PDF-Upload, KEINE strukturierten Rangdaten.
- Schemata dokumentiert in Memory `project_exchange_schema` (eventexport / resultexport / liveupdate).
- Offene Fragen für den Plan: strukturierte Ergebnisse (für sortier-/filterbare öffentliche
  Rangliste) vs. nur PDF? Welcher Key (`RESULTS_API_KEY`)? Öffentliche Anzeige-Route
  (`public/`-Ranglistenseite analog startlist)? Team-Challenge-/KO-Ranglisten mit abdecken?
- **Nächster Schritt:** Plan erstellen (Datenvertrag `resultexport.v1` prüfen + Portal-Import +
  öffentliche Anzeige + Phasen), DANN implementieren. User-Entscheide einholen.

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
- [ ] Teilnehmer eintragen via **kompletter AOA-Import** (echte Teilnehmer, KEINE Dummies) —
      User-Entscheid 2026-10-07. Flow `/admin/aoa-import` (Event wählen → CSV/xlsx → preview →
      execute, legt CONFIRMED-Regs an). Details Memory `project_aoa_import_event9_dryrun`.
      Entscheid lokal vs. Prod für den Trockenlauf offen; Exportdatei-Pfad vom User noch ausstehend.
- [ ] **Startlisten** (User-Plan 2026-10-07): morgen Do 08.10. die Freitag-Startliste,
      am Fr 10.10. dann die fürs Wochenende (Events 10/11) — gemeinsam mit Claude.
      ⚠️ Vorher Teil-8-Bündel deployen, sonst Startliste noch mit Vereinsnummern/ohne Rasse.

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

- [ ] **Edelweiss-TESTEVENT auf dem Portal — User braucht es bis Freitag 10.10.2026.**
      Offene Abstimmung (am 2026-10-07 an User gestellt, Antwort steht aus): (a) auf prod
      portal.z-b.tech als `is_test`-Event oder erstmal lokal? (b) volles LiTyWee-3-Tage-Setup
      oder schlankes Gerüst zum Anmelde-Test? (c) Dummy-Teilnehmer oder leer? Software hat bereits
      ein Demo-Event `DEMO_EDELWEISS`. Vorschlag: Do/Fr anlegen (nach Jump-Into-Fall-Startlisten).
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

## Layout / Design der Druck-/PDF-Dokumente — ⏳ OFFEN (kartiert 2026-10-07)

Design-Vorgaben noch offen → zuerst mit Chris klären (Design-Richtung, gemeinsames
Look&Feel Software↔Portal, Logo/Farben, Top-3 vs. volle Liste, Hoch-/Querformat).
Detail-Inventar in Memory `project_design_pdf_siegerehrung`.

**Schon gut (nicht grundlos anfassen):**
- Portal `app/templates/club/event_results_print.html` — sauber (Logos, Klassenblöcke,
  Zebra, @page A4, Flexbox, Browser-Druck).
- AgilitySoftware `web_app/templates/print_ranking_pdf.html` — durchdesignt, bewusst
  `display:table` (via **xhtml2pdf/pisa**, NICHT WeasyPrint); wird von
  `/live/upload_ranking_pdf/<event_id>/<run_id>` an Portal `POST /api/resultpdf`
  (Header `X-Api-Key`) hochgeladen.

**Offen (Priorität in dieser Reihenfolge):**
- [ ] **Siegerehrungsliste** `AgilitySoftware/web_app/templates/print_award_list.html`:
      zieht Bootstrap über **CDN** → am Event ohne Internet unformatiert (Bug). Grosse
      Schrift, Default nur Top 3, kein Logo-Kopf. Routes `/print/select_award_list` +
      `/print/award_list` (routes_print.py ~305-341), Kopf `templates/print/_print_header.html`.
- [ ] **KO-Druck** `AgilitySoftware` `ko_cup_rankings.html` + `ko_cup_print.html`
      (Standard-Bootstrap) aufs HCS-/Druck-Design abstimmen (vor 30.10.).
- [x] **CDN→lokal** FERTIG (Software `feature/ko-cup` `07ead9b`). User bestätigt: Venue hat
      LAN, Internet soll kein Zwang sein. Bootstrap 5.3.3 + FA 6.5.2 (inkl. woff2) + socket.io
      4.7.5 + Tailwind-Play-JS nach `web_app/static/vendor/` vendored, `layout.html` +
      `ring_pc_dashboard.html` (doppelter socket.io raus) + `ko_cup_ring.html` umgebogen.
      Smoke: 9 Vendor-URLs 200, Startseite ohne CDN. Spec bundelt `static/` schon → braucht nur
      EXE-Rebuild. Bewusst CDN belassen: `crashguard.py` Pico-CSS (Crash-Seite, braucht eh Internet).
- [ ] Weitere Druck-Listen (Startlisten, Steward/Marshall, Teilnehmer, Zeitplan) auf
      gemeinsames Design-System vereinheitlichen.

## Architektur-Notiz

- Wird vom AdminPortal verwaltet (Subdomain portal.z-b.tech, Port 8020)
- Sister-Projekt: AgilitySoftware (Online-Offline-Pair, `_related/AgilitySoftware/` falls Cross-Link gesetzt)
- Folgt TKAMO-Reglemente: https://www.tkamo.ch/de/agility/reglemente.html
- Deploy: `supervisorctl restart agilityportal` (AdminPortal-managed)
