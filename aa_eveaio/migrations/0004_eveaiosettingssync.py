"""Create EveAioSettingsSync model for cloud sync of app settings."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0003_general_and_id_fields"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EveAioSettingsSync",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("settings_json", models.TextField(default="{}", help_text="JSON blob of EVE AIO app settings (config.json contents).")),
                ("app_version", models.CharField(blank=True, default="", help_text="EVE AIO version that uploaded these settings.", max_length=32)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="eveaio_settings_sync", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "EVE AIO settings sync",
                "verbose_name_plural": "EVE AIO settings syncs",
            },
        ),
    ]
