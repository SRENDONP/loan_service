"""Pruebas del contexto de auditoría y de la IP del cliente (SPEC 05, §3.4 y §3.5)."""

import threading
import uuid

import pytest
from django.test import RequestFactory

from apps.auditoria.context import (
    AuditContext,
    audit_context,
    context_from_request,
    get_client_ip,
    get_context,
)
from apps.auditoria.models import AuditSource


@pytest.fixture
def rf() -> RequestFactory:
    return RequestFactory()


# Contexto por defecto y audit_context


def test_default_context_is_system_without_ip():
    context = get_context()

    assert context == AuditContext()
    assert context.source == AuditSource.SYSTEM
    assert context.ip_address is None
    assert context.request_id is None


def test_audit_context_sets_and_restores():
    with audit_context(source=AuditSource.COMMAND) as context:
        assert get_context() is context
        assert get_context().source == AuditSource.COMMAND

    assert get_context() == AuditContext()


def test_audit_context_nests():
    with audit_context(source=AuditSource.COMMAND):
        with audit_context(source=AuditSource.WEB, ip_address="10.0.0.1"):
            assert get_context().source == AuditSource.WEB
        assert get_context().source == AuditSource.COMMAND


def test_audit_context_restores_after_exception():
    with pytest.raises(RuntimeError):
        with audit_context(source=AuditSource.COMMAND):
            raise RuntimeError

    assert get_context() == AuditContext()


def test_context_does_not_cross_threads():
    seen = []

    with audit_context(source=AuditSource.COMMAND):
        thread = threading.Thread(target=lambda: seen.append(get_context()))
        thread.start()
        thread.join()

    assert seen == [AuditContext()]


# context_from_request


def test_context_from_request(rf):
    request = rf.post(
        "/usuarios/?token=secreto",
        REMOTE_ADDR="10.0.0.1",
        HTTP_USER_AGENT="Navegador/1.0",
    )

    context = context_from_request(request)

    assert context.source == AuditSource.WEB
    assert context.ip_address == "10.0.0.1"
    assert context.user_agent == "Navegador/1.0"
    assert context.request_method == "POST"
    assert context.request_path == "/usuarios/"
    assert isinstance(context.request_id, uuid.UUID)


def test_admin_path_has_admin_source(rf):
    context = context_from_request(rf.get("/admin/accounts/user/"))

    assert context.source == AuditSource.ADMIN


def test_each_request_gets_a_new_request_id(rf):
    first = context_from_request(rf.get("/"))
    second = context_from_request(rf.get("/"))

    assert first.request_id != second.request_id


def test_user_agent_and_path_are_truncated(rf):
    long_path = "/" + "a" * 300
    request = rf.get(long_path, HTTP_USER_AGENT="x" * 300)

    context = context_from_request(request)

    assert len(context.user_agent) == 255
    assert len(context.request_path) == 255


def test_missing_user_agent_is_empty(rf):
    assert context_from_request(rf.get("/")).user_agent == ""


def test_source_is_web_when_admin_is_not_routed(rf, settings):
    settings.ROOT_URLCONF = "apps.core.urls"

    assert context_from_request(rf.get("/admin/")).source == AuditSource.WEB


# IP del cliente


def forwarded(rf, header: str, remote: str = "10.0.0.1"):
    return rf.get("/", REMOTE_ADDR=remote, HTTP_X_FORWARDED_FOR=header)


def test_without_trusted_proxies_forwarded_for_is_ignored(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 0

    assert get_client_ip(forwarded(rf, "1.2.3.4")) == "10.0.0.1"


def test_with_one_trusted_proxy_uses_last_entry(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 1

    assert get_client_ip(forwarded(rf, "1.2.3.4")) == "1.2.3.4"
    # El cliente puede anteponer entradas falsas; solo cuenta la del proxy.
    assert get_client_ip(forwarded(rf, "6.6.6.6, 1.2.3.4")) == "1.2.3.4"


def test_with_two_trusted_proxies_counts_from_the_right(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 2

    assert get_client_ip(forwarded(rf, "1.2.3.4, 5.6.7.8")) == "1.2.3.4"


def test_header_shorter_than_trusted_proxies_uses_remote_addr(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 2

    assert get_client_ip(forwarded(rf, "1.2.3.4")) == "10.0.0.1"


def test_missing_header_uses_remote_addr(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 1

    assert get_client_ip(rf.get("/", REMOTE_ADDR="10.0.0.1")) == "10.0.0.1"


@pytest.mark.parametrize("header", ["no-es-ip", "999.1.1.1", ""])
def test_invalid_forwarded_ip_is_none(rf, settings, header):
    settings.AUDIT_TRUSTED_PROXIES = 1

    request = forwarded(rf, f"1.2.3.4, {header}" if header else ",")

    assert get_client_ip(request) is None


def test_invalid_remote_addr_is_none(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 0

    assert get_client_ip(rf.get("/", REMOTE_ADDR="")) is None


def test_ipv6_is_accepted(rf, settings):
    settings.AUDIT_TRUSTED_PROXIES = 0

    assert get_client_ip(rf.get("/", REMOTE_ADDR="::1")) == "::1"
