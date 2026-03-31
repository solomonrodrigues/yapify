#!/bin/bash

set -e

echo "Running database migrations..."
python manage.py migrate --noinput

echo "Building Tailwind CSS..."
tailwindcss -i ./djangoapp/static/css/input.css -o ./djangoapp/static/css/output.css

echo "Starting Tailwind CSS watcher..."
tailwindcss -i ./djangoapp/static/css/input.css -o ./djangoapp/static/css/output.css --watch &

exec "$@"
