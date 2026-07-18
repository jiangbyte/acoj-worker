import asyncio
import smtplib
import ssl
from email.message import EmailMessage

from app.core.config.settings import settings
from app.core.exceptions.business import BusinessError


async def send_mail(to_email: str, subject: str, body: str) -> None:
    """Send a plain-text email through configured SMTP settings."""
    mail = settings.mail
    if not mail.host or not mail.from_email:
        raise BusinessError("Mail service is not configured")

    message = EmailMessage()
    message["From"] = f"{mail.from_name} <{mail.from_email}>"
    message["To"] = to_email
    message["Subject"] = subject
    message.set_content(body)

    await asyncio.to_thread(_send_sync, message)


def _send_sync(message: EmailMessage) -> None:
    mail = settings.mail
    try:
        if mail.use_tls:
            with smtplib.SMTP(mail.host, mail.port, timeout=mail.timeout_seconds) as smtp:
                smtp.starttls(context=ssl.create_default_context())
                _login(smtp)
                smtp.send_message(message)
        else:
            with smtplib.SMTP(mail.host, mail.port, timeout=mail.timeout_seconds) as smtp:
                _login(smtp)
                smtp.send_message(message)
    except OSError as exc:
        raise BusinessError("Failed to send email") from exc
    except smtplib.SMTPException as exc:
        raise BusinessError("Failed to send email") from exc


def _login(smtp: smtplib.SMTP) -> None:
    mail = settings.mail
    if mail.username:
        smtp.login(mail.username, mail.password)
