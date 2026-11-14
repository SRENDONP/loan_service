"""Pruebas de los roles y de su sincronización (SPEC 04, §3.1 y paso 2)."""

from io import StringIO

import pytest
from django.apps import apps
from django.contrib.auth.models import Group, Permission
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.db import connection
from django.test.utils import CaptureQueriesContext

from apps.accounts import roles
from apps.accounts.models import User
from apps.accounts.roles import (
    CATALOG_PERMISSIONS,
    PARAMETROS_PERMISSIONS,
    PRODUCT_PERMISSIONS,
    PRODUCT_VIEW_PERMISSIONS,
    ROLE_PERMISSIONS,
    USER_MANAGEMENT_PERMISSIONS,
    Role,
    get_role,
    has_role,
    sync_roles,
)

pytestmark = pytest.mark.django_db

ROLE_NAMES = {"Administrador", "Supervisor", "Cajero/Cobrador", "Consulta"}


def group_perms(name: str) -> set[str]:
    group = Group.objects.get(name=name)
    return {
        f"{app}.{codename}"
        for app, codename in group.permissions.values_list(
            "content_type__app_label", "codename"
        )
    }


def groups_with(perm: str) -> list[str]:
    """Los roles cuyo grupo tiene `perm`, por nombre."""
    app_label, codename = perm.split(".", 1)
    return list(
        Group.objects.filter(
            name__in=ROLE_NAMES,
            permissions__content_type__app_label=app_label,
            permissions__codename=codename,
        )
        .order_by("name")
        .values_list("name", flat=True)
    )


def test_role_values_are_the_group_names():
    assert set(Role.values) == ROLE_NAMES
    assert set(ROLE_PERMISSIONS) == set(Role)


def test_migrate_creates_the_four_groups():
    # La base de pruebas se crea con migrate, que emite post_migrate.
    assert ROLE_NAMES <= set(Group.objects.values_list("name", flat=True))


def test_administrator_has_user_management_parametros_catalog_and_product_permissions():
    assert group_perms("Administrador") == (
        USER_MANAGEMENT_PERMISSIONS
        | PARAMETROS_PERMISSIONS
        | CATALOG_PERMISSIONS
        | PRODUCT_PERMISSIONS
    )
    assert len(USER_MANAGEMENT_PERMISSIONS) == 7
    # SPEC 06, §3.8.
    assert PARAMETROS_PERMISSIONS == {
        "parametros.view_globalsettings",
        "parametros.change_globalsettings",
    }


def test_catalog_permissions_cover_the_seven_models_without_delete():
    # SPEC 07, §3.9: view, add y change de los seis catálogos y los festivos.
    from apps.parametros.catalogs import CATALOGS
    from apps.parametros.models import Holiday

    models = [catalog.model for catalog in CATALOGS] + [Holiday]
    expected = {
        f"parametros.{action}_{model._meta.model_name}"
        for model in models
        for action in ("view", "add", "change")
    }

    assert CATALOG_PERMISSIONS == expected
    assert len(CATALOG_PERMISSIONS) == 21
    assert not any("delete_" in perm for perm in CATALOG_PERMISSIONS)


@pytest.mark.parametrize("perm", sorted(CATALOG_PERMISSIONS))
def test_only_the_administrator_group_has_each_catalog_permission(perm):
    assert groups_with(perm) == ["Administrador"]


def test_product_permissions_cover_the_four_models_without_delete():
    # SPEC 08, §3.7: view, add y change de productos, versiones, tipos y valores.
    from apps.parametros.models import (
        CreditProduct,
        ProductRateVersion,
        RateCapType,
        RateCapValue,
    )

    models = [CreditProduct, ProductRateVersion, RateCapType, RateCapValue]
    assert PRODUCT_PERMISSIONS == {
        f"parametros.{action}_{model._meta.model_name}"
        for model in models
        for action in ("view", "add", "change")
    }
    assert PRODUCT_VIEW_PERMISSIONS == {
        f"parametros.view_{model._meta.model_name}" for model in models
    }
    assert not any("delete_" in perm for perm in PRODUCT_PERMISSIONS)


# Matriz de la SPEC 08, §3.7: quién tiene cada permiso de productos y topes.
PRODUCT_MATRIX = {
    action: (
        ["Administrador", "Consulta", "Supervisor"]
        if action == "view"
        else ["Administrador"]
    )
    for action in ("view", "add", "change")
}


@pytest.mark.parametrize("perm", sorted(PRODUCT_PERMISSIONS))
def test_product_permission_matrix(perm):
    action = perm.split(".", 1)[1].split("_", 1)[0]

    assert groups_with(perm) == PRODUCT_MATRIX[action]


def test_supervisor_and_viewer_only_see_products_and_rate_caps():
    assert group_perms("Supervisor") == PRODUCT_VIEW_PERMISSIONS
    assert group_perms("Consulta") == PRODUCT_VIEW_PERMISSIONS


def test_only_the_administrator_can_edit_parametros():
    for role, perms in ROLE_PERMISSIONS.items():
        edits_parametros = any(
            perm.startswith("parametros.") and not perm.startswith("parametros.view_")
            for perm in perms
        )
        assert edits_parametros is (role is Role.ADMINISTRATOR)


def test_only_the_administrator_sees_global_settings_and_catalogs():
    for perm in PARAMETROS_PERMISSIONS | CATALOG_PERMISSIONS:
        assert groups_with(perm) == ["Administrador"]


