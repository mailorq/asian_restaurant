from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ops', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='restaurantorder',
            name='address',
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name='restaurantorder',
            name='address_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='restaurantorder',
            name='recipient_name',
            field=models.CharField(blank=True, max_length=150),
        ),
    ]
