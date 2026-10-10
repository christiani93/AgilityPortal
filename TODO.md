# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-10-10

## Session 2026-10-10 — Hundeführer pro Anmeldung wechseln

- [x] **Neue Funktion: Hundeführer einer einzelnen Anmeldung wechseln** (committed,
      3 neue Tests + volle Suite grün): Bug/Gap gefunden — der bestehende ✎-Button
      ("Name korrigieren", `registration_rename`) ändert die Person-Stammdaten
      global, betrifft also ALLE Anmeldungen derselben Person (z.B. alle Hunde
      von Corinne Boeufvé statt nur den einen, der zu Chloé wechseln soll). Neue
      Route `POST /club/registrations/<reg_id>/change_handler` (`routes.py`)
      hängt nur `reg.handler_id` dieser EINEN Anmeldung um (Dropdown: bereits im
      Event vorkommende Personen; Fallback: Freitext legt neue Person an).
      Button "⇄" in `club/event_detail.html`. Stammdaten/andere Hunde unberührt.

## Session 2026-10-09 (Teil 3) — ZIP-Export aller Ranglisten-PDFs

- [x] **Neue Funktion: Alle Ranglisten-PDFs als ZIP exportieren** (committed,
      6 neue Tests + volle Suite grün): `GET /club/events/<id>/results/pdfs.zip`
      in `app/blueprints/club/routes.py`, geschützt via `_assert_event_access`
      (Veranstalter-Club oder Superadmin). Button in `club/event_info.html` über
      der Ranglisten-Liste, gleiche Sichtbarkeits-Bedingung wie Routen-Prüfung.
      Test-Datei `tests/test_result_pdfs_zip.py` neu. Memory
      `project_portal_result_pdfs_zip_export` (enthält wichtige Architektur-Notiz:
      `_assert_event_access` ist club- nicht rollenbasiert).

## Session 2026-10-09 (Teil 2) — i18n öffentl. Zeitplan + Edelweiss-Vorlage + Funktionen-Dropdown-Plan

