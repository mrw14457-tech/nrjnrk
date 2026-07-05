# -*- coding: utf-8 -*-
"""
نظام الوصية الرقمية (Dead Man's Switch)
التطبيق الرئيسي
المصمم: عمرو
"""
import datetime
from functools import wraps

from flask import (Flask, render_template, request, redirect, url_for,
                   session, flash, jsonify)

from config import Config
from models import (db, AppSettings, Recipient, EventLog,
                    get_settings, log_event)
from crypto_utils import encrypt
from mailer import send_email, test_connection
import scheduler as sched


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    db.init_app(app)

    with app.app_context():
        db.create_all()
        _ensure_settings()

    _register_routes(app)

    # تشغيل المجدول في الخلفية
    sched.start_scheduler(app)
    return app


def _ensure_settings():
    """إنشاء سجل الإعدادات إذا لم يوجد."""
    s = db.session.get(AppSettings, 1)
    if s is None:
        s = AppSettings(id=1)
        s.set_password("admin")  # كلمة المرور الافتراضية (يجب تغييرها!)
        s.last_checkin = datetime.datetime.utcnow()
        db.session.add(s)
        db.session.commit()
        log_event("system", "تم تهيئة النظام لأول مرة. كلمة المرور الافتراضية: admin")


# ------------------------------------------------------------------
def _register_routes(app):

    def login_required(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login"))
            return f(*args, **kwargs)
        return wrapper

    # ---------------- تسجيل الدخول ----------------
    @app.route("/login", methods=["GET", "POST"])
    def login():
        settings = get_settings()
        if request.method == "POST":
            pw = request.form.get("password", "")
            if settings and settings.check_password(pw):
                session["logged_in"] = True
                session.permanent = True
                log_event("login", "تسجيل دخول ناجح للوحة التحكم")
                return redirect(url_for("dashboard"))
            else:
                log_event("login", "محاولة دخول فاشلة")
                flash("كلمة المرور غير صحيحة", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    # ---------------- لوحة التحكم ----------------
    @app.route("/")
    @login_required
    def dashboard():
        settings = get_settings()
        recipients = Recipient.query.order_by(Recipient.created_at.desc()).all()
        recent_logs = (EventLog.query
                       .order_by(EventLog.created_at.desc())
                       .limit(8).all())
        return render_template("dashboard.html",
                               s=settings,
                               recipients=recipients,
                               logs=recent_logs,
                               checkin_url=sched.build_checkin_url(settings))

    # ---------------- Check-in (أنا بخير) من اللوحة ----------------
    @app.route("/checkin", methods=["POST"])
    @login_required
    def checkin():
        settings = get_settings()
        settings.last_checkin = datetime.datetime.utcnow()
        # لو كانت الوصية لم تنفذ، نبقيها كما هي؛ الفحص لا يعيد تفعيل وصية منفّذة
        db.session.commit()
        log_event("checkin", "تسجيل حياة يدوي من لوحة التحكم")
        flash("تم تسجيل أنك بخير ✅ وأُعيد ضبط المؤقّت", "success")
        return redirect(url_for("dashboard"))

    # ---------------- رابط التحقق السري (بدون تسجيل دخول) ----------------
    @app.route("/alive/<token>")
    def alive(token):
        settings = get_settings()
        if settings and secrets_equal(token, settings.secret_token):
            settings.last_checkin = datetime.datetime.utcnow()
            db.session.commit()
            log_event("checkin", "تسجيل حياة عبر الرابط السري")
            return render_template("alive.html",
                                   ok=True,
                                   days=settings.deadline_days,
                                   name=settings.owner_name)
        return render_template("alive.html", ok=False), 404

    # ---------------- المستلمون ----------------
    @app.route("/recipients/add", methods=["POST"])
    @login_required
    def add_recipient():
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip()
        if email:
            db.session.add(Recipient(name=name, email=email, active=True))
            db.session.commit()
            log_event("recipient", f"إضافة مستلم: {email}")
            flash("تمت إضافة المستلم", "success")
        else:
            flash("البريد الإلكتروني مطلوب", "error")
        return redirect(url_for("dashboard"))

    @app.route("/recipients/<int:rid>/toggle", methods=["POST"])
    @login_required
    def toggle_recipient(rid):
        r = db.session.get(Recipient, rid)
        if r:
            r.active = not r.active
            db.session.commit()
        return redirect(url_for("dashboard"))

    @app.route("/recipients/<int:rid>/delete", methods=["POST"])
    @login_required
    def delete_recipient(rid):
        r = db.session.get(Recipient, rid)
        if r:
            db.session.delete(r)
            db.session.commit()
            log_event("recipient", f"حذف مستلم: {r.email}")
        return redirect(url_for("dashboard"))

    # ---------------- الإعدادات ----------------
    @app.route("/settings", methods=["GET", "POST"])
    @login_required
    def settings_page():
        settings = get_settings()
        if request.method == "POST":
            f = request.form
            settings.owner_name = f.get("owner_name", "").strip()
            settings.owner_email = f.get("owner_email", "").strip()
            settings.deadline_days = int(f.get("deadline_days") or 60)
            settings.reminder_every_days = int(f.get("reminder_every_days") or 7)

            # البريد SMTP
            settings.smtp_host = f.get("smtp_host", "smtp.gmail.com").strip()
            settings.smtp_port = int(f.get("smtp_port") or 465)
            settings.email_address = f.get("email_address", "").strip()
            new_pw = f.get("email_password", "")
            if new_pw:  # فقط لو أدخل كلمة مرور جديدة
                settings.email_password_enc = encrypt(new_pw)

            # محتوى الوصية
            settings.final_subject = f.get("final_subject", "").strip()
            settings.final_message = f.get("final_message", "")
            settings.video_url = f.get("video_url", "").strip()

            # حالة النظام
            settings.system_active = (f.get("system_active") == "on")

            db.session.commit()
            log_event("settings", "تحديث الإعدادات")
            flash("تم حفظ الإعدادات ✅", "success")
            return redirect(url_for("settings_page"))

        return render_template("settings.html", s=settings)

    # ---------------- تغيير كلمة مرور اللوحة ----------------
    @app.route("/change-password", methods=["POST"])
    @login_required
    def change_password():
        settings = get_settings()
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        if not settings.check_password(current):
            flash("كلمة المرور الحالية غير صحيحة", "error")
        elif len(new) < 4:
            flash("كلمة المرور الجديدة قصيرة جداً", "error")
        else:
            settings.set_password(new)
            db.session.commit()
            log_event("security", "تم تغيير كلمة مرور اللوحة")
            flash("تم تغيير كلمة المرور ✅", "success")
        return redirect(url_for("settings_page"))

    # ---------------- اختبار البريد ----------------
    @app.route("/test-email", methods=["POST"])
    @login_required
    def test_email():
        settings = get_settings()
        ok, msg = test_connection(settings)
        if ok and settings.owner_email:
            send_email(settings, settings.owner_email,
                       "اختبار النظام ✅",
                       "هذه رسالة اختبار من نظام الوصية الرقمية. إذا وصلتك، فالبريد يعمل بنجاح.")
            flash(msg + " — وأُرسلت رسالة اختبار إلى بريدك.", "success")
        elif ok:
            flash(msg, "success")
        else:
            flash(msg, "error")
        return redirect(url_for("settings_page"))

    # ---------------- تشغيل الفحص يدوياً (اختبار المجدول) ----------------
    @app.route("/run-check", methods=["POST"])
    @login_required
    def run_check():
        sched.run_now(app)
        flash("تم تشغيل الفحص يدوياً. راجع السجل للنتيجة.", "success")
        return redirect(url_for("dashboard"))

    # ---------------- تنفيذ فوري (اختبار الوصية) ----------------
    @app.route("/force-execute", methods=["POST"])
    @login_required
    def force_execute():
        settings = get_settings()
        confirm = request.form.get("confirm", "")
        if confirm != "تنفيذ":
            flash("للتأكيد، اكتب كلمة: تنفيذ", "error")
            return redirect(url_for("dashboard"))
        sched._execute_will(app, settings)
        flash("تم تنفيذ الوصية يدوياً. راجع السجل.", "success")
        return redirect(url_for("dashboard"))

    # ---------------- إعادة تفعيل بعد التنفيذ ----------------
    @app.route("/reset-will", methods=["POST"])
    @login_required
    def reset_will():
        settings = get_settings()
        settings.will_executed = False
        settings.executed_at = None
        settings.last_checkin = datetime.datetime.utcnow()
        db.session.commit()
        log_event("system", "إعادة تفعيل الوصية وإعادة ضبط المؤقّت")
        flash("تمت إعادة تفعيل النظام ✅", "success")
        return redirect(url_for("dashboard"))

    # ---------------- السجل الكامل ----------------
    @app.route("/logs")
    @login_required
    def logs_page():
        logs = (EventLog.query.order_by(EventLog.created_at.desc())
                .limit(200).all())
        return render_template("logs.html", logs=logs)

    # ---------------- صفحة صحة النظام (لـ UptimeRobot) ----------------
    @app.route("/health")
    def health():
        return jsonify({"status": "ok",
                        "time": datetime.datetime.utcnow().isoformat()})


def secrets_equal(a, b):
    """مقارنة آمنة لمنع timing attacks."""
    import hmac
    return hmac.compare_digest(str(a), str(b))


app = create_app()
app.permanent_session_lifetime = datetime.timedelta(days=30)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
