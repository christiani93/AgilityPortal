# AgilityPortal — Offene Punkte

## Titelverteidiger / Cup-System
- [ ] **Konsolidierung der zwei TV-Systeme** — NACH dem BCCS-Wochenende (21.–22.11.2026).
      HCS läuft über das Cup-System (automatisch, `detect_title_defenders`), BCCS-SM über
      das EventFinalist-Register (manuell, `bccs_qualification_service._auto_qualify_title_defenders`).
      Der BCCS-Pfad ist am Wochenende live-kritisch → vorher nicht anfassen. Danach entscheiden:
      konsolidieren oder nur Pflege-UI zusammenführen. Siehe Memory `reference_cup_title_defender_chain`.
- [ ] **HCS 2027:** sobald Event/Saison kommt, läuft `seed-season-events` → legt den Cup
      `halloween_cup/season=2027` automatisch an (`_CUP_SEASON_RULESETS`). Dann schlägt das
      System die 2026er-Sieger als Titelverteidiger vor; resultexport importiert die 2027er.

## Self-Service-Anmeldung testen (ENTSCHEIDUNG offen)
- [ ] Chris wollte mit dem echten „Abendmeeting" (Event 33) eine Test-Anmeldung machen,
      fand aber keinen Button. Grund: `event_view` (`/club/events/<id>/view`) ist für ECHTE
      Turniere bewusst Superadmin-only — normale Konten dürfen sich nur bei `is_test=True`
      anmelden (*„Self-Service noch im Aufbau"*). Test-Konto `test@handler.ch` (users.id 2)
      ist `club_admin` ohne Verein, NICHT Superadmin → 403, kein Button.
      Chris muss zwischen 3 Optionen wählen:
      A) Superadmin-Konto für dieses eine Event anmelden,
      B) Event 33 testweise `is_test=True` setzen (verschwindet dann aus öffentlicher Liste),
      C) Superadmin-Sperre für echte Turniere ganz entfernen (Produktentscheid, nur mit OK).

## Erledigt in Session 2026-11-19/20 (Referenz)
- MySQL-Connection-Reset-Crashes behoben (`d2c3ae9`, deployed): pool_pre_ping + pool_recycle.
- HCS-2026-Titelverteidiger im Cup-System festgesetzt (Prod Cup id 1).
- `seed-season-events` legt Saison-Cups automatisch an (`d53c6a0`, deployed).
- BCCS-2025-Titelverteidiger fürs Wochenende via agilityevents.ch-PDFs re-verifiziert (Events 34/35 korrekt).
- Manuelle Teilnehmererfassung: HF-Name per LIZ-Lookup vorausgefüllt + Verein-Datalist (`af2e6a9`, deployed).
- Teilnehmer-Dashboard: Vergangene Turniere ergänzt (`75c45a1`); „Offene Turniere" filtert jetzt
  nach Datum, nicht nur Status (`69215a3`, deployed).
- TKAMO-Autoload lief bei jedem Öffnen der Edit-Seite und überschrieb manuelle Felder → nur noch
  beim Neuanlegen automatisch (`0fdbb3a`, deployed).
- Events 34/35: Duplikat-Richter (143/144, ohne AIS, am 09.11. falsch angelegt) auf die korrekten
  Records (83 Alejandro Salas/AIS 21905, 109 Elpina Ismael/AIS 22340) umgehängt (event_runs +
  schedule_blocks-Finals + event_judges), Duplikate gelöscht. Reine Prod-Daten-Korrektur.
  Backup: `.claude/backups/events_34_35_judges_before_20261120.json`.
