"""
Auditoría de las cuentas (SPEC 05, §3.7).

Bloqueo, cambios de contraseña, servicios de gestión de usuarios y admin de
Django sobre usuarios.
"""

import re
from datetime import timedelta

import pytest
from django.contrib.auth.models import Group
from django.core.exceptions import PermissionDenied
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.accounts import admin as accounts_admin
from apps.accounts import services, views
from apps.accounts.models import User
from apps.accounts.roles import Role, get_role
from apps.auditoria.actions import AuditAction, AuditCategory
from apps.auditoria.models import AuditEvent, AuditSource

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")
WRONG_PASSWORD = "otra2026"


def events(action: AuditAction) -> list[AuditEvent]:
    return list(AuditEvent.objects.filter(action=action).order_by("id"))


def post_login(client, username: str, password: str):
    return client.post(
        LOGIN, {"username": username, "password": password}, REMOTE_ADDR="10.0.0.9"
    )


# Bloqueo --------------------------------------------------------------------


@override_settings(ACCOUNTS_MAX_FAILED_ATTEMPTS=3)
def test_attempt_that_reaches_the_limit_records_failed_and_locked(client, user):
    for _ in range(3):
        post_login(client, "cobrador", WRONG_PASSWORD)

    assert len(events(AuditAction.LOGIN_FAILED)) == 3
    [locked] = events(AuditAction.ACCOUNT_LOCKED)
    user.refresh_from_db()
    assert locked.category == AuditCategory.ACCESS
    assert locked.actor is None
    assert locked.object_id == str(user.pk)
    assert locked.extra["attempts"] == 3
    # DjangoJSONEncoder guarda la fecha en ISO 8601 con milisegundos.
    stored_until = parse_datetime(locked.extra["locked_until"])
    assert abs(stored_until - user.locked_until) < timedelta(milliseconds=1)
    assert locked.ip_address == "10.0.0.9"
    # El bloqueo se registra después del último fallo y en la misma petición.
    last_failed = events(AuditAction.LOGIN_FAILED)[-1]
    assert locked.id > last_failed.id
    assert locked.request_id == last_failed.request_id


@override_settings(ACCOUNTS_MAX_FAILED_ATTEMPTS=3)
def test_attempts_below_the_limit_do_not_record_a_lock(client, user):
    for _ in range(2):
        post_login(client, "cobrador", WRONG_PASSWORD)

    assert not events(AuditAction.ACCOUNT_LOCKED)


@pytest.mark.parametrize("typed_password", ["cobro2026", WRONG_PASSWORD])
def test_attempt_during_lock_records_blocked(client, make_user, typed_password):
    locked_until = timezone.now() + timedelta(minutes=10)
    user = make_user("bloqueado", locked_until=locked_until)

    response = post_login(client, "bloqueado", typed_password)

    assert response.status_code == 200
    [blocked] = events(AuditAction.LOGIN_BLOCKED)
    assert blocked.category == AuditCategory.ACCESS
    assert blocked.actor is None
    assert blocked.identifier == "bloqueado"
    assert blocked.object_id == str(user.pk)
    assert "locked_until" in blocked.extra
    assert not events(AuditAction.LOGIN_SUCCEEDED)
    assert not events(AuditAction.LOGIN_FAILED)
    assert not events(AuditAction.ACCOUNT_LOCKED)


def test_attempt_during_lock_by_email_keeps_the_typed_text(make_user):
    make_user(
        "bloqueado",
        email="bloq@example.com",
        locked_until=timezone.now() + timedelta(minutes=10),
    )

    services.authenticate_with_lockout(None, "BLOQ@example.com", WRONG_PASSWORD)

    [blocked] = events(AuditAction.LOGIN_BLOCKED)
    assert blocked.identifier == "BLOQ@example.com"


def test_attempt_after_lock_expires_is_a_normal_failure(make_user):
    now = timezone.now()
    make_user("vencido", locked_until=now - timedelta(minutes=1))

    services.authenticate_with_lockout(None, "vencido", WRONG_PASSWORD, now)

    assert not events(AuditAction.LOGIN_BLOCKED)
    assert len(events(AuditAction.LOGIN_FAILED)) == 1


