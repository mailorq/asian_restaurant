from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Q

from accounts.models import EMPLOYEE_GROUP
from employee import service


class Command(BaseCommand):
    help = "Emit current authorization state for all operations-capable users (staff + superusers)."

    def handle(self, *args, **options) -> None:
        group = Group.objects.filter(name=EMPLOYEE_GROUP).first()
        criteria = Q(is_superuser=True)
        if group is not None:
            criteria |= Q(groups=group)
        users = get_user_model().objects.filter(criteria).distinct()
        emitted = 0
        with transaction.atomic():
            for user in users.iterator():
                service.emit_authz_state(user)
                emitted += 1
        self.stdout.write(self.style.SUCCESS(f"emitted authz state for {emitted} operations-capable users"))
