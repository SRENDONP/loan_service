"""Pruebas de los servicios de creación y edición de usuarios (SPEC 04, §3.5)."""

import pytest
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts import services
from apps.accounts.models import User
from apps.accounts.roles import Role, get_role
from apps.accounts.services import (
    TEMPORARY_PASSWORD_ALPHABET,
    UserRuleError,
    create_user,
    generate_temporary_password,
    update_user,
)

pytestmark = pytest.mark.django_db

AMBIGUOUS = "0Oo1lI"

NEW_USER = {
    "username": "ana",
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
def superuser(make_user):
    return make_user("root", is_superuser=True)


def group_names(user: User) -> list[str]:
    return list(user.groups.values_list("name", flat=True))


# --- Contraseña temporal ---------------------------------------------------


def test_alphabet_has_no_ambiguous_characters():
    assert not set(AMBIGUOUS) & set(TEMPORARY_PASSWORD_ALPHABET)


@pytest.mark.parametrize("attempt", range(20))
def test_temporary_password_follows_the_rules(attempt):
    password = generate_temporary_password()

    assert len(password) == 12
    assert set(password) <= set(TEMPORARY_PASSWORD_ALPHABET)
    assert any(char.isalpha() for char in password)
    assert any(char.isdigit() for char in password)
    validate_password(password)


def test_temporary_password_uses_policy_length_when_longer(global_settings):
    global_settings.password_min_length = 16
    global_settings.save()
    assert len(generate_temporary_password()) == 16


def test_temporary_password_retries_until_it_has_letters_and_digits(monkeypatch):
    # Primero solo dígitos, luego solo letras y por último una mezcla válida.
    sequence = iter("234567892345" + "abcdefghijkm" + "abcdef234567")
    monkeypatch.setattr(services.secrets, "choice", lambda alphabet: next(sequence))

    assert generate_temporary_password() == "abcdef234567"


def test_temporary_password_retries_when_validation_fails(monkeypatch):
    calls = []

    def fake_validate(password):
        calls.append(password)
        if len(calls) == 1:
            raise ValidationError("demasiado común")

    monkeypatch.setattr(services, "validate_password", fake_validate)

    password = generate_temporary_password()

    assert len(calls) == 2
    assert password == calls[1]


def test_temporary_passwords_are_different():
    assert len({generate_temporary_password() for _ in range(10)}) == 10


# --- Crear -----------------------------------------------------------------


def test_create_user_with_role_and_temporary_password(administrator):
    user, password = create_user(administrator, data=NEW_USER, role=Role.COLLECTOR)

    user.refresh_from_db()
    assert user.username == "ana"
    assert user.first_name == "Ana"
    assert user.phone == "3001234567"
    assert user.document_number == "1020304050"
    assert user.must_change_password is True
    assert user.check_password(password)
    assert group_names(user) == ["Cajero/Cobrador"]


def test_create_user_accepts_role_value(administrator):
    user, _ = create_user(administrator, data=NEW_USER, role="Consulta")

    assert get_role(user) is Role.VIEWER


def test_create_user_uppercases_document_number(administrator):
    data = {**NEW_USER, "document_type": "PA", "document_number": "ab123"}

    user, _ = create_user(administrator, data=data, role=Role.VIEWER)

    assert user.document_number == "AB123"


def test_create_user_without_permission_is_denied(make_user):
    viewer = make_user("consulta1", role=Role.VIEWER)

    with pytest.raises(PermissionDenied):
        create_user(viewer, data=NEW_USER, role=Role.VIEWER)

    assert not User.objects.filter(username="ana").exists()


@pytest.mark.parametrize(
    "change",
    [
        {"phone": "6011234567"},
        {"username": "ana@example"},
        {"document_number": ""},
        {"email": "no-es-correo"},
    ],
)
def test_create_user_with_invalid_data_creates_nothing(administrator, change):
    with pytest.raises(ValidationError):
        create_user(administrator, data={**NEW_USER, **change}, role=Role.VIEWER)

    assert not User.objects.exclude(pk=administrator.pk).exists()


def test_create_user_with_duplicate_email_fails(administrator, make_user):
    make_user("otra", email="ANA@example.com")

    with pytest.raises(ValidationError):
        create_user(administrator, data=NEW_USER, role=Role.VIEWER)


def test_create_user_with_unknown_role_fails(administrator):
    with pytest.raises(ValueError):
        create_user(administrator, data=NEW_USER, role="Gerente")

    assert not User.objects.filter(username="ana").exists()


# --- Editar ----------------------------------------------------------------


def test_update_user_changes_profile_and_ignores_username(administrator, make_user):
    target = make_user("pedro", role=Role.COLLECTOR)

    update_user(
        administrator,
        target,
        data={"username": "otro", "first_name": "Pedro", "phone": "3109876543"},
        role=Role.COLLECTOR,
    )

    target.refresh_from_db()
    assert target.username == "pedro"
    assert target.first_name == "Pedro"
    assert target.phone == "3109876543"


def test_update_user_changes_role_keeping_exactly_one_group(administrator, make_user):
    target = make_user("pedro", role=Role.COLLECTOR)

    update_user(administrator, target, data={}, role=Role.SUPERVISOR)

    assert group_names(target) == ["Supervisor"]


def test_update_user_gives_role_to_user_without_role(administrator, make_user):
    target = make_user("pedro")

    update_user(administrator, target, data={}, role=Role.VIEWER)

    assert group_names(target) == ["Consulta"]


def test_update_user_with_invalid_data_changes_nothing(administrator, make_user):
    target = make_user("pedro", role=Role.COLLECTOR, phone="3001234567")

    with pytest.raises(ValidationError):
        update_user(administrator, target, data={"phone": "123"}, role=Role.SUPERVISOR)

    target.refresh_from_db()
    assert target.phone == "3001234567"
    assert group_names(target) == ["Cajero/Cobrador"]


def test_update_user_without_permission_is_denied(make_user):
    supervisor = make_user("super1", role=Role.SUPERVISOR)
    target = make_user("pedro", role=Role.COLLECTOR)

    with pytest.raises(PermissionDenied):
        update_user(supervisor, target, data={}, role=Role.SUPERVISOR)

    assert get_role(target) is Role.COLLECTOR


def test_nobody_changes_own_role(administrator, make_user):
    make_user("admin2", role=Role.ADMINISTRATOR)

    with pytest.raises(UserRuleError, match="No puedes cambiar tu propio rol."):
        update_user(administrator, administrator, data={}, role=Role.VIEWER)

    assert get_role(administrator) is Role.ADMINISTRATOR


def test_user_can_edit_own_data_keeping_role(administrator):
    update_user(
        administrator,
        administrator,
        data={"first_name": "Nuevo", "phone": "3001112233"},
        role=Role.ADMINISTRATOR,
    )

    administrator.refresh_from_db()
    assert administrator.first_name == "Nuevo"
    assert get_role(administrator) is Role.ADMINISTRATOR


@pytest.mark.parametrize("actor_name", ["administrator", "superuser"])
def test_superuser_cannot_be_edited(request, actor_name, make_user):
    actor = request.getfixturevalue(actor_name)
    target = make_user("root2", is_superuser=True, first_name="Root")

    with pytest.raises(UserRuleError, match="superusuarios"):
        update_user(actor, target, data={"first_name": "X"}, role=Role.VIEWER)

    target.refresh_from_db()
    assert target.first_name == "Root"


def test_last_administrator_keeps_role_even_with_active_superuser(
    administrator, superuser
):
    with pytest.raises(UserRuleError, match="al menos un administrador activo"):
        update_user(superuser, administrator, data={}, role=Role.SUPERVISOR)

    assert get_role(administrator) is Role.ADMINISTRATOR


def test_inactive_administrator_does_not_count(administrator, superuser, make_user):
    make_user("admin_inactivo", role=Role.ADMINISTRATOR, is_active=False)

    with pytest.raises(UserRuleError):
        update_user(superuser, administrator, data={}, role=Role.SUPERVISOR)


def test_administrator_can_change_role_of_another_administrator(
    administrator, make_user
):
    other = make_user("admin2", role=Role.ADMINISTRATOR)

    update_user(administrator, other, data={}, role=Role.SUPERVISOR)

    assert get_role(other) is Role.SUPERVISOR


def test_inactive_administrator_role_can_change(administrator, make_user):
    inactive = make_user("admin2", role=Role.ADMINISTRATOR, is_active=False)

    update_user(administrator, inactive, data={}, role=Role.VIEWER)

    assert get_role(inactive) is Role.VIEWER
