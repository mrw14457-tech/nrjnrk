# -*- coding: utf-8 -*-
"""
أدوات التشفير للبيانات الحساسة (كلمة مرور SMTP)
المصمم: عمرو
"""
from cryptography.fernet import Fernet
from config import get_or_create_encryption_key

_fernet = None


def _get_fernet():
    global _fernet
    if _fernet is None:
        _fernet = Fernet(get_or_create_encryption_key())
    return _fernet


def encrypt(text: str) -> str:
    if not text:
        return ""
    return _get_fernet().encrypt(text.encode("utf-8")).decode("utf-8")


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _get_fernet().decrypt(token.encode("utf-8")).decode("utf-8")
    except Exception:
        return ""
