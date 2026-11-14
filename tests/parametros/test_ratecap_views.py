"""Pruebas de las pantallas de topes de tasa (SPEC 08, §3.8 y §3.9).

Hoy está fijado en el 13 de noviembre de 2026 (fixture `today`).
"""

from datetime import date
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.accounts.roles import Role
from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent
from apps.parametros.catalogs import RATE_CAP_USURY
from apps.parametros.models import RateCapType, RateCapValue

pytestmark = pytest.mark.django_db

NOV_13 = date(2026, 11, 13)
DEC_1 = date(2026, 12, 1)
LIST_URL = reverse("parametros:ratecap_list")
CREATE_URL = reverse("parametros:ratecap_create")


def usury() -> RateCapType:
    return RateCapType.objects.get(code=RATE_CAP_USURY)


def url(name: str, *args) -> str:
    return reverse(f"parametros:{name}", args=args)


def page_messages(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


def add_value(cap_type, user, valid_from: date, rate: str = "25.02", **fields):
    return RateCapValue.objects.create(
        cap_type=cap_type,
        valid_from=valid_from,
        annual_effective_rate=Decimal(rate),
        created_by=user,
        **fields,
    )


@pytest.fixture
def admin_user(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR)


@pytest.fixture
def admin_client(client, admin_user, today):
    client.force_login(admin_user)
    return client


@pytest.fixture
def internal_cap():
    return RateCapType.objects.create(code="TOPE_INTERNO", name="Tope interno")


def all_routes(cap_type: RateCapType, value: RateCapValue) -> list[tuple[str, str]]:
    return [
        ("get", LIST_URL),
        ("get", CREATE_URL),
        ("post", CREATE_URL),
        ("get", url("ratecap_detail", cap_type.pk)),
        ("get", url("ratecap_update", cap_type.pk)),
        ("post", url("ratecap_update", cap_type.pk)),
        ("post", url("ratecap_deactivate", cap_type.pk)),
        ("post", url("ratecap_reactivate", cap_type.pk)),
        ("get", url("ratecap_value_create", cap_type.pk)),
        ("post", url("ratecap_value_create", cap_type.pk)),
        ("post", url("ratecap_value_void", cap_type.pk, value.pk)),
    ]


# Rutas


def test_urls_follow_the_spec():
    assert LIST_URL == "/parametros/topes/"
    assert CREATE_URL == "/parametros/topes/nuevo/"
    assert url("ratecap_detail", 7) == "/parametros/topes/7/"
    assert url("ratecap_update", 7) == "/parametros/topes/7/editar/"
    assert url("ratecap_deactivate", 7) == "/parametros/topes/7/desactivar/"
    assert url("ratecap_reactivate", 7) == "/parametros/topes/7/reactivar/"
    assert url("ratecap_value_create", 7) == "/parametros/topes/7/valores/nuevo/"
    assert url("ratecap_value_void", 7, 3) == "/parametros/topes/7/valores/3/anular/"


# Menú y permisos


def test_administrator_sees_the_entry_and_every_route_answers(
    admin_client, admin_user, internal_cap
):
    value = add_value(internal_cap, admin_user, DEC_1)
    home = admin_client.get(reverse("core:home")).content.decode()
    assert "Topes de tasa" in home
    assert f'href="{LIST_URL}"' in home

    for method, route in all_routes(internal_cap, value):
        status = getattr(admin_client, method)(route).status_code
        assert status in (200, 302), (method, route, status)


def test_the_list_marks_its_menu_entry_as_active(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert f'<a class="nav-link" href="{LIST_URL}" aria-current="page">' in content


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.VIEWER])
def test_viewers_see_lists_and_details_without_edit_buttons(
    client, make_user, admin_user, internal_cap, role, today
):
    add_value(usury(), admin_user, NOV_13)
    value = add_value(internal_cap, admin_user, DEC_1)
    client.force_login(make_user("lectora", role=role))

    home = client.get(reverse("core:home")).content.decode()
    assert "Topes de tasa" in home
    assert "Catálogos" not in home
    assert "Parámetros globales" not in home

    for route in (LIST_URL, url("ratecap_detail", internal_cap.pk)):
        response = client.get(route)
        content = response.content.decode()
        assert response.status_code == 200
        for label in ("Nuevo tope", "Editar", "Programar nuevo valor", "Anular"):
            assert label not in content, (route, label)
        assert "Desactivar" not in content

    for method, route in all_routes(internal_cap, value):
        if method == "get" and route in (
            LIST_URL,
            url("ratecap_detail", internal_cap.pk),
        ):
            continue
        assert getattr(client, method)(route).status_code == 403, (method, route)


