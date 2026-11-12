"""Pruebas de las políticas de cuentas (SPEC 03, §3.2; SPEC 06, §3.4)."""

import re
from datetime import timedelta
from pathlib import Path

import pytest

from apps.accounts import policy

pytestmark = pytest.mark.django_db


def test_max_failed_attempts_default():
    assert policy.get_max_failed_attempts() == 5


def test_max_failed_attempts_follows_parameters(global_settings):
    global_settings.max_failed_attempts = 3
    global_settings.save()

    assert policy.get_max_failed_attempts() == 3


def test_lockout_duration_default():
    assert policy.get_lockout_duration() == timedelta(minutes=15)


def test_lockout_duration_follows_parameters(global_settings):
    global_settings.lockout_minutes = 30
    global_settings.save()

    assert policy.get_lockout_duration() == timedelta(minutes=30)


def test_password_min_length_default():
    assert policy.get_password_min_length() == 8


def test_password_min_length_follows_parameters(global_settings):
    global_settings.password_min_length = 12
    global_settings.save()

    assert policy.get_password_min_length() == 12


def test_password_reset_timeout_default():
    assert policy.get_password_reset_timeout() == 3600


def test_password_reset_timeout_follows_parameters(global_settings):
    global_settings.password_reset_timeout_minutes = 15
    global_settings.save()

    assert policy.get_password_reset_timeout() == 15 * 60


@pytest.mark.parametrize(
    "name",
    [
        "ACCOUNTS_MAX_FAILED_ATTEMPTS",
        "ACCOUNTS_LOCKOUT_MINUTES",
        "ACCOUNTS_PASSWORD_MIN_LENGTH",
        "PASSWORD_RESET_TIMEOUT",
    ],
)
def test_policy_settings_are_not_defined_in_project_settings(name):
    # SPEC 06: los cuatro valores salen del registro de parámetros.
    # PASSWORD_RESET_TIMEOUT tiene un valor global en Django, así que se revisa
    # el código de config/settings/ y no el objeto settings.
    settings_dir = Path(__file__).resolve().parents[2] / "config" / "settings"
    pattern = re.compile(rf"^\s*{name}\s*=", re.MULTILINE)

    for module in settings_dir.glob("*.py"):
        assert not pattern.search(module.read_text(encoding="utf-8")), module.name
