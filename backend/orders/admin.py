from django.contrib import admin

from orders.models import (
    DeliveryAddress,
    Order,
    OrderItem,
    OrderOutbox,
    OrderStatusHistory,
    ProcessedEvent,
)


@admin.register(OrderOutbox)
class OrderOutboxAdmin(admin.ModelAdmin):
    list_display = ("aggregate_id", "event_type", "status", "attempts", "created_at", "published_at")
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id",)
    readonly_fields = ("created_at", "published_at")


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ("product", "product_name", "unit_price", "quantity", "line_total")
    can_delete = False


class OrderStatusHistoryInline(admin.TabularInline):
    model = OrderStatusHistory
    extra = 0
    readonly_fields = ("from_status", "to_status", "changed_by", "note", "created_at")
    can_delete = False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "status", "payment_method", "total", "created_at")
    list_filter = ("status", "payment_method")
    search_fields = ("id", "phone", "user__username")
    readonly_fields = ("idempotency_key", "source_cart_id", "source_cart_version", "created_at", "updated_at")
    inlines = (OrderItemInline, OrderStatusHistoryInline)


@admin.register(DeliveryAddress)
class DeliveryAddressAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "address", "is_verified", "created_at")
    list_filter = ("is_verified", "provider")
    search_fields = ("address", "user__username")


@admin.register(ProcessedEvent)
class ProcessedEventAdmin(admin.ModelAdmin):
    list_display = ("event_id", "consumer", "processed_at")
    search_fields = ("event_id",)
