"""
Models for the EVE AIO Alliance Auth plugin.

- General: unmanaged meta model that defines the plugin's permissions.
- EveAioServiceToken: one per user; secret key shown on the Services page and
  entered in EVE AIO.
- EveAioCharacterRole: which character_id has which EVE AIO role
  (e.g. station_manager). Character IDs are the same as in-game / ESI; EVE AIO
  matches toons by character_id.
"""

import secrets

from django.conf import settings
from django.db import models


class General(models.Model):
    """Meta model for app permissions."""

    class Meta:
        """Meta definitions."""

        managed = False
        default_permissions = ()
        permissions = (
            ("basic_access", "Can access this app"),
            ("manage_roles", "Can manage EVE AIO character roles"),
        )


def generate_token():
    """Generate a URL-safe token for EVE AIO (32 bytes -> 43 chars base64)."""
    return secrets.token_urlsafe(32)


class EveAioServiceToken(models.Model):
    """One token per user for EVE AIO. Created when the user activates the service."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eveaio_service_token",
    )
    token = models.CharField(
        max_length=64, unique=True, default=generate_token, editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO service token"
        verbose_name_plural = "EVE AIO service tokens"

    def __str__(self):
        return f"EVE AIO token for {self.user}"

    def regenerate_token(self):
        """Issue a new token, invalidating the old one."""
        self.token = generate_token()
        self.save(update_fields=["token", "updated_at"])


ROLE_STATION_MANAGER = "station_manager"
ROLE_DIRECTOR = "director"
ROLE_CHOICES = [
    (ROLE_STATION_MANAGER, "Station Manager (structures/fuel in EVE AIO)"),
    (ROLE_DIRECTOR, "Director"),
]


class EveAioCharacterRole(models.Model):
    """
    Grants an EVE AIO role to a character.

    Admins assign these in the EVE AIO admin panel; EVE AIO uses them when the
    user has connected the same character and entered their AA key.
    """

    character_id = models.BigIntegerField(
        db_index=True,
        help_text="EVE character ID (same as in-game/ESI; EVE AIO matches by this).",
    )
    role = models.CharField(max_length=64, choices=ROLE_CHOICES)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "EVE AIO character role"
        verbose_name_plural = "EVE AIO character roles"
        unique_together = [("character_id", "role")]

    def __str__(self):
        return f"Character {self.character_id} -> {self.get_role_display()}"


class EveAioSettingsSync(models.Model):
    """Cloud sync blob for EVE AIO app settings.

    Stores a JSON blob of the user's app config (toggles, alert rules,
    watchlists, intel channels, theme, etc.) so they can replicate their
    setup across multiple PCs. One blob per user (last-write-wins)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eveaio_settings_sync",
    )
    settings_json = models.TextField(
        default="{}",
        help_text="JSON blob of EVE AIO app settings (config.json contents).",
    )
    app_version = models.CharField(
        max_length=32, blank=True, default="",
        help_text="EVE AIO version that uploaded these settings.",
    )
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "EVE AIO settings sync"
        verbose_name_plural = "EVE AIO settings syncs"

    def __str__(self):
        return f"EVE AIO settings sync for {self.user}"


