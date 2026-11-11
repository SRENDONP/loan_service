"""Backend de autenticación por nombre de usuario o correo (SPEC 03)."""

from datetime import datetime
from typing import Any

from asgiref.sync import sync_to_async
from django.contrib.auth import check_password_with_timing_attack_mitigation
from django.contrib.auth.backends import ModelBackend
from django.http import HttpRequest
from django.views.decorators.debug import sensitive_variables

from apps.accounts.models import User
from apps.accounts.services import find_user_by_identifier, is_locked


class UsernameOrEmailBackend(ModelBackend):
    """
    Autentica con el nombre de usuario o con el correo.

    Rechaza a los usuarios inactivos y a las cuentas bloqueadas. El bloqueo se
    aplica primero en `services.authenticate_with_lockout`; este backend es la
    segunda barrera, para que ningún otro camino que llame a `authenticate()`
    lo salte.
    """

    @sensitive_variables("password")
    def authenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        now: datetime | None = None,
        **kwargs: Any,
    ) -> User | None:
        if username is None or password is None:
            return None
        user = find_user_by_identifier(username)
        # Con un usuario inexistente igual se calcula un hash, para que el
        # tiempo de respuesta no revele qué usuarios existen.
        if check_password_with_timing_attack_mitigation(
            user, password
        ) and self._can_authenticate(user, now):
            return user
        return None

    async def aauthenticate(
        self,
        request: HttpRequest | None,
        username: str | None = None,
        password: str | None = None,
        now: datetime | None = None,
        **kwargs: Any,
    ) -> User | None:
        # El `aauthenticate` de ModelBackend busca solo por nombre de usuario.
        return await sync_to_async(self.authenticate)(
            request, username=username, password=password, now=now, **kwargs
        )

    def user_can_authenticate(self, user: User) -> bool:
        return self._can_authenticate(user, now=None)

    def get_user(self, user_id: Any) -> User | None:
        """
        Carga al usuario de una sesión ya abierta.

        Solo rechaza a los inactivos: el bloqueo impide entrar, pero no cierra
        las sesiones abiertas. Así, quien bloquea a propósito la cuenta de un
        cobrador no lo saca mientras trabaja (SPEC 03, §6).
        """
        try:
            user = User._default_manager.get(pk=user_id)
        except User.DoesNotExist:
            return None
        return user if super().user_can_authenticate(user) else None

    def _can_authenticate(self, user: User, now: datetime | None) -> bool:
        return super().user_can_authenticate(user) and not is_locked(user, now)
