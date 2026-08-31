# build context is the repository root (needs packages/ and services/)
FROM python:3.13-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app

COPY packages/event_contracts /packages/event_contracts
RUN pip install --upgrade pip && pip install /packages/event_contracts

COPY services/order_operations/pyproject.toml /app/pyproject.toml
COPY services/order_operations/ /app/
RUN pip install -r requirements.txt && pip install --no-deps .

COPY services/order_operations/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]

FROM base AS dev
RUN pip install ".[dev]" && pip install "/packages/event_contracts[dev]"
CMD ["python", "manage.py", "runserver", "0.0.0.0:9000"]

FROM base AS prod
CMD ["gunicorn", "config.asgi:application", "-k", "uvicorn.workers.UvicornWorker", "--bind", "0.0.0.0:9000"]
