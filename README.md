# Yapify: backend

**Catch what your friends say before they deny it.**

Yapify is a private social app for friend groups. Someone says something ridiculous, you post it as a quote attributed to them, and the rest of the group can witness it ("I was there"), react, and play a guessing game: *who said it?*

This repo is the Django REST API behind the iOS app. The app itself lives in [yapify-app](https://github.com/solomonrodrigues/yapify-app).

**Status:** Built through to App Store–ready (accounts, groups, push notifications, moderation, privacy and terms) but not currently live. I'd like to bring it back one day.

## Features

- **Groups.** Quotes live inside private groups. You can only quote, see and witness quotes in groups you belong to.
- **Quotes.** Post a quote with context, attributed to a group member or to someone who isn't on the app.
- **Witnessing and reactions.** Members confirm they were there, like, save or hide quotes, and respond to quotes about themselves.
- **"Who said it?"** A guessing game across your groups' quotes, with streaks: correct guesses extend it, wrong ones reset it, and you get 3 skips a week.
- **Notifications.** In-app and push notifications for invites, new quotes, witnesses, likes and guesses, processed by a background worker.
- **Safety.** Blocking, reporting, hidden quotes, account deletion, email verification and password reset.

## Built with

- **Django 6.0** and **Django REST Framework** on Python 3.13
- **JWT authentication** (`djangorestframework-simplejwt`) with email-based login
- **PostgreSQL**
- **Django Q2** for background jobs (notification fan-out and push delivery)
- **drf-spectacular** for the OpenAPI schema, which the app generates its TypeScript types from
- **Mailgun** (via `django-anymail`) for transactional email
- **Tailwind CSS** for the landing, invite, privacy and terms pages
- **Sentry** for error tracking, **WhiteNoise** for static files

## Design notes

- **Visibility is scoped to groups.** Every quote belongs to a group, and the API only returns quotes from groups you share. Viewing someone's profile quotes requires sharing at least one group with them.
- **No API versioning.** Instead the app sends its version in an `X-App-Version` header, and the API enforces a minimum supported version, telling outdated clients to update. That keeps one API surface while still letting breaking changes ship.
- **Notifications are asynchronous.** Requests enqueue events, and a separate Django Q2 worker turns them into notifications and push messages, so API responses stay fast.

## Project layout

```
djangoapp/
├── yapify/     # Settings, core models (User, Group, Quote, Notification…), admin, landing pages
└── api/        # REST endpoints: views, serializers, URL routes
```

API docs are served at `/api/schema/redoc/` when the server is running.

## Running locally

You'll need Docker.

```bash
cp .env.example .env
docker compose up --build
```

This runs migrations, builds the Tailwind CSS and starts the dev server at http://localhost:8000. Create an admin user with `docker compose exec web python manage.py createsuperuser`.

## Deployment

The API was set up to run on Railway, with a `web` process for the API and a `worker` process for background jobs (see `Procfile`). Hosting, email and push notification setup are documented in [docs/operations.md](docs/operations.md).
