# djangoapp/yapify/settings/production.py
from .base import *

DEBUG = False  # SECURITY WARNING: don't run with debug turned on in production!

# Fail loudly if the secret key is not set in the environment.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]

if not DEBUG:
    import sentry_sdk
    sentry_sdk.init(
        # Add data like request headers and IP for users,
        # see https://docs.sentry.io/platforms/python/data-management/data-collected/ for more info
        dsn=os.environ["SENTRY_DSN"],
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

EMAILS_ENABLED = True
EMAIL_BACKEND = "post_office.EmailBackend"
POST_OFFICE = {
    "DEFAULT_PRIORITY": "now",
    "BACKENDS": {
        "default": "anymail.backends.mailgun.EmailBackend",
    }
}

# Mailgun API settings
ANYMAIL = {
    "MAILGUN_API_KEY": os.environ["MAILGUN_API_KEY"],
    "MAILGUN_SENDER_DOMAIN": 'mail.yapify.net',
}
DEFAULT_FROM_EMAIL = "donotreply@mail.yapify.net"

SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = [
    'https://yapify.net',
]
