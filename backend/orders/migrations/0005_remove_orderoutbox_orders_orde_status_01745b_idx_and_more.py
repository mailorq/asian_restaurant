from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_alter_order_idempotency_key_and_more'),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name='orderoutbox',
            name='orders_orde_status_01745b_idx',
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='last_error',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='locked_by',
            field=models.CharField(blank=True, max_length=64),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='locked_until',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='orderoutbox',
            name='next_attempt_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddIndex(
            model_name='orderoutbox',
            index=models.Index(fields=['status', 'next_attempt_at'], name='orders_orde_status_53c195_idx'),
        ),
    ]
