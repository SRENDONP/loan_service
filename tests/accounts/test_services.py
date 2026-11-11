"""Pruebas de los servicios de bloqueo (SPEC 03, §3.3)."""

from datetime import timedelta

import pytest
from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.accounts import services

pytestmark = pytest.mark.django_db

WRONG_PASSWORD = "otra2026"


def fail(identifier: str, times: int, now=None) -> None:
    for _ in range(times):
        assert (
            services.authenticate_with_lockout(None, identifier, WRONG_PASSWORD, now)
            is None
        )


# find_user_by_identifier


def test_find_by_username(make_user):
    user = make_user("ana", email="ana@example.com")

    assert services.find_user_by_identifier("ana") == user


def test_find_by_email_ignoring_case(make_user):
    user = make_user("ana", email="ana@example.com")

    assert services.find_user_by_identifier("Ana@EXAMPLE.com") == user


def test_find_returns_none_for_unknown_or_empty(make_user):
    make_user("ana")

    assert services.find_user_by_identifier("nadie") is None
    assert services.find_user_by_identifier("nadie@example.com") is None
    assert services.find_user_by_identifier("") is None


# is_locked


def test_is_locked(make_user):
    now = timezone.now()
    user = make_user("ana")

    assert services.is_locked(user, now) is False
    user.locked_until = now + timedelta(seconds=1)
    assert services.is_locked(user, now) is True
    user.locked_until = now
    assert services.is_locked(user, now) is False


# authenticate_with_lockout


def test_successful_login_returns_user(make_user, password):
    user = make_user("ana", email="ana@example.com")

    assert services.authenticate_with_lockout(None, "ana", password) == user
    assert services.authenticate_with_lockout(None, "ANA@example.com", password) == user


def test_failed_login_counts_attempt(make_user):
    user = make_user("ana")

    fail("ana", 1)

    user.refresh_from_db()
    assert user.failed_login_attempts == 1
    assert user.locked_until is None


def test_failed_login_with_email_counts_attempt(make_user):
    user = make_user("ana", email="ana@example.com")

    fail("Ana@Example.com", 2)

    user.refresh_from_db()
    assert user.failed_login_attempts == 2


def test_fourth_failure_does_not_lock(make_user, password):
    user = make_user("ana")

    fail("ana", 4)

    user.refresh_from_db()
    assert user.failed_login_attempts == 4
    assert user.locked_until is None
    assert services.authenticate_with_lockout(None, "ana", password) == user


def test_fifth_failure_locks_for_fifteen_minutes(make_user):
    now = timezone.now()
    user = make_user("ana")

    fail("ana", 5, now)

    user.refresh_from_db()
    assert user.locked_until == now + timedelta(minutes=15)
    assert user.failed_login_attempts == 0
    assert services.is_locked(user, now)


def test_locked_account_rejects_correct_password_without_counting(make_user, password):
    now = timezone.now()
    user = make_user("ana")
    fail("ana", 5, now)

    later = now + timedelta(minutes=5)
    assert services.authenticate_with_lockout(None, "ana", password, later) is None
    fail("ana", 3, later)

    user.refresh_from_db()
    assert user.failed_login_attempts == 0
    assert user.locked_until == now + timedelta(minutes=15)


def test_account_unlocks_after_fifteen_minutes(make_user, password):
    now = timezone.now()
    user = make_user("ana")
    fail("ana", 5, now)

    just_before = now + timedelta(minutes=15) - timedelta(seconds=1)
    assert (
        services.authenticate_with_lockout(None, "ana", password, just_before) is None
    )

    after = now + timedelta(minutes=15)
    assert services.authenticate_with_lockout(None, "ana", password, after) == user
    user.refresh_from_db()
    assert user.locked_until is None
    assert user.failed_login_attempts == 0


def test_successful_login_resets_counter(make_user, password):
    user = make_user("ana")
    fail("ana", 3)

    services.authenticate_with_lockout(None, "ana", password)

    user.refresh_from_db()
    assert user.failed_login_attempts == 0


def test_inactive_user_failure_is_counted_and_rejected(make_user, password):
    user = make_user("ana", is_active=False)

    assert services.authenticate_with_lockout(None, "ana", password) is None

    user.refresh_from_db()
    assert user.failed_login_attempts == 1


def test_unknown_user_failure_writes_nothing_but_the_audit():
    from apps.auditoria.actions import AuditAction
    from apps.auditoria.models import AuditEvent

    with CaptureQueriesContext(connection) as queries:
        fail("nadie", 1)
        fail("nadie@example.com", 1)

    writes = [
        query["sql"]
        for query in queries.captured_queries
        if query["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
        and '"auditoria_auditevent"' not in query["sql"]
    ]
    assert writes == []
    # El fallo sí queda en la auditoría (SPEC 05, §3.7).
    assert AuditEvent.objects.filter(action=AuditAction.LOGIN_FAILED).count() == 2


@override_settings(ACCOUNTS_MAX_FAILED_ATTEMPTS=2, ACCOUNTS_LOCKOUT_MINUTES=30)
def test_lockout_follows_policy_settings(make_user, password):
    now = timezone.now()
    user = make_user("ana")

    fail("ana", 2, now)

    user.refresh_from_db()
    assert user.locked_until == now + timedelta(minutes=30)
    assert (
        services.authenticate_with_lockout(
            None, "ana", password, now + timedelta(minutes=15)
        )
        is None
    )
    assert (
        services.authenticate_with_lockout(
            None, "ana", password, now + timedelta(minutes=30)
        )
        == user
    )


# register_failed_attempt, clear_failed_attempts y mark_password_changed


def test_register_failed_attempt_updates_given_instance(make_user):
    user = make_user("ana", failed_login_attempts=4)
    now = timezone.now()

    services.register_failed_attempt(user, now)

    assert user.failed_login_attempts == 0
    assert user.locked_until == now + timedelta(minutes=15)


def test_register_failed_attempt_ignores_locked_account(make_user):
    now = timezone.now()
    locked_until = now + timedelta(minutes=10)
    user = make_user("ana", locked_until=locked_until)

    services.register_failed_attempt(user, now)

    user.refresh_from_db()
    assert user.locked_until == locked_until
    assert user.failed_login_attempts == 0


def test_clear_failed_attempts_unlocks(make_user, password):
    user = make_user(
        "ana",
        failed_login_attempts=3,
        locked_until=timezone.now() + timedelta(minutes=10),
    )

    services.clear_failed_attempts(user)

    user.refresh_from_db()
    assert user.failed_login_attempts == 0
    assert user.locked_until is None
    assert services.authenticate_with_lockout(None, "ana", password) == user


def test_clear_failed_attempts_on_clean_user_writes_nothing(make_user):
    user = make_user("ana")

    with CaptureQueriesContext(connection) as queries:
        services.clear_failed_attempts(user)

    assert queries.captured_queries == []


def test_mark_password_changed(make_user):
    user = make_user("ana", must_change_password=True)

    services.mark_password_changed(user)

    user.refresh_from_db()
    assert user.must_change_password is False

    with CaptureQueriesContext(connection) as queries:
        services.mark_password_changed(user)
    assert queries.captured_queries == []
