from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from employee.service import set_employee_role


class Command(BaseCommand):
    help = "grant or revoke the restaurant_employee role for a user (server access = superuser)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("username", help="username / phone of the target user")
        parser.add_argument("--revoke", action="store_true", help="revoke instead of grant")

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist:
            raise CommandError("пользователь не найден") from None
        set_employee_role(actor=None, target=user, grant=not options["revoke"])
        verb = "revoked" if options["revoke"] else "granted"
        self.stdout.write(self.style.SUCCESS(f"employee role {verb} for {user.username}"))