### Portal (`main`, DEPLOYED portal.z-b.tech, keine Migration) — Memory `reference_portal_i18n`
- [x] **Öffentlicher Zeitplan war unübersetzt** (`4687679`, Prod HEAD, deployed, 137 Tests grün):
      Segment-/Lauf-Labels (Umbau/Vorbereitungspause/Briefing Kl.X, Lauf-Titel wie „Agility Small
      Kl. 1") wurden in `app/blueprints/club/schedule_utils.py` als **deutsche f-Strings** gebaut
      (`compute_detailed_segments`, `compute_timeline`, `_briefing_label`, `auto_title`) → kamen
      fertig-deutsch im Template an, obwohl `public/schedule.html` korrekt `_()` nutzte. FIX:
      `flask_babel.gettext as _` importiert + Labels gewrappt; Katalog-Einträge existierten schon
      (kein extract/update/compile nötig). **Lektion:** Python-Helper die Anzeige-Strings per
      f-String bauen umgehen Template-i18n. **Quirk:** `gettext` braucht Request-/App-Context → die
      2 reinen Timeline-Tests mussten auf `app.test_request_context()` umgestellt werden. Betrifft
      automatisch auch die eingeloggte Veranstalter-Ansicht (gleiche Funktionen). End-to-End mit
      FR-Session verifiziert.

### Portal-Prod-DB direkt (KEIN Code-Deploy, reine Datenänderung) — Memory `project_edelweiss_reglement`
- [x] **Edelweiss-Vorlage bereinigt**: Ab 2027 entfällt der normale Einzel-Agility-Final komplett
      (ersetzt durch Team-Challenge, User-Entscheid). Die 4 `EventTemplateRun`-Zeilen mit
      `is_final=True` (Agility, Kl.3, je S/M/I/L, IDs **78–81**) aus EventTemplate **ID 3** gelöscht
      (per Einmal-Script im App-Context über ssh hostpoint). 24 Standard-Matrix-Läufe bleiben
      (Agility+Jumping × S/M/I/L × Kl.1-3).

### Offen / Folge-Tasks
- [ ] **SW „Funktionen"-Dropdown statt Veranstaltungsart** (NACH Jump-Into-Fall-WE) — Memory
      `project_software_functions_toggle`. User-Entscheid: nicht Dual-Axis wie Portal
      (`type`+`special_ruleset`), sondern **Mehrfachauswahl kombinierbarer Funktionen/Module**
      (z.B. Team-Challenge als Quali UND KO-Cup fürs Finale gleichzeitig am selben Event). Heute
      zeigt `manage_runs.html` den KO-Cup-Button IMMER (ungegated), Team-Challenge/SM/SKBS/BCCS nur
      per `event.Veranstaltungsart == 'X'` (starre 1-von-N). Vor Baubeginn mit User klären: welche
      Funktionen exklusiv vs. kombinierbar, UI (Checkboxen/Chips), ob Portal mitzieht. Nicht
      event-kritisch (Edelweiss erst 08.–10.01.2027).

## Session 2026-10-08 (Teil 5) — Event-Sichtbarkeit + Kommende/Vergangene + Ring-Monitor-Fixes

### Portal (`main`, DEPLOYED portal.z-b.tech, keine Migration) — Memory `project_events_visibility_20261008`
- [x] **Kommende/Vergangene-Split auch in /club/** (`c7c4256`): Club- + Superadmin-
      Übersicht sortiert jetzt wie die öffentliche Liste (nächstes Turnier oben,
      vergangene mit Trennzeile darunter). Geteilte Logik
      `app/models.py::split_events_upcoming_past`. Test `tests/test_dashboard_upcoming_past_smoke.py`.
- [x] **is_published an is_test gekoppelt** (`265f946`): `is_published = not is_test`
      in `event_new`/`event_edit`. Keine separate Publish-Checkbox (in `c7c4256` kurz
      eingeführt, dann auf User-Wunsch entfernt). Nur "Testveranstaltung" steuert alles.
      **QUIRK:** Bestehende DB-Events werden NICHT rückwirkend publiziert — erst beim
      nächsten Form-Speichern. Event 14 "Swiss Agility Summits - Sonntag" (is_test=0,
      aber is_published=0) muss User einmal im Bearbeiten-Formular speichern, damit es
      im "Vergangene"-Bereich erscheint (= sein Testfall fürs letzte Wochenende).

### AgilitySoftware (`main`, committed `ea87048`, ⚠️ NICHT auf GitHub) — Memory `reference_ring_state_dual_mechanism`
- [x] **"Aktueller Starter" auf Ring-Monitor + Sprecher-Display GEFIXT**: 2 Bugs —
      (1) `ring_state._find_entry()` verwarf Rohfelder (Vorname/Hundename/Startnummer),
      die Monitor/Sprecher über `format_ring_name()` direkt lesen → Anzeige leer;
      (2) `apply_result_saved()` war importiert aber nie aufgerufen → current_entry_id
      im ring_entry_state rückte nie weiter. Jetzt in `save_result` + `api_set_participant_status`.
- [x] **Button "Zeit diesem Teilnehmer zuweisen" (kein Timer-Reset)** meldet jetzt
      auch an Hauptserver (neuer Endpoint `POST /live/api/reassign_current_starter` +
      `ring_state.apply_manual_reassign`) → Ring-Monitor/Sprecher ziehen mit. Vorher
      nur lokaler TIMY-Ring-Server-Socket.
- [x] **Ring-Monitor bei inaktivem Ring**: Button "📅 Zeitplan anzeigen" →
      `/print/schedule/<event_id>` (bestehende Druckansicht).
- [x] 173 Tests grün (+4 neue in `tests_pure/test_ring_state.py`).

### Offen / Folge-Tasks
- [ ] **AgilitySoftware Server NEU STARTEN** vor Live-Test (debug=False → kein
      Auto-Reload, EXE ggf. neu bauen aus `ea87048` falls am Turnier die EXE läuft).
- [ ] **Mehrring-Realtest Ring-Monitor/Sprecher** am echten Event (Jump Into Fall).
- [ ] **AgilitySoftware `main` → GitHub pushen**: origin steht auf `49b5972`, lokal
      weit voraus (bc37976/1262f44/f9618e2/41dfbad/d125eb7/f2e9b4e/2fc5ea7/**ea87048**).

## Session 2026-10-08 (Teil 4) — Öffentliche Eventseiten: Rangliste/Live/ZIP/Direktlink — ✅ DEPLOYED

Drei Deploys live auf portal.z-b.tech, keine Migration (Head bleibt `f6a7b8c9d0e1`).
Memory `project_prod_deploy_20261008_public_pages`.

- [x] **Rangliste-Karte + ZIP nur /club/** (`c9f83b6`): Overview bekommt 🏆-Rangliste-Karte
      (gated `has_results`=`ResultImport` existiert); Live-Karte war schon da (`is_event_day`).
      Öffentliche ZIP-Route `public_startlist_zip` **gelöscht** + Buttons aus beiden public-
      Templates raus → `/events/<id>/startlists.zip` ist jetzt 404. ZIP nur noch via
      `club.event_startlist_zip` (`/club/events/<id>/startlists.zip`), Button auf `event_detail`.
- [x] **Kurzlink `/live`** (`f3cfa7c`): `public_events.live_shortcut` leitet auf das heute
      laufende Event (`club.event_live`) weiter, sonst auf `/events`. Für QR-Code gedacht.
- [x] **Direktlink je Klasse** (`fca8992`): „🔗 Nur diese Klasse" pro Block in der Gesamt-
      Startliste → `?cat=&cls=` (Einzelansicht). War die ursprüngliche „pro Klasse verlinken"-
      Frage; Backend konnte es schon, nur UI-Verdrahtung fehlte.

### Offen / Folge-Tasks
- [ ] **Morgen (2026-10-09) `/live` am echten Event prüfen** (User will selbst testen):
      `/live` wählt rein per Datum, `club.event_live` verlangt zusätzlich
      `status in (open,closed,cancelled)`. Jump Into Fall muss an dem Tag auf einem dieser
      Status stehen, sonst zeigt `/live` korrekt hin, aber die Live-Seite gibt 404.
- [ ] **„Vergangene Events" auf /events**: bereits implementiert (`events_index.html` hat
      Abschnitt „Vergangene", Route teilt nach Enddatum<heute). Erscheint automatisch, sobald
      das erste publizierte Event vorbei ist — kein Code-Task.

## Session 2026-10-08 (Teil 3) — Druck-Fixes Runde 2 + LIZ-Spalte + EXE-Build + AOA-Vergleicher-Wunsch

- [x] **Portal: LIZ-Nr in Anmeldungstabelle** (`991578f`, DEPLOYED Prod HEAD `991578f`, keine
      Migration): `club/event_detail.html` zeigt `reg.dog.license_no` als neue Spalte →
      Veranstalter kann per Browser-Suche nach Lizenznummer suchen.
- [x] **Software-Druck-Fixes Runde 2** (committed `d125eb7`/`f2e9b4e`/`2fc5ea7`, AgilitySoftware
      `main`, **NICHT auf GitHub**): Laufvorgaben-Tabelle aus Einweiserliste raus; Zeitplan auf
      ~25 Läufe/Seite + Schreiberlisten ~20 Teilnehmer/Seite verkleinert; „DIS/ABR"-Spalte
      übersetzt (FR DIS/ABD, EN DIS/WD); Logos in print/all jetzt in ALLEN Bündeln (Einweiser +
      Ringbüro banden `_print_header` vorher gar nicht ein). 170 Tests grün. Memory
      `project_print_fixes_20261008`, `reference_print_subsystem_software`.
- [x] **AgilitySoftware.exe neu gebaut** aus HEAD `2fc5ea7` (64-bit, Smoke HTTP 200). AgilityRing.exe
      NICHT neu (keine Ring-Änderungen). Build-Mechanik + pyinstaller.exe-Quirk: Memory
      `project_software_exe_build`.
- [x] **Frage beantwortet (Abmeldung über Portal):** „Anmeldung ablehnen" (`registration_reject`)
      setzt Status CANCELLED **ohne Mail-Versand**, funktioniert auch bei externem Anmeldeportal
      (`registration_external` sperrt nur Self-Registration, nicht Veranstalter-Aktionen).

### Offen / Folge-Tasks
- [ ] **AgilitySoftware `main` pushen**: origin/main steht auf `49b5972`; lokal voraus mit
      `bc37976`/`1262f44`/`f9618e2`/`41dfbad`/`d125eb7`/`f2e9b4e`/`2fc5ea7` (nur lokal).
- [x] **AOA-Vergleicher (Portal)** (`b18545b`, DEPLOYED Prod HEAD `b18545b`, keine Migration,
      129 Tests grün, Realtest OK Event 9): Re-Import-Diff-Tool unter `/admin/aoa-import` →
      Karte „🔄 Re-Import abgleichen". Routen `compare/preview` + `compare/execute` in
      `routes_aoa_import.py`, Template `aoa_import/compare_preview.html`, Test `test_aoa_compare.py`.
      3 Buckets: **neu** (anlegen + angehängte Startnr: max belegte im Kat/Klasse-Band +1,
      bestehende unberührt) / **weggefallen** (=Abmeldung, status CANCELLED, kein Mail) /
      **geändert** (Kat/Klasse optional). Matching = **Lizenznummer**. Alles per Checkbox
      bestätigt, nichts automatisch. Memory `project_aoa_vergleicher_request`.

## Session 2026-10-08 (Teil 2) — Testimport Portal→Software + Import-Verifikation

Pre-Wochenend-Testimport des echten Jump-Into-Fall-Pakets in die AgilitySoftware,
Bugfixes + voller Datenabgleich gegen die Portal-Prod-DB.

- [x] **AgilitySoftware ZIP-Import-Crash GEFIXT** (`bc37976`, AgilitySoftware `main`,
      NICHT zu GitHub gepusht): `import_event_package` schloss den `with ZipFile`-Block vor
      der Logo-Extraktion → „Attempt to use ZIP archive that was already closed" (nur bei
      Export-Paketen MIT `logos/`-Ordner). Zusätzlich latenter Mutable-Default-Bug
      `utils._load_data(filename, default_data=[])` gefixt. Regressionstest
      `web_app/tests/test_import_event_package.py`, 167 Tests grün. **AgilitySoftware.exe neu
      gebaut** (14:49, headless-smoke OK). Memory `project_exe_rebuild_20261008`.
- [x] **Import-Verifikation Event 9 ↔ Portal-Prod-DB** (via ssh hostpoint + mysql): 104
      Starter, 24 Läufe, alle 12 Kat/Klasse-Kombis 1:1, Startnummern 104/104, Richter
      (Elpina Ismael AIS 22340) an allen 24 Blöcken, Logos extrahiert — **stimmt exakt**.
      Neue Referenz `reference_portal_prod_db_direct_query` (DB-Direktabfrage-Weg +
      verified_*-COALESCE-Quirk).
- [x] **Portal-Export-Gap breed + club_name GEFIXT**: Beim Import kamen **Rasse 0/104 +
      Vereinsnummer 0/84** NICHT an. Root Cause: Portal hat ZWEI eventexport-Pfade; die
      real verlinkte `club/routes.py::event_export_zip` exportierte KEIN `breed` und KEIN
      `club_name`. FIX: `breed` in `entities.dogs[]` + `club_name` (roh = Vereinsnummer,
      identisch zu exchange_service) je Registration ergänzt. **Entscheid: Pfade NICHT
      konsolidiert** — es sind zwei legitime Schemata (external_id-Round-Trip Portal↔Portal
      vs. license_no Portal→Software); Merge würde einen Konsumenten brechen. Stattdessen
      neuer Kontrakt-Test `tests/test_club_export_contract.py` auf der echten Route, der
      breed+club_name festnagelt (die alte Test-Lücke, durch die es durchrutschte). 127
      Tests grün. **DEPLOYED 2026-10-08 (Prod-Head `8117fce`, Smoke 200)** + **VERIFIZIERT**:
      Event 9 neu exportiert/importiert → Rasse 104/104 + Vereinsnummer 84/84 angekommen
      (vorher 0/0), Rasse rendert sichtbar in Software-Druck-Startliste. Gap geschlossen.
      Memory `project_portal_export_dual_path_breed_club_gap`.
- [x] **AgilitySoftware Veranstaltungsliste-Crash GEFIXT** (`1262f44`, AgilitySoftware `main`,
      **NICHT zu GitHub gepusht**): nach dem Import 500 auf `/events/` — `events_list.html`
      sortierte via Jinja `|sort(attribute='Datum')`; Legacy-Testevent `E1` (altes Schema
      ohne `Datum`) lag schon in events.json, fiel aber erst auf als der Import ein 2. Event
      dazu brachte (sorted() verglich erstmals). FIX: Sortierung in die Route mit Fallback
      `e.get('Datum') or ''`. 167 Tests grün. Memory `reference_agilitysoftware_dev_run`.

### Offen / Folge-Tasks
- [ ] **AgilitySoftware `main` pushen**: `bc37976` + `1262f44` liegen lokal, noch nicht auf
      GitHub (Portal `8117fce` IST gepusht).
- [ ] **(Idee) Software-Event-Import als Upsert per external_id** statt append-mit-neuer-uuid
      → Re-Import erzeugt sonst Duplikate. Siehe `reference_agilitysoftware_dev_run`.

## Session 2026-10-08 — E-Mail-Fix + Klassen-Tausch + Deploy + Startlisten-Check

- [x] **AOA-Import E-Mail/Telefon-Backfill** (`a3e74d8`): bestehende (per Name gematchte)
      Handler bekamen die E-Mail aus der Startliste nicht nachgetragen → Lizenzcheck-CSV-
      E-Mail-Spalte leer. Jetzt werden leere Kontaktfelder nachgetragen (kein Überschreiben).
      Memory `project_aoa_import_email_backfill`.
  - [x] **Prod-Deploy** erledigt 2026-10-08 (Prod `5d9216e`→`716fc79`, keine Migration,
        0 Crashes, HTTP 200).
  - [x] Kein Startlisten-Reimport nötig: Event 9/10/11 hatten zum Deploy noch 0 Anmeldungen,
        der echte Import lief NACH dem Deploy gegen die gefixte Version.
- [x] **Klasse online tauschen — Veranstalter-seitig** (`716fc79`, UMGESETZT+DEPLOYED
      2026-10-08, keine Migration, 126 Tests grün): Inline-Dropdown Kat/Klasse pro Anmeldung
      in der Veranstalter-Anmeldeliste. Route `POST /club/registrations/<reg_id>/class`
      (`registration_set_class`, Guard `_assert_event_access`); wirkt nur auf diese Anmeldung,
      optional Form-Feld `update_dog` zieht Hunde-Stammdaten nach. Eigentümer-Self-Service
      (`/club/profile/dogs/<id>/class`) bleibt daneben. Memory `project_online_class_swap_request`.
  - [ ] Lizenzcheck-Direktumstellung (Interpretation b, statt Mail-Link) bewusst NICHT gebaut
        — bei Bedarf separat.

### Jump Into Fall Event 9 — echter AOA-Import GELAUFEN (2026-10-08)
- [x] **Event 9** (Jump Into Fall Vendredi 09.10.2026) hat jetzt **104 echte Anmeldungen**
      (`is_test=False`), CONFIRMED. Event 10/11 noch 0 Regs (Import am Fr 10.10. geplant).
      Event 16 (alte Testkopie) existiert in der Prod-DB nicht mehr.
- [x] **Startlisten Freitag erzeugt + plausibilitätsgeprüft**: 12 PDFs unter
      `Y:\Startlisten_Jump_Into_Fall_Vendredi_09_10_2026` (S/M/I/L × Kl.1-3), Summe 104 Teams
      = DB. Kopf/Logo (ALP'IN), Spalten, Startnr.-Schema (1xxx=L/2xxx=I/3xxx=M/4xxx=S,
      2.Stelle=Klasse), Rasse/Verein-Kürzung, Umlaute — alles ok.
- [x] **ENTSCHIEDEN — Person-Duplikat durch Namensdreher** (Benito/Benoit): Quelle
      geprüft (`Y:\_Export_SportyDog_2025_10 (1).xlsx`, Zeilen 28+29) → **beide Records
      stehen schon so in der SportyDog-Quelle**, der Dreher stammt aus der Anmeldung, nicht
      vom Portal-Import. User-Entscheid 2026-10-08: **NICHT mergen** (versch. Kat/Klasse:
      Never Small-Kl.3 / Amigo Medium-Kl.1 → keine Startlisten-Kollision, nicht blockierend).
      Andere 5 shared-email-Fälle Event 9 = echte Familien. Memory
      `project_aoa_import_handler_email_merge_bug`.
- [ ] **OPTIONAL Import-Hardening**: automatische Dreher-Erkennung (E-Mail+Tel gleich,
      Vor-/Nachname über Kreuz gleich) → Merge-Vorschlag beim AOA-Import. Nicht gebaut.

## Session 2026-10-07 (Teil 10) — i18n-Durchsicht Portal + Software — ✅ Portal DEPLOYED, Software committed (unreleased)

Komplette Übersetzungs-Durchsicht aller nicht-Admin-Seiten (Portal) + Druck-Routen
(Software), Auslöser war die Club-Startliste mit DE-Text auf FR/EN. Portal committed
(`5d9216e`) + live deployed (Supervisor-Restart ok, 200 OK, keine Migration). Software
committed (`9ea596b` auf `feature/ko-cup`), noch nicht gemerged/released. Memory:
`project_i18n_review_20261007`, `feedback_pybabel_fuzzy_corruption`,
`software_print_locale_routing_gotcha`.

**Portal (`AgilityPortal`, `main`, committed `5d9216e`, DEPLOYED):**
- [x] `club/startlist.html`, `club/event_live.html` (JS via `I18N`-Objekt),
      `club/event_results_print.html`, `club/template_list.html`,
      `club/template_create_event.html` komplett `_()`-gewrappt.
- [x] Lücken: `club/event_detail.html` (2 confirm-Dialoge + Zahlungs-Platzhalter),
      `club/admin_settings.html`, `public/finalists.html` (Label-Dicts via `_(dict.get())`),
      Python: `routes_lizenzcheck.py` flash, `routes.py` TKAMO-Proxy-JSON-Errors.
- [x] PDF-Generator `app/services/startlist_pdf.py`: `gettext as _` importiert,
      `_DATA_COLUMNS`→Funktion `_data_columns()` (lazy im Request-Kontext),
      Spaltenköpfe/Block-Label/ZIP-Dateiname übersetzt.
- [x] **Katalog-Korruption behoben:** `pybabel update` hatte ~96 FR/EN-Strings per
      Fuzzy-Match verfälscht (LIVE: "Rasse"→FR "Classe"/EN "Class"!). Alle neu/korrekt
      übersetzt, fuzzy=0 empty=0, `.mo` kompiliert, gettext in fr/en/de smoke-getestet.
- [x] PDF-ZIP-Generierung mit FR-Locale getestet (Dateiname korrekt gesluggt).
- [x] Committed + deployed 2026-10-07 (`supervisorctl -c … restart agilityportal`,
      keine Migration, Head bleibt `f6a7b8c9d0e1`). Fix der verfälschten Live-Übersetzungen ist live.

**Software (`AgilitySoftware`, `feature/ko-cup`, committed `9ea596b`):**
- [x] `web_app/app.py` `_select_locale()` erweitert: erfasst jetzt auch Rangliste-PDF
      (`/live/preview_ranking_pdf/`, `/live/upload_ranking_pdf/`) + KO-Druck
      (`/ko-cup/rings_print/`, `*/print`) — vorher IMMER DE (Gotcha-Memory).
- [x] `ko_cup_print.html`, `ko_cup_rings_print.html`, `print/all.html` (5 Header),
      `routes_print.py` (3 flash + 2 title=), `ko_cup.py::round_label()` (mit
      `has_request_context()`-DE-Fallback, bricht Tests ohne App-Kontext nicht).
- [x] SOURCE_LABELS + Rundennamen sind dynamische Lookups → msgids manuell in .po;
      fr/en gefüllt, fuzzy=0 empty=0, kompiliert, Locale-Routing 9/9 Testfälle grün.
- [x] Committed 2026-10-07; geht erst mit `feature/ko-cup`→`main`-Merge + EXE-Rebuild live.

**Bewusst DE belassen (Risiko>Nutzen vor Event):** `models.py`-Label-Dicts (als Strings
verglichen/exportiert), Lizenzcheck-Diagnosemeldungen, VAR-Beamer-Fallback,
Superadmin-only Verein-Dropdown.

## Session 2026-10-07 (Teil 9) — Öffentl. + interne Startliste je Block + ZIP-PDF — ✅ DEPLOYED

Live seit 2026-10-07 (`fb68dae`/`1b80fb7`, danach Follow-up-Fixes `932b442`
Logo-Downscale, `12811f2` ZIP auch in der internen Club-Startliste, `9bebedd`
Logo-Seitenverhältnis, `f8ec0e1` dynamische Spaltenbreiten + einheitliche
Zeilenhöhe + ~30 Zeilen/Seite). GitHub-Push nachgeholt, origin/main synchron.
Keine DB-Migration (Head bleibt `f6a7b8c9d0e1`). Mit Event 16 verifiziert.
Memory: `project_startlist_blocks_zip_pdf`.

- [x] **Daten-Fix (Kern):** Nach AOA-Import+Startnummernvergabe war die öffentliche
      Startliste leer, weil `_collect_startlist_rows` nur die `StartNumber`-Tabelle
      las (wird NUR beim Software-Rücksync befüllt). Jetzt dreistufig:
      StartNumber-Tabelle (Vorrang) → `Registration.start_number` (portal-intern)
      → Meldeliste. In `app/blueprints/public/routes_events.py`.
- [x] **Gruppierung je (Kategorie, Klasse)** wie AgilitySoftware-Startliste
      (`_group_startlist_rows`, Reihenfolge S-M-I-L dann Klasse, Spalten
      Start-Nr./Hundeführer/Hund/Rasse/Verein). On-Screen + Druckseite.
- [x] **Einzelblock** `/events/<id>/startlist?cat=Large&cls=3` (direkt verlinkbar)
      und `/events/<id>/startlist/print?cat=&cls=` (eine Druckseite = ein PDF).
- [x] **ZIP-Download** `/events/<id>/startlists.zip`: ein PDF pro Block, ein
      Download. Button in Event-Übersicht (`overview.html`) + Startlistenseite.
      Einzel-Druckbuttons auf /startlist/ entfernt (ZIP ersetzt sie).
- [x] **PDF-Engine = fpdf2** (`fpdf2==2.8.5`, neu in requirements.txt), NICHT
      xhtml2pdf: dessen aktuelle Version zieht pyHanko + hebt `cryptography`
      42.0.8→50 an (gepinnter DB-Treiber-Stack!). fpdf2 ist pure Python.
      Quirks: Core-Fonts Latin-1 → `_s()`-Sanitizer (curly quotes→ASCII);
      `pdf.table(headings_style=FontFace(...))` (kein dict); Logos aus
      `instance/uploads/logos/<event_id>/` als Datei eingebettet.
- [x] **DEPLOY:** `git pull` + `pip install -r requirements.txt` im Prod-venv
      `.venv` (zieht fpdf2+Pillow+fonttools+defusedxml) + `supervisorctl -c
      ~/.services/supervisord/hostpoint.conf restart agilityportal`. Keine
      Migration. ZIP-Route auf Prod gegen Event 16 verifiziert (öffentlich +
      intern, beide 200).
- [x] **Logo-Fixes (Follow-up):** Logos wurden 1:1 in Originalauflösung
      eingebettet (5907x5059px → 1.38MB/PDF) UND verzerrt (fix w+h statt
      Seitenverhältnis). Jetzt: Pillow-Downscale (max. 400px) + `_fit_box()`
      seitenrichtig, Logo darf bis zur vollen Kopfbereich-Höhe (27mm) gross
      sein, Breite bleibt auf 30mm begrenzt.
- [x] **Spalten/Zeilen (Follow-up):** Start-Nr. inhaltsbasiert statt fix 18mm,
      übrige Spalten dynamisch; bei Platzmangel wird Verein zuerst gekürzt
      ("...", kein Umbruch mehr) → einheitliche Zeilenhöhe; Zeilenhöhe auf
      ~30 Datenzeilen/Seite kalibriert (wie Software-Rangliste-PDF).
- [x] i18n: neue DE-Strings nach FR/EN extrahiert + übersetzt (siehe Teil 10 oben).

## Session 2026-10-07 (Teil 8) — TKAMO-Name + Verein + Rasse + Gap-Neu + AOA-Import-Fix — ✅ DEPLOYED

3 Commits live (`63d9dde` tka_name/Verein/Rasse/Schedule, `862a016` Gap-Neu, `15f1510`
AOA-Import-Merge-Fix). **NEUER Prod-Alembic-Head `f6a7b8c9d0e1`** (additiv dogs.tka_name).
DB-Backup `~/backups/agilityportal_xahizivi_main_20261007_185507.sql`. 115/115 Tests grün.
GitHub-Push nachgeholt (der 500er war nur temporär), origin/main synchron. Details Memory
`project_prod_deploy_20261007_gap_import`.
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
- [x] **Event 9 AOA-Import GELAUFEN** (2026-10-08, echte Teilnehmer): 104 CONFIRMED-Regs,
      `is_test=False`. Event 10/11 noch offen (Import Fr 10.10. geplant). Siehe Session-
      2026-10-08-Block oben.
- [x] **Freitag-Startliste erzeugt + geprüft** (12 PDFs, `Y:\Startlisten_Jump_Into_Fall_Vendredi_09_10_2026`,
      104 Teams). ⚠️ 1 Person-Dreher-Duplikat gefunden (Benito/Benoit) — Merge-Entscheid offen,
      siehe Session-2026-10-08-Block oben.
- [ ] **Startlisten Wochenende**: am Fr 10.10. Events 10/11 importieren + Startlisten erzeugen
      (gemeinsam mit Claude). Teil-8+9-Bündel (Vereinsname/Rasse/Zeitplan-Fix + Block-ZIP-PDF)
      ist deployed.

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