def test_lock_is_reverted_when_its_audit_fails(monkeypatch, make_user):
    user = make_user("cobrador2", failed_login_attempts=4)

    def broken_record(*args, **kwargs):
        raise RuntimeError("auditoría caída")

    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        services.register_failed_attempt(user)

    user.refresh_from_db()
    assert user.failed_login_attempts == 4
    assert user.locked_until is None


# Contraseñas ----------------------------------------------------------------

PASSWORD_CHANGE = reverse("accounts:password_change")
PASSWORD_RESET = reverse("accounts:password_reset")
NEW_PASSWORD = "cuota2027"
RESET_LINK = re.compile(r"https?://[^/\s]+(/contrasena/restablecer/[^/\s]+/[^/\s]+/)")


def change_password(client, old: str = "cobro2026"):
    return client.post(
        PASSWORD_CHANGE,
        {
            "old_password": old,
            "new_password1": NEW_PASSWORD,
            "new_password2": NEW_PASSWORD,
        },
    )


def assert_no_password_hash(event: AuditEvent) -> None:
    stored = f"{event.changes}{event.extra}"
    assert "md5$" not in stored
    assert NEW_PASSWORD not in stored


@pytest.mark.parametrize("forced", [True, False])
def test_password_change_is_recorded(client, make_user, forced):
    user = make_user("ana", must_change_password=forced)
    client.force_login(user)

    response = change_password(client)

    assert response.status_code == 302
    [event] = events(AuditAction.PASSWORD_CHANGED)
    assert event.category == AuditCategory.ACCESS
    assert event.actor == user
    assert event.object_id == str(user.pk)
    assert event.changes == {"password": ["[oculto]", "[oculto]"]}
    assert event.extra == {"forced": forced}
    assert event.request_path == PASSWORD_CHANGE
    assert_no_password_hash(event)


def test_invalid_password_change_is_not_recorded(client, user):
    client.force_login(user)

    change_password(client, old="no-es-la-actual1")

    assert not events(AuditAction.PASSWORD_CHANGED)


def test_password_change_is_reverted_when_its_audit_fails(client, user, monkeypatch):
    def broken_record(*args, **kwargs):
        raise RuntimeError("auditoría caída")

    monkeypatch.setattr(views, "record", broken_record)
    client.force_login(user)

    with pytest.raises(RuntimeError):
        change_password(client)

    user.refresh_from_db()
    assert user.check_password("cobro2026")


def request_reset(client, email: str):
    return client.post(PASSWORD_RESET, {"email": email}, REMOTE_ADDR="10.0.0.9")


def test_reset_request_for_existing_email_is_recorded(client, make_user):
    user = make_user("ana", email="ana@example.com")

    response = request_reset(client, "Ana@Example.com")

    [event] = events(AuditAction.PASSWORD_RESET_REQUESTED)
    assert event.category == AuditCategory.ACCESS
    assert event.actor is None
    assert event.identifier == "Ana@Example.com"
    assert event.object_id == str(user.pk)
    assert event.ip_address == "10.0.0.9"
    assert response.status_code == 302


def test_reset_request_for_unknown_email_is_recorded_without_target(client):
    response = request_reset(client, "nadie@example.com")

    [event] = events(AuditAction.PASSWORD_RESET_REQUESTED)
    assert event.identifier == "nadie@example.com"
    assert event.content_type is None
    assert response.status_code == 302


def test_reset_request_answers_the_same_with_or_without_email(client, make_user):
    make_user("ana", email="ana@example.com")

    known = request_reset(client, "ana@example.com")
    unknown = request_reset(client, "nadie@example.com")

    assert known.status_code == unknown.status_code
    assert known.url == unknown.url
    assert len(events(AuditAction.PASSWORD_RESET_REQUESTED)) == 2


def test_invalid_reset_request_is_not_recorded(client):
    request_reset(client, "no-es-correo")

    assert not events(AuditAction.PASSWORD_RESET_REQUESTED)


def test_password_reset_with_the_link_is_recorded(client, make_user, mailoutbox):
    user = make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")
    link = RESET_LINK.search(mailoutbox[0].body).group(1)
    form_url = client.get(link).url

    response = client.post(
        form_url, {"new_password1": NEW_PASSWORD, "new_password2": NEW_PASSWORD}
    )

    assert response.status_code == 302
    [event] = events(AuditAction.PASSWORD_RESET_COMPLETED)
    assert event.category == AuditCategory.ACCESS
    assert event.actor == user
    assert event.object_id == str(user.pk)
    assert event.changes == {"password": ["[oculto]", "[oculto]"]}
    assert_no_password_hash(event)
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)


