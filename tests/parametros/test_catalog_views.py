"""Pruebas de las pantallas de los catálogos de texto (SPEC 07, §3.9 y §3.10)."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.accounts.roles import Role
from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent
from apps.parametros import services
from apps.parametros.catalogs import CATALOGS, RELATION_CODEBTOR, get_catalog
from apps.parametros.models import CreditPurpose, Occupation, ThirdPartyRelationType

pytestmark = pytest.mark.django_db

OCCUPATIONS = get_catalog("ocupaciones")
LIST_URL = reverse(OCCUPATIONS.list_url_name)
CREATE_URL = reverse("parametros:catalog_create", args=["ocupaciones"])
CATALOG_ACTIONS = [
    AuditAction.CATALOG_ITEM_CREATED,
    AuditAction.CATALOG_ITEM_UPDATED,
    AuditAction.CATALOG_ITEM_DEACTIVATED,
    AuditAction.CATALOG_ITEM_REACTIVATED,
]


def tendero() -> Occupation:
    return Occupation.objects.get(code="TENDERO")


def update_url(item, slug="ocupaciones") -> str:
    return reverse("parametros:catalog_update", args=[slug, item.pk])


def deactivate_url(item, slug="ocupaciones") -> str:
    return reverse("parametros:catalog_deactivate", args=[slug, item.pk])


def reactivate_url(item, slug="ocupaciones") -> str:
    return reverse("parametros:catalog_reactivate", args=[slug, item.pk])


def page_messages(response) -> list[str]:
    return [str(message) for message in response.context["messages"]]


def catalog_events():
    return AuditEvent.objects.filter(action__in=CATALOG_ACTIONS)


@pytest.fixture
def admin_client(client, make_user):
    client.force_login(make_user("admin1", role=Role.ADMINISTRATOR))
    return client


def all_routes() -> list[tuple[str, str]]:
    item = tendero()
    return [
        ("get", LIST_URL),
        ("get", CREATE_URL),
        ("post", CREATE_URL),
        ("get", update_url(item)),
        ("post", update_url(item)),
        ("post", deactivate_url(item)),
        ("post", reactivate_url(item)),
    ]


# Rutas


def test_list_urls_follow_the_spec():
    assert LIST_URL == "/parametros/catalogos/ocupaciones/"
    assert CREATE_URL == "/parametros/catalogos/ocupaciones/nuevo/"
    assert update_url(tendero()) == (
        f"/parametros/catalogos/ocupaciones/{tendero().pk}/editar/"
    )


# Menú y permisos


def test_administrator_sees_the_catalogs_submenu_with_its_entries(admin_client):
    response = admin_client.get(reverse("parametros:global"))
    content = response.content.decode()

    assert "Catálogos" in content
    for catalog in CATALOGS:
        assert f'href="{reverse(catalog.list_url_name)}"' in content


@pytest.mark.parametrize("catalog", CATALOGS, ids=lambda catalog: catalog.slug)
def test_each_list_responds_200_for_the_administrator(admin_client, catalog):
    response = admin_client.get(reverse(catalog.list_url_name))

    assert response.status_code == 200
    assert str(catalog.label) in response.content.decode()


def test_the_list_marks_its_menu_entry_as_active(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert f'class="collapse-item active" href="{LIST_URL}"' in content
    assert 'id="collapse-parametros-catalogos" class="collapse show"' in content


@pytest.mark.parametrize("role", [Role.SUPERVISOR, Role.COLLECTOR, Role.VIEWER])
def test_other_roles_do_not_see_catalogs_and_get_403(client, make_user, role):
    client.force_login(make_user("otro", role=role))

    home = client.get(reverse("core:home")).content.decode()
    assert "Catálogos" not in home
    for method, url in all_routes():
        assert getattr(client, method)(url).status_code == 403, (method, url)


def test_unknown_slug_responds_404(admin_client):
    assert admin_client.get("/parametros/catalogos/no-existe/").status_code == 404
    assert admin_client.get("/parametros/catalogos/no-existe/nuevo/").status_code == (
        404
    )
    assert admin_client.get(
        "/parametros/catalogos/no-existe/1/editar/"
    ).status_code == (404)


def test_pk_of_another_catalog_responds_404(admin_client):
    # Un pk que existe en Destinos de crédito, pero no en Tipos de relación.
    purpose = CreditPurpose.objects.create(code="SOLO_DESTINOS", name="Solo destinos")
    assert not ThirdPartyRelationType.objects.filter(pk=purpose.pk).exists()

    response = admin_client.get(update_url(purpose, slug="tipos-relacion"))

    assert response.status_code == 404


@pytest.mark.parametrize("url_name", ["catalog_deactivate", "catalog_reactivate"])
def test_get_on_state_routes_responds_405(admin_client, url_name):
    url = reverse(f"parametros:{url_name}", args=["ocupaciones", tendero().pk])

    assert admin_client.get(url).status_code == 405


# Listado


def test_list_shows_active_and_inactive_items_with_badges(admin_client):
    Occupation.objects.filter(code="TENDERO").update(is_active=False)

    response = admin_client.get(LIST_URL)
    rows = response.context["table_rows"]

    assert [row[0] for row in rows][:2] == ["COMERCIANTE", "TENDERO"]
    content = response.content.decode()
    assert '<span class="badge badge-success">Activo</span>' in content
    assert '<span class="badge badge-secondary">Inactivo</span>' in content
    assert f'action="{reactivate_url(tendero())}"' in content
    assert f'action="{deactivate_url(tendero())}"' not in content


def test_list_keeps_the_catalog_order_in_datatables(admin_client):
    Occupation.objects.filter(code="OTRA").update(display_order=1)

    response = admin_client.get(LIST_URL)
    content = response.content.decode()

    # DataTables no reordena por la primera columna (el código) al cargar.
    assert 'data-order="[]"' in content
    assert response.context["table_rows"][0][0] == "OTRA"


def test_other_tables_keep_the_default_order(admin_client):
    content = admin_client.get(reverse("accounts:user_list")).content.decode()

    assert "data-order" not in content


def test_list_has_a_new_button(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert f'href="{CREATE_URL}"' in content


def test_relation_types_list_marks_system_items_without_deactivate(admin_client):
    slug = "tipos-relacion"
    response = admin_client.get(reverse(get_catalog(slug).list_url_name))
    content = response.content.decode()

    assert content.count('<span class="badge badge-info">Sistema</span>') == 2
    for code in (RELATION_CODEBTOR, "REFERENCIA_PERSONAL"):
        item = ThirdPartyRelationType.objects.get(code=code)
        assert f'action="{deactivate_url(item, slug)}"' not in content
        assert f'href="{update_url(item, slug)}"' in content
    familiar = ThirdPartyRelationType.objects.get(code="FAMILIAR")
    assert f'action="{deactivate_url(familiar, slug)}"' in content


def test_state_forms_ask_for_confirmation(admin_client):
    content = admin_client.get(LIST_URL).content.decode()

    assert "data-confirm=" in content


def test_list_escapes_item_names(admin_client):
    Occupation.objects.create(code="XSS", name="<script>alert(1)</script>")

    content = admin_client.get(LIST_URL).content.decode()

    assert "<script>alert(1)</script>" not in content
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in content


# Crear


def test_create_form_has_optional_code(admin_client):
    response = admin_client.get(CREATE_URL)
    form = response.context["form"]

    assert response.status_code == 200
    assert list(form.fields) == ["code", "name", "display_order"]
    assert not form.fields["code"].required
    assert "Si lo dejas vacío, se genera del nombre." in response.content.decode()


def test_create_without_code_generates_it_and_redirects(admin_client):
    response = admin_client.post(
        CREATE_URL, {"code": "", "name": "Vendedor de feria", "display_order": "90"}
    )

    assert response.status_code == 302
    assert response.url == LIST_URL
    item = Occupation.objects.get(name="Vendedor de feria")
    assert item.code == "VENDEDOR_DE_FERIA"
    assert item.display_order == 90
    follow = admin_client.get(LIST_URL)
    assert page_messages(follow) == ["Se guardó Vendedor de feria."]


def test_create_with_lowercase_code_saves_it_uppercase(admin_client):
    admin_client.post(
        CREATE_URL,
        {"code": "vendedor_feria", "name": "Vendedor de feria", "display_order": "0"},
    )

    assert Occupation.objects.filter(code="VENDEDOR_FERIA").exists()


def test_create_with_errors_responds_200_with_field_errors(admin_client):
    response = admin_client.post(
        CREATE_URL, {"code": "CON ESPACIO", "name": "tendero", "display_order": "0"}
    )

    assert response.status_code == 200
    errors = response.context["form"].errors
    assert "code" in errors
    assert errors["name"] == ["Ya existe un ítem con ese nombre."]
    assert not catalog_events().exists()


def test_create_with_a_repeated_generated_name_shows_the_name_error(admin_client):
    response = admin_client.post(
        CREATE_URL, {"code": "", "name": "Otra", "display_order": "0"}
    )

    assert response.status_code == 200
    assert "name" in response.context["form"].errors


def test_a_service_error_after_a_valid_form_is_shown_on_the_form(
    admin_client, monkeypatch
):
    # Por ejemplo, otro administrador creó el mismo nombre entre la validación
    # del formulario y el guardado.
    def rejected(*args, **kwargs):
        raise ValidationError({"name": "Ya existe un ítem con ese nombre."})

    monkeypatch.setattr(services, "create_catalog_item", rejected)

    response = admin_client.post(
        CREATE_URL, {"code": "", "name": "Vendedor de feria", "display_order": "0"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors["name"] == [
        "Ya existe un ítem con ese nombre."
    ]


# Editar


def test_update_form_shows_the_code_as_read_only(admin_client):
    response = admin_client.get(update_url(tendero()))
    form = response.context["form"]

    assert list(form.fields) == ["name", "display_order"]
    assert "<code>TENDERO</code>" in response.content.decode()
    assert 'name="code"' not in response.content.decode()


def test_update_saves_and_ignores_the_code(admin_client):
    response = admin_client.post(
        update_url(tendero()),
        {"name": "Tendero de barrio", "display_order": "15", "code": "NUEVO"},
    )

    assert response.status_code == 302
    item = Occupation.objects.get(pk=tendero().pk)
    assert item.name == "Tendero de barrio"
    assert item.display_order == 15
    assert item.code == "TENDERO"
    assert page_messages(admin_client.get(LIST_URL)) == ["Se guardó Tendero de barrio."]


def test_update_without_changes_shows_no_changes_and_records_nothing(admin_client):
    item = tendero()

    admin_client.post(
        update_url(item), {"name": item.name, "display_order": item.display_order}
    )

    assert page_messages(admin_client.get(LIST_URL)) == ["No hubo cambios en Tendero."]
    assert not catalog_events().exists()


def test_update_with_errors_keeps_the_saved_name_in_the_heading(admin_client):
    response = admin_client.post(
        update_url(tendero()), {"name": "Comerciante", "display_order": "20"}
    )

    assert response.status_code == 200
    assert response.context["form"].errors["name"] == [
        "Ya existe un ítem con ese nombre."
    ]
    assert "Editar Tendero" in response.content.decode()
    assert tendero().name == "Tendero"


def test_system_item_can_be_renamed(admin_client):
    item = ThirdPartyRelationType.objects.get(code=RELATION_CODEBTOR)

    admin_client.post(
        update_url(item, "tipos-relacion"), {"name": "Fiador", "display_order": "10"}
    )

    item.refresh_from_db()
    assert item.name == "Fiador"
    assert item.code == RELATION_CODEBTOR


# Desactivar y reactivar


def test_deactivate_and_reactivate_from_the_screen(admin_client):
    response = admin_client.post(deactivate_url(tendero()))

    assert response.status_code == 302
    assert response.url == LIST_URL
    assert not tendero().is_active
    assert page_messages(admin_client.get(LIST_URL)) == ["Se desactivó Tendero."]

    admin_client.post(reactivate_url(tendero()))

    assert tendero().is_active
    assert page_messages(admin_client.get(LIST_URL)) == ["Se reactivó Tendero."]


def test_deactivating_a_system_item_shows_the_rule_error(admin_client):
    item = ThirdPartyRelationType.objects.get(code=RELATION_CODEBTOR)
    slug = "tipos-relacion"

    response = admin_client.post(deactivate_url(item, slug))

    assert response.status_code == 302
    item.refresh_from_db()
    assert item.is_active
    follow = admin_client.get(reverse(get_catalog(slug).list_url_name))
    assert page_messages(follow) == ["Un ítem de sistema no se puede desactivar."]
    assert not catalog_events().exists()


def test_reactivating_an_active_item_shows_the_rule_error(admin_client):
    admin_client.post(reactivate_url(tendero()))

    assert page_messages(admin_client.get(LIST_URL)) == ["El ítem ya está activo."]
