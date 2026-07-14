#!/bin/sh
set -eu

mkdir -p /app/data
python manage.py migrate --noinput
python manage.py collectstatic --noinput

exec gunicorn receipt_tracker.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers "${GUNICORN_WORKERS:-2}" \
    --threads "${GUNICORN_THREADS:-4}" \
    --timeout "${GUNICORN_TIMEOUT:-60}" \
    --access-logfile - \
    --error-logfile -
