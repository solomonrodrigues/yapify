# djangoapp/yapify/settings/production.py
from .base import *

DEBUG = False  # SECURITY WARNING: don't run with debug turned on in production!

if not DEBUG:
    import sentry_sdk
    sentry_sdk.init(
        dsn="https://ffbdad07e6079794aba69ae53083fd0e@o4506320558555136.ingest.us.sentry.io/4509797418336256",
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        send_default_pii=True,
    )

ALLOWED_HOSTS = ['yapify.net',]
CSRF_TRUSTED_ORIGINS = [
    'https://yapify.net',
]

WSGI_APPLICATION = 'djangoapp.yapify.wsgi.application'

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql_psycopg2',
        'NAME': os.environ["PGDATABASE"],
        'USER': os.environ["PGUSER"],
        'PASSWORD': os.environ["PGPASSWORD"],
        'HOST': os.environ["PGHOST"],
        'PORT': os.environ["PGPORT"],
    }
}

EMAIL_BACKEND = "post_office.EmailBackend"

POST_OFFICE = {
    "DEFAULT_PRIORITY": "now",
}

# Mailgun SMTP settings
EMAIL_HOST = "smtp.mailgun.org"
EMAIL_PORT = 587
EMAIL_HOST_USER = "postmaster@YOUR_DOMAIN.mailgun.org"
EMAIL_HOST_PASSWORD = os.environ["MAILGUN_PASSWORD"]
EMAIL_USE_TLS = True

DEFAULT_FROM_EMAIL = "donotreply@yapify-production.up.railway.app"
