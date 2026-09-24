"""Update help_text on EveAioCharacterRole.character_id."""

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="eveaiocharacterrole",
            name="character_id",
            field=models.BigIntegerField(
                db_index=True,
                help_text="EVE character ID (same as in-game/ESI; EVE AIO matches by this).",
            ),
        ),
    ]
