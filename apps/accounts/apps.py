from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default = True
    name = "apps.accounts"
    verbose_name = _("Cuentas")


class SuperuserAdminConfig(admin_apps.AdminConfig):
    """Reemplaza a `django.contrib.admin` para que `admin.site` exija superusuario."""

    # No es la configuración por defecto de `apps.accounts`: se instala por su
    # ruta completa en INSTALLED_APPS, en lugar de "django.contrib.admin".
    default = False
    default_site = "apps.accounts.sites.SuperuserAdminSite"