def test_collector_does_not_see_the_entry_and_gets_403(
    client, make_user, admin_user, internal_cap
):
    value = add_value(internal_cap, admin_user, DEC_1)
    client.force_login(make_user("cobrador1", role=Role.COLLECTOR))

    home = client.get(reverse("core:home")).content.decode()
    assert "Topes de tasa" not in home
    for method, route in all_routes(internal_cap, value):
        assert getattr(client, method)(route).status_code == 403, (method, route)


# Listado


def test_list_shows_usury_without_value_and_its_warning(admin_client):
    response = admin_client.get(LIST_URL)
    content = response.content.decode()

    assert response.status_code == 200
    assert "La usura no tiene un valor vigente." in content
    assert "Sin valor vigente" in content
    assert '<span class="badge badge-info">Sistema</span>' in content
    assert "Nuevo tope" in content
    # La usura no se desactiva.
    assert url("ratecap_deactivate", usury().pk) not in content


def test_list_hides_the_warning_with_a_current_usury_value(admin_client, admin_user):
    add_value(usury(), admin_user, NOV_13, "25.0200")

    content = admin_client.get(LIST_URL).content.decode()

    assert "La usura no tiene un valor vigente." not in content
    assert "25,02 % EA" in content
    assert "13/11/2026" in content


def test_scheduled_usury_value_does_not_count_as_current(admin_client, admin_user):
    add_value(usury(), admin_user, DEC_1)

    content = admin_client.get(LIST_URL).content.decode()

    assert "La usura no tiene un valor vigente." in content


def test_list_links_to_the_detail_and_offers_deactivate(admin_client, internal_cap):
    content = admin_client.get(LIST_URL).content.decode()

    assert f'href="{url("ratecap_detail", internal_cap.pk)}"' in content
    assert url("ratecap_deactivate", internal_cap.pk) in content


# Crear y editar un tipo


def test_create_a_cap_type_redirects_to_its_detail(admin_client):
    response = admin_client.post(
        CREATE_URL, {"code": "", "name": "Tope interno", "display_order": 20}
    )

    created = RateCapType.objects.get(name="Tope interno")
    assert response.status_code == 302
    assert response["Location"] == url("ratecap_detail", created.pk)
    assert created.code == "TOPE_INTERNO"
    assert AuditEvent.objects.filter(
        action=AuditAction.CATALOG_ITEM_CREATED, object_id=str(created.pk)
    ).exists()
    follow = admin_client.get(response["Location"])
    assert "Se guardó Tope interno." in page_messages(follow)


def test_create_with_a_repeated_name_shows_the_error(admin_client):
    response = admin_client.post(CREATE_URL, {"name": "usura", "display_order": 0})

    assert response.status_code == 200
    assert "Ya existe un ítem con ese nombre." in response.content.decode()


def test_edit_a_cap_type_and_edit_without_changes(admin_client, internal_cap):
    edit = url("ratecap_update", internal_cap.pk)

    response = admin_client.post(
        edit, {"name": "Tope del negocio", "display_order": 0}, follow=True
    )
    assert "Se guardó Tope del negocio." in page_messages(response)

    response = admin_client.post(
        edit, {"name": "Tope del negocio", "display_order": 0}, follow=True
    )
    assert "No hubo cambios en Tope del negocio." in page_messages(response)


