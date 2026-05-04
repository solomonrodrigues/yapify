# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Yapify is a Django REST Framework backend for a mobile quote-sharing social network. Users can post quotes attributed to their friends, witness/like quotes, and play a guessing game.

**Stack:** Python 3.13, Django 6.0, Django REST Framework, PostgreSQL, JWT authentication

## Local Development (Docker)

```bash
cp .env.example .env  # first time only — fill in real values
docker compose up --build
```

The container runs migrations, builds Tailwind CSS, starts a Tailwind watcher, then launches the Django dev server on `http://localhost:8000`. Tailwind output is written to `djangoapp/static/css/output.css` (gitignored).

Uses `djangoapp.yapify.settings.local` — PostgreSQL via `DATABASE_URL`, no email sending, simple static file storage (no `collectstatic` needed).

## Common Commands

```bash
# Development server (without Docker)
python manage.py runserver

# Database migrations
python manage.py makemigrations
python manage.py migrate

# Create admin user
python manage.py createsuperuser

# Production (via Procfile)
gunicorn djangoapp.yapify.wsgi
```

Note: No test framework is currently configured.

## Architecture

```
djangoapp/
├── yapify/              # Project configuration and core models
│   ├── settings/        # Environment-specific settings (base, development, production)
│   ├── models.py        # Core data models (User, Quote, Group, GroupMembership, etc.)
│   ├── admin.py         # Django admin configuration
│   ├── managers.py      # Custom user manager (email-based auth)
│   ├── choices.py       # ProfileColor, QuoteResponse, ReportReason enums
│   ├── validators.py    # Username validation rules
│   └── urls.py          # Root URL routing
│
└── api/                 # REST API endpoints
    ├── views.py         # APIView classes for all endpoints
    ├── serializers.py   # DRF serializers with computed fields
    ├── urls.py          # API route definitions
    └── utils.py         # Email utilities
```

## Key Domain Concepts

- **User**: Custom auth model with email-based login, display_name, bio, profile_color, streak tracking
- **Group**: A circle of users; quotes belong to a group and are visible only to its members
- **GroupMembership**: Joins users to groups; basis for quote eligibility, visibility, and witnessing
- **GroupInvite**: Pending invitation to join a group; accepted by the recipient via the notifications surface
- **Block**: Per-user block list; suppresses notifications and excludes the blocker/blocked from each other's feeds
- **Quote**: Posted quotes with text, context, author, and a quoted_user (group member) or quoted_name (non-user). Belongs to a Group.
- **QuoteWitness**: Witnesses verify they saw a quote happen (must be a member of the quote's group)
- **QuoteGuess**: Guessing game tracking with streak mechanics (correct increments, wrong resets, max 3 skips/week)
- **Notification**: 8 types: group_invite, group_invite_accepted, new_quote, quote_witnessed, quote_liked, quote_guessed, you_were_guessed, quote_response

## API Patterns

- JWT authentication via `djangorestframework-simplejwt`
- Pagination: `StandardResultsPagination` (page_size=20, max=100)
- Serializers: Use `MinimalUserSerializer` for nested relationships, `PublicUserSerializer` for privacy-aware responses
- Hidden quotes are excluded from main feed and search endpoints
- API docs available at `/api/schema/redoc/`

## Important Constraints

- Usernames must be lowercase, containing only letters, dots, and underscores
- Users can only quote members of a group they belong to (enforced in model validation)
- Quote visibility is scoped to the quote's group: a quote is visible only to members of that group
- Viewing a user's posted/received quotes requires sharing at least one group with them (or being the user themselves)
- No API versioning - uses minimum app version enforcement via `X-App-Version` header
- Email sending disabled by default (`EMAILS_ENABLED = False` in settings)

## Settings

Three-tier settings structure: `base.py` → `development.py`/`production.py`
- Development: SQLite database, debug toolbar enabled
- Production: PostgreSQL via `DATABASE_URL`, Sentry error tracking, WhiteNoise for static files

## Email Infrastructure

- **Sending:** Mailgun via `django-anymail`. Outbound emails (verification, password reset) send from `donotreply@mail.yapify.net`. Configured via `MAILGUN_API_KEY` env var in Railway.
- **Receiving:** `support@yapify.net` is handled by Cloudflare Email Routing, which forwards inbound mail to `yapifyapp@gmail.com`. There is no mailbox on the server — all support email lands in Gmail.
- **DNS:** Mailgun operates on the `mail.yapify.net` subdomain (SPF, DKIM, MX for sending). Cloudflare Email Routing adds MX records on the root `yapify.net` domain for receiving. They don't conflict.

## Hosting & Deployment

- **Platform:** Railway
- **Database:** Railway-managed PostgreSQL (provisioned as a Railway service, connection string injected as `DATABASE_URL`)
- **CI/CD:** GitHub integration in Railway — pushes to `main` trigger automatic deployments
- **Environment variables:** Managed via the Railway dashboard (not committed to the repo)

Deployments run the `web` process from the Procfile, which automatically runs migrations and collects static files before starting the server:

```
web: python3 manage.py migrate && python3 manage.py collectstatic --no-input && gunicorn djangoapp.yapify.wsgi
worker: python3 manage.py qcluster
```

**The `worker` process must be started manually in Railway.** Railway only starts the `web` process automatically. To run the Django Q2 notification worker, add a second service in the Railway dashboard pointing to the same repo with start command `python3 manage.py qcluster`. Without it, events are enqueued but never processed — no notifications or push alerts will be sent.

## Push Notifications Status

| Platform | Status |
|---|---|
| iOS | Implementation complete. Requires end-to-end testing on a real device via an EAS development or production build. |
| Android | Code wired up but **not functional** — Firebase not yet configured. |

**Android setup required before push works on Android:**
1. Create a Firebase project, register the Android app, download `google-services.json`
2. Add `google-services.json` to the `yapify-app` project
3. Configure FCM v1 credentials in the EAS dashboard (expo.dev → project → credentials)
4. Build with EAS: `eas build --platform android`

Push notifications are not testable in Expo Go on Android (SDK 53+) — a development build is required.
