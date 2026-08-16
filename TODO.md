# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-08-16

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
