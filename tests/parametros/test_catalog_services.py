"""Pruebas del registro de catálogos y de sus servicios (SPEC 07, §3.5 y §3.6)."""

from datetime import date

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError

from apps.parametros.catalogs import (
    CATALOGS,
    RATE_CAP_CATALOG,
    RELATION_CODEBTOR,
    RELATION_PERSONAL_REFERENCE,
    get_catalog,
)
from apps.parametros.models import (
    CatalogItem,
    CreditPurpose,
    Holiday,
    Occupation,
    ThirdPartyRelationType,
)
from apps.parametros.services import (
    CatalogRuleError,
    create_catalog_item,
    deactivate_catalog_item,
    generate_code,
    get_active_items,
    get_holidays,
    get_item_by_code,
    is_business_day,
    reactivate_catalog_item,
    update_catalog_item,
)

pytestmark = pytest.mark.django_db


# Registro


def test_catalogs_registry_has_the_six_text_catalogs_in_order():
    assert [catalog.slug for catalog in CATALOGS] == [
        "tipos-documento",
        "ocupaciones",
        "destinos-credito",
        "motivos-anulacion",
        "motivos-rechazo",
        "tipos-relacion",
    ]
    assert [catalog.order for catalog in CATALOGS] == [10, 20, 30, 40, 50, 60]
    assert len({catalog.model for catalog in CATALOGS}) == 6
    assert all(issubclass(catalog.model, CatalogItem) for catalog in CATALOGS)


def test_every_concrete_catalog_model_is_registered():
    concrete = {
        model for model in CatalogItem.__subclasses__() if not model._meta.abstract
    }

    # Los tipos de tope de tasa no están en `CATALOGS`: tienen su propia
    # pantalla con el historial de valores (SPEC 08, §3.4).
    assert concrete == {catalog.model for catalog in (*CATALOGS, RATE_CAP_CATALOG)}


def test_get_catalog_by_slug():
    catalog = get_catalog("ocupaciones")

    assert catalog.model is Occupation
    assert str(catalog.label) == "Ocupaciones"


def test_get_catalog_with_unknown_slug_raises_key_error():
    with pytest.raises(KeyError):
        get_catalog("no-existe")


def test_catalog_permission():
    assert get_catalog("ocupaciones").permission("view") == (
        "parametros.view_occupation"
    )
    assert get_catalog("tipos-relacion").permission("change") == (
        "parametros.change_thirdpartyrelationtype"
    )


# Ítems


def test_get_active_items_excludes_inactive_and_follows_display_order():
    Occupation.objects.filter(code="TENDERO").update(is_active=False)
    Occupation.objects.filter(code="OTRA").update(display_order=1)

    codes = [item.code for item in get_active_items(Occupation)]

    assert "TENDERO" not in codes
    assert codes[0] == "OTRA"
    assert codes[1:] == [
        "COMERCIANTE",
        "VENDEDOR_AMBULANTE",
        "EMPLEADO",
        "INDEPENDIENTE",
        "TRANSPORTADOR",
        "AMA_DE_CASA",
    ]


def test_get_item_by_code_returns_the_system_items():
    codebtor = get_item_by_code(ThirdPartyRelationType, RELATION_CODEBTOR)
    reference = get_item_by_code(ThirdPartyRelationType, RELATION_PERSONAL_REFERENCE)

    assert codebtor.name == "Codeudor"
    assert reference.name == "Referencia personal"


def test_get_item_by_code_also_returns_inactive_items():
    Occupation.objects.filter(code="TENDERO").update(is_active=False)

    assert get_item_by_code(Occupation, "TENDERO").is_active is False


def test_get_item_by_code_with_unknown_code_raises_does_not_exist():
    with pytest.raises(Occupation.DoesNotExist):
        get_item_by_code(Occupation, "NO_EXISTE")


# Festivos


def test_get_holidays_returns_active_holidays_of_both_origins_in_the_range():
    Holiday.objects.create(date=date(2026, 2, 14), name="Aniversario del negocio")
    Holiday.objects.create(date=date(2026, 2, 21), name="Inactivo", is_active=False)

    result = get_holidays(date(2026, 1, 1), date(2026, 3, 31))

    assert result == frozenset(
        {
            date(2026, 1, 1),
            date(2026, 1, 12),
            date(2026, 2, 14),
            date(2026, 3, 23),
        }
    )


def test_get_holidays_includes_both_ends():
    result = get_holidays(date(2026, 1, 12), date(2026, 3, 23))

    assert date(2026, 1, 12) in result
    assert date(2026, 3, 23) in result


def test_get_holidays_of_a_single_day():
    assert get_holidays(date(2026, 1, 1), date(2026, 1, 1)) == {date(2026, 1, 1)}


