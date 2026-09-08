import functools

from ninja.errors import HttpError

from accounts.roles import Capability, has_capability, is_staff_member


def is_employee(user) -> bool:
    return is_staff_member(user)


def requires(capability: str):
    """server side capability check; a frontend role flag only controls what is shown"""
    def decorator(view):
        @functools.wraps(view)
        def wrapper(request, *args, **kwargs):
            if not has_capability(request.auth, capability):
                raise HttpError(403, "Недостаточно прав")
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


employee_required = requires(Capability.ORDERS)
inventory_required = requires(Capability.INVENTORY)
customers_required = requires(Capability.CUSTOMERS)


def superuser_required(view):
    @functools.wraps(view)
    def wrapper(request, *args, **kwargs):
        if not getattr(request.auth, "is_superuser", False):
            raise HttpError(403, "Управлять ролями может только суперпользователь")
        return view(request, *args, **kwargs)

    return wrapper
