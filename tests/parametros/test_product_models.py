"""Pruebas de los modelos de productos de crédito y tasas (SPEC 08, §3.1 a §3.4)."""

from datetime import date, timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.parametros.catalogs import RATE_CAP_USURY
from apps.parametros.models import (
    CatalogItem,
    CreditProduct,
    InitialChargeType,
    InterestMethod,
    Periodicity,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
    RateUnit,
    RoundingMode,
)

pytestmark = pytest.mark.django_db

ALL_PERIODICITIES = [
    Periodicity.DAILY,
    Periodicity.WEEKLY,
    Periodicity.BIWEEKLY,
    Periodicity.MONTHLY,
]
PRODUCT_MODELS = [CreditProduct, ProductRateVersion, RateCapType, RateCapValue]


def product_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "Diario 20",
        "interest_method": InterestMethod.FLAT_PER_CREDIT,
        "allowed_periodicities": list(ALL_PERIODICITIES),
        "default_periodicity": Periodicity.DAILY,
        "min_amount": Decimal("50000"),
        "max_amount": Decimal("2000000"),
        "min_installments": 10,
        "default_installments": 20,
        "max_installments": 40,
        "late_fee_daily_rate": Decimal("1"),
        "late_fee_cap_percent": Decimal("20"),
        "write_off_min_days_past_due": 90,
    }
    data.update(overrides)
    return data


def product(**overrides: Any) -> CreditProduct:
    return CreditProduct(**product_data(**overrides))


def errors_of(instance) -> dict[str, list[str]]:
    with pytest.raises(ValidationError) as excinfo:
        instance.full_clean()
    return excinfo.value.message_dict


def assert_field_error(instance, field: str, message: str | None = None) -> None:
    errors = errors_of(instance)
    assert field in errors, errors
    assert "__all__" not in errors, errors
    if message is not None:
        assert errors[field] == [message]


def assert_db_rejects(constraint: str | tuple[str, ...], **overrides: Any) -> None:
    """
    El `CHECK` rechaza los datos aunque no pasen por `full_clean()`.

    Si los datos rompen varias reglas a la vez, PostgreSQL informa solo una:
    `constraint` puede ser una tupla con las aceptables.
    """
    names = (constraint,) if isinstance(constraint, str) else constraint
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        CreditProduct.objects.create(**product_data(**overrides))
    message = str(excinfo.value)
    assert any(f"parametros_creditproduct_{name}" in message for name in names)


def usury() -> RateCapType:
    """La usura de sistema que crea la migración 0007."""
    return RateCapType.objects.get(code=RATE_CAP_USURY)


# El producto válido


def test_valid_product_passes_full_clean_and_saves():
    item = product()

    item.full_clean()
    item.save()

    assert item.is_active
    assert item.default_grace_periods == 0
    assert item.initial_charge_type == InitialChargeType.NONE
    assert item.initial_charge_value == Decimal("0")
    assert item.max_active_credits_per_client == 1
    assert item.rounding_multiple is None
    assert item.additional_rate_cap is None


def test_product_str_is_its_name():
    assert str(product()) == "Diario 20"


# Nombre


def test_name_is_stripped_and_required():
    item = product(name="  Semanal  ")
    item.full_clean()
    assert item.name == "Semanal"

    assert_field_error(product(name="   "), "name", "Escribe el nombre del producto.")


def test_name_is_unique_ignoring_case_in_the_application():
    CreditProduct.objects.create(**product_data())

    assert_field_error(
        product(name=" DIARIO 20 "), "name", "Ya existe un producto con ese nombre."
    )


def test_name_is_unique_ignoring_case_in_the_database():
    CreditProduct.objects.create(**product_data())

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        CreditProduct.objects.create(**product_data(name="diario 20"))

    assert "parametros_creditproduct_unique_name" in str(excinfo.value)


def test_saving_the_same_product_again_passes():
    item = CreditProduct.objects.create(**product_data())

    item.full_clean()


# Monto


def test_max_amount_below_min_fails():
    assert_field_error(
        product(min_amount=Decimal("100000"), max_amount=Decimal("99999")),
        "max_amount",
        "El monto máximo no puede ser menor que el mínimo.",
    )
    assert_db_rejects(
        "amount_range", min_amount=Decimal("100000"), max_amount=Decimal("99999")
    )


