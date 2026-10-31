"""SMTP delivery with a plain-text alternative and a responsive branded email."""

import os
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid
from html import escape

from fastapi import HTTPException


def validate_mail_config():
    if os.getenv("APP_ENV", "development") == "production":
        host = os.getenv("SMTP_HOST", "").strip()
        if not host or host == "mailpit" or not os.getenv("SMTP_FROM", "").strip():
            raise RuntimeError("Production requires real SMTP_HOST and SMTP_FROM; see docs/SMTP.md")
        sender = os.getenv("SMTP_FROM", "").strip()
        if sender.endswith(".local") or "@" not in sender:
            raise RuntimeError("Production requires a real SMTP_FROM address; see docs/SMTP.md")
        if host == "smtp.gmail.com" and not all(os.getenv(field, "").strip() for field in ("SMTP_USERNAME", "SMTP_PASSWORD")):
            raise RuntimeError("Gmail requires SMTP_USERNAME and an app password; see docs/SMTP.md")
        if os.getenv("SMTP_SECURITY", "starttls") not in ("starttls", "ssl"):
            raise RuntimeError("Production SMTP must use starttls or ssl")
        if os.getenv("SECURE_COOKIES", "false").lower() != "true":
            raise RuntimeError("Production requires HTTPS and SECURE_COOKIES=true")


def render_code_email(name: str, code: str, purpose: str):
    heading = {"register": "Добро пожаловать в aikadr", "login": "С возвращением в aikadr", "reset": "Новый пароль — новый вход"}[purpose]
    instruction = {"register": "Подтвердите почту, чтобы открыть свой аккаунт.", "login": "Подтвердите вход в свой аккаунт.", "reset": "Введите код на сайте, чтобы задать новый пароль."}[purpose]
    greeting = f"Привет, {name}!" if name else "Здравствуйте!"
    plain = f"{greeting}\n{heading}\n{instruction}\n\nВаш код: {code}\n\nКод действует 10 минут и может быть использован один раз. Никому его не сообщайте. Если это были не вы, просто проигнорируйте письмо."
    html = f'''<!doctype html><html lang="ru"><head><meta name="viewport" content="width=device-width, initial-scale=1"></head>
<body style="margin:0;background:#071925;font-family:Arial,sans-serif;color:#edf3f5">
<div style="display:none;max-height:0;overflow:hidden">Ваш код подтверждения для aikadr. Действует 10 минут.</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#071925;padding:40px 16px"><tr><td align="center">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:#0d2636;border:1px solid #294251;border-radius:24px;overflow:hidden">
<tr><td style="padding:36px 36px 24px;border-top:4px solid #d8b66b"><span style="font-size:32px;font-weight:700;letter-spacing:-1px;color:#d8b66b">ai<span style="color:#f5f7f7">kadr</span></span><p style="font-size:11px;letter-spacing:3px;color:#a8bdc7">ИСТОРИИ НОВОГО ВРЕМЕНИ</p></td></tr>
<tr><td style="padding:0 36px 36px"><p style="color:#bdcbd2;font-size:16px">{escape(greeting)}</p><h1 style="font-size:28px;line-height:1.2;font-weight:500;color:#ffffff">{heading}</h1><p style="font-size:16px;line-height:1.6;color:#bdcbd2">{instruction}</p>
<div style="margin:28px 0;padding:24px 12px;text-align:center;background:#071925;border:1px solid #8b754e;border-radius:14px"><span style="font-family:Consolas,monospace;font-size:38px;font-weight:bold;letter-spacing:8px;color:#f0d594">{escape(code)}</span></div>
<p style="font-size:14px;line-height:1.6;color:#bdcbd2">Код действует <strong style="color:#fff">10 минут</strong> и подходит только для одного подтверждения. Никому его не сообщайте.</p>
<p style="margin-top:28px;font-size:12px;line-height:1.6;color:#91a8b4">Если вы не запрашивали код, просто проигнорируйте письмо. Ответ на это письмо не требуется.</p></td></tr></table>
<p style="font-size:12px;color:#91a8b4">aikadr · Ваше следующее открытие</p></td></tr></table></body></html>'''
    return heading, plain, html


def send_code_email(email: str, name: str, code: str, purpose: str):
    host = os.getenv("SMTP_HOST", "").strip()
    sender = os.getenv("SMTP_FROM", "").strip()
    security = os.getenv("SMTP_SECURITY", "starttls").lower()
    if not host or not sender:
        raise HTTPException(status_code=503, detail="Отправка писем ещё не настроена. Обратитесь к администрации")
    if security not in ("none", "starttls", "ssl"):
        raise HTTPException(status_code=503, detail="Ошибка настройки почтового сервера")
    subject, plain, html = render_code_email(name, code, purpose)
    message = EmailMessage()
    message["From"] = formataddr((os.getenv("SMTP_FROM_NAME", "aikadr"), sender))
    message["To"] = email
    message["Subject"] = subject
    message["Date"] = formatdate(localtime=False)
    message["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1])
    message.set_content(plain)
    message.add_alternative(html, subtype="html")
    try:
        port = int(os.getenv("SMTP_PORT", "465" if security == "ssl" else "587"))
        smtp_class = smtplib.SMTP_SSL if security == "ssl" else smtplib.SMTP
        options = {"context": ssl.create_default_context()} if security == "ssl" else {}
        with smtp_class(host, port, timeout=12, **options) as smtp:
            if security == "starttls":
                smtp.starttls(context=ssl.create_default_context())
            username = os.getenv("SMTP_USERNAME", "")
            if username:
                smtp.login(username, os.getenv("SMTP_PASSWORD", ""))
            smtp.send_message(message)
    except (OSError, smtplib.SMTPException, ValueError):
        raise HTTPException(status_code=503, detail="Не удалось отправить письмо. Попробуйте позже") from None
