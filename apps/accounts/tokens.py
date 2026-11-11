"""Tokens del enlace de recuperación de contraseña (SPEC 03)."""

from django.contrib.auth.base_user import AbstractBaseUser
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.utils.crypto import constant_time_compare
from django.utils.http import base36_to_int

from apps.accounts.policy import get_password_reset_timeout


class PolicyPasswordResetTokenGenerator(PasswordResetTokenGenerator):
    """
    Generador de tokens cuya vigencia sale de `policy.py` en cada uso.

    El de Django lee `settings.PASSWORD_RESET_TIMEOUT` directamente; aquí se
    consulta `get_password_reset_timeout()`, para que la SPEC 06 pueda cambiarla.
    El token deja de servir al usarse, porque su hash incluye la contraseña.
    """

    def check_token(self, user: AbstractBaseUser | None, token: str | None) -> bool:
        if not (user and token):
            return False
        try:
            ts_b36, _ = token.split("-")
            ts = base36_to_int(ts_b36)
        except ValueError:
            return False

        for secret in [self.secret, *self.secret_fallbacks]:
            if constant_time_compare(
                self._make_token_with_timestamp(user, ts, secret), token
            ):
                break
        else:
            return False

        return (self._num_seconds(self._now()) - ts) <= get_password_reset_timeout()


password_reset_token_generator = PolicyPasswordResetTokenGenerator()