def test_min_amount_must_be_positive():
    assert_field_error(
        product(min_amount=Decimal("0")),
        "min_amount",
        "El monto mínimo debe ser mayor que cero.",
    )
    assert_db_rejects("amount_range", min_amount=Decimal("0"))


def test_equal_min_and_max_amount_is_allowed():
    product(min_amount=Decimal("50000"), max_amount=Decimal("50000")).full_clean()


# Cuotas


@pytest.mark.parametrize(
    ("low", "default", "high", "field"),
    [
        (10, 5, 20, "default_installments"),
        (10, 30, 20, "max_installments"),
        (0, 5, 10, "min_installments"),
        (1, 5, 1000, "max_installments"),
    ],
)
def test_installments_out_of_order_fail_on_their_field(low, default, high, field):
    item = product(
        min_installments=low,
        default_installments=default,
        max_installments=high,
        max_grace_periods=0,
    )

    assert_field_error(item, field)


@pytest.mark.parametrize(
    ("low", "default", "high"),
    [(10, 5, 20), (10, 30, 20), (0, 5, 10), (1, 5, 1000)],
)
def test_installments_out_of_order_fail_in_the_database(low, default, high):
    # Con cero cuotas mínimas, la gracia (0) tampoco es menor que ellas.
    assert_db_rejects(
        ("installments_range", "grace_range"),
        min_installments=low,
        default_installments=default,
        max_installments=high,
    )


def test_single_installment_and_999_are_allowed():
    product(
        min_installments=1, default_installments=1, max_installments=999
    ).full_clean()


# Periodicidades


def test_default_periodicity_must_be_allowed():
    item = product(
        allowed_periodicities=[Periodicity.WEEKLY],
        default_periodicity=Periodicity.DAILY,
    )

    assert_field_error(
        item,
        "default_periodicity",
        "La periodicidad por defecto tiene que estar entre las permitidas.",
    )
    assert_db_rejects(
        "default_periodicity_allowed",
        allowed_periodicities=[Periodicity.WEEKLY],
        default_periodicity=Periodicity.DAILY,
    )


def test_periodicities_cannot_be_empty():
    assert_field_error(product(allowed_periodicities=[]), "allowed_periodicities")
    # Una lista vacía tampoco contiene la periodicidad por defecto.
    assert_db_rejects(
        ("periodicities_valid", "default_periodicity_allowed"),
        allowed_periodicities=[],
    )


def test_periodicities_cannot_repeat():
    item = product(allowed_periodicities=[Periodicity.DAILY, Periodicity.DAILY])

    assert_field_error(item, "allowed_periodicities", "No repitas periodicidades.")


def test_unknown_periodicity_fails_in_the_database():
    assert_db_rejects(
        "periodicities_valid", allowed_periodicities=[Periodicity.DAILY, "yearly"]
    )


def test_per_period_method_with_two_periodicities_fails():
    item = product(
        interest_method=InterestMethod.FLAT_PER_INSTALLMENT,
        allowed_periodicities=[Periodicity.DAILY, Periodicity.WEEKLY],
    )

    assert_field_error(
        item,
        "allowed_periodicities",
        "Con el método Plano por cuota, la tasa es por periodo y el producto "
        "admite una sola periodicidad.",
    )
    assert_db_rejects(
        "per_period_single_periodicity",
        interest_method=InterestMethod.FLAT_PER_INSTALLMENT,
        allowed_periodicities=[Periodicity.DAILY, Periodicity.WEEKLY],
    )


def test_per_period_method_with_one_periodicity_saves():
    item = product(
        interest_method=InterestMethod.FRENCH,
        allowed_periodicities=[Periodicity.WEEKLY],
        default_periodicity=Periodicity.WEEKLY,
    )

    item.full_clean()
    item.save()


def test_flat_per_credit_with_the_four_periodicities_saves():
    item = product(interest_method=InterestMethod.FLAT_PER_CREDIT)

    item.full_clean()
    item.save()

    assert item.allowed_periodicities == ALL_PERIODICITIES


# Gracia


@pytest.mark.parametrize("max_grace", [10, 11])
def test_max_grace_must_be_less_than_min_installments(max_grace):
    item = product(min_installments=10, max_grace_periods=max_grace)

    assert_field_error(
        item,
        "max_grace_periods",
        "Los periodos de gracia tienen que ser menos que las cuotas mínimas.",
    )
    assert_db_rejects("grace_range", min_installments=10, max_grace_periods=max_grace)


