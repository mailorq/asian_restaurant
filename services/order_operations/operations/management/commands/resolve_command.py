"""
operator closure of a command whose delivery never resolved

deliberately not exposed over the employee API: closing such a command asserts what happened in
the storefront, which no employee request can prove, so it stays behind shell access and audit
"""

import uuid

from django.core.management.base import BaseCommand, CommandError

from operations.commands import MANUAL_OUTCOMES, CommandNotResolvable, resolve_manually
from operations.models import OperationCommand


class Command(BaseCommand):
    help = "Closes a timed_out or dispatch_failed command on the verdict of an operator who checked the order."

    def add_arguments(self, parser) -> None:
        parser.add_argument("command_id")
        parser.add_argument("--outcome", required=True, choices=sorted(MANUAL_OUTCOMES))
        parser.add_argument("--operator", required=True, help="who is taking the decision")
        parser.add_argument("--reason", required=True, help="what was checked in the storefront")

    def handle(self, *args, **options) -> None:
        try:
            command_id = uuid.UUID(options["command_id"])
        except (AttributeError, ValueError) as exc:
            raise CommandError(f"{options['command_id']} is not a command id") from exc
        command = OperationCommand.objects.filter(command_id=command_id).first()
        if command is None:
            raise CommandError(f"no command {command_id}")
        try:
            resolved = resolve_manually(
                command, outcome=options["outcome"],
                operator=options["operator"], reason=options["reason"],
            )
        except (CommandNotResolvable, ValueError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"{resolved.command_id} -> {resolved.status}"))