def test_edit_form_shows_the_code_as_read_only(admin_client):
    content = admin_client.get(url("ratecap_update", usury().pk)).content.decode()

    assert "<code>USURA</code>" in content
    assert 'name="code"' not in content


# Desactivar y reactivar


def test_deactivate_and_reactivate_a_cap_type(admin_client, internal_cap):
    response = admin_client.post(
        url("ratecap_deactivate", internal_cap.pk), follow=True
    )
    assert "Se desactivó Tope interno." in page_messages(response)
    internal_cap.refresh_from_db()
    assert not internal_cap.is_active

    response = admin_client.post(
        url("ratecap_reactivate", internal_cap.pk), follow=True
    )
    assert "Se reactivó Tope interno." in page_messages(response)


def test_deactivating_usury_shows_the_rule(admin_client):
    response = admin_client.post(url("ratecap_deactivate", usury().pk), follow=True)

    assert "Un ítem de sistema no se puede desactivar." in page_messages(response)


def test_deactivating_a_cap_in_use_shows_the_product(
    admin_client, internal_cap, make_product
):
    make_product("Semanal", additional_rate_cap=internal_cap)

    response = admin_client.post(
        url("ratecap_deactivate", internal_cap.pk), follow=True
    )

    assert (
        "Lo usa el producto Semanal. Quítalo del producto antes de desactivarlo."
        in page_messages(response)
    )


def test_state_routes_reject_get(admin_client, internal_cap, admin_user):
    value = add_value(internal_cap, admin_user, DEC_1)

    for route in (
        url("ratecap_deactivate", internal_cap.pk),
        url("ratecap_reactivate", internal_cap.pk),
        url("ratecap_value_void", internal_cap.pk, value.pk),
    ):
        assert admin_client.get(route).status_code == 405, route


# Detalle


def test_usury_detail_says_it_applies_to_every_product(admin_client):
    content = admin_client.get(url("ratecap_detail", usury().pk)).content.decode()

    assert "Aplica a todos los productos." in content
    assert "La usura no tiene un valor vigente." in content


def test_detail_lists_the_products_that_use_the_cap(
    admin_client, internal_cap, make_product
):
    make_product("Semanal", additional_rate_cap=internal_cap)
    make_product("Mensual", additional_rate_cap=internal_cap, is_active=False)

    content = admin_client.get(url("ratecap_detail", internal_cap.pk)).content.decode()

    assert "Semanal" in content
    assert "Mensual" in content
    assert "La usura no tiene un valor vigente." not in content


def test_detail_shows_each_value_with_its_state(admin_client, admin_user, internal_cap):
    from django.utils import timezone

    add_value(internal_cap, admin_user, date(2026, 11, 1), valid_to=date(2026, 11, 12))
    add_value(internal_cap, admin_user, NOV_13, "30", valid_to=date(2026, 11, 30))
    add_value(internal_cap, admin_user, DEC_1, "31")
    add_value(
        internal_cap,
        admin_user,
        date(2026, 12, 15),
        "32",
        voided_at=timezone.now(),
        voided_by=admin_user,
    )

    content = admin_client.get(url("ratecap_detail", internal_cap.pk)).content.decode()

    assert '<span class="badge badge-secondary">Anterior</span>' in content
    assert '<span class="badge badge-success">Vigente</span>' in content
    assert '<span class="badge badge-info">Programada</span>' in content
    assert '<span class="badge badge-dark">Anulada</span>' in content
    assert "30 % EA" in content
    # Solo la última programada se anula.
    assert content.count('data-confirm-button="Anular"') == 1


# Programar y anular valores


