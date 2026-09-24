"""Remove license_api_key field from EveAioLicense."""

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0007_eveaiolicense_corp_id"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="eveaiolicense",
            name="license_api_key",
        ),
    ]
