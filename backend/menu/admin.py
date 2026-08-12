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
        # name/stock are projected by operations: route edits through the single writer so
        # a version bump + event happen atomically instead of a silent direct write
        routed = {"name", "stock_quantity"} & set(form.changed_data)
        if change and routed:
            db = Product.objects.get(pk=obj.pk)
            new_name = obj.name if "name" in routed else None
            new_stock = obj.stock_quantity if "stock_quantity" in routed else None
            obj.name, obj.stock_quantity = db.name, db.stock_quantity
            super().save_model(request, obj, form, change)
            inventory.set_product_state(obj.pk, name=new_name, stock=new_stock, reason="admin edit", staff=request.user)
            obj.refresh_from_db()
            return
        super().save_model(request, obj, form, change)
        if not change:
            # a new product must reach operations as a live event, not only via bootstrap
            inventory.emit_state(obj)

    def has_delete_permission(self, request, obj=None):
        # hard delete would leave an obsolete projection with no deletion event; deactivate instead
        return False


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
