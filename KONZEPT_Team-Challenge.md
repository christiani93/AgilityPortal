# Konzept: Team-Challenge (Edelweiss Samstagsspiel 2027)

> Stand: 2026-10-05 · Erst-Ausgabe Edelweiss Challenge 08.–10.01.2027 (LiTyWee)
> Betrifft: **AgilityPortal** (Erfassung/Anzeige) + **AgilitySoftware** (Durchführung/Wertung)
> Grundlage: Veranstalter-Mail + [[edelweiss-reglement]] + Code-Sichtung beider Repos 2026-10-05

---

## 1. Das Format (Zusammenfassung)

Das bisherige Samstagsspiel „Who can beat the judge?" wird durch ein **2er-Team-Format**
ersetzt:

- **Team = 2 Mensch-Hund-Paare.** Beide Hunde müssen **derselben Grössenkategorie** angehören.
- **Zwei Prüfungen (= Level):**
  - **Soft** = Grad/Klasse **1 + 2** (Grad-Mix im Team erlaubt)
  - **Expert** = Grad/Klasse **3**
- Jede Prüfung besteht aus **zwei Parcours auf demselben Feld**: ein **Agility** + ein **Jumping**
  (je 15–20 Hindernisse).
- Pro Team läuft **ein Mitglied den Agility, das andere den Jumping** — **direkt nacheinander**
  auf demselben Feld.
- **Jeder Lauf wird separat gewertet und gestoppt.**
- **Teamergebnis = Σ Fehlerpunkte + Σ Zeiten** der beiden Läufe.
- **Rangliste: zuerst Gesamt-Fehlerpunkte, dann Gesamt-Zeit.**
- **Separate Rangliste pro Grössenkategorie.**

### Abgeleitete Struktur

| | Soft (Kl. 1+2) | Expert (Kl. 3) |
|---|---|---|
| **Agility-Lauf** | 1 physischer Lauf | 1 physischer Lauf |
| **Jumping-Lauf** | 1 physischer Lauf | 1 physischer Lauf |

→ **4 physische Läufe.** Die 4 Grössen (S/M/I/L) sind **innerhalb** dieser Läufe gemischt;
die Grösse **splittet nur die Rangliste**, nicht den Lauf.

→ **8 Ranglisten total** = 4 Grössen × 2 Level.

**Wichtig:** Jedes Mensch-Hund-Paar läuft **genau einen** der beiden Parcours (entweder Agility
*oder* Jumping). Damit erscheint jedes Paar in **genau einem** der 4 physischen Läufe — das passt
1:1 auf das bestehende „ein Starter = ein Lauf-Eintrag"-Modell. Neu ist allein die **Verknüpfung
zweier Starter zu einem Team** und die **Aggregation** ihrer zwei Lauf-Resultate.

---

## 2. Grundsatz-Entscheidungen

1. **Weg A — echtes, wiederverwendbares Team-Feature** (nicht der pragmatische Workaround).
   Begründung: Es wird weitere Teamläufe geben; das Team wird eine eigene Datenebene.
   → Neuer, **generischer** `Event.type = "team_challenge"` (NICHT edelweiss-spezifisch).
   Edelweiss-spezifische Feinheiten ggf. über das bestehende `special_ruleset="edelweiss_challenge"`.

2. **Erfassung im Portal, Bearbeitung in der Software.**
   Teams werden im **Portal-Admin** gebildet (aus 2 bereits importierten Registrations),
   reisen im Event-Paket zur Software und sind **am Turniertag in der Software bearbeitbar**
   (Mitglied tauschen, Rolle Agility/Jumping tauschen, Team hinzufügen/löschen).

3. **Rechnende Instanz = AgilitySoftware (offline-first).**
   Deckt sich mit der bestehenden Architektur ([[offline-architektur-qualifinal-berechnung]]):
   das Portal rechnet **keine** Lauf-Ränge selbst, sondern importiert fertige `Result`-Zeilen.
   Die **Team-Wertung** ist eine Aggregation auf diesen Lauf-Resultaten → wird **in der Software**
   gerechnet (offline am Event-Tag möglich) und als fertige **Team-Rangliste** ans Portal
   exportiert. Portal = **Anzeige + Zweit-Validierung** (exakt das `EventFinalist`-Muster von
   SKBS-/BCCS-SM).

