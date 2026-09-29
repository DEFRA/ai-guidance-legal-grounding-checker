"""Pluggable mailer — SMTP when MAIL_URL is set, otherwise a job-local log."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from urllib.parse import unquote, urlparse

from .settings import Settings
from .store import Job

log = logging.getLogger(__name__)


class Mailer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def send(self, job: Job, *, subject: str, body: str) -> None:
        status = job.read_status()
        if status.get("email_sent_at"):
            return
        email = str(job.read_meta().get("email") or "")
        if not email:
            job.write_status(email_sent_at=job.read_status().get("updated_at"))
            return
        if self.settings.mail_url:
            self._smtp(email, subject, body)
        else:
            log.warning("MAIL_URL unset; writing mail to %s/mail.log", job.root)
            (job.root / "mail.log").write_text(
                f"To: {email}\nSubject: {subject}\n\n{body}\n"
            )
        job.write_status(email_sent_at=job.read_status()["updated_at"])

    def _smtp(self, to: str, subject: str, body: str) -> None:
        parsed = urlparse(self.settings.mail_url or "")
        host = parsed.hostname or "localhost"
        implicit_tls = parsed.scheme == "smtps" or parsed.port == 465
        port = parsed.port or (465 if implicit_tls else 587)
        user = unquote(parsed.username) if parsed.username else ""
        password = unquote(parsed.password) if parsed.password else ""
        msg = EmailMessage()
        msg["From"] = self.settings.mail_from
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        factory = smtplib.SMTP_SSL if implicit_tls else smtplib.SMTP
        with factory(host, port, timeout=20) as smtp:
            smtp.ehlo()
            if not implicit_tls and smtp.has_extn("starttls"):
                smtp.starttls()
                smtp.ehlo()
            if user:
                smtp.login(user, password)
            smtp.send_message(msg)


def job_mail(job: Job, settings: Settings) -> tuple[str, str]:
    status = job.read_status().get("status")
    url = f"{settings.grf_public_base_url.rstrip('/')}/jobs/{job.id}"
    cat = job.read_meta().get("category") or "category"
    if status == "done":
        return (
            f"Guidance relevance filter ready: {cat}",
            f"Your relevance-filter run for {cat!r} finished.\n\n"
            f"Open: {url}\n"
            f"Zip: {url}/download.zip\n"
            f"Spreadsheet: {url}/pages.xlsx\n",
        )
    if status == "blocked_cap":
        return (
            f"Guidance relevance filter blocked: {cat}",
            f"The run for {cat!r} was not sent to the model because it exceeded "
            f"the page cap.\n\nDetails: {url}\n",
        )
    err = job.read_status().get("error") or "unknown error"
    return (
        f"Guidance relevance filter failed: {cat}",
        f"The run for {cat!r} failed: {err}\n\nDetails: {url}\n",
    )
