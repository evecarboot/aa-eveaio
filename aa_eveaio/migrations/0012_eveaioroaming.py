"""Add EveAioRoamingProfile and EveAioRoamingObject models."""

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("aa_eveaio", "0011_eveaiodoctrine"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="EveAioRoamingProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("manifest_json", models.TextField(blank=True, default="", help_text="Client manifest JSON, stored verbatim (opaque metadata).")),
                ("generation", models.IntegerField(default=0, help_text="Committed manifest generation — the optimistic-lock counter.")),
                ("profile_id", models.CharField(blank=True, default="", help_text="Client profile UUID (display/logging only, not authorization).", max_length=64)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("user", models.OneToOneField(on_delete=models.deletion.CASCADE, related_name="eveaio_roaming_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "verbose_name": "EVE AIO roaming profile",
                "verbose_name_plural": "EVE AIO roaming profiles",
            },
        ),
        migrations.CreateModel(
            name="EveAioRoamingObject",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("kind", models.CharField(choices=[("blob", "Encrypted snapshot blob"), ("record", "Small JSON record")], max_length=8)),
                ("name", models.CharField(help_text="Snapshot filename or record relative path.", max_length=255)),
                ("payload", models.BinaryField(blank=True, default=None, help_text="Opaque encrypted bytes (blob kind only).", null=True)),
                ("record_json", models.TextField(blank=True, default="", help_text="Record JSON, stored verbatim (record kind only).")),
                ("size", models.IntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("profile", models.ForeignKey(on_delete=models.deletion.CASCADE, related_name="roaming_objects", to="aa_eveaio.eveaioroamingprofile")),
            ],
            options={
                "verbose_name": "EVE AIO roaming object",
                "verbose_name_plural": "EVE AIO roaming objects",
            },
        ),
        migrations.AddConstraint(
            model_name="eveaioroamingobject",
            constraint=models.UniqueConstraint(fields=("profile", "kind", "name"), name="aa_eveaio_roaming_object_unique_name"),
        ),
        migrations.AddIndex(
            model_name="eveaioroamingobject",
            index=models.Index(fields=["profile", "kind", "name"], name="aa_eveaio_roam_obj_lookup"),
        ),
    ]
