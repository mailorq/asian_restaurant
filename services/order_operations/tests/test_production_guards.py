"""production must not boot on a value the repository ships as an example"""

import os
import subprocess
import sys

import pytest

BASE = {
    "OPERATIONS_PRODUCTION": "1",
    "OPERATIONS_DEBUG": "0",
    "OPERATIONS_ALLOWED_HOSTS": "ops.example.com",
    "OPERATIONS_SECRET_KEY": "y" * 50,
    "OPERATIONS_DATABASE_URL": "postgres://u:p@operations-db:5432/operations",
}


def _boots(**overrides) -> bool:
    env = {**os.environ, **BASE, **overrides}
    result = subprocess.run(
        [sys.executable, "-c", "import django, os;"
         "os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings');"
         "django.setup()"],
        cwd="/app", env=env, capture_output=True, text=True, timeout=60,
    )
    return result.returncode == 0


def test_the_baseline_starts():
    assert _boots()


@pytest.mark.parametrize("secret", [
    "ops-dev-insecure", "change-me-ops-secret", "CHANGE-ME-OPS", "dev-anything",
])
def test_a_placeholder_shaped_secret_refuses_to_start(secret):
    assert not _boots(OPERATIONS_SECRET_KEY=secret), f"production booted on {secret!r}"
