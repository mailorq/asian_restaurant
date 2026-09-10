"""
production must not boot on a placeholder-shaped secret

the guards named two historical defaults by hand, so every placeholder the repository shipped
afterwards booted a production stack without complaint. these assert the shape, not a list
"""

import os
import subprocess
import sys

import pytest

BASE = {
    "DJANGO_PRODUCTION": "1",
    "DJANGO_DEBUG": "0",
    "DJANGO_ALLOWED_HOSTS": "app.example.com",
    "DJANGO_SECRET_KEY": "x" * 50,
    "DATABASE_URL": "postgres://u:p@db:5432/s",
    "REDIS_URL": "redis://redis:6379/1",
    "CART_REDIS_URL": "redis://redis:6379/0",
    "RABBITMQ_URL": "amqp://u:p@rabbitmq:5672/storefront",
    "IDENTITY_JWT_KID": "prod-2026-01",
}


def _boots(**overrides) -> bool:
    env = {**os.environ, **BASE, **overrides}
    env.pop("DJANGO_SETTINGS_MODULE", None)
    result = subprocess.run(
        [sys.executable, "-c", "import django, os;"
         "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
         "django.setup()"],
        cwd="/app", env=env, capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


def test_the_baseline_starts():
    assert _boots(), "the test itself must not be the reason a start fails"


# every value the repository has ever shipped as an example, plus the shape they share
@pytest.mark.parametrize("secret", [
    "dev-insecure-change-me",
    "change-me-to-a-50-char-random-string",
    "change-me-anything",
    "CHANGE-ME-UPPERCASE",
    "dev-whatever",
])
def test_a_placeholder_shaped_secret_refuses_to_start(secret):
    assert not _boots(DJANGO_SECRET_KEY=secret), f"production booted on {secret!r}"


@pytest.mark.parametrize("kid", ["dev-1", "dev-local-1", "dev-anything"])
def test_a_development_signing_kid_refuses_to_start(kid):
    assert not _boots(IDENTITY_JWT_KID=kid)
