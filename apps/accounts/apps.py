from django.apps import AppConfig
from django.contrib.admin import apps as admin_apps
from django.db.models.signals import post_migrate
from django.utils.translation import gettext_lazy as _


class AccountsConfig(AppConfig):
    default = True
    name = "apps.accounts"
    verbose_name = _("Cuentas")

    def ready(self) -> None:
        # Sincroniza los grupos con ROLE_PERMISSIONS después de cada migrate
        # (SPEC 04 y ADR-002). Es configuración de acceso, no regla de negocio.
        from apps.accounts.roles import sync_roles_after_migrate

        post_migrate.connect(
            sync_roles_after_migrate, dispatch_uid="accounts.sync_roles"
        )


class SuperuserAdminConfig(admin_apps.AdminConfig):
    """Reemplaza a `django.contrib.admin` para que `admin.site` exija superusuario."""

    # No es la configuración por defecto de `apps.accounts`: se instala por su
    # ruta completa en INSTALLED_APPS, en lugar de "django.contrib.admin".
    default = False
    default_site = "apps.accounts.sites.SuperuserAdminSite"