4. **„Ordentliche Sync für Sonderauswertungen"** (dein Stichwort) = ein sauberer **Round-Trip**:
   Portal-erstellte Sonderstruktur (Teams) → Software (bearbeitbar) → berechnete Sonderergebnisse
   (Team-Ranglisten) → Portal. Abgleich über stabile **`external_id`** pro Team. Siehe §5.

---

## 3. Datenmodell — Portal

### 3.1 Neu: `Team` (Paarung)

Tabelle `teams` (neues Model in `app/models.py`, angelehnt an `AsmvTeam`-Precedent):

| Feld | Typ | Bemerkung |
|---|---|---|
| `id` | PK | |
| `event_id` | FK events | |
| `external_id` | String, unique | **UUID, stabiler Round-Trip-Schlüssel** (wie bei Registration/Dog) |
| `name` | String, nullable | optionaler Teamname |
| `category_code` | String(20) | `Small`/`Medium`/`Intermediate`/`Large` (Konvention wie `Registration.category_code`) |
| `level` | String(10) | `soft` / `expert` |
| `member_agility_registration_id` | FK registrations | Paar, das den **Agility**-Parcours läuft |
| `member_jumping_registration_id` | FK registrations | Paar, das den **Jumping**-Parcours läuft |
| `source` | String(10) | `portal` / `software` (wer das Team angelegt hat — für Reconciliation) |

**Constraints / Validierung (bei Anlage im Portal):**
- Beide Mitglieder gehören **demselben Event** an.
- **Beide Hunde = gleiche Grössenkategorie** (= `Team.category_code`).
- **Level-Konsistenz:** `soft` → beide Registrations `class_level ∈ {1,2}`; `expert` → beide `class_level = 3`.
- **Ein Paar/Hund nur in EINEM Team** pro Event → App-seitige Prüfung über beide Member-Spalten
  (ein Unique-Constraint reicht nicht, da zwei Spalten; Validierung im Service + DB-Check
  per `registration_id`-Scan).
- Die beiden Member sollten **verschiedene** Registrations sein.

### 3.2 Erweiterung: `EventRun` (4 Team-Läufe + Zeitplan/Richter)

Das bestehende `EventRun`-Modell (`run_type`, `category`, `class_level`, `is_final`, `judge_id`)
passt nicht sauber, weil ein Team-Lauf **grössenübergreifend** (category gemischt) ist und
„Soft" die Klassen **1+2** umspannt. Lösung:

- **Neue nullable Spalte `team_level` (String(10), `soft`/`expert`)** auf `EventRun`.
- Für `type="team_challenge"`-Events werden **genau 4 EventRuns** angelegt:
  `run_type ∈ {agility,jumping}` × `team_level ∈ {soft,expert}`, mit
  `category = NULL` (Grösse gemischt) und `class_level = NULL`.
- Unique-Constraint `uq_event_run` um `team_level` erweitern.

**Gewinn:** Zeitplan (`ScheduleBlock.event_run_id`), **Richter-Zuweisung pro Lauf** und die
`EventJudge`-„Anwesend"-Logik (frisch konsolidiert in `ce95fc7`) funktionieren für die 4
Team-Läufe **unverändert** weiter.

### 3.3 Neu: `EventTeamResult` (importierte Team-Rangliste)

Analog zu `EventFinalist` — von der Software berechnet, ins Portal importiert, read-only Anzeige:

| Feld | Typ |
|---|---|
| `event_id` | FK |
| `team_external_id` | String (Verweis auf `Team.external_id`) |
| `category_code`, `level` | Gruppierung (→ eine der 8 Ranglisten) |
| `team_name` | String |
| `agility_faults`, `agility_time`, `agility_rank`, `agility_status` | Teilresultat Agility-Mitglied |
| `jumping_faults`, `jumping_time`, `jumping_rank`, `jumping_status` | Teilresultat Jumping-Mitglied |
| `total_faults`, `total_time` | Team-Summen |
| `rank` | Rang **innerhalb (category_code, level)** |
| `status` | z.B. `ok` / `incomplete` (ein Mitglied DIS/DNS) |

