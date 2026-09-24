"""Django admin registration for the EVE AIO plugin."""

from django.contrib import admin
from django.utils.html import format_html

from aa_eveaio.models import (
    EveAioCharacterRole,
    EveAioServiceToken,
    EveAioSettingsSync,
    EveAioDataSync,
    EveAioFleetTemplate,
    EveAioDoctrine,
    EveAioDoctrineFitting,
    EveAioRoamingProfile,
    EveAioRoamingObject,
)


@admin.register(EveAioServiceToken)
class EveAioServiceTokenAdmin(admin.ModelAdmin):
    list_display = ("user", "token_preview", "created_at")
    search_fields = ("user__username", "token")
    readonly_fields = ("token", "created_at", "updated_at")

    def token_preview(self, obj):
        if not obj.token:
            return "-"
        return f"{obj.token[:8]}…{obj.token[-4:]}" if len(obj.token) > 16 else "***"

    token_preview.short_description = "Token"


@admin.register(EveAioCharacterRole)
class EveAioCharacterRoleAdmin(admin.ModelAdmin):
    list_display = ("character_id", "character_name", "role", "created_at")
    list_filter = ("role",)
    search_fields = ("character_id",)
    ordering = ("character_id", "role")

    def character_name(self, obj):
        try:
            from allianceauth.eveonline.models import EveCharacter

            c = EveCharacter.objects.filter(character_id=obj.character_id).first()
            return c.character_name if c else f"ID {obj.character_id}"
        except Exception:
            return str(obj.character_id)

    character_name.short_description = "Character"


@admin.register(EveAioSettingsSync)
class EveAioSettingsSyncAdmin(admin.ModelAdmin):
    list_display = ("user", "app_version", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("user__username",)


@admin.register(EveAioDataSync)
class EveAioDataSyncAdmin(admin.ModelAdmin):
    list_display = ("user", "app_version", "updated_at")
    readonly_fields = ("created_at", "updated_at")
    search_fields = ("user__username",)


@admin.register(EveAioFleetTemplate)
class EveAioFleetTemplateAdmin(admin.ModelAdmin):
    list_display = ("name", "updated_at")
    search_fields = ("name",)
    readonly_fields = ("created_at", "updated_at")


@admin.register(EveAioDoctrine)
class EveAioDoctrineAdmin(admin.ModelAdmin):
    list_display = ("name", "ship_class", "tags", "updated_at")
    search_fields = ("name", "tags", "ship_class")
    readonly_fields = ("created_at", "updated_at")


@admin.register(EveAioDoctrineFitting)
class EveAioDoctrineFittingAdmin(admin.ModelAdmin):
    list_display = ("name", "ship_name", "doctrine", "updated_at")
    search_fields = ("name", "ship_name", "doctrine__name")
    readonly_fields = ("created_at", "updated_at")
    list_filter = ("doctrine",)


@admin.register(EveAioRoamingProfile)
class EveAioRoamingProfileAdmin(admin.ModelAdmin):
    """Safe metadata only — the manifest is opaque client data and the
    encrypted payloads live in EveAioRoamingObject. Nothing here may
    decrypt or display ciphertext."""
    list_display = ("user", "profile_id", "generation", "object_count",
                    "updated_at")
    search_fields = ("user__username", "profile_id")
    readonly_fields = ("user", "profile_id", "generation",
                       "manifest_json", "created_at", "updated_at")

    def object_count(self, obj):
        return obj.roaming_objects.count()

    object_count.short_description = "Objects"

    def has_add_permission(self, request):
        return False


@admin.register(EveAioRoamingObject)
class EveAioRoamingObjectAdmin(admin.ModelAdmin):
    """Read-only metadata — payload/record bodies are never rendered."""
    list_display = ("profile_user", "kind", "name", "size", "updated_at")
    list_filter = ("kind",)
    search_fields = ("name", "profile__user__username")
    fields = ("profile", "kind", "name", "size", "created_at", "updated_at")
    readonly_fields = fields

    def profile_user(self, obj):
        return obj.profile.user

    profile_user.short_description = "User"

    def has_add_permission(self, request):
        return False
