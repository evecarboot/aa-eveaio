"""App configuration for the EVE AIO Alliance Auth plugin."""

from django.apps import AppConfig

from aa_eveaio import __version__


class AaEveaioConfig(AppConfig):
    """App config for the EVE AIO Alliance Auth plugin."""

    name = "aa_eveaio"
    label = "aa_eveaio"
    verbose_name = f"EVE AIO v{__version__}"

    def ready(self):
        try:
            import aa_eveaio.auth_hooks  # noqa: F401
        except Exception:
            pass