def test_default_grace_cannot_exceed_max():
    item = product(default_grace_periods=3, max_grace_periods=2)

    assert_field_error(item, "default_grace_periods")
    assert_db_rejects("grace_range", default_grace_periods=3, max_grace_periods=2)


def test_grace_below_min_installments_is_allowed():
    product(default_grace_periods=1, max_grace_periods=9).full_clean()


# Mora y castigo


@pytest.mark.parametrize("field", ["late_fee_daily_rate", "late_fee_cap_percent"])
def test_late_fee_percentages_go_up_to_100(field):
    product(**{field: Decimal("100")}).full_clean()
    product(**{field: Decimal("0")}).full_clean()

    assert_field_error(product(**{field: Decimal("100.0001")}), field)
    assert_field_error(product(**{field: Decimal("-0.0001")}), field)
    assert_db_rejects("late_fee_range", **{field: Decimal("101")})


def test_late_tolerance_goes_up_to_90_days():
    product(late_tolerance_days=90).full_clean()

    assert_field_error(product(late_tolerance_days=91), "late_tolerance_days")
    assert_db_rejects("late_tolerance_range", late_tolerance_days=91)


def test_write_off_needs_at_least_one_day():
    product(write_off_min_days_past_due=1).full_clean()

    assert_field_error(
        product(write_off_min_days_past_due=0), "write_off_min_days_past_due"
    )
    assert_db_rejects("write_off_days_min", write_off_min_days_past_due=0)


# Gasto inicial


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (InitialChargeType.NONE, Decimal("5")),
        (InitialChargeType.FIXED, Decimal("0")),
        (InitialChargeType.FIXED, Decimal("50000")),
        (InitialChargeType.FIXED, Decimal("60000")),
        (InitialChargeType.PERCENT, Decimal("0")),
        (InitialChargeType.PERCENT, Decimal("100")),
    ],
)
def test_invalid_initial_charge_fails(kind, value):
    item = product(initial_charge_type=kind, initial_charge_value=value)

    assert_field_error(item, "initial_charge_value")
    assert_db_rejects(
        "initial_charge_value", initial_charge_type=kind, initial_charge_value=value
    )


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (InitialChargeType.NONE, Decimal("0")),
        (InitialChargeType.FIXED, Decimal("49999.99")),
        (InitialChargeType.PERCENT, Decimal("5")),
        (InitialChargeType.PERCENT, Decimal("99.99")),
    ],
)
def test_valid_initial_charge_passes(kind, value):
    product(initial_charge_type=kind, initial_charge_value=value).full_clean()


# Límite y redondeo


def test_active_credits_limit_needs_at_least_one():
    assert_field_error(
        product(max_active_credits_per_client=0), "max_active_credits_per_client"
    )
    assert_db_rejects("max_active_credits_min", max_active_credits_per_client=0)


@pytest.mark.parametrize(
    ("multiple", "mode"), [(100, None), (None, RoundingMode.UP), (100, "")]
)
def test_rounding_needs_both_or_none(multiple, mode):
    item = product(rounding_multiple=multiple, rounding_mode=mode)

    assert_field_error(
        item,
        "rounding_mode",
        "Elige el múltiplo y el modo, o deja los dos vacíos para usar el redondeo "
        "global.",
    )


@pytest.mark.parametrize(("multiple", "mode"), [(100, None), (None, RoundingMode.UP)])
def test_rounding_pair_is_enforced_by_the_database(multiple, mode):
    assert_db_rejects("rounding_pair", rounding_multiple=multiple, rounding_mode=mode)


def test_rounding_with_both_values_passes():
    product(rounding_multiple=100, rounding_mode=RoundingMode.UP).full_clean()


def test_rounding_multiple_must_be_from_the_list():
    assert_field_error(
        product(rounding_multiple=7, rounding_mode=RoundingMode.UP),
        "rounding_multiple",
    )


# Tope adicional


def test_usury_cannot_be_the_additional_cap():
    item = product(additional_rate_cap=usury())

    assert_field_error(
        item, "additional_rate_cap", "La usura ya aplica a todos los productos."
    )


def test_active_cap_can_be_the_additional_cap():
    cap = RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")

    product(additional_rate_cap=cap).full_clean()


