"""Pruebas del admin de la auditoría, de solo lectura (SPEC 05, §3.8)."""

import uuid

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.accounts.models import User
from apps.accounts.roles import Role
from apps.auditoria.actions import AuditAction
from apps.auditoria.admin import AuditEventAdmin
from apps.auditoria.context import audit_context
from apps.auditoria.models import AuditEvent, AuditSource
from apps.auditoria.services import record

pytestmark = pytest.mark.django_db

CHANGELIST = reverse("admin:auditoria_auditevent_changelist")
ADD = reverse("admin:auditoria_auditevent_add")


@pytest.fixture
def superuser(password):
    return User.objects.create_superuser("root", "root@example.com", password)


@pytest.fixture
def admin_client(client, superuser):
    client.force_login(superuser)
    return client


@pytest.fixture
def event(user) -> AuditEvent:
    with audit_context(source=AuditSource.WEB, ip_address="10.0.0.1"):
        return record(
            AuditAction.USER_DEACTIVATED,
            actor=user,
            target=user,
            changes={"is_active": [True, False]},
            extra={"reason": "Retiro voluntario"},
        )


def test_audit_event_is_registered():
    assert isinstance(admin.site._registry[AuditEvent], AuditEventAdmin)


def test_superuser_sees_the_list_with_filters(admin_client, event):
    response = admin_client.get(CHANGELIST)

    assert response.status_code == 200
    changelist = response.context["cl"]
    assert event in changelist.result_list
    filters = [spec.title for spec in changelist.filter_specs]
    assert filters == ["categoría", "acción", "origen", "fecha y hora"]
    assert changelist.date_hierarchy == "occurred_at"


def test_list_offers_no_delete_action(admin_client, event):
    response = admin_client.get(CHANGELIST)

    assert "delete_selected" not in response.context["cl"].model_admin.get_actions(
        response.wsgi_request
    )
    assert b"delete_selected" not in response.content


@pytest.mark.parametrize("term", ["cobrador", "10.0.0.1"])
def test_search_by_username_and_ip(admin_client, event, term):
    response = admin_client.get(CHANGELIST, {"q": term})

    assert list(response.context["cl"].result_list) == [event]


def test_search_by_identifier(admin_client):
    event = record(AuditAction.LOGIN_FAILED, identifier="intruso@example.com")

    response = admin_client.get(CHANGELIST, {"q": "intruso"})

    assert list(response.context["cl"].result_list) == [event]


def test_search_by_request_id(admin_client, user):
    with audit_context(request_id=uuid.uuid4()) as context:
        event = record(AuditAction.LOGOUT, actor=user)

    response = admin_client.get(CHANGELIST, {"q": str(context.request_id)})

    assert list(response.context["cl"].result_list) == [event]


def test_detail_is_read_only(admin_client, event):
    url = reverse("admin:auditoria_auditevent_change", args=[event.pk])

    response = admin_client.get(url)

    assert response.status_code == 200
    assert not response.context["adminform"].form.fields
    content = response.content.decode()
    assert 'name="_save"' not in content
    assert 'name="_continue"' not in content
    assert "deletelink" not in content
    # Los cambios y el contexto se muestran como JSON con sangría.
    assert "<pre>{\n  &quot;is_active&quot;: [\n    true,\n    false\n  ]\n}</pre>" in (
        content
    )
    assert "Retiro voluntario" in content


def test_post_to_detail_does_not_change_the_event(admin_client, event):
    url = reverse("admin:auditoria_auditevent_change", args=[event.pk])

    response = admin_client.post(url, {"actor_username": "otro"})

    assert response.status_code == 403
    assert AuditEvent.objects.get(pk=event.pk).actor_username == "cobrador"


def test_add_route_is_forbidden(admin_client):
    assert admin_client.get(ADD).status_code == 403


def test_delete_route_is_forbidden(admin_client, event):
    url = reverse("admin:auditoria_auditevent_delete", args=[event.pk])

    assert admin_client.get(url).status_code == 403
    assert admin_client.post(url, {"post": "yes"}).status_code == 403
    assert AuditEvent.objects.filter(pk=event.pk).exists()


def test_administrator_who_is_not_superuser_cannot_enter(client, make_user):
    client.force_login(make_user("admin1", role=Role.ADMINISTRATOR))

    response = client.get(CHANGELIST)

    assert response.status_code == 302
    assert response.url.startswith(reverse("admin:login"))
