from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AmortizacionConfig(AppConfig):
    """Motor de amortización (SPEC 09).

    Es el único archivo de la app que importa Django. Los módulos de cálculo son
    lógica pura (constitución §5.2).
    """

    name = "apps.amortizacion"
    verbose_name = _("Amortización")
