"""Pruebas de la configuración de autenticación (SPEC 03)."""

import importlib
import os
import sys

import environ
import pytest
from django.conf import settings
from django.contrib.auth.hashers import make_password
from django.core.exceptions import ImproperlyConfigured
from django.core.mail import send_mail
from django.test import override_settings

ARGON2_HASHER = "django.contrib.auth.hashers.Argon2PasswordHasher"


def project_password_hashers() -> list[str]:
    """
    Hashers configurados en los settings del proyecto.

    `django.conf.settings` no sirve aquí: la fixture `fast_password_hashers` de
    tests/conftest.py lo cambia a MD5 en cada prueba. Por eso se lee el módulo
    de settings que usa la suite (`settings.SETTINGS_MODULE` vale `None` mientras
    los settings están sobrescritos).
    """
    module = importlib.import_module(os.environ["DJANGO_SETTINGS_MODULE"])
    return module.PASSWORD_HASHERS


def test_session_expires_at_browser_close_and_lasts_at_most_a_day():
    # SPEC 06, §3.5: la duración real es un parámetro (12 horas por defecto) y
    # la cookie usa el máximo del rango como tope duro.
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True
    assert settings.SESSION_COOKIE_AGE == 24 * 60 * 60


def test_login_required_middleware_follows_authentication():
    middleware = settings.MIDDLEWARE
    auth = middleware.index("django.contrib.auth.middleware.AuthenticationMiddleware")
    login_required = middleware.index(
        "django.contrib.auth.middleware.LoginRequiredMiddleware"
    )

    # Entre los dos van el contexto de auditoría (SPEC 05, §3.4) y el cierre de
    # sesión por inactividad (SPEC 06, §3.5), que solo responde a usuarios con
    # sesión.
    assert middleware[auth + 1 : login_required] == [
        "apps.auditoria.middleware.AuditContextMiddleware",
        "apps.accounts.middleware.SessionPolicyMiddleware",
    ]


def test_argon2_is_the_first_password_hasher():
    assert project_password_hashers()[0] == ARGON2_HASHER


def test_project_hashers_store_passwords_with_argon2():
    with override_settings(PASSWORD_HASHERS=project_password_hashers()):
        encoded = make_password("abc12345")

    assert encoded.startswith("argon2")


# Correo simulado ------------------------------------------------------------


@pytest.fixture
def fresh_base_import(monkeypatch):
    """
    Importa config.settings.base desde cero, sin leer el `.env` local.

    monkeypatch restaura sys.modules y el entorno al terminar la prueba.
    """
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *a, **k: None))
    monkeypatch.delitem(sys.modules, "config.settings.base", raising=False)
    monkeypatch.setenv("DATABASE_URL", "postgres://user:pass@localhost:5432/db")
    for key in ("EMAIL_BACKEND", "EMAIL_FILE_PATH", "DEFAULT_FROM_EMAIL"):
        monkeypatch.delenv(key, raising=False)

    def _import():
        return importlib.import_module("config.settings.base")

    return _import


def test_console_is_the_default_email_backend(fresh_base_import):
    base = fresh_base_import()

    assert base.MAILERS == {
        "default": {"BACKEND": "django.core.mail.backends.console.EmailBackend"}
    }
    assert base.DEFAULT_FROM_EMAIL == "no-responder@localhost"


def test_file_email_backend_uses_email_file_path(fresh_base_import, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "file")
    monkeypatch.setenv("EMAIL_FILE_PATH", "tmp/correos")
    monkeypatch.setenv("DEFAULT_FROM_EMAIL", "cobros@example.com")

    base = fresh_base_import()

    assert base.MAILERS == {
        "default": {
            "BACKEND": "django.core.mail.backends.filebased.EmailBackend",
            "OPTIONS": {"file_path": str(base.BASE_DIR / "tmp" / "correos")},
        }
    }
    assert base.DEFAULT_FROM_EMAIL == "cobros@example.com"


def test_file_email_backend_defaults_to_tmp_emails(fresh_base_import, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "file")

    base = fresh_base_import()

    file_path = base.MAILERS["default"]["OPTIONS"]["file_path"]
    assert file_path == str(base.BASE_DIR / "tmp" / "emails")


def test_unknown_email_backend_is_improperly_configured(fresh_base_import, monkeypatch):
    monkeypatch.setenv("EMAIL_BACKEND", "smtp")

    with pytest.raises(ImproperlyConfigured, match="EMAIL_BACKEND"):
        fresh_base_import()


def test_file_email_backend_writes_the_message(settings, tmp_path):
    settings.MAILERS = {
        "default": {
            "BACKEND": "django.core.mail.backends.filebased.EmailBackend",
            "OPTIONS": {"file_path": str(tmp_path)},
        }
    }

    send_mail("Asunto", "Cuerpo del correo", None, ["ana@example.com"])

    (message_file,) = tmp_path.iterdir()
    content = message_file.read_text(encoding="utf-8")
    assert "Cuerpo del correo" in content
    assert "From: no-responder@localhost" in content
