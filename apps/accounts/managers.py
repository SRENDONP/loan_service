"""Manager del modelo de usuario."""

from typing import Any

from django.contrib.auth.models import UserManager as DjangoUserManager


class UserManager(DjangoUserManager):
    """
    Manager de `apps.accounts.User`.

    Todo usuario nuevo debe cambiar la contraseña en su primer ingreso, salvo el
    superusuario creado con `createsuperuser`: quien lo crea ya eligió su
    contraseña (SPEC 03, §6).
    """

    def create_superuser(
        self,
        username: str,
        email: str | None = None,
        password: str | None = None,
        **extra_fields: Any,
    ):
        extra_fields.setdefault("must_change_password", False)
        return super().create_superuser(username, email, password, **extra_fields)
