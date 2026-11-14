"""Pruebas de las pantallas de productos de crédito (SPEC 08, §3.8 y §3.9).

Hoy está fijado en el 13 de noviembre de 2026 (fixture `today`).
"""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.roles import Role
from apps.auditoria.actions import AuditAction
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

pytestmark = pytest.mark.django_db

NOV_13 = date(2026, 11, 13)
DEC_1 = date(2026, 12, 1)
LIST_URL = reverse("parametros:product_list")
CREATE_URL = reverse("parametros:product_create")


def url(name: str, *args) -> str:
    return reverse(f"parametros:{name}", args=args)


def page_messages(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


def usury() -> RateCapType:
    return RateCapType.objects.get(code=RATE_CAP_USURY)


def product_post(**overrides: Any) -> dict[str, Any]:
    """Un POST válido del formulario de creación, con la tasa inicial."""
    data: dict[str, Any] = {
        "name": "Diario 20",
        "description": "",
        "interest_method": InterestMethod.FLAT_PER_CREDIT,
        "allowed_periodicities": [Periodicity.DAILY, Periodicity.WEEKLY],
        "default_periodicity": Periodicity.DAILY,
        "min_amount": "50000",
        "max_amount": "2000000",
        "min_installments": "10",
        "default_installments": "20",
        "max_installments": "40",
        "default_grace_periods": "0",
        "max_grace_periods": "0",
        "late_fee_daily_rate": "1",
        "late_fee_cap_percent": "20",
        "late_tolerance_days": "0",
        "write_off_min_days_past_due": "90",
        "initial_charge_type": "none",
        "initial_charge_value": "0",
        "max_active_credits_per_client": "1",
        "rounding_multiple": "",
        "rounding_mode": "",
        "additional_rate_cap": "",
        "rate-min_rate": "10",
        "rate-default_rate": "20",
        "rate-max_rate": "25",
        "rate-valid_from": "2026-11-13",
    }
    data.update(overrides)
    return data


def edit_post(product: CreditProduct, **overrides: Any) -> dict[str, Any]:
    """El POST de edición con los valores actuales del producto."""
    data = {
        key: value
        for key, value in product_post().items()
        if not key.startswith("rate-") and key != "interest_method"
    }
    data["allowed_periodicities"] = list(product.allowed_periodicities)
    data["default_periodicity"] = product.default_periodicity
    data.update(overrides)
    return data


@pytest.fixture
def admin_user(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def admin_client(client, admin_user, today):
    client.force_login(admin_user)
    return client


@pytest.fixture
def product(make_product):
    return make_product(valid_from=NOV_13)


def schedule(product, user, valid_from: date, **fields) -> ProductRateVersion:
    values = {
        "product": product,
        "valid_from": valid_from,
        "min_rate": Decimal("11"),
        "default_rate": Decimal("21"),
        "max_rate": Decimal("26"),
        "created_by": user,
    }
    values.update(fields)
    return ProductRateVersion.objects.create(**values)


def all_routes(product: CreditProduct, version: ProductRateVersion):
    return [
        ("get", LIST_URL),
        ("get", CREATE_URL),
        ("post", CREATE_URL),
        ("get", url("product_detail", product.pk)),
        ("get", url("product_update", product.pk)),
        ("post", url("product_update", product.pk)),
        ("post", url("product_deactivate", product.pk)),
        ("post", url("product_reactivate", product.pk)),
        ("get", url("rate_version_create", product.pk)),
        ("post", url("rate_version_create", product.pk)),
        ("post", url("rate_version_void", product.pk, version.pk)),
    ]


# Rutas


def test_urls_follow_the_spec():
    assert LIST_URL == "/parametros/productos/"
    assert CREATE_URL == "/parametros/productos/nuevo/"
    assert url("product_detail", 7) == "/parametros/productos/7/"
    assert url("product_update", 7) == "/parametros/productos/7/editar/"
    assert url("product_deactivate", 7) == "/parametros/productos/7/desactivar/"
    assert url("product_reactivate", 7) == "/parametros/productos/7/reactivar/"
    assert url("rate_version_create", 7) == "/parametros/productos/7/tasas/nueva/"
    assert url("rate_version_void", 7, 3) == "/parametros/productos/7/tasas/3/anular/"


# Menú y permisos


def test_administrator_sees_both_entries_and_every_route_answers(
    admin_client, admin_user, product
):
    version = schedule(product, admin_user, DEC_1)
    home = admin_client.get(reverse("core:home")).content.decode()
    assert "Productos de crédito" in home
    assert "Topes de tasa" in home
    assert home.index("Catálogos") < home.index("Productos de crédito")
    assert home.index("Productos de crédito") < home.index("Topes de tasa")

    for method, route in all_routes(product, version):
        status = getattr(admin_client, method)(route).status_code
        assert status in (200, 302), (method, route, status)


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.VIEWER])
def test_viewers_see_list_and_detail_without_edit_buttons(
    client, make_user, admin_user, product, role, today
):
    version = schedule(product, admin_user, DEC_1)
    client.force_login(make_user("lectora", role=role))

    home = client.get(reverse("core:home")).content.decode()
    assert "Productos de crédito" in home
    assert "Topes de tasa" in home

    read_routes = (LIST_URL, url("product_detail", product.pk))
    for route in read_routes:
        response = client.get(route)
        content = response.content.decode()
        assert response.status_code == 200
        for label in (
            "Nuevo producto",
            "Editar",
            "Desactivar",
            "Programar nueva tasa",
            "Anular",
        ):
            assert label not in content, (route, label)

    for method, route in all_routes(product, version):
        if method == "get" and route in read_routes:
            continue
        assert getattr(client, method)(route).status_code == 403, (method, route)


