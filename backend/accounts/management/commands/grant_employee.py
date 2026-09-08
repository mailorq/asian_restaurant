from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from accounts.roles import StaffRole, set_staff_role


class Command(BaseCommand):
    help = "assign or clear a staff role for a user (server access = superuser)."

    def add_arguments(self, parser) -> None:
        parser.add_argument("username", help="username / phone of the target user")
        parser.add_argument("--role", choices=sorted(StaffRole.values), default=None,
                            help="omit to clear every staff role")

    def handle(self, *args, **options) -> None:
        user_model = get_user_model()
        try:
            user = user_model.objects.get(username=options["username"])
        except user_model.DoesNotExist:
            raise CommandError("пользователь не найден") from None
        set_staff_role(actor=None, target=user, role=options["role"])
        held = options["role"] or "none"
        self.stdout.write(self.style.SUCCESS(f"staff role of {user.username} is now {held}"))
