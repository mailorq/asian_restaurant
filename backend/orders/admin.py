from django.contrib import admin

from orders.models import OrderOutbox


@admin.register(OrderOutbox)
class OrderOutboxAdmin(admin.ModelAdmin):
    list_display = ("aggregate_id", "event_type", "status", "attempts", "created_at", "published_at")
    list_filter = ("status", "event_type")
    search_fields = ("aggregate_id",)
    readonly_fields = ("created_at", "published_at")
