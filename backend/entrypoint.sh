#!/usr/bin/env sh
set -e

# fresh multiprocess dir so gunicorn workers export prometheus metrics correctly.
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    rm -rf "$PROMETHEUS_MULTIPROC_DIR"
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
fi

# dev convenience only. generate missing migrations. in prod they are committed.
if [ "$DJANGO_MAKEMIGRATIONS" = "1" ]; then
    echo "[entrypoint] makemigrations"
    python manage.py makemigrations --noinput
fi

echo "[entrypoint] migrate"
python manage.py migrate --noinput

if [ "$DJANGO_COLLECTSTATIC" = "1" ]; then
    echo "[entrypoint] collectstatic"
    python manage.py collectstatic --noinput
fi

exec "$@"
