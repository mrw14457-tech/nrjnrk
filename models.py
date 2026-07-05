# -*- coding: utf-8 -*-
"""
نماذج قاعدة البيانات لنظام الوصية الرقمية
المصمم: عمرو
"""
import datetime
import secrets

from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


def _now():
    return datetime.datetime.utcnow()


class AppSettings(db.Model):
    """إعدادات النظام العامة (سجل واحد فقط id=1)."""
    __tablename__ = "app_settings"

    id = db.Column(db.Integer, primary_key=True)

    # اسم المالك (لظهوره في الرسائل)
    owner_name = db.Column(db.String(120), default="")

    # كلمة مرور لوحة التحكم (مُشفّرة hash)
    admin_password_hash = db.Column(db.String(255), default="")

    # مدة المهلة بالأيام قبل تنفيذ الوصية
    deadline_days = db.Column(db.Integer, default=60)

    # كل كام يوم يُرسل تذكير "أنا بخير"
    reminder_every_days = db.Column(db.Integer, default=7)

    # آخر check-in (تسجيل حياة)
    last_checkin = db.Column(db.DateTime, default=_now)

    # آخر مرة أُرسل فيها تذكير
    last_reminder_sent = db.Column(db.DateTime, nullable=True)

    # هل نُفّذت الوصية بالفعل؟ (لمنع التكرار)
    will_executed = db.Column(db.Boolean, default=False)

    # وقت تنفيذ الوصية
    executed_at = db.Column(db.DateTime, nullable=True)

    # هل النظام مُفعّل؟ (يمكن إيقافه مؤقتاً)
    system_active = db.Column(db.Boolean, default=True)

    # ----------- إعدادات البريد (SMTP) -----------
    smtp_host = db.Column(db.String(120), default="smtp.gmail.com")
    smtp_port = db.Column(db.Integer, default=465)
    email_address = db.Column(db.String(200), default="")
    email_password_enc = db.Column(db.Text, default="")  # مُشفّرة

    # بريد المالك (يستقبل التذكيرات)
    owner_email = db.Column(db.String(200), default="")

    # ----------- محتوى الوصية -----------
    final_subject = db.Column(db.String(300),
                              default="رسالة مهمة")
    final_message = db.Column(db.Text, default="")
    video_url = db.Column(db.String(500), default="")

    # رابط التحقق السري (توكن عشوائي)
    secret_token = db.Column(db.String(64),
                             default=lambda: secrets.token_urlsafe(24))

    created_at = db.Column(db.DateTime, default=_now)

    # ---------- طرق مساعدة ----------
    def set_password(self, raw):
        self.admin_password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        if not self.admin_password_hash:
            return False
        return check_password_hash(self.admin_password_hash, raw)

    @property
    def deadline_date(self):
        base = self.last_checkin or _now()
        return base + datetime.timedelta(days=self.deadline_days)

    @property
    def days_remaining(self):
        delta = self.deadline_date - _now()
        return delta.days + (1 if delta.seconds > 0 else 0)

    @property
    def is_overdue(self):
        return _now() >= self.deadline_date


class Recipient(db.Model):
    """المستلمون الذين ستصلهم الوصية."""
    __tablename__ = "recipients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), default="")
    email = db.Column(db.String(200), nullable=False)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=_now)


class EventLog(db.Model):
    """سجل الأحداث في النظام."""
    __tablename__ = "event_logs"

    id = db.Column(db.Integer, primary_key=True)
    event_type = db.Column(db.String(60))   # checkin, reminder, execute, login, error...
    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=_now)


def log_event(event_type, message):
    """إضافة حدث للسجل."""
    try:
        entry = EventLog(event_type=event_type, message=message)
        db.session.add(entry)
        db.session.commit()
    except Exception:
        db.session.rollback()


def get_settings():
    """جلب سجل الإعدادات الوحيد (id=1)."""
    s = db.session.get(AppSettings, 1)
    return s
