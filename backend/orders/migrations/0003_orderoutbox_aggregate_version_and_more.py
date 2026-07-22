import uuid

from django.db import migrations, models


def _backfill_event_id(apps, schema_editor):
    outbox = apps.get_model("orders", "OrderOutbox")
    for row in outbox.objects.all().iterator():
        outbox.objects.filter(pk=row.pk).update(event_id=uuid.uuid4())


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_geocodecache_deliveryaddress_order_orderitem_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='orderoutbox',
            name='aggregate_version',
            field=models.PositiveIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='correlation_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='routing_key',
            field=models.CharField(default='order.created', max_length=64),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='schema_version',
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='event_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, null=True),
        ),
        migrations.RunPython(_backfill_event_id, migrations.RunPython.noop),
        migrations.AlterField(
            model_name='orderoutbox',
            name='event_id',
            field=models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
        ),
    ]
