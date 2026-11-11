from django.apps import AppConfig
from django.utils.module_loading import autodiscover_modules


class CoreConfig(AppConfig):
    name = "apps.core"

    def ready(self) -> None:
        # Importa el `menu.py` de cada app instalada para que registre sus
        # secciones y entradas en apps.core.navigation.registry.
        autodiscover_modules("menu")
