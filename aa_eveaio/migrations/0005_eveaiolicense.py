"""Create EveAioLicense singleton model."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0004_eveaiosettingssync"),
    ]

    operations = [
        migrations.CreateModel(
            name="EveAioLicense",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("license_key", models.CharField(blank=True, default="", max_length=128)),
                ("last_validated", models.DateTimeField(blank=True, null=True)),
                ("last_valid", models.BooleanField(default=False)),
                ("license_tier", models.CharField(blank=True, default="", max_length=32)),
                ("license_expires", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=256)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "EVE AIO license",
                "verbose_name_plural": "EVE AIO license",
            },
        ),
    ]
