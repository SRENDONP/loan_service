"""Pruebas del servicio provisional de políticas (SPEC 03, §3.2)."""

from datetime import timedelta

from django.test import override_settings

from apps.accounts import policy


def test_max_failed_attempts_default():
    assert policy.get_max_failed_attempts() == 5


@override_settings(ACCOUNTS_MAX_FAILED_ATTEMPTS=3)
def test_max_failed_attempts_follows_settings():
    assert policy.get_max_failed_attempts() == 3


def test_lockout_duration_default():
    assert policy.get_lockout_duration() == timedelta(minutes=15)


@override_settings(ACCOUNTS_LOCKOUT_MINUTES=30)
def test_lockout_duration_follows_settings():
    assert policy.get_lockout_duration() == timedelta(minutes=30)


def test_password_min_length_default():
    assert policy.get_password_min_length() == 8


@override_settings(ACCOUNTS_PASSWORD_MIN_LENGTH=12)
def test_password_min_length_follows_settings():
    assert policy.get_password_min_length() == 12


def test_password_reset_timeout_default():
    assert policy.get_password_reset_timeout() == 3600


@override_settings(PASSWORD_RESET_TIMEOUT=600)
def test_password_reset_timeout_follows_settings():
    assert policy.get_password_reset_timeout() == 600
