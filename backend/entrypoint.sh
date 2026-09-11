#!/usr/bin/env sh
set -e

# fresh multiprocess dir so gunicorn workers export prometheus metrics correctly. emptied in place, it can be a mount point
if [ -n "$PROMETHEUS_MULTIPROC_DIR" ]; then
    mkdir -p "$PROMETHEUS_MULTIPROC_DIR"
    find "$PROMETHEUS_MULTIPROC_DIR" -mindepth 1 -delete
fi

# dev convenience only. generate missing migrations. in prod they are committed.
if [ "$DJANGO_MAKEMIGRATIONS" = "1" ]; then
    echo "[entrypoint] makemigrations"
    python manage.py makemigrations --noinput
fi

# only the deployment step migrates. every image shares this entrypoint, so without the opt-in each of them would race the others on the same database at every rollout
if [ "$RUN_MIGRATIONS" = "1" ]; then
    echo "[entrypoint] migrate"
    python manage.py migrate --noinput
fi

exec "$@"
