"""Add license_api_key field to EveAioLicense."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0005_eveaiolicense"),
    ]

    operations = [
        migrations.AddField(
            model_name="eveaiolicense",
            name="license_api_key",
            field=models.CharField(blank=True, default="", max_length=256),
        ),
    ]
