# -*- coding: utf-8 -*-
"""
محرك المراقبة والمجدول (Scheduler)
- يفحص المهلة يومياً
- يرسل تذكيرات دورية
- ينفّذ الوصية عند انتهاء المهلة
المصمم: عمرو
"""
import datetime

from apscheduler.schedulers.background import BackgroundScheduler

from models import db, get_settings, log_event, Recipient
from mailer import send_email

_scheduler = None


def _now():
    return datetime.datetime.utcnow()


def build_checkin_url(settings):
    from config import Config
    base = (Config.PUBLIC_BASE_URL or "").rstrip("/")
    path = f"/alive/{settings.secret_token}"
    return f"{base}{path}" if base else path


def daily_job(app):
    """المهمة الرئيسية — تُشغّل يومياً (وعند الطلب يدوياً)."""
    with app.app_context():
        settings = get_settings()
        if settings is None:
            return

        if not settings.system_active:
            return

        # لو الوصية نُفّذت بالفعل، لا تكرر
        if settings.will_executed:
            return

        now = _now()

        # ============ 1) هل انتهت المهلة؟ ============
        if settings.is_overdue:
            _execute_will(app, settings)
            return

        # ============ 2) هل حان وقت التذكير؟ ============
        every = max(1, settings.reminder_every_days or 7)
        last_rem = settings.last_reminder_sent
        should_remind = False
        if last_rem is None:
            should_remind = True
        elif (now - last_rem).days >= every:
            should_remind = True

        if should_remind and settings.owner_email:
            _send_reminder(app, settings)


def _send_reminder(app, settings):
    """إرسال رابط 'أنا بخير' إلى بريد المالك."""
    link = build_checkin_url(settings)
    name = settings.owner_name or "صديقي"
    days_left = settings.days_remaining
    body = (
        f"مرحباً {name},\n\n"
        f"هذا تذكير دوري لتأكيد أنك بخير.\n"
        f"اضغط على الرابط التالي لإعادة ضبط المؤقّت:\n\n"
        f"{link}\n\n"
        f"المهلة المتبقية حالياً: {days_left} يوم.\n"
        f"إذا لم تضغط الرابط قبل انتهاء المهلة، سيتم تنفيذ الإجراء المحدّد مسبقاً تلقائياً.\n"
    )
    ok, err = send_email(settings, settings.owner_email,
                         "تأكيد النشاط — اضغط لتأكيد أنك بخير", body)
    if ok:
        settings.last_reminder_sent = _now()
        db.session.commit()
        log_event("reminder", f"تم إرسال تذكير إلى {settings.owner_email}")
    else:
        log_event("error", f"فشل إرسال التذكير: {err}")


def _execute_will(app, settings):
    """تنفيذ الوصية — إرسال الرسالة النهائية لكل المستلمين."""
    recipients = Recipient.query.filter_by(active=True).all()
    if not recipients:
        log_event("error", "انتهت المهلة لكن لا يوجد مستلمون مُفعّلون.")
        # نعتبرها منفذة حتى لا تتكرر المحاولات بلا فائدة؟ لا — نتركها ليتم التنبيه.
        return

    subject = settings.final_subject or "رسالة مهمة"
    base_msg = settings.final_message or ""
    if settings.video_url:
        base_msg = base_msg + f"\n\nرابط الفيديو:\n{settings.video_url}"

    success, failed = 0, 0
    for r in recipients:
        greeting = f"مرحباً {r.name}،\n\n" if r.name else ""
        body = greeting + base_msg
        ok, err = send_email(settings, r.email, subject, body)
        if ok:
            success += 1
            log_event("execute", f"تم إرسال الوصية إلى {r.email}")
        else:
            failed += 1
            log_event("error", f"فشل الإرسال إلى {r.email}: {err}")

    settings.will_executed = True
    settings.executed_at = _now()
    db.session.commit()
    log_event("execute",
              f"تم تنفيذ الوصية. نجاح: {success} / فشل: {failed}")


def run_now(app):
    """تشغيل المهمة يدوياً (لأزرار الاختبار)."""
    daily_job(app)


def start_scheduler(app):
    """تشغيل المجدول في الخلفية."""
    global _scheduler
    if _scheduler and _scheduler.running:
        return _scheduler

    from config import Config
    _scheduler = BackgroundScheduler(timezone=Config.TIMEZONE)

    # يعمل كل ساعة للتأكد من عدم تفويت أي فحص، والمنطق داخلياً يمنع التكرار
    _scheduler.add_job(
        func=lambda: daily_job(app),
        trigger="interval",
        hours=1,
        id="dead_man_switch_check",
        replace_existing=True,
        max_instances=1,
    )
    _scheduler.start()
    return _scheduler
