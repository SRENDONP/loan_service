"""Pruebas de la pantalla de parámetros globales y su menú (SPEC 06, §3.8 y §3.9)."""

import pytest
from django.urls import reverse

from apps.accounts.roles import Role
from apps.auditoria.models import AuditEvent
from apps.parametros.models import GlobalSettings

pytestmark = pytest.mark.django_db

PAGE = reverse("parametros:global")
UPDATE_URLS = {
    "business": reverse("parametros:update_business"),
    "collection": reverse("parametros:update_collection"),
    "rounding": reverse("parametros:update_rounding"),
    "security": reverse("parametros:update_security"),
}

BUSINESS = {
    "business_name": "Gestión de préstamos",
    "brand_icon": "fas fa-hand-holding-usd",
    "currency_code": "COP",
    "currency_symbol": "$",
    "currency_decimals": "0",
    "date_format": "d/m/Y",
}
COLLECTION = {
    "collection_weekdays": ["1", "2", "3", "4", "5", "6"],
    "collection_start_time": "06:00",
    "collection_end_time": "20:00",
    "non_business_weekdays": ["7"],
    "holiday_shift_rule": "cascade",
}
ROUNDING = {"rounding_multiple": "50", "rounding_mode": "half_up"}
SECURITY = {
    "max_failed_attempts": "5",
    "lockout_minutes": "15",
    "password_min_length": "8",
    "password_reset_timeout_minutes": "60",
    "session_idle_timeout_minutes": "30",
    "session_max_hours": "12",
}
DEFAULTS = {
    "business": BUSINESS,
    "collection": COLLECTION,
    "rounding": ROUNDING,
    "security": SECURITY,
}


@pytest.fixture
def administrator(make_user):
    return make_user("admin1", role=Role.ADMINISTRATOR, first_name="Ada")


@pytest.fixture
def admin_client(client, administrator):
    client.force_login(administrator)
    return client


def row() -> GlobalSettings:
    return GlobalSettings.objects.get()