# Gestión de usuarios --------------------------------------------------------

NEW_USER = {
    "username": "nueva",
    "first_name": "Ana",
    "last_name": "Pérez",
    "email": "ana@example.com",
    "phone": "3001234567",
    "document_type": "CC",
    "document_number": "1020304050",
}


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def target(make_user):
    return make_user(
        "cobrador1", role=Role.COLLECTOR, first_name="Luis", email="luis@example.com"
    )


def profile_of(user: User) -> dict:
    return {field: getattr(user, field) for field in services.PROFILE_FIELDS}


def the_event(action: AuditAction) -> AuditEvent:
    [event] = events(action)
    return event


def assert_audited(event: AuditEvent, actor: User, target: User) -> None:
    assert event.category == AuditCategory.SECURITY
    assert event.actor == actor
    assert event.actor_username == actor.username
    assert event.object_id == str(target.pk)
    assert event.object_repr == target.username


def broken_record(*args, **kwargs):
    raise RuntimeError("auditoría caída")


def test_create_user_is_recorded(administrator):
    user, password = services.create_user(
        administrator, data=NEW_USER, role=Role.SUPERVISOR
    )

    event = the_event(AuditAction.USER_CREATED)
    assert_audited(event, administrator, user)
    assert event.changes == {
        "first_name": [None, "Ana"],
        "last_name": [None, "Pérez"],
        "email": [None, "ana@example.com"],
        "phone": [None, "3001234567"],
        "document_type": [None, "CC"],
        "document_number": [None, "1020304050"],
        "role": [None, "Supervisor"],
    }
    assert "password" not in event.changes
    assert password not in f"{event.changes}{event.extra}"


def test_update_user_records_only_what_changed(administrator, target):
    services.update_user(
        administrator,
        target,
        data={**profile_of(target), "first_name": "Luis Alberto"},
        role=Role.COLLECTOR,
    )

    event = the_event(AuditAction.USER_UPDATED)
    assert_audited(event, administrator, target)
    assert event.changes == {"first_name": ["Luis", "Luis Alberto"]}


def test_update_user_records_the_role_change(administrator, target):
    services.update_user(
        administrator, target, data=profile_of(target), role=Role.SUPERVISOR
    )

    event = the_event(AuditAction.USER_UPDATED)
    assert event.changes == {"role": ["Cajero/Cobrador", "Supervisor"]}


def test_update_user_without_changes_is_not_recorded(administrator, target):
    services.update_user(
        administrator, target, data=profile_of(target), role=Role.COLLECTOR
    )

    assert not events(AuditAction.USER_UPDATED)


def test_deactivate_user_is_recorded(administrator, target, client):
    client.force_login(target)

    services.deactivate_user(administrator, target, reason="  Retiro voluntario ")

    event = the_event(AuditAction.USER_DEACTIVATED)
    assert_audited(event, administrator, target)
    assert event.changes == {"is_active": [True, False]}
    assert event.extra == {"reason": "Retiro voluntario", "sessions_closed": 1}


def test_reactivate_user_is_recorded(administrator, make_user):
    user = make_user("inactivo", role=Role.VIEWER, is_active=False)

    services.reactivate_user(administrator, user)

    event = the_event(AuditAction.USER_REACTIVATED)
    assert_audited(event, administrator, user)
    assert event.changes == {
        "is_active": [False, True],
        "must_change_password": [False, True],
    }


def test_unlock_user_is_recorded(administrator, make_user):
    locked_until = timezone.now() + timedelta(minutes=10)
    user = make_user("bloqueado", failed_login_attempts=2, locked_until=locked_until)

    services.unlock_user(administrator, user)

    event = the_event(AuditAction.USER_UNLOCKED)
    assert_audited(event, administrator, user)
    assert set(event.changes) == {"failed_login_attempts", "locked_until"}
    assert event.changes["failed_login_attempts"] == [2, 0]
    assert event.changes["locked_until"][1] is None
    assert parse_datetime(event.changes["locked_until"][0]) is not None


