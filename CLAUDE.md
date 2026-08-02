# AgilityPortal

Online-Plattform für Agility-Veranstaltungen: Anmeldungen, Event-Verwaltung,
Ergebnisveroeffentlichung. Lizenzcheck (TKAMO), Zahlungslogik, Startlisten.

**Stack**: Python/Flask + Gunicorn + Supervisor + Nginx (HostPoint xahizivi).
**URL**: https://portal.z-b.tech
**Server-Pfad**: `~/apps/agilityportal`
**Service-Name**: `agilityportal`
**Deploy**: `git pull && supervisorctl restart agilityportal` (NICHT mit `-c`-Argument,
da AdminPortal-managed Service mit anderer supervisord-Default-Config als
Auftragsverwaltung).

## Schwester-Projekt mit geteiltem Memory

**AgilitySoftware** (`C:\Users\chris\OneDrive\Code\AgilitySoftware\`)
→ Lokale Offline-Anwendung des Agility-Auswertungssystems.

Beide Projekte teilen den Memory-Pool **AgilityAuswertung** (Junction auf
`~\OneDrive\ClaudeSync\projects-memory\AgilityAuswertung\`). Was du in einer
Session lernst, ist in der anderen verfuegbar.

Datenfluss zur AgilitySoftware:
- **Vor Event**: Portal → AgilitySoftware (Event-Paket: Teilnehmer, Startlisten)
- **Waehrend Event**: AgilitySoftware → Portal (Live-Daten, falls Internet)
- **Nach Event**: AgilitySoftware → Portal (Resultate, Ranglisten)

## Verwaltet vom AdminPortal

Reservationen / Backend-Aktionen laufen ueber **AdminPortal**
(`C:\Users\chris\OneDrive\Code\AdminPortal\`, admin.z-b.tech).
Bei Aenderungen die Reservations- oder Bexio-Logik betreffen ggf. dort pruefen.

## Geplante Anbindung

Indirekt: AgilitySoftware soll spaeter als Informationssender fuer VAR-System
(`C:\Users\chris\OneDrive\Code\VAR-System\`) dienen. Schnittstellen-Aenderungen
in AgilitySoftware koennen also auch hier Auswirkungen haben.

## Regulatorisches

Alles unter **TKAMO**-Reglement: https://www.tkamo.ch/de/agility/reglemente.html
Bei neuen Features pruefen ob Reglement betroffen ist.
