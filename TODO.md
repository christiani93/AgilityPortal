# AgilityPortal — Offene Punkte

> Persistente ToDo-Liste fuer dieses Projekt. Wird beim Wechsel ins Projekt von
> Claude gelesen. Bei Aenderungen manuell aktuell halten.

Stand: 2026-05-30

## Crashguard-Rollout

Code (`crashguard.py` im Projekt-Root) ist eingebaut. Server-Aktivierung offen.

- [ ] In `~/apps/agilityportal/.env` ergaenzen:
  ```
  CRASHGUARD_URL=https://admin.z-b.tech
  CRASHGUARD_TOKEN=<token-aus-AdminPortal-Setup>
  ```
- [ ] `supervisorctl restart agilityportal`
- [ ] Verifikation: in Claude-MultiPC unter `🐞 Crashes` sollte ein Test-Crash erscheinen, sobald hier ein Fehler auftritt (oder via `crashguard.report_manual(...)`)

Anleitung: `~/.claude/playbooks/crashguard-deploy.md`

## Aktive Entwicklung (Feature-Stand laut git log)

In aktiver Entwicklung — letzte Commits:
- AOA-Import (auslaendische Lizenzen werden automatisch erkannt)
- Cup-Verwaltung: Vereins-Freigaben, Veranstalter-Einschraenkung, Titelverteidiger-Erkennung
- Qualifikation per Lauf (Halloween Cup)
- Field-Rename `Event.date_from` → `starts_at` (Korrektur)

→ Bei neuen Sessions: pruefen ob WIP-Branch offen ist (`git status` + `git log --oneline -5`).

## Architektur-Notiz

- Wird vom AdminPortal verwaltet (Subdomain portal.z-b.tech, Port 8020)
- Sister-Projekt: AgilitySoftware (Online-Offline-Pair, `_related/AgilitySoftware/` falls Cross-Link gesetzt)
- Folgt TKAMO-Reglemente: https://www.tkamo.ch/de/agility/reglemente.html
- Deploy: `supervisorctl restart agilityportal` (AdminPortal-managed)