def test_reset_user_password_is_recorded_without_the_password(
    administrator, target, client
):
    client.force_login(target)

    password = services.reset_user_password(administrator, target)

    event = the_event(AuditAction.USER_PASSWORD_RESET)
    assert_audited(event, administrator, target)
    assert event.changes == {
        "password": ["[oculto]", "[oculto]"],
        "must_change_password": [False, True],
    }
    assert event.extra == {"sessions_closed": 1}
    stored = f"{event.changes}{event.extra}"
    assert password not in stored
    assert "md5$" not in stored


def test_logout_user_sessions_is_recorded(administrator, target, client):
    client.force_login(target)

    services.logout_user_sessions(administrator, target)

    event = the_event(AuditAction.USER_SESSIONS_CLOSED)
    assert_audited(event, administrator, target)
    assert event.changes == {}
    assert event.extra == {"count": 1}


def test_create_user_is_reverted_when_its_audit_fails(administrator, monkeypatch):
    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        services.create_user(administrator, data=NEW_USER, role=Role.SUPERVISOR)

    assert not User.objects.filter(username="nueva").exists()


def test_update_user_is_reverted_when_its_audit_fails(
    administrator, target, monkeypatch
):
    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        services.update_user(
            administrator,
            target,
            data={**profile_of(target), "first_name": "Otro"},
            role=Role.SUPERVISOR,
        )

    target.refresh_from_db()
    assert target.first_name == "Luis"
    assert get_role(target) == Role.COLLECTOR


def test_deactivate_user_is_reverted_when_its_audit_fails(
    administrator, target, monkeypatch
):
    monkeypatch.setattr(services, "record", broken_record)

    with pytest.raises(RuntimeError):
        services.deactivate_user(administrator, target, reason="Retiro")

    target.refresh_from_db()
    assert target.is_active
    assert target.deactivation_reason == ""


def test_rule_errors_are_not_recorded(administrator, make_user):
    root = make_user("root", is_superuser=True)

    with pytest.raises(services.UserRuleError):
        services.deactivate_user(administrator, administrator, reason="Yo")
    with pytest.raises(services.UserRuleError):
        services.unlock_user(administrator, root)
    with pytest.raises(services.UserRuleError):
        services.deactivate_user(administrator, root, reason="")

    assert not AuditEvent.objects.filter(category=AuditCategory.SECURITY).exists()


def test_permission_errors_are_not_recorded(make_user, target):
    viewer = make_user("consulta", role=Role.VIEWER)

    with pytest.raises(PermissionDenied):
        services.create_user(viewer, data=NEW_USER, role=Role.SUPERVISOR)
    with pytest.raises(PermissionDenied):
        services.reset_user_password(viewer, target)

    assert not AuditEvent.objects.filter(category=AuditCategory.SECURITY).exists()


def test_user_action_from_the_web_has_web_source(client, administrator, target):
    client.force_login(administrator)
    url = reverse("accounts:user_unlock", args=[target.pk])

    client.post(url, REMOTE_ADDR="10.0.0.3", HTTP_USER_AGENT="Navegador/2.0")

    event = the_event(AuditAction.USER_UNLOCKED)
    assert event.source == AuditSource.WEB
    assert event.ip_address == "10.0.0.3"
    assert event.user_agent == "Navegador/2.0"
    assert event.request_method == "POST"
    assert event.request_path == url
    assert event.request_id is not None


# Admin de Django sobre usuarios ---------------------------------------------

ADMIN_USER_ADD = reverse("admin:accounts_user_add")


@pytest.fixture
def superuser():
    return User.objects.create_superuser("root", "root@example.com", "x1y2z3w4")


@pytest.fixture
def superuser_client(client, superuser):
    client.force_login(superuser)
    return client


def admin_change_data(user: User, **overrides) -> dict:
    """Los datos del formulario de edición del admin, con los valores actuales."""
    groups = list(user.groups.values_list("pk", flat=True))
    data = {
        "username": user.username,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "email": user.email,
        "is_active": "on",
        "groups": groups,
        "date_joined_0": user.date_joined.date().isoformat(),
        "date_joined_1": "10:00:00",
        "last_login_0": "",
        "last_login_1": "",
        "phone": user.phone,
        "document_type": user.document_type,
        "document_number": user.document_number,
        "deactivated_at_0": "",
        "deactivated_at_1": "",
        "deactivated_by": "",
        "deactivation_reason": "",
        "failed_login_attempts": "0",
        "locked_until_0": "",
        "locked_until_1": "",
    }
    data.update(overrides)
    return data


