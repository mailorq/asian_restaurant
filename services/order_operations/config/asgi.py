import os

from django.conf import settings
from django.core.asgi import get_asgi_application
from prometheus_client import start_http_server

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

application = get_asgi_application()

# the api's counters live only in this process. gunicorn runs a single worker here, so one process holds the port
start_http_server(settings.METRICS_PORT)