def test_get_holidays_of_a_year_without_load_is_empty():
    assert get_holidays(date(2031, 1, 1), date(2031, 12, 31)) == frozenset()


def test_get_holidays_with_start_after_end_raises_value_error():
    with pytest.raises(ValueError):
        get_holidays(date(2026, 2, 1), date(2026, 1, 1))


def test_get_holidays_excludes_the_inactive_coincidence_of_2030():
    july = get_holidays(date(2030, 7, 1), date(2030, 7, 31))

    assert july == {date(2030, 7, 1), date(2030, 7, 20)}


# Día hábil


def test_official_holiday_on_monday_is_not_a_business_day():
    assert is_business_day(date(2026, 1, 12)) is False


def test_sunday_is_not_a_business_day():
    assert is_business_day(date(2026, 1, 11)) is False


def test_tuesday_after_a_holiday_is_a_business_day():
    assert is_business_day(date(2026, 1, 13)) is True


def test_holiday_of_a_year_without_load_is_a_business_day():
    # Reyes Magos de 2031, pero 2031 no está cargado.
    assert date(2031, 1, 6).isoweekday() == 1
    assert is_business_day(date(2031, 1, 6)) is True


def test_custom_holiday_is_not_a_business_day():
    Holiday.objects.create(date=date(2026, 2, 14), name="Aniversario del negocio")

    assert is_business_day(date(2026, 2, 14)) is False


def test_deactivating_a_holiday_makes_the_day_a_business_day():
    assert is_business_day(date(2026, 1, 12)) is False

    Holiday.objects.filter(date=date(2026, 1, 12)).update(is_active=False)

    assert is_business_day(date(2026, 1, 12)) is True


def test_holiday_on_a_non_business_weekday_is_still_not_a_business_day():
    # 1 de noviembre de 2026: domingo (el festivo se corrió al 2).
    assert is_business_day(date(2026, 11, 1)) is False


# Edición de ítems


def purposes():
    return get_catalog("destinos-credito")


def test_create_generates_the_code_from_the_name(catalog_editor):
    item = create_catalog_item(catalog_editor, purposes(), {"name": "Pago de arriendo"})

    assert item.code == "PAGO_DE_ARRIENDO"
    assert item.name == "Pago de arriendo"
    assert item.is_active
    assert not item.is_system
    assert item.updated_by == catalog_editor


def test_create_adds_a_suffix_when_the_generated_code_exists(catalog_editor):
    item = create_catalog_item(catalog_editor, purposes(), {"name": "Capital trabajo"})
    again = create_catalog_item(
        catalog_editor, purposes(), {"name": "Capital  trabajo!"}
    )

    assert item.code == "CAPITAL_TRABAJO_2"
    assert again.code == "CAPITAL_TRABAJO_3"


