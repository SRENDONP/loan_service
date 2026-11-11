"""Pruebas de los datos nuevos del usuario (SPEC 04, §3.2 y paso 1)."""

from datetime import timedelta

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts.models import DocumentType, User
from apps.accounts.validators import (
    colombian_mobile_validator,
    document_number_validator,
)


@pytest.mark.parametrize("phone", ["3001234567", "3209876543"])
def test_valid_colombian_mobile(phone):
    colombian_mobile_validator(phone)


@pytest.mark.parametrize(
    "phone", ["300123456", "30012345678", "6011234567", "300-123-4567", "300 1234567"]
)
def test_invalid_colombian_mobile(phone):
    with pytest.raises(ValidationError):
        colombian_mobile_validator(phone)


@pytest.mark.parametrize("number", ["123", "1020304050", "AB12345", "x" * 20])
def test_valid_document_number(number):
    document_number_validator(number)


@pytest.mark.parametrize("number", ["12", "1.020.304", "10 20 30", "x" * 21, "12-3"])
def test_invalid_document_number(number):
    with pytest.raises(ValidationError):
        document_number_validator(number)


@pytest.mark.django_db
def test_full_clean_uppercases_document_number():
    user = User(username="ana", document_type=DocumentType.PA, document_number="ab123")
    user.set_unusable_password()

    user.full_clean()

    assert user.document_number == "AB123"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("document_type", "document_number"), [(DocumentType.CC, ""), ("", "123456")]
)
def test_document_must_be_complete(document_type, document_number):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        User.objects.create_user(
            "ana", document_type=document_type, document_number=document_number
        )

    assert "accounts_user_document_complete" in str(excinfo.value)


@pytest.mark.django_db
def test_incomplete_document_has_spanish_message_on_full_clean():
    user = User(username="ana", document_type=DocumentType.CC)
    user.set_unusable_password()

    with pytest.raises(ValidationError) as excinfo:
        user.full_clean()

    assert (
        "Escribe el tipo y el número de documento, o deja los dos vacíos."
        in excinfo.value.messages
    )


@pytest.mark.django_db
def test_document_type_and_number_are_unique():
    User.objects.create_user("ana", document_type="CC", document_number="123456")

    with pytest.raises(IntegrityError), transaction.atomic():
        User.objects.create_user("ana2", document_type="CC", document_number="123456")


@pytest.mark.django_db
def test_same_number_with_other_type_is_allowed():
    User.objects.create_user("ana", document_type="CC", document_number="123456")
    User.objects.create_user("ana2", document_type="CE", document_number="123456")

    assert User.objects.filter(document_number="123456").count() == 2


@pytest.mark.django_db
def test_duplicate_document_has_spanish_message_on_full_clean():
    User.objects.create_user("ana", document_type="CC", document_number="123456")
    duplicate = User(username="ana2", document_type="CC", document_number="123456")
    duplicate.set_unusable_password()

    with pytest.raises(ValidationError) as excinfo:
        duplicate.full_clean()

    assert (
        "Ya existe un usuario con este tipo y número de documento."
        in excinfo.value.messages
    )


@pytest.mark.django_db
def test_several_users_without_document_are_allowed():
    User.objects.create_user("sin_doc_1")
    User.objects.create_user("sin_doc_2")

    assert User.objects.filter(document_number="").count() == 2


@pytest.mark.django_db
def test_status_active_locked_and_inactive(make_user):
    user = make_user()
    assert user.status == "active"

    user.locked_until = timezone.now() + timedelta(minutes=5)
    assert user.status == "locked"

    user.locked_until = timezone.now() - timedelta(minutes=5)
    assert user.status == "active"

    user.locked_until = timezone.now() + timedelta(minutes=5)
    user.is_active = False
    assert user.status == "inactive"


@pytest.mark.django_db
def test_user_permissions_exist_without_delete():
    codenames = set(
        Permission.objects.filter(content_type__app_label="accounts").values_list(
            "codename", flat=True
        )
    )

    assert {
        "view_user",
        "add_user",
        "change_user",
        "deactivate_user",
        "unlock_user",
        "reset_user_password",
        "logout_user_sessions",
    } <= codenames
    assert User._meta.default_permissions == ("add", "change", "view")
