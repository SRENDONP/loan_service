"""Middleware de la auditoría (SPEC 05, §3.4)."""

from collections.abc import Callable

from django.http import HttpRequest, HttpResponse

from apps.auditoria.context import context_from_request, use_context


class AuditContextMiddleware:
    """
    Fija el contexto de auditoría al empezar cada petición.

    Lo restablece al terminar, aunque la vista lance una excepción. Va justo
    después de AuthenticationMiddleware.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        with use_context(context_from_request(request)):
            return self.get_response(request)