def test_create_with_a_repeated_name_fails(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        create_catalog_item(catalog_editor, purposes(), {"name": "otro"})

    assert "name" in excinfo.value.message_dict


def test_create_normalizes_a_written_code(catalog_editor):
    item = create_catalog_item(
        catalog_editor,
        get_catalog("ocupaciones"),
        {"code": "vendedor_feria", "name": "Vendedor de feria"},
    )

    assert item.code == "VENDEDOR_FERIA"


@pytest.mark.parametrize("code", ["CÉDULA", "CON ESPACIO"])
def test_create_rejects_a_code_with_accent_or_space(catalog_editor, code):
    with pytest.raises(ValidationError) as excinfo:
        create_catalog_item(
            catalog_editor, get_catalog("ocupaciones"), {"code": code, "name": "X"}
        )

    assert "code" in excinfo.value.message_dict


def test_create_with_a_repeated_written_code_fails(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        create_catalog_item(
            catalog_editor, get_catalog("ocupaciones"), {"code": "tendero", "name": "X"}
        )

    assert "code" in excinfo.value.message_dict


def test_create_ignores_is_system_and_is_active(catalog_editor):
    item = create_catalog_item(
        catalog_editor,
        get_catalog("tipos-relacion"),
        {"name": "Vecino", "is_system": True, "is_active": False},
    )

    assert not item.is_system
    assert item.is_active


def test_create_without_name_fails(catalog_editor):
    with pytest.raises(ValidationError) as excinfo:
        create_catalog_item(catalog_editor, purposes(), {"name": "   "})

    assert "name" in excinfo.value.message_dict


def test_create_without_permission_is_denied(no_perms_user):
    with pytest.raises(PermissionDenied):
        create_catalog_item(no_perms_user, purposes(), {"name": "Pago de arriendo"})

    assert not CreditPurpose.objects.filter(name="Pago de arriendo").exists()


def test_update_changes_only_name_and_order(catalog_editor):
    item = Occupation.objects.get(code="TENDERO")

    updated = update_catalog_item(
        catalog_editor,
        item,
        {
            "name": "Tendero de barrio",
            "display_order": 5,
            "code": "OTRO_CODIGO",
            "is_active": False,
            "is_system": True,
        },
    )

    updated.refresh_from_db()
    assert updated.name == "Tendero de barrio"
    assert updated.display_order == 5
    assert updated.code == "TENDERO"
    assert updated.is_active
    assert not updated.is_system
    assert updated.updated_by == catalog_editor


def test_update_without_changes_does_not_save(catalog_editor):
    item = Occupation.objects.get(code="TENDERO")

    result = update_catalog_item(catalog_editor, item, {"name": " Tendero "})

    result.refresh_from_db()
    assert result.updated_at == item.updated_at
    assert result.updated_by is None


def test_update_can_rename_a_system_item(catalog_editor):
    item = get_item_by_code(ThirdPartyRelationType, RELATION_CODEBTOR)

    updated = update_catalog_item(catalog_editor, item, {"name": "Fiador"})

    assert updated.name == "Fiador"
    assert updated.code == RELATION_CODEBTOR
    assert updated.is_system


def test_update_with_a_repeated_name_fails(catalog_editor):
    item = Occupation.objects.get(code="TENDERO")

    with pytest.raises(ValidationError):
        update_catalog_item(catalog_editor, item, {"name": "comerciante"})


def test_update_without_permission_is_denied(no_perms_user):
    item = Occupation.objects.get(code="TENDERO")

    with pytest.raises(PermissionDenied):
        update_catalog_item(no_perms_user, item, {"name": "Otro nombre"})


def test_permission_of_one_catalog_does_not_open_another(make_user):
    user = make_user("solo_ocupaciones")
    user.user_permissions.add(Permission.objects.get(codename="change_occupation"))

    with pytest.raises(PermissionDenied):
        update_catalog_item(
            user, CreditPurpose.objects.get(code="OTRO"), {"name": "Otros"}
        )


def test_deactivate_and_reactivate(catalog_editor):
    item = Occupation.objects.get(code="TENDERO")

    deactivated = deactivate_catalog_item(catalog_editor, item)
    assert not Occupation.objects.get(pk=item.pk).is_active
    assert deactivated.updated_by == catalog_editor

    reactivate_catalog_item(catalog_editor, item)
    assert Occupation.objects.get(pk=item.pk).is_active


def test_deactivate_a_system_item_is_a_rule_error(catalog_editor):
    item = get_item_by_code(ThirdPartyRelationType, RELATION_CODEBTOR)

    with pytest.raises(CatalogRuleError) as excinfo:
        deactivate_catalog_item(catalog_editor, item)

    assert excinfo.value.messages == ["Un ítem de sistema no se puede desactivar."]
    assert ThirdPartyRelationType.objects.get(pk=item.pk).is_active


def test_deactivate_an_inactive_item_is_a_rule_error(catalog_editor):
    item = Occupation.objects.get(code="TENDERO")
    deactivate_catalog_item(catalog_editor, item)

    with pytest.raises(CatalogRuleError) as excinfo:
        deactivate_catalog_item(catalog_editor, item)

    assert excinfo.value.messages == ["El ítem ya está inactivo."]


def test_reactivate_an_active_item_is_a_rule_error(catalog_editor):
    with pytest.raises(CatalogRuleError) as excinfo:
        reactivate_catalog_item(catalog_editor, Occupation.objects.get(code="TENDERO"))

    assert excinfo.value.messages == ["El ítem ya está activo."]


def test_catalog_rule_error_is_a_validation_error():
    assert issubclass(CatalogRuleError, ValidationError)


@pytest.mark.parametrize("service", [deactivate_catalog_item, reactivate_catalog_item])
def test_state_changes_without_permission_are_denied(no_perms_user, service):
    with pytest.raises(PermissionDenied):
        service(no_perms_user, Occupation.objects.get(code="TENDERO"))


# Generación del código


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Pago de arriendo", "PAGO_DE_ARRIENDO"),
        ("Compra de maquinaria", "COMPRA_DE_MAQUINARIA"),
        ("Niño / niña", "NINO_NINA"),
        ("  Año 2027 ", "ANO_2027"),
        ("¡¿?!", "ITEM"),
    ],
)
def test_generate_code(name, expected):
    assert generate_code(CreditPurpose, name) == expected


def test_generate_code_never_exceeds_the_field_length():
    long_name = "Préstamo para la compra de mercancía al por mayor"
    first = generate_code(CreditPurpose, long_name)
    CreditPurpose.objects.create(code=first, name="Uno")

    second = generate_code(CreditPurpose, long_name)

    assert len(first) == 30
    assert len(second) == 30
    assert second.endswith("_2")
    assert second != first
