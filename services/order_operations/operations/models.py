import uuid

from django.db import models


class OperationOrder(models.Model):
    source_order_id = models.PositiveIntegerField(unique=True)
    customer_id = models.PositiveIntegerField(db_index=True)
    aggregate_version = models.PositiveIntegerField(default=0)
    status = models.CharField(max_length=16)
    total = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    recipient_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    address = models.CharField(max_length=500, blank=True)
    address_verified = models.BooleanField(default=False)
    payment_method = models.CharField(max_length=8, blank=True)
    source_event_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"OperationOrder<{self.source_order_id}> ({self.status})"


class EmployeeAuthorization(models.Model):
    subject_id = models.PositiveIntegerField(unique=True)
    authz_version = models.PositiveIntegerField(default=0)
    role_active = models.BooleanField(default=False)
    user_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"authz<{self.subject_id}> v{self.authz_version}"


class SnapshotRun(models.Model):
    run_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=12, default="started")
    expected_counts = models.JSONField(default=dict)
    # source boundary the run was taken at; projections newer than this are post-boundary
    as_of = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"run<{self.run_id}> {self.status}"


class SnapshotExpectation(models.Model):
    snapshot_run_id = models.CharField(max_length=64, db_index=True)
    aggregate_type = models.CharField(max_length=16)
    aggregate_id = models.CharField(max_length=64)
    aggregate_version = models.PositiveIntegerField(default=0)
    payload = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["snapshot_run_id", "aggregate_type", "aggregate_id"], name="uniq_snapshot_aggregate"
            ),
        ]

    def __str__(self) -> str:
        return f"snapshot<{self.aggregate_type}:{self.aggregate_id}> v{self.aggregate_version}"


class OperationOrderItem(models.Model):
    order = models.ForeignKey(OperationOrder, on_delete=models.CASCADE, related_name="items")
    product_code = models.CharField(max_length=64)
    name = models.CharField(max_length=255)
    quantity = models.PositiveIntegerField()
    unit_price = models.DecimalField(max_digits=10, decimal_places=2)
    line_total = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self) -> str:
        return f"{self.name} x{self.quantity}"


class CustomerProjection(models.Model):
    source_customer_id = models.PositiveIntegerField(unique=True)
    name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=32, blank=True)
    active_orders_count = models.PositiveIntegerField(default=0)
    aggregate_version = models.PositiveIntegerField(default=0)
    source_event_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Customer<{self.source_customer_id}>"


class InventoryProjection(models.Model):
    # operations owns product_code + name + stock only; price and is_active stay
    # storefront truth and are never presented here as operational state
    product_code = models.CharField(max_length=64, unique=True)
    name = models.CharField(max_length=255, blank=True)
    stock_quantity = models.PositiveIntegerField(default=0)
    aggregate_version = models.PositiveIntegerField(default=0)
    source_event_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"{self.product_code}: {self.stock_quantity}"


class InboxEvent(models.Model):
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=64)
    aggregate_version = models.PositiveIntegerField(default=0)
    received_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.event_type}:{self.event_id}"


class OperationCommand(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"            # created; requested event not yet on the broker
        DISPATCHED = "dispatched", "Dispatched"   # requested event confirmed to the broker
        TIMED_OUT = "timed_out", "Timed out"      # deadline passed, no outcome yet
        DISPATCH_FAILED = "dispatch_failed", "Dispatch failed"  # relay exhausted retries -> DLQ
        SUCCEEDED = "succeeded", "Succeeded"      # storefront applied it (succeeded outcome)
        REJECTED = "rejected", "Rejected"         # storefront refused it (rejected outcome)

    # only an applied outcome is terminal. Under at-least-once transport, neither a missing
    # publisher confirm (dispatch_failed) nor an elapsed deadline (timed_out) proves the
    # storefront did not receive the command, so both stay non-terminal and a late outcome may
    # still finalize the command. They require alert/retry/reconciliation, not a terminal verdict.
    TERMINAL = frozenset({Status.SUCCEEDED, Status.REJECTED})

    command_id = models.UUIDField(unique=True, default=uuid.uuid4)
    command_type = models.CharField(max_length=64)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    # envelope id of the request event, reused on every publish attempt
    request_event_id = models.UUIDField(unique=True)
    # the acting employee, taken only from the verified JWT subject, never the request body
    actor_id = models.PositiveBigIntegerField()
    # client-supplied dedup key; the unique constraint below makes creation idempotent
    idempotency_key = models.CharField(max_length=200)
    target = models.CharField(max_length=64)
    payload = models.JSONField(default=dict)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING, db_index=True)
    result_code = models.CharField(max_length=64, blank=True)
    result_detail = models.TextField(blank=True)
    # a still-open command past this deadline is swept to timed_out
    deadline_at = models.DateTimeField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["actor_id", "command_type", "target", "idempotency_key"],
                name="uniq_operation_command_idempotency",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.command_type}:{self.command_id} ({self.status})"


class OperationsOutbox(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PUBLISHED = "published", "Published"

    event_id = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    correlation_id = models.UUIDField(default=uuid.uuid4, editable=False)
    causation_id = models.UUIDField(null=True, blank=True)
    command = models.OneToOneField(
        "OperationCommand", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="outbox_event",
    )
    producer = models.CharField(max_length=32, default="operations")
    aggregate_id = models.CharField(max_length=64, default="")
    aggregate_version = models.PositiveIntegerField(default=1)
    routing_key = models.CharField(max_length=64)
    event_type = models.CharField(max_length=64)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField()
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True, db_index=True)
    locked_until = models.DateTimeField(null=True, blank=True)
    locked_by = models.CharField(max_length=64, blank=True)
    last_error = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    published_at = models.DateTimeField(null=True, blank=True)

    def __str__(self) -> str:
        return f"{self.event_type}:{self.event_id} ({self.status})"


class OperationAuditLog(models.Model):
    actor_id = models.CharField(max_length=64, blank=True)
    actor_role = models.CharField(max_length=32, blank=True)
    action = models.CharField(max_length=64)
    target = models.CharField(max_length=64, blank=True)
    command_id = models.UUIDField(null=True, blank=True)
    result = models.CharField(max_length=32, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.action} -> {self.target} ({self.result})"
