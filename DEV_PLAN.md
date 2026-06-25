# AgilityPortal — Dev-Plan (Wettkampf-Saison H2 2026 / Anfang 2027)

> Sprint-Plan für die Veranstaltungen, die Chris betreut. Ergänzt `TODO.md`
> (allgemeine Projektpunkte) und `CLAUDE.md` (Stack/Deploy).
> Stand: 2026-06-21.

## Arbeitsrhythmus

- **Mo–Fr — Entwicklung.** Coden, Features, Migrationen vorbereiten (mit Claude).
- **Wochenende — Testen unter Claudes Anleitung.** Chris testet zuhause am Portal
  (im Büro zu stressig); Claude führt Schritt für Schritt durch Tests und Verifikation.
- **Ziel jeder Woche:** Freitags liegt ein **lauffähiger, testbarer Stand** + eine kurze
  **Test-Anleitung** bereit. Wochenend-Funde fliessen in die nächste Woche zurück.

Deploy bleibt: `git pull && supervisorctl restart agilityportal` (AdminPortal-managed).
Erst deployen, wenn ein Stand am Wochenende getestet wurde.

## Backlog nach Deadline (harte Termine)

| Deadline | Veranstaltung | Wertung | Status |
|---|---|---|---|
| **15.11.2026** (1. v. 4 Meetings) | WiMeSma-Cup (Small/Medium) | Saison-Cup, `wimesma_cup` | 🟡 Fundament gebaut (Commit `dbe60c4`); Punktetabelle offen (Reglement-Website war down) |
| **21.–22.11.2026** | BCCS-SM (Border Collie) | `bccs_sm`, 2 Quali + 2 Final | 🔴 Reglement liegt vor (PDF 2023); Implementation offen |
| **27.–29.11.2026** | Adventscup | `advents_cup`? | 🔴 Regelwerk klären (reicht Halloween-Muster?) |
| **05.–06.12.2026** | SKBS-SM + FMBB-Quali Münsingen | `skbs_sm` / `fmbb_quali` | 🟡 Plan vorhanden (Dezember-Plan + FMBB-Plan) |
| **08.–10.01.2027** | Edelweiss Challenge | `edelweiss_challenge`? | 🔴 Reglement noch offen |

WiMeSma-Meetings 26/27: **15.11.2026 · 12.12.2026 · 17.01.2027 · 13.02.2027** (+ Final danach).

## Sprint-Reihenfolge (Entwicklungs-Fokus)

Reihenfolge nach Deadline **und** Baubarkeit (Reglement vorhanden?):

1. **WiMeSma fertigstellen** *(klein, weitgehend erledigt)*
   - [x] Cup-Saisonwertung repariert (`points_table`, `count_best_meetings`, `standings_disciplines`)
   - [x] `special_ruleset = "wimesma_cup"`, Admin-Form-Felder
   - [x] **Platzhalter-Punktetabelle** (Top 10: 20·17·15·13·11·9·7·5·3·1) — wird beim Anlegen
         eines WiMeSma-Cups automatisch gesetzt, falls leer. **PROVISORISCH**, mit Reglement ersetzen.
   - [ ] Test-Cup mit 4 Meetings anlegen, öffentliche Rangliste prüfen (Wochenende)
   - [ ] **Blocker (echte Werte):** exakte Punktetabelle Rang 1–10 (Open/Jumping) + beste-N
         — sobald wimesma.ch wieder online (Platzhalter ersetzen)
   - [ ] Klären: Cup-Punkte pro Klasse getrennt oder Small/Medium kombiniert (`split_by_class`)
   - [ ] Final-Modus (Open-Lauf, Startreihenfolge umgekehrt) — wartet auf verifiziertes Reglement

