"""Create General permissions model and align id fields with project default."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0002_alter_character_id_help"),
    ]

    operations = [
        migrations.CreateModel(
            name="General",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
            ],
            options={
                "permissions": (
                    ("basic_access", "Can access this app"),
                    ("manage_roles", "Can manage EVE AIO character roles"),
                ),
                "managed": False,
                "default_permissions": (),
            },
        ),
        migrations.AlterField(
            model_name="eveaiocharacterrole",
            name="id",
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
        migrations.AlterField(
            model_name="eveaioservicetoken",
            name="id",
            field=models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID"),
        ),
    ]
