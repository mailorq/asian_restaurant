import json

from django.core.management.base import BaseCommand

from operations.reconciliation import reconcile


class Command(BaseCommand):
    help = "Compare source snapshots against projections and report discrepancies."

    def handle(self, *args, **options) -> None:
        report = reconcile()
        self.stdout.write(json.dumps(report, ensure_ascii=False, indent=2))
        if report["unexplained"]:
            # non-zero exit lets a staging gate fail the Phase 1C completion check
            raise SystemExit(1)
