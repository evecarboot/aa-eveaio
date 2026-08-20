"""
Register EVE AIO with Alliance Auth: URLs, sidebar menu and Services page.
"""

from django.template.loader import render_to_string
from django.urls import reverse
from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.services.hooks import MenuItemHook, ServicesHook, UrlHook

from aa_eveaio import urls
from aa_eveaio.models import EveAioServiceToken


class EveAioMenuItem(MenuItemHook):
    """Sidebar menu item for EVE AIO, shown to users with basic_access."""

    def __init__(self):
        MenuItemHook.__init__(
            self,
            _("EVE AIO"),
            "fas fa-desktop fa-fw",
            "aa_eveaio:index",
            navactive=["aa_eveaio:"],
            order=150,
        )

    def render(self, request):
        if request.user.has_perm("aa_eveaio.basic_access"):
            return MenuItemHook.render(self, request)
        return ""


@hooks.register("menu_item_hook")
def register_menu():
    """Register the EVE AIO sidebar menu item."""
    return EveAioMenuItem()


@hooks.register("url_hook")
def register_urls():
    """
    Include our URLs.

    The API endpoints are excluded from the default ``main_character_required``
    decorator so EVE AIO can call them with just the token (no AA session).
    """
    return UrlHook(
        urls,
        "aa_eveaio",
        r"^eveaio/",
        excluded_views=[
            "aa_eveaio.views.api_roles",
            "aa_eveaio.views.api_esi_tokens",
            "aa_eveaio.views.api_esi_proxy",
            "aa_eveaio.views.api_settings_sync",
            "aa_eveaio.views.api_auth",
        ],
    )


@hooks.register("services_hook")
def register_service():
    """Register EVE AIO on the Services page: activate = get key, deactivate = remove key."""
    return EveAioServiceHook()


class EveAioServiceHook(ServicesHook):
    """Service hook for EVE AIO: no external account; we only store a token and show it."""

    def __init__(self):
        super().__init__()
        self.name = "eveaio"
        self.service_ctrl_template = "aa_eveaio/service_ctrl.html"

    @property
    def title(self):
        return _("EVE AIO")

    @property
    def service_url(self):
        """Link to the EVE AIO plugin index."""
        return reverse("aa_eveaio:index")

    def delete_user(self, user, notify_user=False):
        """Remove the user's EVE AIO token when they deactivate the service."""
        try:
            token_obj = EveAioServiceToken.objects.get(user=user)
            token_obj.delete()
            if notify_user:
                try:
                    from allianceauth.notifications import notify

                    notify(user, "EVE AIO", "Your EVE AIO service access has been disabled.")
                except Exception:
                    pass
            return True
        except EveAioServiceToken.DoesNotExist:
            return False

    def validate_user(self, user):
        """Remove the token if the user should no longer have access."""
        if not self.service_active_for_user(user):
            self.delete_user(user, notify_user=True)

    def service_active_for_user(self, user):
        """Service is 'active' when the user has a token (has activated)."""
        return EveAioServiceToken.objects.filter(user=user).exists()

    def render_services_ctrl(self, request):
        """Render the Services page row: name, key preview, link, Activate/Deactivate."""
        token_obj = getattr(request.user, "eveaio_service_token", None)
        urls_obj = self.Urls()
        urls_obj.auth_activate = "aa_eveaio:activate"
        urls_obj.auth_deactivate = "aa_eveaio:deactivate"
        urls_obj.auth_reset_password = None
        urls_obj.auth_set_password = None
        return render_to_string(
            self.service_ctrl_template,
            {
                "service_name": self.title,
                "urls": urls_obj,
                "service_url": request.build_absolute_uri(reverse("aa_eveaio:index")),
                "username": "EVE AIO",
                "has_token": token_obj is not None,
                "token_preview": (
                    f"{token_obj.token[:8]}…" if token_obj and token_obj.token else None
                ),
                "show_token_url": (
                    reverse("aa_eveaio:show_token") if token_obj else None
                ),
            },
            request=request,
        )
