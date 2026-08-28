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
