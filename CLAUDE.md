# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Yapify is a Django REST Framework backend for a mobile quote-sharing social network. Users can post quotes attributed to their friends, witness/like quotes, and play a guessing game.

**Stack:** Python 3.13, Django 6.0, Django REST Framework, PostgreSQL, JWT authentication

## Common Commands

```bash
# Development server
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
│   ├── models.py        # 12 data models (User, Quote, Friendship, etc.)
│   ├── admin.py         # Django admin configuration
│   ├── managers.py      # Custom user manager (email-based auth)
│   ├── choices.py       # ProfileColor, QuoteVisibility enums
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

- **User**: Custom auth model with email-based login, display_name, bio, profile_color, quote_visibility, streak tracking
- **Friendship**: Friend relationships with statuses (pending, accepted, rejected, blocked). Users can only quote their friends.
- **Quote**: Posted quotes with text, context, author, and a quoted_user (friend) or quoted_name (non-user)
- **QuoteWitness**: Witnesses verify they saw a quote happen
- **QuoteGuess**: Guessing game tracking with streak mechanics (correct increments, wrong resets, max 3 skips/week)
- **Notification**: 5 types: friend_request, friend_accepted, new_quote, quote_witnessed, quote_liked

## API Patterns

- JWT authentication via `djangorestframework-simplejwt`
- Pagination: `StandardResultsPagination` (page_size=20, max=100)
- Serializers: Use `MinimalUserSerializer` for nested relationships, `PublicUserSerializer` for privacy-aware responses
- Hidden quotes are excluded from main feed and search endpoints
- API docs available at `/api/schema/redoc/`

## Important Constraints

- Usernames must be lowercase, containing only letters, dots, and underscores
- Users can only quote their friends (enforced in model validation)
- Quote visibility settings control who sees the user when quoted (mutuals only vs friends of friends)
- No API versioning - uses minimum app version enforcement via `X-App-Version` header
- Email sending disabled by default (`EMAILS_ENABLED = False` in settings)

## Settings

Three-tier settings structure: `base.py` → `development.py`/`production.py`
- Development: SQLite database, debug toolbar enabled
- Production: PostgreSQL via `DATABASE_URL`, Sentry error tracking, WhiteNoise for static files