def test_create_user_in_admin_is_recorded(superuser_client, superuser):
    response = superuser_client.post(
        ADMIN_USER_ADD,
        {
            "username": "desde_admin",
            "email": "admin.creado@example.com",
            "usable_password": "true",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    created = User.objects.get(username="desde_admin")
    event = the_event(AuditAction.USER_CREATED)
    assert event.source == AuditSource.ADMIN
    assert event.category == AuditCategory.SECURITY
    assert event.actor == superuser
    assert event.object_id == str(created.pk)
    assert event.changes["email"] == [None, "admin.creado@example.com"]
    # El alta del admin no asigna grupos: sin rol, `role` no cambia de null.
    assert "role" not in event.changes
    assert "password" not in event.changes
    assert_no_password_hash(event)


def test_edit_user_in_admin_is_recorded_with_the_role(
    superuser_client, superuser, target
):
    url = reverse("admin:accounts_user_change", args=[target.pk])
    supervisor = Group.objects.get(name=Role.SUPERVISOR)

    response = superuser_client.post(
        url,
        admin_change_data(target, first_name="Luis Alberto", groups=[supervisor.pk]),
    )

    assert response.status_code == 302, response.context["adminform"].form.errors
    event = the_event(AuditAction.USER_UPDATED)
    assert event.source == AuditSource.ADMIN
    assert event.actor == superuser
    assert event.object_id == str(target.pk)
    assert event.changes == {
        "first_name": ["Luis", "Luis Alberto"],
        "role": ["Cajero/Cobrador", "Supervisor"],
    }
    assert event.request_path == url


def test_edit_user_in_admin_without_changes_is_not_recorded(superuser_client, target):
    url = reverse("admin:accounts_user_change", args=[target.pk])

    response = superuser_client.post(url, admin_change_data(target))

    assert response.status_code == 302
    assert not events(AuditAction.USER_UPDATED)


def test_edit_user_in_admin_is_reverted_when_its_audit_fails(
    superuser_client, target, monkeypatch
):
    monkeypatch.setattr(accounts_admin, "record", broken_record)
    url = reverse("admin:accounts_user_change", args=[target.pk])

    with pytest.raises(RuntimeError):
        superuser_client.post(url, admin_change_data(target, first_name="Otro"))

    target.refresh_from_db()
    assert target.first_name == "Luis"


def test_change_password_in_admin_is_recorded(superuser_client, superuser, target):
    url = reverse("admin:auth_user_password_change", args=[target.pk])

    response = superuser_client.post(
        url,
        {
            "usable_password": "true",
            "password1": NEW_PASSWORD,
            "password2": NEW_PASSWORD,
        },
    )

    assert response.status_code == 302
    event = the_event(AuditAction.USER_PASSWORD_RESET)
    assert event.source == AuditSource.ADMIN
    assert event.actor == superuser
    assert event.object_id == str(target.pk)
    assert event.changes == {"password": ["[oculto]", "[oculto]"]}
    assert_no_password_hash(event)


def test_invalid_password_change_in_admin_is_not_recorded(superuser_client, target):
    url = reverse("admin:auth_user_password_change", args=[target.pk])

    response = superuser_client.post(
        url, {"usable_password": "true", "password1": "a", "password2": "b"}
    )

    assert response.status_code == 200
    assert not events(AuditAction.USER_PASSWORD_RESET)


def test_change_password_in_admin_is_reverted_when_its_audit_fails(
    superuser_client, target, monkeypatch
):
    monkeypatch.setattr(accounts_admin, "record", broken_record)
    url = reverse("admin:auth_user_password_change", args=[target.pk])

    with pytest.raises(RuntimeError):
        superuser_client.post(
            url,
            {
                "usable_password": "true",
                "password1": NEW_PASSWORD,
                "password2": NEW_PASSWORD,
            },
        )

    target.refresh_from_db()
    assert target.check_password("cobro2026")
