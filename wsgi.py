# -*- coding: utf-8 -*-
"""
نقطة الدخول لخوادم الإنتاج (PythonAnywhere / gunicorn / Render)
المصمم: عمرو
"""
from app import app as application  # PythonAnywhere يبحث عن 'application'

app = application

if __name__ == "__main__":
    application.run()