Idempotenter Import pro Event (alte Zeilen löschen + neu, wie `_import_finalists`).

---

## 4. Datenmodell — AgilitySoftware

Dict-basiert in `events.json`. Ergänzungen am Event-Dict:

- `Veranstaltungsart = "Team-Challenge"` (neuer Wert in den `event_types`-Listen
  `routes_events.py:1158` und `:1189`).
- **`event["teams"]`** — Liste von Team-Dicts:
  ```json
  {
    "external_id": "<uuid>",
    "name": "…",
    "kategorie": "Large",            // = category_code
    "level": "soft",                 // soft | expert
    "mitglied_agility": "<lizenz|registration_external_id>",
    "mitglied_jumping": "<lizenz|registration_external_id>",
    "source": "portal"
  }
  ```
- Die **4 Läufe** entstehen beim Import regulär über die bestehende
  `_apply_eventexport_registrations`-Gruppierung (`(discipline, category, class_level)`), müssen
  aber für Team-Challenge auf **(laufart, level)** umgestellt werden (Grösse gemischt, Soft = Kl. 1+2
  zusammen). → kleiner Sonderpfad im Importer für `Veranstaltungsart == "Team-Challenge"`.
- Jedes Mitglied bleibt ein normaler `entry` im jeweiligen Lauf (Agility- bzw. Jumping-Lauf).
  Die bestehende Lauf-Wertung `_calculate_run_results` (sortiert nach `(fehler_total, zeit_total)`)
  liefert pro Mitglied `fehler_total` + `zeit_total` — **genau die zwei Bausteine** der Team-Summe.

---

## 5. Sync-Erweiterung („ordentliche Sync für Sonderauswertungen")

Beide Richtungen werden **additiv** erweitert (bewährtes Muster: `finalists.json` v1.6 — neue
Datei im ZIP, Schema-String bleibt, Datei-Existenz zur Laufzeit geprüft).

### 5.1 Portal → Software (`eventexport`): neu `teams.json`

```json
{
  "event_external_id": "<uuid>",
  "veranstaltungsart": "Team-Challenge",
  "teams": [ { … Team-Dict wie §4 … } ]
}
```
- Erzeuger: `exchange_service.build_event_export_zip` (neuer Helper `_build_teams_payload`).
- Empfänger: `routes_events.import_event_package` → `_apply_eventexport_teams` (neu) füllt
  `event["teams"]` und mappt Member auf lokale Registrations/Lizenzen.
- Zusätzlich sollte der Export die **4 Läufe explizit** als `runs.json` mitliefern
  (`{run_type, team_level}`) — der Import liest `runs.json` bereits optional; so sind die Läufe
  deterministisch (unabhängig davon, ob zu jedem Lauf schon Registrations existieren).

### 5.2 Software → Portal (`resultexport`): neu `team_results.json`

```json
{
  "event_external_id": "<uuid>",
  "veranstaltungsart": "Team-Challenge",
  "team_results": [
    {
      "team_external_id": "<uuid>", "team_name": "…",
      "category_code": "Large", "level": "soft",
      "agility": {"faults": …, "time": …, "rank": …, "status": "…"},
      "jumping": {"faults": …, "time": …, "rank": …, "status": "…"},
      "total_faults": …, "total_time": …,
      "rank": …, "status": "ok"
    }
  ]
}
```
- Erzeuger: neuer Branch in `portal_sync._build_finalists_payload`-Nachbarschaft, besser eigener
  `_build_team_results_payload(event)` → ruft das neue Wertungsmodul (§6).
- Empfänger: `exchange_service` → `_import_team_results` (analog `_import_finalists`) → persistiert
  in `EventTeamResult`.

### 5.3 Round-Trip / Reconciliation

- Team im Portal erstellt → bekommt `external_id` (uuid) → reist in `teams.json` → Software
  speichert es am lokalen Team-Dict.