def test_collector_has_no_permissions_yet():
    assert group_perms("Cajero/Cobrador") == set()


def test_delete_user_is_in_no_group():
    assert not Group.objects.filter(permissions__codename="delete_user").exists()


def test_sync_removes_manual_permission_from_managed_group():
    extra = Permission.objects.get(codename="view_group")
    Group.objects.get(name="Consulta").permissions.add(extra)

    call_command("sync_roles", stdout=StringIO())

    assert group_perms("Consulta") == PRODUCT_VIEW_PERMISSIONS


def test_sync_restores_missing_permission():
    group = Group.objects.get(name="Administrador")
    group.permissions.remove(Permission.objects.get(codename="unlock_user"))

    sync_roles()

    assert group_perms("Administrador") == ROLE_PERMISSIONS[Role.ADMINISTRATOR]


def test_sync_recreates_a_deleted_group():
    Group.objects.filter(name="Supervisor").delete()

    sync_roles()

    assert Group.objects.filter(name="Supervisor").exists()


def test_sync_does_not_touch_other_groups():
    other = Group.objects.create(name="Externo")
    other.permissions.add(Permission.objects.get(codename="view_group"))

    sync_roles()

    assert group_perms("Externo") == {"auth.view_group"}


def test_sync_does_not_touch_user_permissions(make_user):
    user = make_user()
    user.user_permissions.add(Permission.objects.get(codename="view_group"))

    sync_roles()

    assert user.user_permissions.filter(codename="view_group").exists()


def test_sync_twice_changes_nothing_the_second_time():
    sync_roles()

    with CaptureQueriesContext(connection) as queries:
        sync_roles()

    writes = [
        q["sql"]
        for q in queries.captured_queries
        if q["sql"].lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE"))
    ]
    assert writes == []


def test_unknown_permission_raises_and_changes_nothing(monkeypatch):
    monkeypatch.setitem(
        roles.ROLE_PERMISSIONS, Role.VIEWER, frozenset({"accounts.does_not_exist"})
    )
    Group.objects.get(name="Administrador").permissions.clear()

    with pytest.raises(ImproperlyConfigured, match="accounts.does_not_exist"):
        sync_roles()

    assert group_perms("Administrador") == set()


def test_command_prints_success():
    out = StringIO()

    call_command("sync_roles", stdout=out)

    assert "Roles sincronizados." in out.getvalue()


def test_receiver_ignores_signals_of_other_apps(monkeypatch):
    calls = []
    monkeypatch.setattr(roles, "sync_roles", lambda **kwargs: calls.append(kwargs))

    roles.sync_roles_after_migrate(sender=apps.get_app_config("auth"), using="x")
    roles.sync_roles_after_migrate(sender=roles._last_app_with_models(), using="x")

    assert calls == [{"using": "x"}]


def test_get_role_and_has_role(make_user):
    user = make_user()
    assert get_role(user) is None

    user.groups.add(Group.objects.get(name="Supervisor"))

    assert get_role(user) is Role.SUPERVISOR
    assert has_role(user, Role.SUPERVISOR)
    assert not has_role(user, Role.ADMINISTRATOR)


def test_get_role_ignores_groups_that_are_not_roles(make_user):
    user = make_user()
    user.groups.add(Group.objects.create(name="Externo"))

    assert get_role(user) is None


def test_get_role_of_superuser_without_group_is_none():
    superuser = User.objects.create_superuser("root", "root@example.com", "x1y2z3w4")

    assert get_role(superuser) is None


def test_get_role_of_unsaved_user_is_none():
    assert get_role(User(username="nuevo")) is None


@pytest.mark.django_db(transaction=True)
def test_groups_survive_flush():
    # flush vuelve a emitir post_migrate, así que los grupos se recrean.
    call_command("flush", interactive=False, verbosity=0)

    assert ROLE_NAMES <= set(Group.objects.values_list("name", flat=True))
    assert group_perms("Administrador") == ROLE_PERMISSIONS[Role.ADMINISTRATOR]


def test_with_role_includes_inactive_users(make_user):
    active = make_user("activo", role=Role.SUPERVISOR)
    inactive = make_user("inactivo", role=Role.SUPERVISOR, is_active=False)
    make_user("otro", role=Role.VIEWER)

    assert set(User.objects.with_role(Role.SUPERVISOR)) == {active, inactive}


def test_collectors_exclude_inactive_superusers_and_other_roles(make_user):
    collector = make_user("cobrador1", role=Role.COLLECTOR)
    make_user("cobrador_inactivo", role=Role.COLLECTOR, is_active=False)
    make_user("cobrador_root", role=Role.COLLECTOR, is_superuser=True)
    make_user("supervisor1", role=Role.SUPERVISOR)
    make_user("sin_rol")

    assert list(User.objects.collectors()) == [collector]


def test_active_administrators_exclude_inactive_and_superusers(make_user):
    administrator = make_user("admin1", role=Role.ADMINISTRATOR)
    make_user("admin_inactivo", role=Role.ADMINISTRATOR, is_active=False)
    make_user("admin_root", role=Role.ADMINISTRATOR, is_superuser=True)
    make_user("root", is_superuser=True)

    assert list(User.objects.active_administrators()) == [administrator]


def test_make_user_with_role_has_exactly_that_role(make_user):
    user = make_user(role=Role.COLLECTOR)

    assert list(user.groups.values_list("name", flat=True)) == ["Cajero/Cobrador"]
