# djangoapp/yapify/settings/base.py
import os
from pathlib import Path
from datetime import timedelta

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "unsafe-secret-key-for-dev")
DEBUG = False

INSTALLED_APPS = [  # Django apps
    'unfold',
    'unfold.contrib.filters',
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
]
INSTALLED_APPS += [  # Third party apps
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'corsheaders',  # for mobile app CORS
    'drf_spectacular',
    'post_office',
    'anymail',
]
INSTALLED_APPS += [  # Custom apps
    'djangoapp.api',
    'djangoapp.yapify',
    'djangoapp.notifications',
    'django_q',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',
]

ROOT_URLCONF = 'djangoapp.yapify.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [os.path.join(BASE_DIR, 'templates')],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

# Password validation
# https://docs.djangoproject.com/en/5.2/ref/settings/#auth-password-validators
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]


# Internationalization
# https://docs.djangoproject.com/en/5.2/topics/i18n/
LANGUAGE_CODE = 'en-us'

TIME_ZONE = 'UTC'

USE_I18N = True

USE_TZ = True


# Static files (CSS, JavaScript, Images)
# https://docs.djangoproject.com/en/5.2/howto/static-files/
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'staticfiles')
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

# Default primary key field type
# https://docs.djangoproject.com/en/5.2/ref/settings/#default-auto-field
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

AUTH_USER_MODEL = 'yapify.User'

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '20/min',
        'user': '100/min',
        'auth': '5/min',
    },
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# rest_framework_simplejwt ships with sane defaults, however specifying audience and issuer is useful to prevent
# cross-environment auth artifacts during testing. Also extending token lifetimes due to low risk.
SIMPLE_JWT = {
    "SIGNING_KEY": SECRET_KEY,
    # distinct per env:
    "AUDIENCE": os.environ.get("SIMPLE_JWT_AUDIENCE", 'yapify-dev'),
    "ISSUER": os.environ.get("SIMPLE_JWT_ISSUER", 'http://localhost:8000'),

    # increased token lifetimes
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=15),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=90),  # require re-auth after 90 days inactivity

    "ROTATE_REFRESH_TOKENS": True,  # issue a brand-new refresh token on each refresh
    "BLACKLIST_AFTER_ROTATION": True,  # immediately revoke the old refresh token
}

# Allow all origins during development (NOT for production)
# ToDo: Handle cors allowed origins for production
CORS_ALLOW_ALL_ORIGINS = True

# By default, send via Post Office
EMAILS_ENABLED = False
EMAIL_BACKEND = "post_office.EmailBackend"
POST_OFFICE = {
    "DEFAULT_PRIORITY": "medium",  # Default to queued
}

DEFAULT_FROM_EMAIL = "noreply@example.com"

# drf-spectacular ships with sane default settings that should work reasonably well out of the box.
# It is not necessary to specify any settings, but it's recommended to specify at least some metadata.
SPECTACULAR_SETTINGS = {
    'TITLE': 'Yapify API',
    'DESCRIPTION': 'An app to share quotes that your friends have said.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': True,
    'SERVE_PERMISSIONS': [
        'rest_framework.permissions.IsAdminUser',
    ],
    "SERVE_AUTHENTICATION": [
        "rest_framework.authentication.SessionAuthentication"
    ],
}

QUOTE_GUESS_MAX_SKIPS_PER_WEEK = 3
QUOTE_EDIT_WINDOW = timedelta(minutes=15)

PUSH_NOTIFICATIONS_ENABLED = False  # Overridden to True in production
NOTIFICATION_RETENTION_DAYS = 90

Q_CLUSTER = {
    'name': 'yapify',
    'workers': 2,
    'recycle': 500,
    'timeout': 60,
    'retry': 120,
    'save_limit': 250,
    'orm': 'default',
    'catch_up': False,
}

# Django Unfold admin theme
UNFOLD = {
    "SITE_TITLE": "Yapify Admin",
    "SITE_HEADER": "Yapify",
    "DASHBOARD_CALLBACK": "djangoapp.yapify.dashboard.dashboard_callback",
    "SIDEBAR": {
        "navigation": [
            {
                "title": "Users & Auth",
                "items": [
                    {"title": "Users", "link": "/admin/yapify/user/", "icon": "person"},
                    {"title": "Email Verifications", "link": "/admin/yapify/emailverification/", "icon": "mark_email_read"},
                ],
            },
            {
                "title": "Content",
                "items": [
                    {"title": "Quotes", "link": "/admin/yapify/quote/", "icon": "format_quote"},
                    {"title": "Quote Witnesses", "link": "/admin/yapify/quotewitness/", "icon": "visibility"},
                    {"title": "Quote Likes", "link": "/admin/yapify/quotelike/", "icon": "favorite"},
                    {"title": "Quote Guesses", "link": "/admin/yapify/quoteguess/", "icon": "quiz"},
                    {"title": "Saved Quotes", "link": "/admin/yapify/savedquote/", "icon": "bookmark"},
                    {"title": "Hidden Quotes", "link": "/admin/yapify/hiddenquote/", "icon": "visibility_off"},
                ],
            },
            {
                "title": "Social",
                "items": [
                    {"title": "Friendships", "link": "/admin/yapify/friendship/", "icon": "group"},
                    {"title": "Recent Searches", "link": "/admin/yapify/recentsearchitem/", "icon": "search"},
                ],
            },
            {
                "title": "Notifications",
                "items": [
                    {"title": "Notifications", "link": "/admin/notifications/notification/", "icon": "notifications"},
                    {"title": "Events", "link": "/admin/notifications/event/", "icon": "bolt"},
                    {"title": "Device Tokens", "link": "/admin/notifications/devicetoken/", "icon": "smartphone"},
                ],
            },
            {
                "title": "Moderation",
                "items": [
                    {"title": "Reports", "link": "/admin/yapify/report/", "icon": "flag"},
                ],
            },
            {
                "title": "Email",
                "items": [
                    {"title": "Emails", "link": "/admin/post_office/email/", "icon": "mail"},
                    {"title": "Templates", "link": "/admin/post_office/emailtemplate/", "icon": "description"},
                    {"title": "Attachments", "link": "/admin/post_office/attachment/", "icon": "attach_file"},
                    {"title": "Logs", "link": "/admin/post_office/log/", "icon": "receipt_long"},
                ],
            },
        ],
    },
}