def page_messages(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


# Acceso y menú


def test_administrator_sees_the_page_with_four_cards(admin_client):
    response = admin_client.get(PAGE)

    html = response.content.decode()
    assert response.status_code == 200
    for card in ("business", "collection", "rounding", "security"):
        assert f'id="card-{card}"' in html
        assert f'action="{UPDATE_URLS[card]}"' in html


def test_administrator_sees_the_menu_entry_in_configuracion(admin_client):
    html = admin_client.get(reverse("core:home")).content.decode()

    assert "Configuración" in html
    assert f'href="{PAGE}"' in html
    assert "Parámetros globales" in html
    # La sección va antes de "Administración" (orden 800 frente a 900).
    assert html.index("Configuración") < html.index("Administración")


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_get_403_and_no_menu_entry(client, make_user, role):
    client.force_login(make_user("otro", role=role))

    assert f'href="{PAGE}"' not in client.get(reverse("core:home")).content.decode()
    assert client.get(PAGE).status_code == 403
    for group, url in UPDATE_URLS.items():
        assert client.post(url, DEFAULTS[group]).status_code == 403


@pytest.mark.parametrize("url", list(UPDATE_URLS.values()))
def test_get_to_a_save_route_is_405(admin_client, url):
    assert admin_client.get(url).status_code == 405


def test_page_requires_login(client):
    response = client.get(PAGE)

    assert response.status_code == 302
    assert response.url.startswith(reverse("accounts:login"))


# Contenido


def test_business_card_shows_time_zone_read_only(admin_client):
    html = admin_client.get(PAGE).content.decode()

    assert 'readonly class="form-control-plaintext" id="time-zone"' in html
    assert 'value="America/Bogota"' in html
    assert 'name="time_zone"' not in html


def test_page_shows_initial_state_without_editor(admin_client):
    html = admin_client.get(PAGE).content.decode()

    assert "Todavía nadie ha editado los parámetros" in html


def test_page_shows_last_update_and_editor(admin_client, administrator):
    admin_client.post(UPDATE_URLS["rounding"], ROUNDING | {"rounding_multiple": "100"})

    html = admin_client.get(PAGE).content.decode()
    last = html.split('id="last-update"', 1)[1].split("</p>", 1)[0]

    assert "Última edición:" in last
    assert "Ada" in last


def test_page_renders_the_fields_with_their_widgets(admin_client):
    html = admin_client.get(PAGE).content.decode()

    assert 'type="time" name="collection_start_time" value="06:00"' in html
    assert html.count('name="collection_weekdays"') == 7
    assert 'name="non_business_weekdays" value="7"' in html
    assert '<i class="fas fa-hand-holding-usd fa-2x"' in html


# Guardado


@pytest.mark.parametrize(
    ("group", "field", "value", "expected", "title"),
    [
        (
            "business",
            "business_name",
            "Créditos Ya",
            "Créditos Ya",
            "negocio y formatos",
        ),
        (
            "collection",
            "collection_weekdays",
            ["1", "3"],
            [1, 3],
            "cobro y días no hábiles",
        ),
        ("rounding", "rounding_multiple", "1000", 1000, "redondeo"),
        ("security", "max_failed_attempts", "3", 3, "seguridad y sesión"),
    ],
)
def test_valid_save_redirects_with_message_and_changes_only_its_group(
    admin_client, group, field, value, expected, title
):
    response = admin_client.post(
        UPDATE_URLS[group], DEFAULTS[group] | {field: value}, follow=True
    )

    assert response.redirect_chain == [(PAGE, 302)]
    assert page_messages(response) == [f"Se guardaron los parámetros de {title}."]
    current = row()
    assert getattr(current, field) == expected
    # Los demás grupos siguen con sus valores.
    if group != "business":
        assert current.business_name == "Gestión de préstamos"
    if group != "security":
        assert current.max_failed_attempts == 5


def test_field_of_another_group_is_ignored(admin_client):
    admin_client.post(
        UPDATE_URLS["rounding"],
        ROUNDING | {"rounding_multiple": "100", "business_name": "Otro"},
    )

    assert row().rounding_multiple == 100
    assert row().business_name == "Gestión de préstamos"


def test_invalid_save_shows_errors_in_its_card_and_keeps_the_row(admin_client):
    response = admin_client.post(
        UPDATE_URLS["security"], SECURITY | {"max_failed_attempts": "2"}
    )

    html = response.content.decode()
    security = html.split('id="card-security"', 1)[1]
    others = html.split('id="card-security"', 1)[0]
    assert response.status_code == 200
    assert 'name="max_failed_attempts"' in security
    assert "is-invalid" in security
    assert "is-invalid" not in others
    assert row().max_failed_attempts == 5


def test_cross_field_error_is_shown(admin_client):
    response = admin_client.post(
        UPDATE_URLS["collection"],
        COLLECTION | {"collection_start_time": "21:00"},
    )

    assert response.status_code == 200
    assert (
        "La hora de inicio debe ser anterior a la de fin." in response.content.decode()
    )
    assert str(row().collection_start_time) == "06:00:00"


def test_no_collection_days_shows_the_spec_message(admin_client):
    data = dict(COLLECTION)
    del data["collection_weekdays"]

    response = admin_client.post(UPDATE_URLS["collection"], data)

    assert response.status_code == 200
    html = response.content.decode()
    assert "Elige al menos un día de cobro." in html
    assert "invalid-feedback d-block" in html


def test_save_without_changes_shows_message_and_records_nothing(admin_client):
    response = admin_client.post(UPDATE_URLS["business"], BUSINESS, follow=True)

    assert page_messages(response) == ["No hubo cambios en negocio y formatos."]
    assert not AuditEvent.objects.filter(action__startswith="parametros.").exists()


def test_service_validation_error_is_shown_in_the_form(admin_client, monkeypatch):
    from django.core.exceptions import ValidationError

    from apps.parametros import views

    def failing(actor, data):
        raise ValidationError({"rounding_mode": "Error del servicio."})

    group = views.GROUPS_BY_KEY["rounding"]
    monkeypatch.setitem(
        views.GROUPS_BY_KEY,
        "rounding",
        views.Group(group.key, group.title, group.form_class, failing, group.url_name),
    )

    response = admin_client.post(UPDATE_URLS["rounding"], ROUNDING)

    assert response.status_code == 200
    assert "Error del servicio." in response.content.decode()
