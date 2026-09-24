"""App URLs for the EVE AIO Alliance Auth plugin."""

from django.urls import path

from aa_eveaio import views

app_name = "aa_eveaio"

urlpatterns = [
    path("", views.index, name="index"),
    path("license/", views.license_config, name="license_config"),
    path("token/", views.show_token, name="show_token"),
    path("activate/", views.activate, name="activate"),
    path("deactivate/", views.deactivate, name="deactivate"),
    path("regenerate/", views.regenerate_token, name="regenerate_token"),
    path("api/roles/", views.api_roles, name="api_roles"),
    path("api/esi_tokens/", views.api_esi_tokens, name="api_esi_tokens"),
    path("api/esi/<path:esi_path>", views.api_esi_proxy, name="api_esi_proxy"),
    path("api/settings_sync/", views.api_settings_sync, name="api_settings_sync"),
    path("api/data_sync/", views.api_data_sync, name="api_data_sync"),
    path("api/auth/", views.api_auth, name="api_auth"),
    path("api/fleet/roster/", views.api_fleet_roster, name="api_fleet_roster"),
    path("api/discord_map/", views.api_discord_map, name="api_discord_map"),
    path("api/groups/", views.api_groups, name="api_groups"),
    path("api/doctrines/", views.api_doctrines, name="api_doctrines"),
    path("api/doctrine_publish/", views.api_doctrine_publish, name="api_doctrine_publish"),
    path("api/doctrine_delete/", views.api_doctrine_delete, name="api_doctrine_delete"),
    path("api/srp/eligible/", views.api_srp_eligible, name="api_srp_eligible"),
    path("api/srp/claim/", views.api_srp_claim, name="api_srp_claim"),
    path("api/timers/", views.api_timers, name="api_timers"),
    path("api/fleet_templates/", views.api_fleet_templates, name="api_fleet_templates"),
    # Roaming Profile API (v1) — one encrypted profile per AA user.
    # Blob/record item routes intentionally have no trailing slash:
    # the desktop provider addresses them verbatim and never follows
    # redirects (its X-Eveaio-Token must not leak to other hosts).
    path("api/capabilities/", views.api_capabilities, name="api_capabilities"),
    path("api/roaming/manifest/", views.api_roaming_manifest, name="api_roaming_manifest"),
    path("api/roaming/blobs/", views.api_roaming_blobs, name="api_roaming_blobs"),
    path("api/roaming/blob/<str:name>", views.api_roaming_blob, name="api_roaming_blob"),
    path("api/roaming/records/", views.api_roaming_records, name="api_roaming_records"),
    path("api/roaming/records/<path:rel>", views.api_roaming_record, name="api_roaming_record"),
]
