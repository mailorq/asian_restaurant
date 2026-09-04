"""standalone sweep for manual recovery; the relay runs the same service call every cycle"""

from django.core.management.base import BaseCommand

from operations.commands import sweep_expired


class Command(BaseCommand):
    help = "Finalises commands whose deadline has passed: expired before dispatch, or timed out."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--limit", type=int, default=200)

    def handle(self, *args, **options) -> None:
        swept = sweep_expired(limit=options["limit"])
        self.stdout.write(
            self.style.SUCCESS(f"expired {swept['expired']}, timed out {swept['timed_out']}")
        )
