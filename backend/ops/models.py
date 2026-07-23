from django.db import models


class RestaurantOrder(models.Model):
    """
    Ops-side projection of a storefront order, built only from the event bus
    """

    source_order_id = models.PositiveIntegerField(unique=True)
    status = models.CharField(max_length=16)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    phone = models.CharField(max_length=16, blank=True)
    recipient_name = models.CharField(max_length=150, blank=True)
    address = models.CharField(max_length=500, blank=True)
    address_verified = models.BooleanField(default=False)
    items = models.JSONField(default=list)
    last_aggregate_version = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"RestaurantOrder<{self.source_order_id}> ({self.status})"
