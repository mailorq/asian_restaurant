from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from accounts import service as accounts_service
from accounts.models import User

_PROFILE_FIELDS = {"first_name", "phone"}


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Contact", {"fields": ("phone", "customer_version")}),)
    list_display = ("username", "phone", "email", "is_staff")
    search_fields = ("username", "phone", "email")
    readonly_fields = ("customer_version",)

    def save_model(self, request, obj, form, change):
        # name/phone are customer-projection source fields: route changes through the
        # single writer so customer_version bump + outbox event happen atomically
        changed = _PROFILE_FIELDS & set(form.changed_data)
        if change and changed:
            db = User.objects.get(pk=obj.pk)
            new_name, new_phone = obj.first_name, obj.phone
            obj.first_name, obj.phone = db.first_name, db.phone
            super().save_model(request, obj, form, change)
            accounts_service.set_customer_profile(obj.pk, name=new_name, phone=new_phone)
            obj.refresh_from_db()
            return
        super().save_model(request, obj, form, change)
        if not change:
            # a new customer must reach operations as a live event, not only via bootstrap
            accounts_service.emit_state(obj)

    def has_delete_permission(self, request, obj=None):
        # hard delete would leave an obsolete projection with no deletion event; deactivate instead
        return False
