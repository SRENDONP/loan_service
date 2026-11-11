"""Manager del modelo de usuario."""

from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import UserManager as DjangoUserManager
from django.db.models import QuerySet

if TYPE_CHECKING:
    from apps.accounts.roles import Role


class UserManager(DjangoUserManager):
    """
    Manager de `apps.accounts.User`.

    Todo usuario nuevo debe cambiar la contraseña en su primer ingreso, salvo el
    superusuario creado con `createsuperuser`: quien lo crea ya eligió su
    contraseña (SPEC 03, §6).

    También define quién tiene cada rol (SPEC 04, §3.3). `collectors()` es la
    definición oficial de "cobrador" que usan créditos, pagos, cierre de caja y
    dashboard.
    """

    def with_role(self, role: Role) -> QuerySet:
        """Usuarios del grupo de ese rol, activos o no."""
        return self.get_queryset().filter(groups__name=role.value)

    def collectors(self) -> QuerySet:
        """Cobradores: activos, que no son superusuarios, con el rol Cajero/Cobrador."""
        from apps.accounts.roles import Role

        return self.with_role(Role.COLLECTOR).filter(is_active=True, is_superuser=False)

    def active_administrators(self) -> QuerySet:
        """Administradores activos que no son superusuarios (SPEC 04, §3.5)."""
        from apps.accounts.roles import Role

        return self.with_role(Role.ADMINISTRATOR).filter(
            is_active=True, is_superuser=False
        )

    def create_superuser(
        self,
        username: str,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ):
        extra_fields.setdefault("must_change_password", False)
        return super().create_superuser(username, email, password, **extra_fields)
