from django.contrib.auth.models import Group
from django.db import transaction

from accounts.models import EMPLOYEE_GROUP, EmployeeRoleAudit


@transaction.atomic
def set_employee_role(actor, target, grant: bool):
    group, _ = Group.objects.get_or_create(name=EMPLOYEE_GROUP)
    if grant:
        target.groups.add(group)
        action = EmployeeRoleAudit.Action.GRANT
    else:
        target.groups.remove(group)
        action = EmployeeRoleAudit.Action.REVOKE
    EmployeeRoleAudit.objects.create(actor=actor, target=target, action=action)
    return target
