import os
import dj_database_url

os.environ.setdefault("DJANGO_SECRET_KEY", "unsafe-secret-key-for-dev-only")

from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]
CSRF_TRUSTED_ORIGINS = [
    "http://localhost:8000",
    "http://127.0.0.1:8000",
]

INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE += [
    "debug_toolbar.middleware.DebugToolbarMiddleware",
]

INTERNAL_IPS = ["127.0.0.1"]

DATABASES = {
    "default": dj_database_url.config(
        env="DATABASE_URL",
        conn_max_age=600,
    )
}

# Use simple storage in development — no collectstatic needed
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

EMAILS_ENABLED = False
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
POST_OFFICE = {
    "DEFAULT_PRIORITY": "now",
}
