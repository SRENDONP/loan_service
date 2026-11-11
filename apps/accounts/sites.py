"""Sitio del admin de Django solo para superusuarios (SPEC 03)."""

from django.contrib.admin import AdminSite
from django.http import HttpRequest


class SuperuserAdminSite(AdminSite):
    """
    Admin de Django al que solo entran superusuarios activos.

    Sirve para crear usuarios hasta la SPEC 04. Su login redirige al login
    propio (`accounts.views.admin_login_redirect`), así que también aplican el
    bloqueo y el cambio obligatorio de contraseña.
    """

    def has_permission(self, request: HttpRequest) -> bool:
        user = request.user
        return user.is_active and user.is_superuser
