"""Django admin registration for the EVE AIO plugin."""

from django.contrib import admin
from django.utils.html import format_html

from aa_eveaio.models import EveAioCharacterRole, EveAioServiceToken, EveAioSettingsSync, EveAioLicense


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


@admin.register(EveAioLicense)
class EveAioLicenseAdmin(admin.ModelAdmin):
    list_display = ("license_key_preview", "last_valid", "license_tier", "last_validated", "license_expires")
    readonly_fields = ("last_validated", "last_valid", "license_tier", "license_expires", "last_error", "updated_at")
    fieldsets = (
        ("License Keys", {
            "fields": ("license_key", "license_api_key", "corp_id"),
        }),
        ("Validation Status", {
            "fields": ("last_valid", "license_tier", "last_validated", "license_expires", "last_error", "updated_at"),
            "classes": ("collapse",),
        }),
    )

    def license_key_preview(self, obj):
        if not obj.license_key:
            return "(not set)"
        return f"{obj.license_key[:8]}…{obj.license_key[-4:]}" if len(obj.license_key) > 16 else obj.license_key

    license_key_preview.short_description = "License Key"

    def has_add_permission(self, request):
        """Only one license record (singleton)."""
        return not EveAioLicense.objects.exists()

    def has_delete_permission(self, request, obj=None):
        """Don't allow deleting the license record."""
        return False
