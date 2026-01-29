# AgilityPortal

## Lokaler Start

```bash
export FLASK_APP=wsgi.py
flask run
```

In der Produktion läuft die App über `wsgi.py` (Hostpoint).

ADMIN-Key (für /admin-Routen):

```bash
export ADMIN_KEY=dev-admin-key
```

## Lokale Datenbank initialisieren

1. Virtuelle Umgebung aktivieren und Abhängigkeiten installieren.
2. Die Anwendung konfigurieren (z. B. `FLASK_APP=wsgi.py`).
3. Migrationen erstellen und anwenden:

```bash
flask db migrate
flask db upgrade
```

Hinweis: Online-Tests folgen später. Aktuell ist nur die lokale Initialisierung vorgesehen.

Beispiel-URLs (lokal):

- http://localhost:5000/admin/tka?key=dev-admin-key
- http://localhost:5000/admin/tka/dev/seed?key=dev-admin-key
- http://localhost:5000/admin/tka/events/1/export?key=dev-admin-key
