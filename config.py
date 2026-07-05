# -*- coding: utf-8 -*-
"""
نظام الوصية الرقمية (Dead Man's Switch)
الإعدادات الأساسية للتطبيق
المصمم: عمرو
"""
import os
from pathlib import Path

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)


class Config:
    # مفتاح الجلسات — يُقرأ من متغير بيئة، وإلا يُولّد ملف محلي
    SECRET_KEY = os.environ.get("SECRET_KEY") or "CHANGE_ME_SECRET_KEY_عمرو_2026"

    # قاعدة البيانات
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL"
    ) or f"sqlite:///{DATA_DIR / 'app.db'}"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # مفتاح التشفير للبيانات الحساسة (كلمات مرور الإيميل)
    # يجب ضبطه في الإنتاج. لو غير موجود، يُقرأ/يُنشأ ملف محلي.
    ENCRYPTION_KEY = os.environ.get("ENCRYPTION_KEY")

    # المنطقة الزمنية للمجدول
    TIMEZONE = os.environ.get("TIMEZONE", "Africa/Cairo")

    # عنوان التطبيق العام (يُستخدم في روابط التحقق بالإيميل)
    # مثال: https://amr.pythonanywhere.com
    PUBLIC_BASE_URL = os.environ.get("PUBLIC_BASE_URL", "")


def get_or_create_encryption_key():
    """جلب مفتاح التشفير أو إنشاء واحد وحفظه محلياً."""
    from cryptography.fernet import Fernet

    key = os.environ.get("ENCRYPTION_KEY")
    if key:
        return key.encode() if isinstance(key, str) else key

    key_file = DATA_DIR / "encryption.key"
    if key_file.exists():
        return key_file.read_bytes()

    new_key = Fernet.generate_key()
    key_file.write_bytes(new_key)
    return new_key
