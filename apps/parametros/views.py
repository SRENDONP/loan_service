"""
Pantalla de parámetros globales (SPEC 06, §3.9).

Una página con una tarjeta y un formulario por grupo. Cada formulario envía a
su propia ruta, que solo acepta POST y llama al servicio de edición del grupo.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings as django_settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View

from apps.accounts.permissions import PermissionRequiredMixin
from apps.parametros import services
from apps.parametros.forms import (
    BusinessForm,
    CollectionForm,
    RoundingForm,
    SecurityForm,
)
from apps.parametros.models import GlobalSettings

TEMPLATE = "parametros/global_settings.html"


@dataclass(frozen=True)
class Group:
    key: str
    title: str
    form_class: type
    service: Callable[..., GlobalSettings]
    url_name: str


GROUPS: tuple[Group, ...] = (
    Group(
        "business",
        gettext_lazy("negocio y formatos"),
        BusinessForm,
        services.update_business,
        "parametros:update_business",
    ),
    Group(
        "collection",
        gettext_lazy("cobro y días no hábiles"),
        CollectionForm,
        services.update_collection,
        "parametros:update_collection",
    ),
    Group(
        "rounding",
        gettext_lazy("redondeo"),
        RoundingForm,
        services.update_rounding,
        "parametros:update_rounding",
    ),
    Group(
        "security",
        gettext_lazy("seguridad y sesión"),
        SecurityForm,
        services.update_security,
        "parametros:update_security",
    ),
)
GROUPS_BY_KEY = {group.key: group for group in GROUPS}


def render_page(
    request: HttpRequest, bound: dict[str, Any] | None = None
) -> HttpResponse:
    """La página con los cuatro formularios. `bound` reemplaza el de un grupo."""
    current = services.get_settings()
    forms = {group.key: group.form_class(instance=current) for group in GROUPS}
    forms.update(bound or {})
    context = {
        "settings_row": current,
        "forms": forms,
        "time_zone": django_settings.TIME_ZONE,
    }
    return render(request, TEMPLATE, context)


class GlobalSettingsView(PermissionRequiredMixin, View):
    """Muestra los parámetros globales. Solo para el Administrador."""

    permission_required = "parametros.view_globalsettings"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        return render_page(request)


class GroupUpdateView(PermissionRequiredMixin, View):
    """Guarda un grupo de parámetros. Solo acepta POST (un GET responde 405)."""

    permission_required = "parametros.change_globalsettings"
    http_method_names = ["post", "options"]
    group_key: str = ""

    def post(self, request: HttpRequest) -> HttpResponse:
        group = GROUPS_BY_KEY[self.group_key]
        form = group.form_class(request.POST, instance=services.get_settings())
        if form.is_valid():
            previous_update = services.get_settings().updated_at
            try:
                saved = group.service(request.user, form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if saved.updated_at != previous_update:
                    messages.success(
                        request,
                        _("Se guardaron los parámetros de %(group)s.")
                        % {"group": group.title},
                    )
                else:
                    messages.info(
                        request,
                        _("No hubo cambios en %(group)s.") % {"group": group.title},
                    )
                return redirect("parametros:global")
        return render_page(request, bound={group.key: form})
