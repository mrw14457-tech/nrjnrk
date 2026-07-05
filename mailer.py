# -*- coding: utf-8 -*-
"""
نظام إرسال البريد الإلكتروني
المصمم: عمرو
"""
import smtplib
import ssl
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from crypto_utils import decrypt


def send_email(settings, to_addr, subject, body, owner_name=None):
    """
    إرسال بريد إلكتروني عبر إعدادات SMTP المحفوظة.
    يرجع (True, "") عند النجاح أو (False, "سبب الخطأ").
    """
    host = settings.smtp_host or "smtp.gmail.com"
    port = int(settings.smtp_port or 465)
    sender = settings.email_address
    password = decrypt(settings.email_password_enc)

    if not sender or not password:
        return False, "إعدادات البريد غير مكتملة (البريد/كلمة المرور)."

    display_name = owner_name or settings.owner_name or sender

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((str(display_name), sender))
    msg["To"] = to_addr

    # نسخة نصية بسيطة + نسخة HTML بسيطة
    text_part = MIMEText(body, "plain", "utf-8")
    html_body = _build_html(subject, body)
    html_part = MIMEText(html_body, "html", "utf-8")
    msg.attach(text_part)
    msg.attach(html_part)

    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=30) as server:
                server.login(sender, password)
                server.sendmail(sender, [to_addr], msg.as_string())
        else:
            with smtplib.SMTP(host, port, timeout=30) as server:
                server.starttls(context=context)
                server.login(sender, password)
                server.sendmail(sender, [to_addr], msg.as_string())
        return True, ""
    except Exception as e:
        return False, str(e)


def _build_html(subject, body):
    """تحويل الرسالة النصية إلى HTML بسيط ومنسق (RTL)."""
    safe = (body or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    safe = safe.replace("\n", "<br>")
    return f"""\
<!DOCTYPE html>
<html dir="rtl" lang="ar">
<head><meta charset="utf-8"></head>
<body style="font-family: Tahoma, Arial, sans-serif; background:#f4f6f9; margin:0; padding:24px;">
  <div style="max-width:600px; margin:0 auto; background:#fff; border-radius:12px;
              overflow:hidden; box-shadow:0 4px 20px rgba(0,0,0,.08);">
    <div style="background:#1f2937; color:#fff; padding:20px 24px; font-size:18px; font-weight:bold;">
      {subject}
    </div>
    <div style="padding:24px; color:#374151; line-height:1.9; font-size:15px;">
      {safe}
    </div>
    <div style="padding:14px 24px; background:#f9fafb; color:#9ca3af; font-size:12px;
                border-top:1px solid #eee;">
      رسالة تلقائية
    </div>
  </div>
</body>
</html>"""


def test_connection(settings):
    """اختبار اتصال SMTP فقط (بدون إرسال)."""
    host = settings.smtp_host or "smtp.gmail.com"
    port = int(settings.smtp_port or 465)
    sender = settings.email_address
    password = decrypt(settings.email_password_enc)
    if not sender or not password:
        return False, "إعدادات البريد غير مكتملة."
    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, context=context, timeout=20) as server:
                server.login(sender, password)
        else:
            with smtplib.SMTP(host, port, timeout=20) as server:
                server.starttls(context=context)
                server.login(sender, password)
        return True, "نجح الاتصال بخادم البريد ✅"
    except Exception as e:
        return False, f"فشل الاتصال: {e}"