class EveAioLicense(models.Model):
    """Singleton model for license configuration."""

    license_key = models.CharField(
        max_length=128,
        blank=True,
        default="",
    )
    corp_id = models.BigIntegerField(
        null=True,
        blank=True,
        default=None,
    )
    last_validated = models.DateTimeField(null=True, blank=True)
    last_valid = models.BooleanField(default=False)
    license_tier = models.CharField(max_length=32, blank=True, default="")
    license_expires = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=256, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO license"
        verbose_name_plural = "EVE AIO license"

    def __str__(self):
        if self.license_key:
            return f"EVE AIO license ({self.license_key[:8]}…)"
        return "EVE AIO license (not set)"

    @classmethod
    def get_solo(cls):
        """Return the singleton instance, creating it if needed."""
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class EveAioDataSync(models.Model):
    """Cloud sync blob for EVE AIO user data (build jobs, custom prices, etc.).
    Stores multiple named JSON blobs so users can replicate their manual data
    across multiple PCs. One record per user (last-write-wins)."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eveaio_data_sync",
    )
    data_json = models.TextField(
        default="{}",
        help_text="JSON object of named data blobs: {ledger: {...}, custom_prices: {...}, ...}",
    )
    app_version = models.CharField(max_length=32, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "EVE AIO data sync"
        verbose_name_plural = "EVE AIO data syncs"

    def __str__(self):
        return f"EVE AIO data sync for {self.user}"


class EveAioFleetTemplate(models.Model):
    """Corp-shared fleet template for the Fleet Manager."""

    name = models.CharField(max_length=128)
    description = models.TextField(blank=True, default="")
    template_json = models.TextField(
        default="{}",
        help_text="JSON blob of the fleet template",
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO fleet template"
        verbose_name_plural = "EVE AIO fleet templates"
        ordering = ["name"]

    def __str__(self):
        return self.name


class EveAioDoctrine(models.Model):
    """Doctrine published from EVE AIO desktop app by directors/CEOs/FCs."""

    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, default="")
    tags = models.CharField(
        max_length=256,
        blank=True,
        default="",
        help_text="Comma-separated tags (e.g. armor,shield,bombers)",
    )
    ship_class = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Ship class label (e.g. Cruiser, Battleship, Frigate)",
    )
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO doctrine"
        verbose_name_plural = "EVE AIO doctrines"
        ordering = ["name"]

    def __str__(self):
        return self.name


ROAMING_KIND_BLOB = "blob"
ROAMING_KIND_RECORD = "record"
ROAMING_KIND_CHOICES = [
    (ROAMING_KIND_BLOB, "Encrypted snapshot blob"),
    (ROAMING_KIND_RECORD, "Small JSON record"),
]


class EveAioRoamingProfile(models.Model):
    """One encrypted EVE AIO Roaming Profile per AA user.

    The manifest is opaque safe metadata produced by the desktop client
    (profile UUID, generation, snapshot filename, payload hash,
    timestamps). The server stores it verbatim and uses ``generation``
    only for optimistic-concurrency checks. No plaintext secrets ever
    reach this table — the profile payload lives encrypted in
    :class:`EveAioRoamingObject` rows.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="eveaio_roaming_profile",
    )
    manifest_json = models.TextField(
        default="",
        blank=True,
        help_text="Client manifest JSON, stored verbatim (opaque metadata).",
    )
    generation = models.IntegerField(
        default=0,
        help_text="Committed manifest generation — the optimistic-lock counter.",
    )
    profile_id = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Client profile UUID (display/logging only, not authorization).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO roaming profile"
        verbose_name_plural = "EVE AIO roaming profiles"

    def __str__(self):
        return f"EVE AIO roaming profile for {self.user} (gen {self.generation})"


class EveAioRoamingObject(models.Model):
    """A single object inside a user's Roaming Profile.

    Two kinds share one namespace-per-kind:
    - ``blob``: an encrypted snapshot (``snapshot_NNNNNN.roam``) — opaque
      ciphertext bytes, never decoded or logged server-side.
    - ``record``: a small JSON document (``recovery.json`` wrapped-key
      material, ``devices/<id>.json`` heartbeat records).
    """

    profile = models.ForeignKey(
        EveAioRoamingProfile,
        on_delete=models.CASCADE,
        related_name="roaming_objects",
    )
    kind = models.CharField(max_length=8, choices=ROAMING_KIND_CHOICES)
    name = models.CharField(
        max_length=255,
        help_text="Snapshot filename or record relative path.",
    )
    payload = models.BinaryField(
        null=True,
        blank=True,
        default=None,
        help_text="Opaque encrypted bytes (blob kind only).",
    )
    record_json = models.TextField(
        default="",
        blank=True,
        help_text="Record JSON, stored verbatim (record kind only).",
    )
    size = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO roaming object"
        verbose_name_plural = "EVE AIO roaming objects"
        constraints = [
            models.UniqueConstraint(
                fields=["profile", "kind", "name"],
                name="aa_eveaio_roaming_object_unique_name",
            )
        ]
        indexes = [
            models.Index(
                fields=["profile", "kind", "name"],
                name="aa_eveaio_roam_obj_lookup",
            )
        ]

    def __str__(self):
        return f"{self.kind}:{self.name} ({self.size} bytes)"


class EveAioDoctrineFitting(models.Model):
    """Individual fitting within a doctrine, published from EVE AIO."""

    doctrine = models.ForeignKey(
        EveAioDoctrine,
        on_delete=models.CASCADE,
        related_name="fittings",
    )
    name = models.CharField(max_length=128)
    ship_type_id = models.IntegerField(default=0)
    ship_name = models.CharField(max_length=128, blank=True, default="")
    eft_text = models.TextField(blank=True, default="", help_text="EFT format fitting")
    dna = models.CharField(max_length=512, blank=True, default="", help_text="DNA format fitting")
    description = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "EVE AIO doctrine fitting"
        verbose_name_plural = "EVE AIO doctrine fittings"
        ordering = ["name"]

    def __str__(self):
        return f"{self.doctrine.name} — {self.name}"
