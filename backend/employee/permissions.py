import functools

from ninja.errors import HttpError

from accounts.models import EMPLOYEE_GROUP


def is_employee(user) -> bool:
    # is_staff on its own does NOT grant access — only superuser or the group
    return bool(
        getattr(user, "is_superuser", False)
        or user.groups.filter(name=EMPLOYEE_GROUP).exists()
    )


def employee_required(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not is_employee(request.auth):
            raise HttpError(403, "Доступ только для сотрудников ресторана")
        return view(request, *args, **kwargs)

    return wrapper


def superuser_required(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not getattr(request.auth, "is_superuser", False):
            raise HttpError(403, "Управлять ролями может только суперпользователь")
        return view(request, *args, **kwargs)

    return wrapper
