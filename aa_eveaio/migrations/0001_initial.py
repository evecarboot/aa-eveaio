from django.conf import settings
from django.db import migrations, models
import aa_eveaio.models


class Migration(migrations.Migration):

    initial = True
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]
    operations = [
        migrations.CreateModel(
            name="EveAioServiceToken",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("token", models.CharField(default=aa_eveaio.models.generate_token, editable=False, max_length=64, unique=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=models.CASCADE, related_name="eveaio_service_token", to=settings.AUTH_USER_MODEL)),
            ],
            options={"verbose_name": "EVE AIO service token", "verbose_name_plural": "EVE AIO service tokens"},
        ),
        migrations.CreateModel(
            name="EveAioCharacterRole",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("character_id", models.BigIntegerField(db_index=True, help_text="EVE character ID (same as in-game/ESI).")),
                ("role", models.CharField(choices=[("station_manager", "Station Manager (structures/fuel in EVE AIO)"), ("director", "Director")], max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={"verbose_name": "EVE AIO character role", "verbose_name_plural": "EVE AIO character roles"},
        ),
        migrations.AlterUniqueTogether(
            name="eveaiocharacterrole",
            unique_together={("character_id", "role")},
        ),
    ]
