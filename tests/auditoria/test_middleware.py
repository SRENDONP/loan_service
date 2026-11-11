"""Pruebas de AuditContextMiddleware (SPEC 05, §3.4)."""

import pytest
from django.conf import settings
from django.http import HttpResponse
from django.test import RequestFactory

from apps.auditoria.context import AuditContext, get_context
from apps.auditoria.middleware import AuditContextMiddleware
from apps.auditoria.models import AuditSource

MIDDLEWARE_PATH = "apps.auditoria.middleware.AuditContextMiddleware"


def test_middleware_runs_right_after_authentication():
    middleware = settings.MIDDLEWARE
    authentication = middleware.index(
        "django.contrib.auth.middleware.AuthenticationMiddleware"
    )

    assert middleware[authentication + 1] == MIDDLEWARE_PATH


def test_context_is_set_during_the_request_and_restored_after():
    seen = []

    def view(request):
        seen.append(get_context())
        return HttpResponse()

    request = RequestFactory().get("/usuarios/?q=1", REMOTE_ADDR="10.0.0.1")

    AuditContextMiddleware(view)(request)

    assert seen[0].source == AuditSource.WEB
    assert seen[0].ip_address == "10.0.0.1"
    assert seen[0].request_path == "/usuarios/"
    assert seen[0].request_id is not None
    assert get_context() == AuditContext()


def test_context_is_restored_when_the_view_raises():
    def view(request):
        raise RuntimeError

    with pytest.raises(RuntimeError):
        AuditContextMiddleware(view)(RequestFactory().get("/"))

    assert get_context() == AuditContext()


def test_two_requests_have_different_request_ids():
    seen = []

    def view(request):
        seen.append(get_context().request_id)
        return HttpResponse()

    middleware = AuditContextMiddleware(view)
    middleware(RequestFactory().get("/"))
    middleware(RequestFactory().get("/"))

    assert seen[0] != seen[1]


def test_forged_forwarded_for_is_ignored_by_default(settings):
    settings.AUDIT_TRUSTED_PROXIES = 0
    seen = []

    def view(request):
        seen.append(get_context().ip_address)
        return HttpResponse()

    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4"
    )
    AuditContextMiddleware(view)(request)

    assert seen == ["10.0.0.1"]


@pytest.mark.django_db
def test_real_request_passes_through_the_middleware(client):
    # El healthcheck es público, así que la petición atraviesa toda la pila.
    response = client.get("/health/")

    assert response.status_code == 200
    assert get_context() == AuditContext()
