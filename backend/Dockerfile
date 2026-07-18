# syntax=docker/dockerfile:1

# base: deps + source
FROM python:3.13-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

COPY . .
RUN pip install --upgrade pip && pip install .

RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]

# dev: adds tooling; command comes from the compose override
FROM base AS dev
RUN pip install ".[dev]"
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]

# prod: gunicorn + uvicorn worker (asgi) behind nginx — async endpoints run concurrently
FROM base AS prod
EXPOSE 8000
CMD ["gunicorn", "config.asgi:application", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "4", \
     "--timeout", "60", \
     "--access-logfile", "-", \
     "--error-logfile", "-"]
