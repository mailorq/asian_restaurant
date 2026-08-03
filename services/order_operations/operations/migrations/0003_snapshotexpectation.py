from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("operations", "0002_projection_versioning")]

    operations = [
        migrations.CreateModel(
            name="SnapshotExpectation",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("aggregate_type", models.CharField(max_length=16)),
                ("aggregate_id", models.CharField(max_length=64)),
                ("aggregate_version", models.PositiveIntegerField(default=0)),
                ("payload", models.JSONField(default=dict)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="snapshotexpectation",
            constraint=models.UniqueConstraint(
                fields=["aggregate_type", "aggregate_id"], name="uniq_snapshot_aggregate"
            ),
        ),
    ]