def test_collector_does_not_see_the_entries_and_gets_403(
    client, make_user, admin_user, product
):
    version = schedule(product, admin_user, DEC_1)
    client.force_login(make_user("cobrador1", role=Role.COLLECTOR))

    home = client.get(reverse("core:home")).content.decode()
    assert "Productos de crédito" not in home
    assert "Topes de tasa" not in home
    for method, route in all_routes(product, version):
        assert getattr(client, method)(route).status_code == 403, (method, route)


# Listado


def test_list_shows_the_current_default_rate_with_its_unit(admin_client, product):
    response = admin_client.get(LIST_URL)
    content = response.content.decode()

    assert response.status_code == 200
    assert f'href="{url("product_detail", product.pk)}"' in content
    assert "Plano fijo por crédito" in content
    assert "Diaria, Semanal" in content
    assert "$50.000 – $2.000.000" in content
    assert "10 – 40" in content
    assert "20 % por crédito" in content
    assert '<span class="badge badge-success">Activo</span>' in content
    assert "Nuevo producto" in content


def test_list_marks_products_without_a_current_rate(admin_client, make_product):
    make_product("Futuro", valid_from=DEC_1)
    make_product("Inactivo", is_active=False)

    content = admin_client.get(LIST_URL).content.decode()

    assert (
        content.count('<span class="badge badge-warning">Sin tasa vigente</span>') == 2
    )
    assert '<span class="badge badge-secondary">Inactivo</span>' in content


# Crear


def test_create_form_has_the_cards_the_initial_rate_and_the_options(admin_client):
    content = admin_client.get(CREATE_URL).content.decode()

    for title in (
        "Identificación",
        "Método y periodicidad",
        "Monto y cuotas",
        "Gracia",
        "Mora y castigo",
        "Gasto inicial",
        "Límite y redondeo",
        "Tope adicional",
        "Tasa inicial",
    ):
        assert f">{title}</h2>" in content, title
    assert 'type="checkbox" name="allowed_periodicities"' in content
    assert "Usar el redondeo global (50, al más cercano)" in content
    assert ">Ninguno</option>" in content
    # Django 6.1 trae la opción vacía sin traducir.
    assert content.count('<option value="" selected>Elige una opción</option>') == 2
    assert "Select an option" not in content
    assert 'name="rate-valid_from"' in content
    assert 'value="2026-11-13"' in content
    assert "Plano fijo: % por crédito." in content


