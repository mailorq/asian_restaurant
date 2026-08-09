from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0004_operationorder_payment_method")]

    operations = [
        migrations.RemoveConstraint(model_name="snapshotexpectation", name="uniq_snapshot_aggregate"),
        migrations.AddField(
            model_name="snapshotexpectation",
            name="snapshot_run_id",
            field=models.CharField(db_index=True, default="", max_length=64),
            preserve_default=False,
        ),
        migrations.AddConstraint(
            model_name="snapshotexpectation",
            constraint=models.UniqueConstraint(
                fields=["snapshot_run_id", "aggregate_type", "aggregate_id"], name="uniq_snapshot_aggregate"
            ),
        ),
        migrations.CreateModel(
            name="SnapshotRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.CharField(max_length=64, unique=True)),
                ("status", models.CharField(default="started", max_length=12)),
                ("expected_counts", models.JSONField(default=dict)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
            ],
        ),
    ]
