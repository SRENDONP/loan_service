"""Pruebas de los servicios de productos de crédito (SPEC 08, §3.5).

Hoy está fijado en el 13 de noviembre de 2026 (fixture `today`).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from apps.accounts.roles import Role
from apps.auditoria.models import AuditEvent
from apps.parametros.catalogs import RATE_CAP_USURY
from apps.parametros.models import (
    CreditProduct,
    InterestMethod,
    Periodicity,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
    RoundingMode,
)
from apps.parametros.services import (
    ApplicableCap,
    ProductRuleError,
    RoundingRule,
    create_product,
    deactivate_product,
    get_applicable_caps,
    get_offerable_products,
    get_product,
    get_product_rounding_rule,
    get_rate_version,
    reactivate_product,
    schedule_rate_cap_value,
    schedule_rate_version,
    update_product,
    void_rate_cap_value,
    void_rate_version,
)
from tests.parametros.conftest import product_fields

pytestmark = pytest.mark.django_db

NOV_13 = date(2026, 11, 13)
DEC_1 = date(2026, 12, 1)


def usury() -> RateCapType:
    return RateCapType.objects.get(code=RATE_CAP_USURY)


def internal_cap() -> RateCapType:
    return RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")


def cap_value(cap_type, user, valid_from: date, rate: str) -> RateCapValue:
    return RateCapValue.objects.create(
        cap_type=cap_type,
        valid_from=valid_from,
        annual_effective_rate=Decimal(rate),
        created_by=user,
    )


# Productos ofrecibles


def test_offerable_products_have_a_current_rate_and_are_sorted_by_name(
    make_product, today
):
    weekly = make_product("Semanal", valid_from=NOV_13)
    daily = make_product("Diario", valid_from=NOV_13)
    make_product("Sin tasa")

    assert list(get_offerable_products()) == [daily, weekly]


def test_product_with_a_future_first_rate_is_offered_from_that_day(make_product, today):
    product = make_product(valid_from=DEC_1)

    assert product not in get_offerable_products()
    assert product not in get_offerable_products(on=date(2026, 11, 30))
    assert list(get_offerable_products(on=DEC_1)) == [product]


def test_inactive_product_is_never_offered(make_product, today):
    make_product(valid_from=NOV_13, is_active=False)

    assert not get_offerable_products().exists()
    assert not get_offerable_products(on=date(2030, 1, 1)).exists()


def test_product_whose_only_rate_is_voided_is_not_offered(make_product, user, today):
    from django.utils import timezone

    product = make_product(valid_from=NOV_13)
    product.rate_versions.update(voided_at=timezone.now(), voided_by=user)

    assert product not in get_offerable_products()


# Un producto


def test_get_product_returns_active_and_inactive_products(make_product):
    active = make_product("Diario")
    inactive = make_product("Semanal", is_active=False)

    assert get_product(active.pk) == active
    assert get_product(inactive.pk) == inactive


def test_get_product_with_unknown_pk_raises_does_not_exist():
    with pytest.raises(CreditProduct.DoesNotExist):
        get_product(999_999)


# Topes que aplican


def test_product_without_additional_cap_gets_only_usury(make_product, user, today):
    value = cap_value(usury(), user, NOV_13, "25.02")
    product = make_product()

    assert get_applicable_caps(product) == [ApplicableCap(usury(), value)]


def test_usury_without_a_current_value_comes_with_none(make_product, today):
    assert get_applicable_caps(make_product()) == [ApplicableCap(usury(), None)]


def test_additional_cap_comes_after_usury_with_its_own_value(make_product, user, today):
    cap = internal_cap()
    usury_value = cap_value(usury(), user, NOV_13, "25.02")
    later_value = cap_value(cap, user, DEC_1, "20")
    product = make_product(additional_rate_cap=cap)

    assert get_applicable_caps(product) == [
        ApplicableCap(usury(), usury_value),
        ApplicableCap(cap, None),
    ]
    assert get_applicable_caps(product, on=DEC_1) == [
        ApplicableCap(usury(), usury_value),
        ApplicableCap(cap, later_value),
    ]


# Redondeo


def test_product_without_rounding_uses_the_global_rule(make_product, global_settings):
    global_settings.rounding_multiple = 500
    global_settings.rounding_mode = RoundingMode.DOWN
    global_settings.save()

    assert get_product_rounding_rule(make_product()) == RoundingRule(
        Decimal("500"), RoundingMode.DOWN
    )


def test_product_with_its_own_rounding_uses_it(make_product):
    product = make_product(rounding_multiple=100, rounding_mode=RoundingMode.UP)

    assert get_product_rounding_rule(product) == RoundingRule(
        Decimal("100"), RoundingMode.UP
    )


# Crear


def initial_rate(**overrides) -> dict:
    rate = {
        "min_rate": "10",
        "default_rate": "20",
        "max_rate": "25",
        "valid_from": NOV_13,
    }
    rate.update(overrides)
    return rate


def test_create_product_creates_it_with_its_first_rate(product_editor, today):
    product = create_product(product_editor, product_fields(), initial_rate())

    product.refresh_from_db()
    assert product.is_active
    assert product.updated_by == product_editor
    version = product.rate_versions.get()
    assert version.default_rate == Decimal("20.0000")
    assert version.valid_from == NOV_13
    assert version.valid_to is None
    assert version.created_by == product_editor
    assert get_rate_version(product) == version


def test_create_product_ignores_is_active_and_unknown_fields(product_editor, today):
    product = create_product(
        product_editor,
        product_fields(is_active=False, updated_by=None, created_at=None),
        initial_rate(),
    )

    assert product.is_active
    assert product.updated_by == product_editor


def test_invalid_rate_does_not_create_the_product(product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        create_product(product_editor, product_fields(), initial_rate(min_rate="21"))

    assert "default_rate" in excinfo.value.message_dict
    assert not CreditProduct.objects.exists()
    assert not ProductRateVersion.objects.exists()
    assert not AuditEvent.objects.filter(action__startswith="productos.").exists()


def test_past_initial_rate_does_not_create_the_product(product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        create_product(
            product_editor,
            product_fields(),
            initial_rate(valid_from=date(2026, 11, 12)),
        )

    assert excinfo.value.message_dict["valid_from"] == [
        "La vigencia no puede empezar en una fecha pasada."
    ]
    assert not CreditProduct.objects.exists()


def test_invalid_product_reports_errors_by_field(product_editor, today):
    with pytest.raises(ValidationError) as excinfo:
        create_product(
            product_editor,
            product_fields(min_amount=Decimal("100"), max_amount=Decimal("99")),
            initial_rate(),
        )

    assert "max_amount" in excinfo.value.message_dict
    assert not CreditProduct.objects.exists()


# Editar


def test_update_product_changes_the_conditions(product_editor, make_product):
    product = make_product()

    updated = update_product(
        product_editor,
        product,
        {"max_installments": 60, "late_tolerance_days": 2, "description": "Nuevo"},
    )

    product.refresh_from_db()
    assert product.max_installments == 60
    assert product.late_tolerance_days == 2
    assert product.description == "Nuevo"
    assert product.updated_by == product_editor
    assert updated.max_installments == 60


def test_update_product_ignores_the_method(product_editor, make_product):
    product = make_product()

    update_product(
        product_editor,
        product,
        {"interest_method": InterestMethod.FRENCH, "name": "Diario nuevo"},
    )

    product.refresh_from_db()
    assert product.interest_method == InterestMethod.FLAT_PER_CREDIT
    assert product.name == "Diario nuevo"


def test_update_product_ignores_is_active(product_editor, make_product):
    product = make_product()

    update_product(product_editor, product, {"is_active": False})

    product.refresh_from_db()
    assert product.is_active


def test_per_period_product_keeps_its_periodicity(product_editor, make_product):
    product = make_product(
        interest_method=InterestMethod.FRENCH,
        allowed_periodicities=[Periodicity.WEEKLY],
        default_periodicity=Periodicity.WEEKLY,
    )

    update_product(
        product_editor,
        product,
        {
            "allowed_periodicities": [Periodicity.DAILY],
            "default_periodicity": Periodicity.DAILY,
            "max_installments": 50,
        },
    )

    product.refresh_from_db()
    assert product.allowed_periodicities == [Periodicity.WEEKLY]
    assert product.default_periodicity == Periodicity.WEEKLY
    assert product.max_installments == 50


def test_flat_product_can_change_its_periodicities(product_editor, make_product):
    product = make_product()

    update_product(
        product_editor,
        product,
        {
            "allowed_periodicities": [Periodicity.MONTHLY],
            "default_periodicity": Periodicity.MONTHLY,
        },
    )

    product.refresh_from_db()
    assert product.allowed_periodicities == [Periodicity.MONTHLY]


def test_update_without_changes_does_not_save_or_record(product_editor, make_product):
    product = make_product()
    updated_at = product.updated_at

    update_product(
        product_editor,
        product,
        {
            "name": "Diario 20",
            "min_amount": "50000",
            "late_fee_daily_rate": Decimal("1.0"),
            "allowed_periodicities": [Periodicity.DAILY, Periodicity.WEEKLY],
        },
    )

    product.refresh_from_db()
    assert product.updated_at == updated_at
    assert product.updated_by is None
    assert not AuditEvent.objects.filter(action="productos.updated").exists()


def test_invalid_update_raises_and_keeps_the_product(product_editor, make_product):
    product = make_product()

    with pytest.raises(ValidationError) as excinfo:
        update_product(product_editor, product, {"max_amount": Decimal("1")})

    assert "max_amount" in excinfo.value.message_dict
    product.refresh_from_db()
    assert product.max_amount == Decimal("2000000")


# Desactivar y reactivar


def test_deactivate_and_reactivate_product(product_editor, make_product):
    product = make_product()

    deactivate_product(product_editor, product)
    product.refresh_from_db()
    assert not product.is_active

    reactivate_product(product_editor, product)
    product.refresh_from_db()
    assert product.is_active
    assert product.updated_by == product_editor


def test_deactivating_an_inactive_product_fails(product_editor, make_product):
    product = make_product(is_active=False)

    with pytest.raises(ProductRuleError) as excinfo:
        deactivate_product(product_editor, product)

    assert excinfo.value.messages == ["El producto ya está inactivo."]


def test_reactivating_an_active_product_fails(product_editor, make_product):
    with pytest.raises(ProductRuleError) as excinfo:
        reactivate_product(product_editor, make_product())

    assert excinfo.value.messages == ["El producto ya está activo."]


def test_product_rule_error_is_a_validation_error():
    assert issubclass(ProductRuleError, ValidationError)


# Permisos


@pytest.fixture(params=["supervisor", "no_perms"])
def unauthorized(request, make_user, no_perms_user):
    if request.param == "supervisor":
        return make_user("supervisora", role=Role.SUPERVISOR)
    return no_perms_user


def test_editing_services_require_permissions(unauthorized, make_product, today):
    product = make_product(valid_from=DEC_1)
    version = product.rate_versions.get()
    cap = usury()
    value = RateCapValue.objects.create(
        cap_type=cap,
        valid_from=DEC_1,
        annual_effective_rate=Decimal("25"),
        created_by=version.created_by,
    )
    before = AuditEvent.objects.count()
    later = date(2026, 12, 2)
    calls = [
        lambda: create_product(
            unauthorized, product_fields(name="Otro"), initial_rate()
        ),
        lambda: update_product(unauthorized, product, {"name": "Otro"}),
        lambda: deactivate_product(unauthorized, product),
        lambda: reactivate_product(unauthorized, product),
        lambda: schedule_rate_version(
            unauthorized, product, initial_rate(valid_from=later)
        ),
        lambda: void_rate_version(unauthorized, version),
        lambda: schedule_rate_cap_value(
            unauthorized, cap, {"annual_effective_rate": "26", "valid_from": later}
        ),
        lambda: void_rate_cap_value(unauthorized, value),
    ]

    for call in calls:
        with pytest.raises(PermissionDenied):
            call()

    assert AuditEvent.objects.count() == before
    assert CreditProduct.objects.count() == 1
    assert ProductRateVersion.objects.count() == 1
    assert RateCapValue.objects.count() == 1
    product.refresh_from_db()
    assert product.name == "Diario 20"
    assert product.is_active
    version.refresh_from_db()
    assert version.voided_at is None


def test_product_created_with_a_future_initial_rate_is_offered_from_that_day(
    product_editor, today
):
    product = create_product(
        product_editor, product_fields(), initial_rate(valid_from=DEC_1)
    )

    assert product not in get_offerable_products()
    assert list(get_offerable_products(on=DEC_1)) == [product]

    deactivate_product(product_editor, product)
    assert not get_offerable_products(on=DEC_1).exists()