def test_additional_cap_offers_active_types_without_usury(admin_client):
    RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")
    RateCapType.objects.create(code="VIEJO", name="Tope viejo", is_active=False)

    content = admin_client.get(CREATE_URL).content.decode()

    assert ">Tope interno</option>" in content
    assert ">Tope viejo</option>" not in content
    assert ">Usura</option>" not in content


def test_create_a_product_redirects_to_its_detail_with_the_rate_current(
    admin_client, admin_user
):
    response = admin_client.post(CREATE_URL, product_post())

    product = CreditProduct.objects.get(name="Diario 20")
    assert response.status_code == 302
    assert response["Location"] == url("product_detail", product.pk)
    follow = admin_client.get(response["Location"])
    assert "Se guardó Diario 20." in page_messages(follow)
    content = follow.content.decode()
    assert '<span class="badge badge-success">Vigente</span>' in content
    assert "20 % por crédito" in content
    assert product.updated_by == admin_user
    assert list(
        AuditEvent.objects.filter(object_id__in=[str(product.pk)]).values_list(
            "action", flat=True
        )
    ) == [AuditAction.PRODUCT_CREATED]
    assert AuditEvent.objects.filter(action=AuditAction.PRODUCT_RATE_SCHEDULED).exists()


def test_create_with_errors_shows_them_on_their_fields(admin_client):
    response = admin_client.post(
        CREATE_URL,
        product_post(max_amount="10", **{"rate-min_rate": "30"}),
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "El monto máximo no puede ser menor que el mínimo." in content
    assert 'id="id_max_amount_error"' in content
    assert "La tasa por defecto no puede ser menor que la mínima." in content
    assert 'id="id_rate-default_rate_error"' in content
    assert not CreditProduct.objects.exists()


def test_create_with_a_past_rate_shows_the_service_error_on_its_field(admin_client):
    response = admin_client.post(
        CREATE_URL, product_post(**{"rate-valid_from": "2026-11-12"})
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "La vigencia no puede empezar en una fecha pasada." in content
    assert 'id="id_rate-valid_from_error"' in content
    assert not CreditProduct.objects.exists()


def test_per_period_product_with_two_periodicities_fails(admin_client):
    response = admin_client.post(
        CREATE_URL, product_post(interest_method=InterestMethod.FRENCH)
    )

    assert response.status_code == 200
    assert (
        "Con el método Cuota fija (francés), la tasa es por periodo"
        in response.content.decode()
    )


# Editar


def test_edit_form_shows_the_method_as_text(admin_client, product):
    content = admin_client.get(url("product_update", product.pk)).content.decode()

    assert 'name="interest_method"' not in content
    assert "Plano fijo por crédito" in content
    assert 'name="allowed_periodicities"' in content
    assert "Tasa inicial" not in content


def test_edit_form_of_a_per_period_product_locks_the_periodicity(
    admin_client, make_product
):
    product = make_product(
        "Francés semanal",
        interest_method=InterestMethod.FRENCH,
        allowed_periodicities=[Periodicity.WEEKLY],
        default_periodicity=Periodicity.WEEKLY,
    )

    content = admin_client.get(url("product_update", product.pk)).content.decode()

    assert 'name="allowed_periodicities"' not in content
    assert 'name="default_periodicity"' not in content
    assert "Con tasa por periodo, la periodicidad no cambia." in content


def test_posting_the_method_does_not_change_it(admin_client, product):
    response = admin_client.post(
        url("product_update", product.pk),
        {**edit_post(product), "interest_method": InterestMethod.FRENCH},
    )

    assert response.status_code == 302
    product.refresh_from_db()
    assert product.interest_method == InterestMethod.FLAT_PER_CREDIT


def test_edit_a_product_and_edit_without_changes(admin_client, product):
    edit = url("product_update", product.pk)

    response = admin_client.post(edit, edit_post(product), follow=True)
    assert "No hubo cambios en Diario 20." in page_messages(response)

    response = admin_client.post(
        edit,
        edit_post(
            product,
            max_installments="60",
            rounding_multiple="100",
            rounding_mode=RoundingMode.UP,
        ),
        follow=True,
    )
    assert "Se guardó Diario 20." in page_messages(response)
    product.refresh_from_db()
    assert product.max_installments == 60
    assert product.rounding_multiple == 100
    assert "100, siempre hacia arriba" in response.content.decode()


def test_edit_with_errors_responds_200(admin_client, product):
    response = admin_client.post(
        url("product_update", product.pk),
        edit_post(product, rounding_multiple="100"),
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "Elige el múltiplo y el modo" in content
    assert "Editar Diario 20" in content


def test_assigned_inactive_cap_is_still_offered_when_editing(
    admin_client, make_product
):
    cap = RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")
    product = make_product(additional_rate_cap=cap)
    RateCapType.objects.filter(pk=cap.pk).update(is_active=False)

    content = admin_client.get(url("product_update", product.pk)).content.decode()

    assert ">Tope interno</option>" in content


# Desactivar y reactivar


def test_deactivate_and_reactivate_from_the_detail(admin_client, product):
    response = admin_client.post(url("product_deactivate", product.pk), follow=True)
    assert "Se desactivó Diario 20." in page_messages(response)
    assert url("product_reactivate", product.pk) in response.content.decode()

    response = admin_client.post(url("product_deactivate", product.pk), follow=True)
    assert "El producto ya está inactivo." in page_messages(response)

    response = admin_client.post(url("product_reactivate", product.pk), follow=True)
    assert "Se reactivó Diario 20." in page_messages(response)


def test_state_and_void_routes_reject_get(admin_client, admin_user, product):
    version = schedule(product, admin_user, DEC_1)

    for route in (
        url("product_deactivate", product.pk),
        url("product_reactivate", product.pk),
        url("rate_version_void", product.pk, version.pk),
    ):
        assert admin_client.get(route).status_code == 405, route


# Detalle


def test_detail_shows_conditions_rates_and_caps(admin_client, admin_user, product):
    schedule(product, admin_user, DEC_1)

    content = admin_client.get(url("product_detail", product.pk)).content.decode()

    assert '<span class="badge badge-success">Vigente</span>' in content
    assert '<span class="badge badge-info">Programada</span>' in content
    assert content.count('data-confirm-button="Anular"') == 1
    assert "Programar nueva tasa" in content
    assert "$50.000" in content
    assert "1 % diario sobre el valor vencido" in content
    assert "90 días" in content
    assert "Sin gasto inicial" in content
    assert "Usar el redondeo global (50, al más cercano)" in content
    assert "Usura no tiene un valor vigente." in content
    assert "La tasa se valida contra estos topes en cada crédito" in content


def test_detail_hides_the_usury_alert_with_a_current_value(
    admin_client, admin_user, product
):
    RateCapValue.objects.create(
        cap_type=usury(),
        valid_from=NOV_13,
        annual_effective_rate=Decimal("25.02"),
        created_by=admin_user,
    )

    content = admin_client.get(url("product_detail", product.pk)).content.decode()

    assert "Usura no tiene un valor vigente." not in content
    assert "25,02 % EA" in content


def test_detail_shows_the_additional_cap_without_value(admin_client, make_product):
    cap = RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")
    product = make_product(additional_rate_cap=cap, valid_from=NOV_13)

    content = admin_client.get(url("product_detail", product.pk)).content.decode()

    assert "Tope interno no tiene un valor vigente." in content


# Versiones de tasa


def test_rate_form_has_the_unit_and_the_current_rate(admin_client, product):
    content = admin_client.get(url("rate_version_create", product.pk)).content.decode()

    assert '<span class="input-group-text">% por crédito</span>' in content
    assert (
        "Tasa vigente: mínima 10 % por crédito, por defecto 20 % por crédito y "
        "máxima 25 % por crédito, desde el 13/11/2026."
    ) in content


def test_schedule_and_void_a_rate_from_the_screen(admin_client, admin_user, product):
    response = admin_client.post(
        url("rate_version_create", product.pk),
        {
            "min_rate": "11",
            "default_rate": "21",
            "max_rate": "26",
            "valid_from": "2026-12-01",
        },
        follow=True,
    )
    assert "Se programó la tasa de Diario 20 desde el 01/12/2026." in page_messages(
        response
    )
    content = response.content.decode()
    assert '<span class="badge badge-info">Programada</span>' in content

    scheduled = product.rate_versions.get(valid_from=DEC_1)
    response = admin_client.post(
        url("rate_version_void", product.pk, scheduled.pk), follow=True
    )

    assert (
        "Se anuló la tasa de Diario 20 que iba a regir desde el 01/12/2026."
        in page_messages(response)
    )
    assert '<span class="badge badge-dark">Anulada</span>' in response.content.decode()


def test_rate_with_errors_responds_200(admin_client, product):
    response = admin_client.post(
        url("rate_version_create", product.pk),
        {
            "min_rate": "10",
            "default_rate": "20",
            "max_rate": "25",
            "valid_from": "2026-11-13",
        },
    )

    assert response.status_code == 200
    assert "La vigencia tiene que empezar después del 13/11/2026" in (
        response.content.decode()
    )


def test_voiding_a_current_rate_shows_the_rule(admin_client, product):
    version = product.rate_versions.get()

    response = admin_client.post(
        url("rate_version_void", product.pk, version.pk), follow=True
    )

    assert any("no se puede anular" in text for text in page_messages(response))


def test_version_of_another_product_responds_404(
    admin_client, admin_user, product, make_product
):
    other = make_product("Semanal")
    foreign = schedule(other, admin_user, DEC_1)

    response = admin_client.post(url("rate_version_void", product.pk, foreign.pk))

    assert response.status_code == 404
    foreign.refresh_from_db()
    assert foreign.voided_at is None


def test_unknown_product_responds_404(admin_client):
    assert admin_client.get(url("product_detail", 999_999)).status_code == 404
    assert admin_client.get(url("product_update", 999_999)).status_code == 404


def test_voided_version_shows_as_voided(admin_client, admin_user, product):
    schedule(product, admin_user, DEC_1, voided_at=timezone.now(), voided_by=admin_user)

    content = admin_client.get(url("product_detail", product.pk)).content.decode()

    assert '<span class="badge badge-dark">Anulada</span>' in content
    assert 'data-confirm-button="Anular"' not in content


@pytest.mark.parametrize(
    ("kind", "value", "expected"),
    [("fixed", Decimal("5000"), "$5.000"), ("percent", Decimal("5"), "5 % del monto")],
)
def test_detail_shows_the_initial_charge(
    admin_client, make_product, kind, value, expected
):
    product = make_product(initial_charge_type=kind, initial_charge_value=value)

    content = admin_client.get(url("product_detail", product.pk)).content.decode()

    assert expected in content


def test_service_errors_without_a_known_field_go_to_the_product_form():
    from django import forms
    from django.core.exceptions import ValidationError

    from apps.parametros.views import apply_service_errors

    class One(forms.Form):
        name = forms.CharField(required=False)

    class Two(forms.Form):
        rate = forms.CharField(required=False)

    first, second = One({}), Two({})
    first.is_valid(), second.is_valid()

    apply_service_errors(ValidationError("Regla general."), first, second)
    apply_service_errors(
        ValidationError({"other": "Otro campo.", "rate": "Tasa mala."}), first, second
    )

    assert first.non_field_errors() == ["Regla general.", "Otro campo."]
    assert second.errors["rate"] == ["Tasa mala."]