2. **BCCS-SM** *(grösster Neubau, Reglement vorhanden → Haupt-Aufwand Juli–Okt)*
   - Muster = **SKBS-SM** end-to-end: Berechnung in AgilitySoftware → `finalists.json`
     (Schema `resultexport.v1`, v1.6) → Portal-Import `event_finalists`. Im Portal sind
     `bccs_sm`-Type + `EventFinalist`-Modell + Import bereits generisch vorhanden (keine Migration nötig).
   - [x] **Berechnungskern** `AgilitySoftware/web_app/bccs_sm_qualification.py` + Unit-Tests
         (`tests_pure/test_bccs_sm_qualification.py`, 12 grün): 15 %-Quote, I+L getrennt,
         SM (Kl.3) / Nachwuchs (Kl.1+2 kombiniert), alternierendes Nachrücken, Titelverteidiger,
         2-Lauf-Final summiert (Fehler→Parcours→Zeit, ex aequo)
   - [ ] **Offene Reglement-Annahmen bestätigen** (im Modul-Docstring dokumentiert): Nachwuchs
         Kl.1/2 wirklich kombiniert? Quali-Lauf-Reihenfolge fürs Nachrücken? Mindest-Quote?
   - [x] Routes + Templates in AgilitySoftware: `routes_bccs_sm.py` (Dashboard/Config/CSV),
         `bccs_sm_dashboard.html` + `bccs_sm_config.html`, Blueprint in `app.py`, Event-Typ „BCCS-SM"
         im Dropdown (`routes_events.py`), `is_final`-Run-Markierung (manage_runs/run_form). Smoke + 12 Tests grün.
   - [x] `portal_sync.py`: Finalisten-Payload für BCCS-SM (mit `category`+`division`)
   - [x] **Portal-Import:** `EventFinalist` um `category`+`division` erweitert (Migration `zc2d3e4f5a6b`),
         `_import_finalists` übernimmt sie; SKBS lässt NULL. Tests `test_finalists_import.py` (3) grün.
   - [x] Portal: öffentliche Finalisten-Anzeige `GET /events/<id>/finalists` (BCCS nach Kategorie+Division
         gruppiert, SKBS flach) + Template `public/finalists.html`. Tests `test_public_finalists.py` (4) grün.
         (Direkt-URL wie Zeitplan/Startliste; `is_published`-Guard + Admin-Key.)
   - [ ] Browser-Test Dashboard (AgilitySoftware) + Import-Roundtrip am Wochenende (I/L, SM + Nachwuchs)
   - [ ] Reglement: `Reglemente_Nützliches/BCCS_Agility_SM_Reglement_2023.pdf`

3. **Adventscup** *(klein)* — prüfen ob `advents_cup` analog Halloween reicht; sonst eigene Regel.

4. **SKBS-SM + FMBB Münsingen** — bestehender Dezember-Plan + FMBB-Plan abarbeiten.

5. **Edelweiss Challenge** — Regelwerk besorgen/klären, dann einplanen.

## Test-Daten-Automatisierung (vom User 2026-06-21 freigegeben)

Ziel: aus offiziellen Listen automatisch Startlisten/Ergebnisse/Ranglisten erzeugen +
Soll/Ist gegen die AgilitySoftware-Auswertung vergleichen.

