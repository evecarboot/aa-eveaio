"""Add corp_id field to EveAioLicense."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0006_eveaiolicense_api_key"),
    ]

    operations = [
        migrations.AddField(
            model_name="eveaiolicense",
            name="corp_id",
            field=models.BigIntegerField(blank=True, default=None, null=True),
        ),
    ]
