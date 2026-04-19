"""
E-Mail-Dienst für AgilityPortal.

Funktionen:
  send_registration_confirmation(registration)
      Sendet die dreisprachige Bestätigungsmail an den Hundeführer.

  send_bulk_email(event, subject, body_text, registrations, app)
      Versendet eine Mail an alle übergebenen Anmeldungen (1 Mail/Sekunde,
      läuft in einem Hintergrund-Thread). Gibt eine Callback-Funktion zurück,
      mit der der Fortschritt abgefragt werden kann.
"""

import threading
import time
import logging

from flask import render_template, current_app
from flask_mail import Message

from app.extensions import mail

log = logging.getLogger(__name__)


# ── Bestätigungsmail ─────────────────────────────────────────────────────────

def send_registration_confirmation(registration) -> None:
    """
    Sendet die dreisprachige Anmeldebestätigung an den Hundeführer.
    Wird direkt nach dem Anlegen einer Anmeldung (Status PENDING) aufgerufen.
    Fehler werden geloggt, aber nie an den Aufrufer weitergereicht.
    """
    try:
        if not current_app.config.get("MAIL_SERVER"):
            log.warning("send_registration_confirmation: MAIL_SERVER nicht konfiguriert.")
            return

        event   = registration.event
        handler = registration.handler
        dog     = registration.dog

        if not handler or not handler.email:
            log.info("send_registration_confirmation: Kein Empfänger für Registrierung %s", registration.id)
            return

        handler_name = f"{handler.first_name} {handler.last_name}".strip() or handler.email
        dog_name     = dog.name if dog else "—"
        category     = registration.category_code or "—"
        class_level  = registration.class_level or "—"

        html_body = render_template(
            "email/registration_confirmation.html",
            event=event,
            handler_name=handler_name,
            dog_name=dog_name,
            category=category,
            class_level=class_level,
        )

        # Reply-To = Klub des Veranstalters (falls vorhanden)
        reply_to = None
        if event.organiser_club and event.organiser_club.email:
            reply_to = event.organiser_club.email

        msg = Message(
            subject=f"Anmeldung / Inscription / Registration – {event.name}",
            recipients=[handler.email],
            html=html_body,
            reply_to=reply_to,
        )
        mail.send(msg)
        log.info("Bestätigungsmail gesendet an %s (Reg %s)", handler.email, registration.id)

    except Exception as exc:
        log.warning("send_registration_confirmation fehlgeschlagen: %s", exc)


# ── Sammelmail ───────────────────────────────────────────────────────────────

class BulkEmailJob:
    """Hält den Status eines laufenden Sammelmail-Versands."""

    def __init__(self, total: int):
        self.total   = total
        self.sent    = 0
        self.failed  = 0
        self.done    = False
        self._lock   = threading.Lock()

    def record_sent(self):
        with self._lock:
            self.sent += 1

    def record_failed(self):
        with self._lock:
            self.failed += 1

    def finish(self):
        with self._lock:
            self.done = True

    @property
    def status(self) -> dict:
        with self._lock:
            return {
                "total":  self.total,
                "sent":   self.sent,
                "failed": self.failed,
                "done":   self.done,
            }


def send_bulk_email(event, subject: str, body_text: str,
                    registrations: list, app) -> BulkEmailJob:
    """
    Startet den Versand einer Sammelmail in einem Hintergrund-Thread.
    - 1 Sekunde Pause zwischen den Mails (SMTP-Schutz)
    - Reply-To = Club-E-Mail des Veranstalters
    - Gibt ein BulkEmailJob-Objekt zurück, über das der Fortschritt abgefragt wird.
    """
    job = BulkEmailJob(total=len(registrations))

    # Reply-To ermitteln
    reply_to = None
    if event.organiser_club and event.organiser_club.email:
        reply_to = event.organiser_club.email

    # Empfänger-Liste aufbauen (dedupliziert nach E-Mail-Adresse)
    recipients = []
    seen_emails: set = set()
    for reg in registrations:
        handler = reg.handler
        if handler and handler.email and handler.email not in seen_emails:
            seen_emails.add(handler.email)
            recipients.append({
                "email": handler.email,
                "name":  f"{handler.first_name} {handler.last_name}".strip(),
            })

    job.total = len(recipients)  # echte Empfänger (dedupliziert)

    def _worker():
        with app.app_context():
            # HTML-Body einmalig rendern
            try:
                html_body = render_template(
                    "email/bulk_message.html",
                    event=event,
                    body=body_text,
                )
            except Exception as exc:
                log.error("bulk_email: Template-Fehler: %s", exc)
                job.finish()
                return

            for i, recipient in enumerate(recipients):
                try:
                    msg = Message(
                        subject=subject,
                        recipients=[recipient["email"]],
                        html=html_body,
                        reply_to=reply_to,
                    )
                    mail.send(msg)
                    job.record_sent()
                    log.info("Bulk-Mail %d/%d → %s", i + 1, len(recipients), recipient["email"])
                except Exception as exc:
                    job.record_failed()
                    log.warning("Bulk-Mail fehlgeschlagen → %s: %s", recipient["email"], exc)

                # 1 Sekunde Pause — ausser nach der letzten Mail
                if i < len(recipients) - 1:
                    time.sleep(1)

            job.finish()
            log.info("Bulk-Mail Versand abgeschlossen: %d gesendet, %d fehlgeschlagen",
                     job.sent, job.failed)

    thread = threading.Thread(target=_worker, daemon=True)
    thread.start()
    return job