Referenz-Korpus geladen unter `OneDrive\Agility_Test_20260620\`:
- `startlists\` + `official_rankings\` (Swiss Summits 20./21.06.2026)
- `bccs_2025_reference\` (BCCS-SM 2025: Quali + Final + Kombiniert)
- `halloween_cup_2025_reference\`, `fmbb_2024_reference\`

Gebaut: `…\Agility_Test_20260620\tools\parse_rankings.py` — parst agilityevents-Ranglisten
→ strukturiertes JSON (Schlüssel = Lizenznr). ~96 % Abdeckung über 150 PDFs.

Offen (siehe `tools\README.md`): Split-Zeilen + `Kombinierte_*` parsen → Startlisten/Ergebnisse
im Software-Format generieren → Soll/Ist-Diff. BCCS: Quali→`calculate_bccs_sm_qualification`,
Final→`rank_final_bccs` gegen die offiziellen PDFs validieren.

## Wochen-Loop (Vorlage)

1. **Mo:** Wochenziel aus Sprint-Reihenfolge wählen (1 klar abgegrenztes Stück).
2. **Di–Do:** Implementieren + lokal `py_compile`/Smoke-Checks.
3. **Fr:** Stand lauffähig machen; Claude schreibt **Test-Anleitung fürs Wochenende**.
4. **Sa/So:** Chris testet zuhause unter Anleitung; Funde notieren → Backlog.
5. Wenn grün getestet: deployen.

## Nächster Test (Wochenende 27./28.06.2026)

Mehrere Dinge zusammen testbar:

**A) WiMeSma-Cup-Rangliste (reparierter Stand)**
1. Test-Cup „WiMeSma 26/27“ anlegen, `special_ruleset = wimesma_cup`, Kat. Small/Medium.
   → Punktetabelle + Disziplinen (Open/Jumping) werden als **Platzhalter automatisch** gesetzt.
2. Die 4 Meetings (15.11./12.12.2026, 17.01./13.02.2027) als Events verknüpfen.
3. Testresultate importieren (siehe Portalupload-Test).
4. Öffentliche Rangliste öffnen → darf **nicht mehr 500en**; Agility-Läufe dürfen **nicht** zählen;
   bei „beste N“ nur die besten N Meetings summiert.

**B) Portalupload-Test (AgilitySoftware → Portal)**
- Event-Paket / Resultate aus AgilitySoftware ins Portal hochladen (Exchange-Schema) und prüfen,
  dass Import sauber durchläuft und die Daten korrekt ankommen (Teilnehmer, Läufe, Resultate).
- Dient zugleich als Datenquelle für den WiMeSma-Ranglisten-Test (A.3).
- Referenz: [[exchange-schema-portal-software]] (Memory) / `exchange_service.py`.

**D) Ranglisten-Soll/Ist-Vergleich (Starttestdaten 20./21.06.2026)**
- Referenzdaten unter `OneDrive\Agility_Test_20260620\` (geladen 21.06.):
  - `startlists\` (6 PDFs) = Input: Teams, Lizenz, Startnummer, Läufe (A/J/S).
  - `official_rankings\` (56 PDFs) = offizieller Output je Lauf.
- Ist = AgilitySoftware-Auswertung derselben Starttestdaten.
- **Harness fertig + validiert:** `…\Agility_Test_20260620\tools\compare_soll_ist.py`.
  Soll = SportyDog-PDFs via `parse_rankings.py --json` (pro Lauf); Ist = AgilitySoftware-Ausgabe
  (`resultexport.v1`-JSON ODER parse_rankings-Format). Vergleich pro Lauf (Disziplin/Kategorie/Klasse)
  je Lizenz → Rang/Total/Zeit. Selbsttest 209 identisch; Diff-Erkennung bestätigt.
  Ist-Loader an AgilitySoftware `resultexport.v1` angepasst (Lizenz = `registration_external_id`);
  liest das Export-**ZIP direkt** (results.json darin) oder JSON.
  **`parse_rankings.py` kann jetzt BEIDE PDF-Formate:** agilityevents („Normale_Rangliste", via pdftotext)
  UND **swissagilitysummits** (koordinatenbasiert via **pdfplumber** → 0 Lücken, löst das Overlap-Problem).
  Validiert: Summits-Wochenend-Event (20.06.2026) Roundtrip **392 identisch, 0 Abweichungen**; BCCS 140 identisch.
  **Wichtig:** für Summits-PDFs `parse_rankings.py` mit dem **flask_env-Python** laufen (hat pdfplumber):
  `C:\Users\chris\.venvs\AgilitySoftware\flask_env\Scripts\python.exe`.
  **Wochenende:** in AgilitySoftware das Result-Export-ZIP erzeugen, dann
  `<flask_env-py> tools/parse_rankings.py official_rankings/2026-06-20 --json soll.json` und
  `python tools/compare_soll_ist.py soll.json <export>.zip`.
- Hinweis: Die DBISAM-Roh-DB hat KEINEN sauberen Lauf-Schlüssel an fester Stelle (verifiziert) →
  für 1:1 sind die PDFs (= SportyDogs eigene pro-Lauf-Ausgabe) der richtige, fertige Soll-Weg.
  Der DB-Reader (`sportydog_reader.py --export`) bleibt als Zusatz (Qualifikation + RunTime je Lizenz).

**C) BCCS-SM (sobald in der Woche gebaut)** — erste Quali-/Finalisten-Berechnung gegen die
15 %-Regel prüfen (Testdaten Intermediate/Large), sofern bis Freitag testbar.

**E) BCCS-2025-Soll/Ist-Validierung**
- Referenz unter `OneDrive\Agility_Test_20260620\bccs_2025_reference\` (66 offizielle PDFs:
  Quali, 2 Finalläufe, kombinierter Final; SM=Kl.3 / Nachwuchs=Kl.1+2, Intermediate+Large).
- Quali-Läufe → `calculate_bccs_sm_qualification()` → Finalisten-Set vs. Teams in den Final-PDFs.
- Finalläufe → `rank_final_bccs()` → vs. `Kombinierte_…`-PDF (Soll). Schlüssel: Lizenznummer.
- Bestätigt zugleich die offene Annahme „Nachwuchs Kl.1+2 kombiniert" (Struktur stützt sie bereits).

(Detaillierte Klick-Anleitung erstellt Claude am Freitag davor.)