def test_inactive_cap_cannot_be_assigned():
    cap = RateCapType.objects.create(
        code="TOPE_INTERNO", name="Tope interno", is_active=False
    )

    assert_field_error(
        product(additional_rate_cap=cap),
        "additional_rate_cap",
        "Ese tope está inactivo.",
    )

    item = CreditProduct.objects.create(**product_data())
    item.additional_rate_cap = cap
    assert_field_error(item, "additional_rate_cap", "Ese tope está inactivo.")


def test_cap_deactivated_after_being_assigned_keeps_the_product_valid():
    cap = RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")
    item = CreditProduct.objects.create(**product_data(additional_rate_cap=cap))
    RateCapType.objects.filter(pk=cap.pk).update(is_active=False)
    item.refresh_from_db()

    item.full_clean()


# Unidad de la tasa


@pytest.mark.parametrize(
    ("method", "unit"),
    [
        (InterestMethod.FLAT_PER_CREDIT, RateUnit.PER_CREDIT),
        (InterestMethod.FLAT_MONTHLY_PRORATED, RateUnit.MONTHLY),
        (InterestMethod.FLAT_PER_INSTALLMENT, RateUnit.PER_PERIOD),
        (InterestMethod.FRENCH, RateUnit.PER_PERIOD),
        (InterestMethod.GERMAN, RateUnit.PER_PERIOD),
        (InterestMethod.DECLINING_BALANCE, RateUnit.PER_PERIOD),
    ],
)
def test_rate_unit_comes_from_the_method(method, unit):
    assert product(interest_method=method).rate_unit == unit


def test_choice_values_are_the_engine_contract():
    assert InterestMethod.values == [
        "flat_per_credit",
        "flat_monthly_prorated",
        "flat_per_installment",
        "french",
        "german",
        "declining_balance",
    ]
    assert Periodicity.values == ["daily", "weekly", "biweekly", "monthly"]
    assert RateUnit.values == ["per_credit", "monthly", "per_period"]
    assert InitialChargeType.values == ["none", "fixed", "percent"]


# Versiones de tasa


@pytest.fixture
def saved_product() -> CreditProduct:
    return CreditProduct.objects.create(**product_data())


def rate_version(saved_product, user, **overrides: Any) -> ProductRateVersion:
    values: dict[str, Any] = {
        "product": saved_product,
        "valid_from": date(2026, 11, 13),
        "min_rate": Decimal("10"),
        "default_rate": Decimal("20"),
        "max_rate": Decimal("25"),
        "created_by": user,
    }
    values.update(overrides)
    return ProductRateVersion(**values)


def test_valid_rate_version_saves(saved_product, user):
    version = rate_version(saved_product, user)

    version.full_clean()
    version.save()

    assert version.valid_to is None
    assert not version.is_voided
    assert str(version) == "Diario 20 (2026-11-13)"


def test_rates_out_of_order_fail(saved_product, user):
    errors = errors_of(rate_version(saved_product, user, min_rate=Decimal("21")))
    assert errors["default_rate"] == [
        "La tasa por defecto no puede ser menor que la mínima."
    ]

    errors = errors_of(rate_version(saved_product, user, max_rate=Decimal("19")))
    assert errors["max_rate"] == [
        "La tasa máxima no puede ser menor que la de por defecto."
    ]


def test_max_rate_above_100_fails(saved_product, user):
    errors = errors_of(rate_version(saved_product, user, max_rate=Decimal("100.0001")))

    assert "max_rate" in errors


def test_rates_at_zero_save(saved_product, user):
    version = rate_version(
        saved_product,
        user,
        min_rate=Decimal("0"),
        default_rate=Decimal("0"),
        max_rate=Decimal("0"),
    )

    version.full_clean()
    version.save()


@pytest.mark.parametrize(
    "rates",
    [
        {"min_rate": Decimal("21")},
        {"max_rate": Decimal("19")},
        {"max_rate": Decimal("101")},
        {"min_rate": Decimal("-1")},
    ],
)
def test_rate_range_is_enforced_by_the_database(saved_product, user, rates):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        rate_version(saved_product, user, **rates).save()

    assert "parametros_productrateversion_rate_range" in str(excinfo.value)