- **Bearbeitung in der Software** (Member tauschen, Rolle tauschen, Team ergänzen/löschen am
  Event-Tag): Änderungen passieren lokal; die `external_id` bleibt der Anker.
- **Neu in der Software angelegte Teams** erhalten eine software-seitige uuid + `source="software"`.
- Beim Rück-Import (`team_results.json`) gleicht das Portal über `team_external_id` ab:
  bekannte Teams → Resultat anhängen; unbekannte (in Software ergänzte) → als neues
  `EventTeamResult` aufnehmen (Portal-`Team` optional nachträglich anlegen).
- **Konflikt-Regel:** Am Event-Tag ist die **Software führend** (sie hat den tatsächlichen
  Durchführungsstand). Das Portal übernimmt beim Rück-Import die Software-Sicht.

> Diese Round-Trip-Mechanik (Portal-Sonderstruktur → Software editierbar → Sonderergebnis → Portal)
> ist bewusst **generisch** gehalten und damit die Blaupause für künftige Sonderauswertungen.

---

## 6. Wertungslogik

**Software-Seite** (neues `web_app/team_challenge_scoring.py`, pure, unit-getestet — Muster wie
`skbs_sm_qualification.py`):

```
Eingabe:  event["teams"], die 4 Läufe (recalc_and_store → fehler_total/zeit_total pro Eintrag)
Pro Team:
  a = Resultat des Agility-Mitglieds im Agility-Lauf (fehler_total_a, zeit_total_a)
  j = Resultat des Jumping-Mitglieds im Jumping-Lauf (fehler_total_j, zeit_total_j)
  total_faults = fehler_total_a + fehler_total_j
  total_time   = zeit_total_a   + zeit_total_j
Gruppieren nach (kategorie, level)  → 8 Gruppen
Sortieren je Gruppe nach (total_faults, total_time) aufsteigend
Rang 1..n vergeben (unvollständige Teams ans Ende, siehe offene Frage DIS)
```

**Portal-Seite (optional, Zweit-Validierung):** derselbe Algorithmus auf den importierten
`Result`-Zeilen — nice-to-have, nicht blockierend.

---

## 7. Portal-UI

- **Admin:** neuer Blueprint `app/blueprints/admin/routes_team_challenge.py`
  (Muster: `routes_cups.py`, Guard `_require_admin_key`):
  - `/config` — Teams verwalten: 2 Registrations wählen (gefiltert auf gleiche Grösse + passende
    Klasse), Rolle Agility/Jumping zuweisen, Level ableiten, Teamname. Validierung §3.1.
  - `/dashboard` — Übersicht der 8 Gruppen + Status (wie viele Teams, wer unvollständig).
  - `/export-csv` — Team-Ranglisten als CSV (Muster `routes_results_export.py`).
- **Public:** `app/blueprints/public/routes_team_challenge.py` → 8 Ranglisten (read-only aus
  `EventTeamResult`), Muster `public/routes_cups.py::standings`.

## 8. Software-UI (Event-Tag)

- Neuer Blueprint `web_app/blueprints/routes_team_challenge.py` + Template
  `team_challenge_dashboard.html` (Muster `skbs_sm_dashboard.html`).
- Button in `manage_runs.html` konditional auf `Veranstaltungsart == "Team-Challenge"`.
- **Team-Verwaltung lokal** (hinzufügen/bearbeiten/löschen, Rollen tauschen).
- **Ring-/Durchführungs-Ansicht:** Der Ring muss die **paarweise, verschränkte** Startfolge
  zeigen (s. §9): „Team X — erst Agility-Mitglied, dann Jumping-Mitglied", damit der Ringoperator
  die zwei Läufe korrekt abwechselnd stoppt.

## 9. Startnummern & Startreihenfolge

Besonderheit: Die zwei Mitglieder starten **direkt nacheinander auf demselben Feld** (ein Mitglied
Agility, dann das andere Jumping). Das bedeutet **verschränkte Startfolge**:
`Team1-Agility → Team1-Jumping → Team2-Agility → Team2-Jumping → …` pro Level.

- **Gemeinsame Team-Startnummer** (oder zwei benachbarte Nummern) → die zwei Läufe teilen sich die
  Team-Reihenfolge.
