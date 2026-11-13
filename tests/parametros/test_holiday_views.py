"""Pruebas de las pantallas de festivos y su menú (SPEC 07, §3.9 y §3.10)."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.roles import Role
from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent
from apps.parametros import services, views
from apps.parametros.models import Holiday, HolidayOrigin
from apps.parametros.services import load_official_holidays

pytestmark = pytest.mark.django_db

LIST_URL = reverse("parametros:holiday_list")
CREATE_URL = reverse("parametros:holiday_create")
TODAY = date(2026, 11, 13)
HOLIDAY_ACTIONS = [
    AuditAction.HOLIDAY_CREATED,
    AuditAction.HOLIDAY_UPDATED,
    AuditAction.HOLIDAY_DEACTIVATED,
    AuditAction.HOLIDAY_REACTIVATED,
]


@pytest.fixture(autouse=True)
def fixed_today(monkeypatch):
    """La pantalla calcula el año actual con `timezone.localdate()`."""
    monkeypatch.setattr(views.timezone, "localdate", lambda: TODAY)


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("admin1", role=Role.ADMINISTRATOR))
    return client


def reyes(year: int = 2027) -> Holiday:
    return Holiday.objects.get(official_year=year, official_code="reyes_magos")


def update_url(holiday: Holiday) -> str:
    return reverse("parametros:holiday_update", args=[holiday.pk])


def deactivate_url(holiday: Holiday) -> str:
    return reverse("parametros:holiday_deactivate", args=[holiday.pk])


def reactivate_url(holiday: Holiday) -> str:
    return reverse("parametros:holiday_reactivate", args=[holiday.pk])


def page_messages(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


def holiday_events():
    return AuditEvent.objects.filter(action__in=HOLIDAY_ACTIONS)


# Rutas, menú y permisos


def test_urls_follow_the_spec():
    assert LIST_URL == "/parametros/festivos/"
    assert CREATE_URL == "/parametros/festivos/nuevo/"
    assert update_url(reyes()) == f"/parametros/festivos/{reyes().pk}/editar/"


def test_festivos_is_the_last_entry_of_the_catalogs_submenu(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert f'class="collapse-item active" href="{LIST_URL}"' in content
    reasons = reverse("parametros:catalog_tipos_relacion")
    assert content.index(f'href="{reasons}"') < content.index(f'href="{LIST_URL}"')
    assert content.count('class="collapse-item') >= 7


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_get_403_on_every_route(client, make_user, role):
    client.force_login(make_user("otro", role=role))
    holiday = reyes()

    for method, url in [
        ("get", LIST_URL),
        ("get", CREATE_URL),
        ("post", CREATE_URL),
        ("get", update_url(holiday)),
        ("post", update_url(holiday)),
        ("post", deactivate_url(holiday)),
        ("post", reactivate_url(holiday)),
    ]:
        assert getattr(client, method)(url).status_code == 403, (method, url)


def test_unknown_pk_responds_404(admin_client):
    assert admin_client.get("/parametros/festivos/999999/editar/").status_code == 404
    assert (
        admin_client.post("/parametros/festivos/999999/desactivar/").status_code == 404
    )


@pytest.mark.parametrize("url_name", ["holiday_deactivate", "holiday_reactivate"])
def test_get_on_state_routes_responds_405(admin_client, url_name):
    url = reverse(f"parametros:{url_name}", args=[reyes().pk])

    assert admin_client.get(url).status_code == 405


# Listado


def test_list_of_2027_shows_its_18_holidays_with_weekday(admin_client):
    response = admin_client.get(LIST_URL, {"anio": "2027"})

    assert response.status_code == 200
    assert response.context["year"] == 2027
    rows = response.context["table_rows"]
    assert len(rows) == 18
    content = response.content.decode()
    # Reyes Magos de 2027: lunes 11 de enero.
    assert (
        '<span class="d-none">2027-01-11</span>11/01/2027 '
        '<span class="text-gray-600">(Lunes)</span>'
    ) in content
    assert "Festivos de 2027" in content


def test_list_keeps_the_server_order(admin_client):
    content = admin_client.get(LIST_URL, {"anio": "2027"}).content.decode()

    assert 'data-order="[]"' in content
    assert content.index("2027-01-01") < content.index("2027-12-25")


@pytest.mark.parametrize("raw", ["abc", "1980", "2101", ""])
def test_invalid_year_shows_the_current_year(admin_client, raw):
    response = admin_client.get(LIST_URL, {"anio": raw})

    assert response.context["year"] == 2026


def test_year_selector_lists_loaded_years_plus_current_and_next(admin_client):
    response = admin_client.get(LIST_URL, {"anio": "2040"})

    assert response.context["years"] == [2026, 2027, 2028, 2029, 2030, 2040]
    assert '<option value="2040" selected>2040</option>' in response.content.decode()


def test_list_shows_origin_status_and_actions(admin_client):
    Holiday.objects.create(date=date(2027, 2, 13), name="Aniversario del negocio")
    Holiday.objects.filter(pk=reyes().pk).update(is_active=False)

    content = admin_client.get(LIST_URL, {"anio": "2027"}).content.decode()

    assert "<td>Propio</td>" in content
    assert "<td>Oficial</td>" in content
    assert '<span class="badge badge-secondary">Inactivo</span>' in content
    assert f'action="{reactivate_url(reyes())}"' in content
    assert f'action="{deactivate_url(reyes())}"' not in content
    assert "data-confirm=" in content


def test_no_warning_when_current_and_next_year_are_loaded(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert "No hay festivos oficiales cargados" not in content


def test_warning_when_next_year_is_not_loaded(admin_client, monkeypatch):
    monkeypatch.setattr(views.timezone, "localdate", lambda: date(2030, 3, 1))

    content = admin_client.get(LIST_URL).content.decode()

    assert "alert-warning" in content
    assert "No hay festivos oficiales cargados para 2031." in content
    assert "<code>cargar_festivos 2031</code>" in content
    assert "para 2030." not in content


def test_warning_disappears_after_loading_the_year(admin_client, monkeypatch):
    monkeypatch.setattr(views.timezone, "localdate", lambda: date(2030, 3, 1))
    load_official_holidays(2031)

    content = admin_client.get(LIST_URL).content.decode()

    assert "No hay festivos oficiales cargados" not in content


# Crear y editar


def test_create_form_has_date_and_name(admin_client):
    response = admin_client.get(CREATE_URL)

    assert list(response.context["form"].fields) == ["date", "name"]
    assert 'type="date"' in response.content.decode()


def test_create_custom_holiday_redirects_to_its_year(admin_client):
    response = admin_client.post(
        CREATE_URL, {"date": "2027-02-13", "name": "Aniversario del negocio"}
    )

    assert response.status_code == 302
    assert response.url == f"{LIST_URL}?anio=2027"
    holiday = Holiday.objects.get(date=date(2027, 2, 13))
    assert holiday.origin == HolidayOrigin.CUSTOM
    follow = admin_client.get(response.url)
    assert page_messages(follow) == ["Se guardó Aniversario del negocio."]


def test_create_on_an_occupied_date_shows_the_error(admin_client):
    response = admin_client.post(CREATE_URL, {"date": "2027-01-11", "name": "Otro"})

    assert response.status_code == 200
    assert response.context["form"].errors["date"] == [
        "Ya hay un festivo activo el 11/01/2027."
    ]
    assert not holiday_events().exists()


def test_edit_official_shows_origin_and_code_read_only(admin_client):
    response = admin_client.get(update_url(reyes()))
    content = response.content.decode()

    assert list(response.context["form"].fields) == ["date", "name"]
    assert "<code>reyes_magos</code>" in content
    assert "Oficial" in content
    assert 'value="2027-01-11"' in content


def test_edit_changes_date_and_keeps_official_fields(admin_client):
    holiday = reyes()

    response = admin_client.post(
        update_url(holiday),
        {"date": "2027-01-06", "name": "Reyes", "origin": "custom"},
    )

    assert response.status_code == 302
    holiday.refresh_from_db()
    assert holiday.date == date(2027, 1, 6)
    assert holiday.origin == HolidayOrigin.OFFICIAL
    assert holiday.official_code == "reyes_magos"


def test_edit_without_changes_shows_no_changes(admin_client):
    holiday = reyes()

    response = admin_client.post(
        update_url(holiday), {"date": "2027-01-11", "name": holiday.name}
    )

    assert page_messages(admin_client.get(response.url)) == [
        "No hubo cambios en Día de los Reyes Magos."
    ]
    assert not holiday_events().exists()


def test_edit_with_errors_keeps_the_saved_name(admin_client):
    response = admin_client.post(
        update_url(reyes()), {"date": "2027-01-01", "name": "Cambiado"}
    )

    assert response.status_code == 200
    assert "date" in response.context["form"].errors
    assert "Editar Día de los Reyes Magos" in response.content.decode()


# Desactivar y reactivar


def test_deactivate_and_reactivate_from_the_screen(admin_client):
    response = admin_client.post(deactivate_url(reyes()))

    assert response.url == f"{LIST_URL}?anio=2027"
    assert not reyes().is_active
    assert page_messages(admin_client.get(response.url)) == [
        "Se desactivó Día de los Reyes Magos."
    ]

    admin_client.post(reactivate_url(reyes()))

    assert reyes().is_active


def test_reactivate_on_an_occupied_date_shows_the_error(admin_client):
    Holiday.objects.filter(pk=reyes().pk).update(is_active=False)
    Holiday.objects.create(date=date(2027, 1, 11), name="Propio")

    response = admin_client.post(reactivate_url(reyes()))

    assert response.url == f"{LIST_URL}?anio=2027"
    assert not reyes().is_active
    assert page_messages(admin_client.get(response.url)) == [
        "Ya hay un festivo activo el 11/01/2027."
    ]


def test_a_service_error_after_a_valid_form_is_shown_on_the_form(
    admin_client, monkeypatch
):
    # Por ejemplo, otro administrador ocupó la fecha entre la validación del
    # formulario y el guardado.
    def rejected(*args, **kwargs):
        raise ValidationError({"date": "Ya hay un festivo activo el 13/02/2027."})

    monkeypatch.setattr(services, "create_holiday", rejected)

    response = admin_client.post(CREATE_URL, {"date": "2027-02-13", "name": "Propio"})

    assert response.status_code == 200
    assert response.context["form"].errors["date"] == [
        "Ya hay un festivo activo el 13/02/2027."
    ]
