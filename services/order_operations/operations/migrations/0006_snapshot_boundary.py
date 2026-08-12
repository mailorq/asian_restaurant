from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0005_snapshot_run")]

    operations = [
        migrations.AddField(
            model_name="snapshotrun",
            name="as_of",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="operationorder",
            name="source_event_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="customerprojection",
            name="source_event_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="inventoryprojection",
            name="source_event_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
