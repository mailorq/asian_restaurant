#!/usr/bin/env sh
set -e

if [ "$OPERATIONS_MAKEMIGRATIONS" = "1" ]; then
    echo "[ops-entrypoint] makemigrations"
    python manage.py makemigrations --noinput
fi

# only the deployment step migrates; see backend/entrypoint.sh for why
if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "[ops-entrypoint] migrate"
    python manage.py migrate --noinput
fi

exec "$@"
