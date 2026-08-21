"""Add EveAioDataSync model."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0008_remove_eveaiolicense_api_key"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EveAioDataSync",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("data_json", models.TextField(default="{}", help_text="JSON object of named data blobs: {ledger: {...}, custom_prices: {...}, ...}")),
                ("app_version", models.CharField(blank=True, default="", max_length=32)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="eveaio_data_sync", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "EVE AIO data sync",
                "verbose_name_plural": "EVE AIO data syncs",
            },
        ),
    ]
