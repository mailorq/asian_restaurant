import json

from django.core.management.base import BaseCommand

from operations.reconciliation import reconcile


class Command(BaseCommand):
    help = "Reconcile a completed snapshot run against projections (both directions) and report discrepancies."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--run-id", default=None, help="reconcile a specific run; default is the latest completed")

    def handle(self, *args, **options) -> None:
        report = reconcile(options["run_id"])
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if report["status"] != "ok":
            # non-zero exit lets a staging gate block on anything but a clean, complete run
            raise SystemExit(1)
