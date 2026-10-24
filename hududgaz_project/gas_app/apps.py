from django.apps import AppConfig


class GasAppConfig(AppConfig):
    name = "gas_app"
    verbose_name = "Hududgaz"

    def ready(self):
        from . import signals  # noqa: F401
