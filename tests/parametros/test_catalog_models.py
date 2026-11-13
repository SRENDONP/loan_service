"""Pruebas de los modelos de catálogos y festivos (SPEC 07, §3.1 y §3.2)."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, connection, transaction

from apps.parametros.models import (
    CatalogItem,
    CreditPurpose,
    DocumentType,
    Holiday,
    HolidayOrigin,
    Occupation,
    RejectionReason,
    ThirdPartyRelationType,
    VoidReason,
)

pytestmark = pytest.mark.django_db

CATALOG_MODELS = [
    DocumentType,
    Occupation,
    CreditPurpose,
    VoidReason,
    RejectionReason,
    ThirdPartyRelationType,
]
ALL_MODELS = [*CATALOG_MODELS, Holiday]

# Una fecha fuera de la carga inicial, para no chocar con los festivos oficiales.
FREE_DAY = date(2040, 3, 14)


def errors_of(instance) -> dict[str, list[str]]:
    with pytest.raises(ValidationError) as excinfo:
        instance.full_clean()
    return excinfo.value.message_dict


def official(**fields) -> Holiday:
    values = {
        "date": FREE_DAY,
        "name": "Festivo de prueba",
        "origin": HolidayOrigin.OFFICIAL,
        "official_code": "prueba",
        "official_year": 2040,
    }
    values.update(fields)
    return Holiday(**values)


# Catálogos de texto


@pytest.mark.parametrize("model", CATALOG_MODELS)
def test_catalogs_are_concrete_subclasses_of_the_base(model):
    assert issubclass(model, CatalogItem)
    assert not model._meta.abstract
    assert model._meta.app_label == "parametros"


@pytest.mark.parametrize("model", CATALOG_MODELS)
def test_code_is_unique_in_its_catalog(model):
    model.objects.create(code="PRUEBA", name="Prueba uno")

    with pytest.raises(IntegrityError), transaction.atomic():
        model.objects.create(code="PRUEBA", name="Prueba dos")


@pytest.mark.parametrize("model", CATALOG_MODELS)
def test_name_is_unique_ignoring_case(model):
    model.objects.create(code="PRUEBA_1", name="Ítem de prueba")

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        model.objects.create(code="PRUEBA_2", name="ÍTEM DE PRUEBA")

    assert f"parametros_{model._meta.model_name}_unique_name" in str(excinfo.value)


def test_same_code_and_name_are_allowed_in_different_catalogs():
    Occupation.objects.create(code="PRUEBA", name="Prueba")
    CreditPurpose.objects.create(code="PRUEBA", name="Prueba")

    assert Occupation.objects.filter(code="PRUEBA").exists()
    assert CreditPurpose.objects.filter(code="PRUEBA").exists()


def test_full_clean_reports_a_repeated_name_on_the_field():
    Occupation.objects.create(code="PRUEBA_1", name="Ítem de prueba")

    errors = errors_of(Occupation(code="PRUEBA_2", name="  ítem de prueba "))

    assert errors["name"] == ["Ya existe un ítem con ese nombre."]


def test_full_clean_allows_saving_the_same_item_again():
    item = Occupation.objects.create(code="PRUEBA", name="Ítem de prueba")

    item.full_clean()


def test_clean_normalizes_code_and_name():
    item = Occupation(code="  vendedor_feria ", name="  Vendedor de feria  ")

    item.full_clean()

    assert item.code == "VENDEDOR_FERIA"
    assert item.name == "Vendedor de feria"


@pytest.mark.parametrize("code", ["CÉDULA", "CON ESPACIO", "GUION-MEDIO", ""])
def test_invalid_codes_are_rejected(code):
    errors = errors_of(Occupation(code=code, name="Prueba"))

    assert "code" in errors


def test_blank_name_is_rejected():
    errors = errors_of(Occupation(code="PRUEBA", name="   "))

    assert errors["name"] == ["Escribe el nombre."]


def test_system_item_cannot_be_inactive_in_the_application():
    item = ThirdPartyRelationType(code="PRUEBA", name="Prueba", is_system=True)
    item.is_active = False

    errors = errors_of(item)

    assert errors["__all__"] == ["Un ítem de sistema siempre está activo."]


def test_system_item_cannot_be_deactivated_by_sql():
    item = ThirdPartyRelationType.objects.create(
        code="PRUEBA", name="Prueba", is_system=True
    )

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(
                "UPDATE parametros_thirdpartyrelationtype "
                "SET is_active = false WHERE id = %s",
                [item.pk],
            )

    assert "parametros_thirdpartyrelationtype_system_active" in str(excinfo.value)


def test_active_returns_only_active_items_in_catalog_order():
    Occupation.objects.all().update(is_active=False)
    second = Occupation.objects.create(code="B", name="Bravo", display_order=20)
    first = Occupation.objects.create(code="A", name="Alfa", display_order=10)
    Occupation.objects.create(code="C", name="Charlie", is_active=False)

    assert list(Occupation.objects.active()) == [first, second]


def test_items_with_the_same_order_are_sorted_by_name():
    Occupation.objects.all().update(is_active=False)
    zulu = Occupation.objects.create(code="Z", name="Zulú", display_order=5)
    alfa = Occupation.objects.create(code="A", name="Alfa", display_order=5)

    assert list(Occupation.objects.active()) == [alfa, zulu]


def test_item_str_is_its_name():
    assert str(Occupation(code="PRUEBA", name="Prueba")) == "Prueba"


@pytest.mark.parametrize("model", CATALOG_MODELS)
def test_item_delete_is_rejected(model):
    item = model.objects.create(code="PRUEBA", name="Prueba")

    with pytest.raises(PermissionDenied):
        item.delete()

    assert model.objects.filter(pk=item.pk).exists()


# Festivos


def test_custom_holiday_by_default():
    holiday = Holiday.objects.create(date=FREE_DAY, name="Día del negocio")

    assert holiday.origin == HolidayOrigin.CUSTOM
    assert holiday.official_code == ""
    assert holiday.official_year is None
    assert holiday.is_active


def test_two_active_holidays_on_the_same_date_fail():
    Holiday.objects.create(date=FREE_DAY, name="Uno")

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        Holiday.objects.create(date=FREE_DAY, name="Dos")

    assert "parametros_holiday_unique_active_date" in str(excinfo.value)


def test_an_active_and_an_inactive_holiday_on_the_same_date_are_allowed():
    Holiday.objects.create(date=FREE_DAY, name="Uno")
    Holiday.objects.create(date=FREE_DAY, name="Dos", is_active=False)

    assert Holiday.objects.filter(date=FREE_DAY).count() == 2


def test_full_clean_reports_an_occupied_date_with_the_date():
    Holiday.objects.create(date=FREE_DAY, name="Uno")

    errors = errors_of(Holiday(date=FREE_DAY, name="Dos"))

    assert errors["date"] == ["Ya hay un festivo activo el 14/03/2040."]


def test_full_clean_allows_an_inactive_holiday_on_an_occupied_date():
    Holiday.objects.create(date=FREE_DAY, name="Uno")

    Holiday(date=FREE_DAY, name="Dos", is_active=False).full_clean()


def test_full_clean_allows_saving_the_same_holiday_again():
    holiday = Holiday.objects.create(date=FREE_DAY, name="Uno")

    holiday.full_clean()


def test_holiday_blank_name_is_rejected():
    errors = errors_of(Holiday(date=FREE_DAY, name="  "))

    assert errors["name"] == ["Escribe el nombre."]


def test_official_holiday_is_unique_by_year_and_code():
    official().save()

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        official(date=date(2040, 3, 15)).save()

    assert "parametros_holiday_unique_official" in str(excinfo.value)


def test_custom_holidays_do_not_take_part_in_the_official_uniqueness():
    Holiday.objects.create(date=FREE_DAY, name="Uno")
    Holiday.objects.create(date=date(2040, 3, 15), name="Dos")

    assert Holiday.objects.filter(origin=HolidayOrigin.CUSTOM).count() >= 2


@pytest.mark.parametrize(
    "fields",
    [
        {"origin": HolidayOrigin.CUSTOM, "official_code": "prueba"},
        {"origin": HolidayOrigin.CUSTOM, "official_year": 2040},
        {"origin": HolidayOrigin.OFFICIAL, "official_year": None},
        {"origin": HolidayOrigin.OFFICIAL, "official_code": ""},
    ],
)
def test_origin_fields_must_match_the_origin(fields):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        official(**fields).save()

    assert "parametros_holiday_origin_fields" in str(excinfo.value)


def test_holiday_str():
    assert str(Holiday(date=FREE_DAY, name="Uno")) == "Uno (2040-03-14)"


def test_holiday_delete_is_rejected():
    holiday = Holiday.objects.create(date=FREE_DAY, name="Uno")

    with pytest.raises(PermissionDenied):
        holiday.delete()

    assert Holiday.objects.filter(pk=holiday.pk).exists()


# Permisos


@pytest.mark.parametrize("model", ALL_MODELS)
def test_tables_only_have_view_add_and_change_permissions(model):
    codenames = set(
        Permission.objects.filter(
            content_type__app_label="parametros",
            content_type__model=model._meta.model_name,
        ).values_list("codename", flat=True)
    )
    name = model._meta.model_name

    assert codenames == {f"view_{name}", f"add_{name}", f"change_{name}"}
