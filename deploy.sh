#!/bin/sh
# =============================================================================
# deploy.sh  –  AgilityPortal Deploy-Script (FreeBSD / Hostpoint)
# Anpassen: APP_DIR und SUPERVISOR_SERVICE auf den tatsächlichen Wert setzen
# =============================================================================

set -e   # Abbruch bei erstem Fehler

APP_DIR="$HOME/apps/agilityportal"          # <-- Pfad auf dem Server anpassen
VENV="$APP_DIR/.venv"
SUPERVISOR_SERVICE="agilityportal"          # <-- Supervisor-Dienstname anpassen

# ── 1. Ins App-Verzeichnis wechseln ──────────────────────────────────────────
cd "$APP_DIR"

# ── 2. Neusten Code holen ────────────────────────────────────────────────────
echo "[1/4] git pull ..."
git pull

# ── 3. Abhängigkeiten aktualisieren ─────────────────────────────────────────
echo "[2/4] pip install ..."
"$VENV/bin/pip" install -q -r requirements.txt

# ── 4. Datenbank-Migrationen einspielen ─────────────────────────────────────
echo "[3/4] flask db upgrade ..."
"$VENV/bin/flask" --app wsgi db upgrade

# ── 5. Gunicorn-Prozess neu starten ─────────────────────────────────────────
echo "[4/4] supervisorctl restart $SUPERVISOR_SERVICE ..."
supervisorctl restart "$SUPERVISOR_SERVICE"

echo ""
echo "✅  Deploy abgeschlossen."
