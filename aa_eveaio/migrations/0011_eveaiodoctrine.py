"""Add EveAioDoctrine and EveAioDoctrineFitting models."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0010_eveaiofleettemplate"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EveAioDoctrine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128, unique=True)),
                ("description", models.TextField(blank=True, default="")),
                ("tags", models.CharField(blank=True, default="", help_text="Comma-separated tags (e.g. armor,shield,bombers)", max_length=256)),
                ("ship_class", models.CharField(blank=True, default="", help_text="Ship class label (e.g. Cruiser, Battleship, Frigate)", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("published_by", models.ForeignKey(blank=True, null=True, on_delete=models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "EVE AIO doctrine",
                "verbose_name_plural": "EVE AIO doctrines",
                "ordering": ["name"],
            },
        ),
        migrations.CreateModel(
            name="EveAioDoctrineFitting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=128)),
                ("ship_type_id", models.IntegerField(default=0)),
                ("ship_name", models.CharField(blank=True, default="", max_length=128)),
                ("eft_text", models.TextField(blank=True, default="", help_text="EFT format fitting")),
                ("dna", models.CharField(blank=True, default="", help_text="DNA format fitting", max_length=512)),
                ("description", models.TextField(blank=True, default="")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("doctrine", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="fittings", to="aa_eveaio.eveaiodoctrine")),
            ],
            options={
                "verbose_name": "EVE AIO doctrine fitting",
                "verbose_name_plural": "EVE AIO doctrine fittings",
                "ordering": ["name"],
            },
        ),
    ]
