from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin
from django.contrib.auth.models import Group

from accounts import service as accounts_service
from accounts.models import EMPLOYEE_GROUP, User

_PROFILE_FIELDS = {"first_name", "phone"}


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Contact", {"fields": ("phone", "customer_version", "authz_version")}),)
    list_display = ("username", "phone", "email", "is_staff", "is_active")
    search_fields = ("username", "phone", "email")
    readonly_fields = ("customer_version", "authz_version")

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        # the employee role is not editable here; it changes only via employee.service
        if db_field.name == "groups":
            kwargs["queryset"] = Group.objects.exclude(name=EMPLOYEE_GROUP)
        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        # name/phone and is_active are authorization/projection source state: route each
        # change through its service so a version bump + outbox event happen atomically
        changed = set(form.changed_data)
        db = User.objects.get(pk=obj.pk) if change else None
        route_profile = bool(db and (_PROFILE_FIELDS & changed))
        route_active = bool(db and "is_active" in changed)
        new_name, new_phone, new_active = obj.first_name, obj.phone, obj.is_active
        if route_profile:
            obj.first_name, obj.phone = db.first_name, db.phone
        if route_active:
            obj.is_active = db.is_active
        super().save_model(request, obj, form, change)
        if route_profile:
            accounts_service.set_customer_profile(obj.pk, name=new_name, phone=new_phone)
        if route_active:
            from employee import service as employee_service
            employee_service.set_active(actor=request.user, target=obj, active=new_active)
        if route_profile or route_active:
            obj.refresh_from_db()
        if not change:
            accounts_service.emit_state(obj)

    def save_related(self, request, form, formsets, change):
        # restaurant_employee membership only changes via employee.service.set_employee_role;
        # read the pre-save membership from the DB (never instance/self state) and restore it
        user = form.instance
        group, _ = Group.objects.get_or_create(name=EMPLOYEE_GROUP)
        was_member = bool(user.pk) and User.objects.filter(pk=user.pk, groups=group).exists()
        super().save_related(request, form, formsets, change)
        if user.groups.filter(name=EMPLOYEE_GROUP).exists() != was_member:
            (user.groups.add if was_member else user.groups.remove)(group)
            messages.error(request, "Роль сотрудника меняется только через employee API, не в админке")

    def has_delete_permission(self, request, obj=None):
        # hard delete would leave an obsolete projection with no deletion event; deactivate instead
        return False
