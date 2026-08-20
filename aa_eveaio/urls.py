"""App URLs for the EVE AIO Alliance Auth plugin."""

from django.urls import path

from aa_eveaio import views

app_name = "aa_eveaio"

urlpatterns = [
    path("", views.index, name="index"),
    path("token/", views.show_token, name="show_token"),
    path("activate/", views.activate, name="activate"),
    path("deactivate/", views.deactivate, name="deactivate"),
    path("regenerate/", views.regenerate_token, name="regenerate_token"),
    path("api/roles/", views.api_roles, name="api_roles"),
    path("api/esi_tokens/", views.api_esi_tokens, name="api_esi_tokens"),
    path("api/esi/<path:esi_path>", views.api_esi_proxy, name="api_esi_proxy"),
    path("api/settings_sync/", views.api_settings_sync, name="api_settings_sync"),
    path("api/auth/", views.api_auth, name="api_auth"),
]
