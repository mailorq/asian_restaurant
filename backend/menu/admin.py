from django.contrib import admin

from menu.models import Ingredient, Product, StockAdjustment


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "category", "price", "stock_quantity", "is_active", "is_featured")
    list_filter = ("category", "is_active", "is_featured")
    list_editable = ("price", "stock_quantity", "is_active", "is_featured")
    search_fields = ("code", "name", "description")
    filter_horizontal = ("ingredients",)


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    search_fields = ("name",)


@admin.register(StockAdjustment)
class StockAdjustmentAdmin(admin.ModelAdmin):
    list_display = ("product", "old_quantity", "new_quantity", "reason", "staff", "created_at")
    list_filter = ("created_at",)
    search_fields = ("product__code", "product__name", "reason")
    readonly_fields = ("created_at",)
