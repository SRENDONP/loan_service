"""Pruebas de la configuración por entorno (SPEC 01)."""

import importlib
import sys

import environ
import pytest
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def test_locale_and_timezone():
    assert settings.LANGUAGE_CODE == "es-co"
    assert settings.TIME_ZONE == "America/Bogota"
    assert settings.USE_I18N is True
    assert settings.USE_TZ is True


def test_database_engine_is_postgresql():
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.postgresql"


PROD_ENV = {
    "SECRET_KEY": "una-clave-de-prueba-larga-y-aleatoria-para-prod-0123456789",
    "ALLOWED_HOSTS": "prestamos.example.com",
    "DATABASE_URL": "postgres://user:pass@localhost:5432/db",
}


@pytest.fixture
def fresh_prod_import(monkeypatch):
    """
    Importa config.settings.prod desde cero, sin leer el `.env` local.

    monkeypatch restaura sys.modules y el entorno al terminar la prueba.
    """
    monkeypatch.setattr(environ.Env, "read_env", staticmethod(lambda *a, **k: None))
    for module in ("config.settings.prod", "config.settings.base"):
        monkeypatch.delitem(sys.modules, module, raising=False)
    for key, value in PROD_ENV.items():
        monkeypatch.setenv(key, value)

    def _import():
        return importlib.import_module("config.settings.prod")

    return _import


def test_prod_loads_with_required_variables(fresh_prod_import):
    prod = fresh_prod_import()

    assert prod.DEBUG is False
    assert prod.ALLOWED_HOSTS == ["prestamos.example.com"]
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True


@pytest.mark.parametrize("missing", ["SECRET_KEY", "ALLOWED_HOSTS", "DATABASE_URL"])
def test_prod_fails_without_required_variable(fresh_prod_import, monkeypatch, missing):
    monkeypatch.delenv(missing)

    with pytest.raises(ImproperlyConfigured, match=missing):
        fresh_prod_import()


def test_audit_trusted_proxies_defaults_to_zero(fresh_prod_import, monkeypatch):
    monkeypatch.delenv("AUDIT_TRUSTED_PROXIES", raising=False)

    assert fresh_prod_import().AUDIT_TRUSTED_PROXIES == 0


def test_audit_trusted_proxies_is_read_from_env(fresh_prod_import, monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXIES", "1")

    assert fresh_prod_import().AUDIT_TRUSTED_PROXIES == 1


def test_negative_audit_trusted_proxies_fails(fresh_prod_import, monkeypatch):
    monkeypatch.setenv("AUDIT_TRUSTED_PROXIES", "-1")

    with pytest.raises(ImproperlyConfigured, match="AUDIT_TRUSTED_PROXIES"):
        fresh_prod_import()