- `run_order` / Startnummern-Vergabe muss diese Verschränkung je Level erzeugen.
- Technisch bleiben es **zwei getrennte Läufe** (getrennte Wertung/Stoppung) — nur die
  **Ausführungs-Reihenfolge am Feld** ist alternierend.

---

## 10. Offene Fragen (für Rückfrage an LiTyWee)

1. **DIS/Ausfall eines Mitglieds:** Zählt das Team mit dem anderen Lauf weiter (unvollständig,
   ans Ende der Rangliste), oder ist das ganze Team disqualifiziert?
   *Default-Annahme:* Mitglied-DIS → dieser Lauf trägt Sentinel-Fehler (wie intern 999) bei →
   Team sortiert hinter allen vollständigen Teams; zwei DIS schlechter als eines.
2. **„Fehlerpunkte" inkl. Zeitfehler?** Unsere interne `fehler_total` enthält Parcours- **und**
   Zeitfehler. *Default-Annahme: ja* (fehler_total inkl. Zeitfehler), Zeit separat als Tiebreaker.
   Bestätigen lassen.
3. **SCT/Zeitberechnung:** Gilt pro Team-Lauf eine Standardzeit (Soll-Zeit) wie üblich? Vermutlich
   ja (normale Lauf-Berechnung). Falls „reine Zeit ohne SCT-Zeitfehler" gewünscht → Anpassung.
4. **Teamname Pflicht?** (Default: optional.)
5. **Ungerade Teilnehmerzahl** (einer ohne Partner): zugelassen als unvollständiges Team, oder
   Pflicht-Paarung? (Default: nicht zugelassen, Admin muss paaren.)

## 11. Umsetzungsplan (Phasen)

Genug Vorlauf bis 08.01.2027 → eigene Dev-Session(s) werktags, Test am Wochenende
([[dev-test-cadence]]). Reihenfolge: zuerst **Software-Wertung** (Kern), dann **Sync**, zuletzt
**Portal-UI**.

| Phase | Inhalt | Repo |
|---|---|---|
| **P1** | `team_challenge_scoring.py` + Unit-Tests (Kern-Wertung, 8 Gruppen) | Software |
| **P2** | Lokale Team-Verwaltung + Dashboard + manage_runs-Button + `Veranstaltungsart` | Software |
| **P3** | Sync **Portal→Software**: `teams.json` + `runs.json` bauen/importieren | beide |
| **P4** | Sync **Software→Portal**: `team_results.json` + `EventTeamResult` + Import | beide |
| **P5** | Portal-UI: `Team`-Model + Migration + Admin-Config + Validierung | Portal |
| **P6** | Portal: 4 EventRuns (`team_level`) + Zeitplan/Richter + Public-Ranglisten + CSV | Portal |
| **P7** | Startnummern/verschränkte Startfolge + Ring-Ansicht | beide |
| **P8** | Gemeinsamer Realtest (Testdaten-Set, Portal↔Software Round-Trip) | beide |

**Schema-Doku:** Bei jeder Sync-Änderung [[exchange-schema-portal-software]] + `EVENTEXPORT_IMPORT.md`
aktualisieren (beide Repos, additiv, Datei-Existenz zur Laufzeit geprüft).

---

## 12. Kurz-Antwort an den Veranstalter (Entwurf)

> Ja, das Format lässt sich mit dem Programm umsetzen — das Prinzip (zwei getrennt gewertete
> Läufe pro Team, Teamergebnis = Summe Fehler + Summe Zeiten, Rangliste je Grösse und Level)
> passt gut. Die **Teams erfasst ihr nicht im Anmelde-CSV**, sondern ich lege sie als Paarungen
> im Portal an (je 2 bereits angemeldete Starter derselben Grösse, einer Agility / einer Jumping);
> am Turniertag sind die Teams in der Software noch anpassbar.
> Zur Feinabstimmung hätte ich ein paar Rückfragen (siehe §10): v.a. was passiert bei einer
> Disqualifikation eines Mitglieds, und ob die „Fehlerpunkte" die Zeitfehler einschliessen.
