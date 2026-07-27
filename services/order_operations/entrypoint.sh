#!/usr/bin/env sh
set -e

if [ "$OPERATIONS_MAKEMIGRATIONS" = "1" ]; then
    echo "[ops-entrypoint] makemigrations"
    python manage.py makemigrations --noinput
fi

echo "[ops-entrypoint] migrate"
python manage.py migrate --noinput

exec "$@"
