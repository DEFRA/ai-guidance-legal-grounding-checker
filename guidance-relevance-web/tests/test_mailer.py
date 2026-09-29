from email.message import EmailMessage

from guidance_relevance_web.mailer import Mailer


class _FakeSMTP:
    last: object | None = None
    advertise_starttls = True

    def __init__(self, host, port, timeout=None):
        self.host = host
        self.port = port
        self.started_tls = False
        self.logged_in = None
        self.sent = None
        self.ehlo_count = 0
        type(self).last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def ehlo(self):
        self.ehlo_count += 1

    def has_extn(self, name):
        return self.advertise_starttls and name.lower() == "starttls"

    def starttls(self):
        self.started_tls = True

    def login(self, user, password):
        self.logged_in = (user, password)

    def send_message(self, msg: EmailMessage):
        self.sent = msg


class _FakeSMTPSSL(_FakeSMTP):
    ssl_last: object | None = None

    def __init__(self, host, port, timeout=None):
        super().__init__(host, port, timeout)
        type(self).ssl_last = self


def _reset_fakes() -> None:
    _FakeSMTP.last = None
    _FakeSMTP.advertise_starttls = True
    _FakeSMTPSSL.ssl_last = None


def test_gmail_587_starttls_and_unquotes_user(settings, monkeypatch):
    _reset_fakes()
    settings.mail_url = "smtp://you%40gmail.com:ab%23cd@smtp.gmail.com:587"
    monkeypatch.setattr("guidance_relevance_web.mailer.smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("guidance_relevance_web.mailer.smtplib.SMTP_SSL", _FakeSMTPSSL)
    Mailer(settings)._smtp("op@example.gov.uk", "subj", "body")
    smtp = _FakeSMTP.last
    assert smtp.host == "smtp.gmail.com"
    assert smtp.port == 587
    assert smtp.started_tls
    assert smtp.ehlo_count == 2
    assert smtp.logged_in == ("you@gmail.com", "ab#cd")
    assert smtp.sent["To"] == "op@example.gov.uk"
    assert _FakeSMTPSSL.ssl_last is None


def test_gmail_465_uses_implicit_tls(settings, monkeypatch):
    _reset_fakes()
    settings.mail_url = "smtps://you%40gmail.com:secret@smtp.gmail.com:465"
    monkeypatch.setattr("guidance_relevance_web.mailer.smtplib.SMTP", _FakeSMTP)
    monkeypatch.setattr("guidance_relevance_web.mailer.smtplib.SMTP_SSL", _FakeSMTPSSL)
    Mailer(settings)._smtp("op@example.gov.uk", "subj", "body")
    smtp = _FakeSMTPSSL.ssl_last
    assert smtp.port == 465
    assert not smtp.started_tls
    assert smtp.logged_in == ("you@gmail.com", "secret")
    assert _FakeSMTP.last is None


def test_mailpit_1025_stays_plaintext(settings, monkeypatch):
    _reset_fakes()
    settings.mail_url = "smtp://localhost:1025"
    _FakeSMTP.advertise_starttls = False
    monkeypatch.setattr("guidance_relevance_web.mailer.smtplib.SMTP", _FakeSMTP)
    Mailer(settings)._smtp("op@example.gov.uk", "subj", "body")
    smtp = _FakeSMTP.last
    assert smtp.port == 1025
    assert not smtp.started_tls
    assert smtp.logged_in is None
