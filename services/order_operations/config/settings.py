from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("OPERATIONS_SECRET_KEY", default="ops-dev-insecure-change-me")
DEBUG = env.bool("OPERATIONS_DEBUG", default=False)
ALLOWED_HOSTS = env.list("OPERATIONS_ALLOWED_HOSTS", default=["*"])
PRODUCTION = env.bool("OPERATIONS_PRODUCTION", default=False)

if PRODUCTION:
    # refuse to boot production with dev fallbacks that would weaken auth or host checks
    if SECRET_KEY.startswith("ops-dev-insecure"):
        raise ImproperlyConfigured("OPERATIONS_SECRET_KEY must be set (no dev fallback) in production")
    if "*" in ALLOWED_HOSTS:
        raise ImproperlyConfigured("OPERATIONS_ALLOWED_HOSTS must be restricted in production")
    if DEBUG:
        raise ImproperlyConfigured("OPERATIONS_DEBUG must be off in production")

INSTALLED_APPS = ["operations"]

MIDDLEWARE = ["django.middleware.common.CommonMiddleware"]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {},
    }
]

DATABASES = {"default": env.db("OPERATIONS_DATABASE_URL")}

RABBITMQ_URL = env("OPERATIONS_RABBITMQ_URL", default="amqp://guest:guest@rabbitmq:5672/")

# bridge spans vhosts: consumes storefront, publishes operations — distinct creds each side
BRIDGE_CONSUME_URL = env("OPERATIONS_BRIDGE_CONSUME_URL", default=RABBITMQ_URL)
BRIDGE_PUBLISH_URL = env("OPERATIONS_BRIDGE_PUBLISH_URL", default=RABBITMQ_URL)

IDENTITY_JWKS_URL = env("IDENTITY_JWKS_URL", default="")

# consumer exposes its own metrics; the API process cannot see the consumer's counters
METRICS_PORT = env.int("OPERATIONS_METRICS_PORT", default=9101)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
USE_TZ = True
TIME_ZONE = "UTC"
LANGUAGE_CODE = "en-us"
STATIC_URL = "static/"