def test_value_form_has_the_unit_today_and_the_current_value(
    admin_client, admin_user, internal_cap
):
    add_value(internal_cap, admin_user, NOV_13, "25.5")

    content = admin_client.get(
        url("ratecap_value_create", internal_cap.pk)
    ).content.decode()

    assert '<span class="input-group-text">% EA</span>' in content
    assert 'type="date"' in content
    assert 'value="2026-11-13"' in content
    assert "Valor vigente: 25,5 % EA, desde el 13/11/2026." in content


def test_schedule_a_value_from_the_screen(admin_client, internal_cap):
    response = admin_client.post(
        url("ratecap_value_create", internal_cap.pk),
        {
            "annual_effective_rate": "25.02",
            "valid_from": "2026-11-13",
            "reference": "Resolución 1234 de 2026",
        },
    )

    assert response.status_code == 302
    assert response["Location"] == url("ratecap_detail", internal_cap.pk)
    follow = admin_client.get(response["Location"])
    assert "Se programó el valor de Tope interno desde el 13/11/2026." in (
        page_messages(follow)
    )
    content = follow.content.decode()
    assert '<span class="badge badge-success">Vigente</span>' in content
    assert "Resolución 1234 de 2026" in content


def test_past_value_shows_the_error_on_its_field(admin_client, internal_cap):
    response = admin_client.post(
        url("ratecap_value_create", internal_cap.pk),
        {"annual_effective_rate": "25", "valid_from": "2026-11-12"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "La vigencia no puede empezar en una fecha pasada." in content
    assert 'id="id_valid_from_error"' in content
    assert not RateCapValue.objects.exists()


def test_zero_value_shows_the_error_on_its_field(admin_client, internal_cap):
    response = admin_client.post(
        url("ratecap_value_create", internal_cap.pk),
        {"annual_effective_rate": "0", "valid_from": "2026-12-01"},
    )

    content = response.content.decode()
    assert response.status_code == 200
    assert "El valor del tope debe ser mayor que cero." in content
    assert 'id="id_annual_effective_rate_error"' in content


def test_void_a_scheduled_value_from_the_screen(admin_client, admin_user, internal_cap):
    add_value(internal_cap, admin_user, NOV_13)
    scheduled = add_value(internal_cap, admin_user, DEC_1)

    response = admin_client.post(
        url("ratecap_value_void", internal_cap.pk, scheduled.pk), follow=True
    )

    assert (
        "Se anuló el valor de Tope interno que iba a regir desde el 01/12/2026."
        in page_messages(response)
    )
    assert '<span class="badge badge-dark">Anulada</span>' in response.content.decode()
    scheduled.refresh_from_db()
    assert scheduled.voided_by == admin_user


def test_voiding_a_current_value_shows_the_rule(admin_client, admin_user, internal_cap):
    value = add_value(internal_cap, admin_user, NOV_13)

    response = admin_client.post(
        url("ratecap_value_void", internal_cap.pk, value.pk), follow=True
    )

    assert any("no se puede anular" in text for text in page_messages(response))


def test_value_of_another_cap_responds_404(admin_client, admin_user, internal_cap):
    other = add_value(usury(), admin_user, DEC_1)

    response = admin_client.post(url("ratecap_value_void", internal_cap.pk, other.pk))

    assert response.status_code == 404
    other.refresh_from_db()
    assert other.voided_at is None


def test_unknown_cap_type_responds_404(admin_client):
    assert admin_client.get(url("ratecap_detail", 999_999)).status_code == 404
    assert admin_client.get(url("ratecap_value_create", 999_999)).status_code == 404


def test_service_error_is_shown_on_the_form(admin_client, monkeypatch):
    from django.core.exceptions import ValidationError

    from apps.parametros import services

    def reject(*args, **kwargs):
        raise ValidationError({"name": "El servicio rechazó el nombre."})

    monkeypatch.setattr(services, "create_catalog_item", reject)

    response = admin_client.post(CREATE_URL, {"name": "Tope", "display_order": 0})

    assert response.status_code == 200
    assert "El servicio rechazó el nombre." in response.content.decode()
