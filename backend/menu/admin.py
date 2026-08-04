from django.contrib import admin

from menu import inventory
from menu.models import Ingredient, Product, StockAdjustment


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "price", "stock_quantity", "is_active", "is_featured")
    list_filter = ("category", "is_active", "is_featured")
    list_editable = ("price", "is_active", "is_featured")
    search_fields = ("code", "name", "description")
    filter_horizontal = ("ingredients",)
    readonly_fields = ("version",)

    def save_model(self, request, obj, form, change):
        # stock must not be written directly from admin: route any change through the
        # single writer so version bump + outbox event happen atomically
        if change and "stock_quantity" in form.changed_data:
            new_quantity = obj.stock_quantity
            obj.stock_quantity = Product.objects.get(pk=obj.pk).stock_quantity
            super().save_model(request, obj, form, change)
            inventory.set_stock(obj.pk, new_quantity, reason="admin edit", staff=request.user)
            obj.refresh_from_db()
        else:
            super().save_model(request, obj, form, change)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "old_quantity", "new_quantity", "reason", "staff", "created_at")
    list_filter = ("created_at",)
    search_fields = ("product__code", "product__name", "reason")

    # audit log only: entries are written by the inventory service, never by hand
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