def test_two_live_versions_from_the_same_day_fail(saved_product, user):
    rate_version(saved_product, user).save()

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        rate_version(saved_product, user).save()

    assert "parametros_productrateversion_unique_from" in str(excinfo.value)


def test_a_voided_version_does_not_block_its_date(saved_product, user):
    rate_version(saved_product, user, voided_at=timezone.now(), voided_by=user).save()

    rate_version(saved_product, user).save()


def test_voided_at_and_voided_by_go_together(saved_product, user):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        rate_version(saved_product, user, voided_at=timezone.now()).save()

    assert "parametros_productrateversion_voided_pair" in str(excinfo.value)


def test_valid_to_cannot_be_before_valid_from(saved_product, user):
    version = rate_version(saved_product, user)
    version.valid_to = version.valid_from - timedelta(days=1)

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        version.save()

    assert "parametros_productrateversion_valid_to_after_from" in str(excinfo.value)


# Tipos y valores de tope


def test_rate_cap_type_is_a_catalog():
    assert issubclass(RateCapType, CatalogItem)
    assert not RateCapType._meta.abstract


def cap_value(user, **overrides: Any) -> RateCapValue:
    values: dict[str, Any] = {
        "cap_type": RateCapType.objects.get_or_create(
            code="TOPE_INTERNO", defaults={"name": "Tope interno"}
        )[0],
        "valid_from": date(2026, 11, 13),
        "annual_effective_rate": Decimal("25.5"),
        "reference": "  Resolución 1234 de 2026  ",
        "created_by": user,
    }
    values.update(overrides)
    return RateCapValue(**values)


def test_valid_cap_value_saves_with_stripped_reference(user):
    value = cap_value(user)

    value.full_clean()
    value.save()

    assert value.reference == "Resolución 1234 de 2026"
    assert str(value) == "Tope interno (2026-11-13)"


def test_cap_value_of_zero_fails(user):
    errors = errors_of(cap_value(user, annual_effective_rate=Decimal("0")))

    assert errors["annual_effective_rate"] == [
        "El valor del tope debe ser mayor que cero."
    ]


def test_cap_value_goes_up_to_9999_9999(user):
    cap_value(user, annual_effective_rate=Decimal("9999.9999")).full_clean()

    errors = errors_of(cap_value(user, annual_effective_rate=Decimal("10000")))
    assert "annual_effective_rate" in errors


@pytest.mark.parametrize("rate", [Decimal("0"), Decimal("10000")])
def test_cap_value_range_is_enforced_by_the_database(user, rate):
    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        cap_value(user, annual_effective_rate=rate).save()

    assert "parametros_ratecapvalue_rate_range" in str(excinfo.value)


def test_two_live_cap_values_from_the_same_day_fail(user):
    cap_value(user).save()

    with pytest.raises(IntegrityError) as excinfo, transaction.atomic():
        cap_value(user).save()

    assert "parametros_ratecapvalue_unique_from" in str(excinfo.value)


# Borrado y permisos


def test_delete_is_rejected_for_the_four_models(saved_product, user):
    version = rate_version(saved_product, user)
    version.save()
    value = cap_value(user)
    value.save()
    instances = [saved_product, version, value.cap_type, value]

    for instance in instances:
        with pytest.raises(PermissionDenied):
            instance.delete()

    for instance in instances:
        assert type(instance).objects.filter(pk=instance.pk).exists()


@pytest.mark.parametrize("model", PRODUCT_MODELS)
def test_only_view_add_and_change_permissions_exist(model):
    codenames = set(
        Permission.objects.filter(
            content_type__app_label="parametros",
            content_type__model=model._meta.model_name,
        ).values_list("codename", flat=True)
    )

    name = model._meta.model_name
    assert codenames == {f"view_{name}", f"add_{name}", f"change_{name}"}


# Campos que ya fallaron en `clean_fields()`


def test_max_below_min_is_reported_even_without_default_installments():
    errors = errors_of(
        product(min_installments=10, default_installments=None, max_installments=5)
    )

    assert errors["max_installments"] == [
        "Las cuotas máximas no pueden ser menos que las mínimas."
    ]


def test_invalid_numbers_are_reported_on_their_field_without_crashing():
    errors = errors_of(
        product(initial_charge_value=None, min_amount="mucho", max_installments="x")
    )

    assert {"initial_charge_value", "min_amount", "max_installments"} <= set(errors)
