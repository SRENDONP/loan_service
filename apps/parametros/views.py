"""
Pantallas de parámetros globales (SPEC 06, §3.9) y de catálogos (SPEC 07, §3.10).

Parámetros globales: una página con una tarjeta y un formulario por grupo. Cada
formulario envía a su propia ruta, que solo acepta POST y llama al servicio de
edición del grupo.

Catálogos: una sola familia de vistas sirve a los seis catálogos de texto. El
catálogo sale del `slug` de la ruta y el permiso, de su modelo.
"""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from django.conf import settings as django_settings
from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy
from django.views import View

from apps.accounts.permissions import PermissionRequiredMixin
from apps.parametros import services
from apps.parametros.catalogs import Catalog, get_catalog
from apps.parametros.formatting import format_date
from apps.parametros.forms import (
    BusinessForm,
    CollectionForm,
    HolidayForm,
    RoundingForm,
    SecurityForm,
    catalog_item_form,
)
from apps.parametros.holidays import MAX_YEAR, MIN_YEAR
from apps.parametros.models import CatalogItem, GlobalSettings, Holiday, Weekday

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


# Catálogos de texto (SPEC 07, §3.10)


def active_badge(is_active: bool) -> SafeString:
    if is_active:
        return format_html('<span class="badge badge-success">{}</span>', _("Activo"))
    return format_html('<span class="badge badge-secondary">{}</span>', _("Inactivo"))


def catalog_status(item: CatalogItem) -> SafeString:
    """El estado como insignia; un ítem de sistema lleva además la suya."""
    badge = active_badge(item.is_active)
    if item.is_system:
        return format_html(
            '{} <span class="badge badge-info">{}</span>', badge, _("Sistema")
        )
    return badge


class CatalogMixin(PermissionRequiredMixin):
    """
    Resuelve el catálogo del `slug` y pide el permiso de su modelo.

    Un `slug` que no está en `CATALOGS` responde 404, antes de mirar permisos.
    """

    permission_action = "view"
    catalog: Catalog

    def setup(self, request: HttpRequest, *args: Any, **kwargs: Any) -> None:
        super().setup(request, *args, **kwargs)
        try:
            self.catalog = get_catalog(kwargs["slug"])
        except KeyError:
            raise Http404(_("Ese catálogo no existe.")) from None

    def get_permission_required(self) -> tuple[str, ...]:
        return (self.catalog.permission(self.permission_action),)

    def get_item(self) -> CatalogItem:
        """El ítem del `pk` de la ruta dentro de este catálogo, o 404."""
        return get_object_or_404(self.catalog.model, pk=self.kwargs["pk"])

    def list_redirect(self) -> HttpResponse:
        return redirect(self.catalog.list_url_name)

    def context(self, **extra: Any) -> dict[str, Any]:
        return {"catalog": self.catalog, **extra}


class CatalogListView(CatalogMixin, View):
    """El listado de un catálogo, con activos e inactivos."""

    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, slug: str) -> HttpResponse:
        items = self.catalog.model.objects.all()
        can_change = request.user.has_perm(self.catalog.permission("change"))
        rows = [self.row(request, item, can_change) for item in items]
        return render(
            request,
            "parametros/catalog_list.html",
            self.context(
                can_add=request.user.has_perm(self.catalog.permission("add")),
                table_title=self.catalog.label,
                table_columns=[
                    _("Código"),
                    _("Nombre"),
                    _("Orden"),
                    _("Estado"),
                    _("Acciones"),
                ],
                table_rows=rows,
            ),
        )

    def row(self, request: HttpRequest, item: CatalogItem, can_change: bool) -> list:
        actions = ""
        if can_change:
            actions = render_to_string(
                "parametros/includes/catalog_actions.html",
                {"catalog": self.catalog, "item": item},
                request=request,
            )
        return [
            item.code,
            item.name,
            item.display_order,
            catalog_status(item),
            actions,
        ]


class CatalogFormView(CatalogMixin, View):
    """Crear o editar un ítem. La vista llama al servicio, nunca a `form.save()`."""

    http_method_names = ["get", "post", "head", "options"]
    creating = True

    def get_instance(self) -> CatalogItem | None:
        return None if self.creating else self.get_item()

    def get_form(self, data: Any = None, instance: CatalogItem | None = None):
        form_class = catalog_item_form(self.catalog.model, creating=self.creating)
        return form_class(data, instance=instance)

    def render_form(
        self, request: HttpRequest, form: Any, item: CatalogItem | None, name: str
    ) -> HttpResponse:
        # `name` es el nombre guardado: el formulario con errores no lo cambia.
        return render(
            request,
            "parametros/catalog_form.html",
            self.context(form=form, item=item, item_name=name, creating=self.creating),
        )

    def get(self, request: HttpRequest, slug: str, pk: int | None = None):
        item = self.get_instance()
        name = item.name if item else ""
        return self.render_form(request, self.get_form(instance=item), item, name)

    def post(self, request: HttpRequest, slug: str, pk: int | None = None):
        item = self.get_instance()
        name = item.name if item else ""
        previous_update = item.updated_at if item else None
        form = self.get_form(request.POST, instance=item)
        if form.is_valid():
            try:
                saved = self.save(request, item, form.cleaned_data)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if self.creating or saved.updated_at != previous_update:
                    messages.success(
                        request, _("Se guardó %(name)s.") % {"name": saved.name}
                    )
                else:
                    messages.info(
                        request,
                        _("No hubo cambios en %(name)s.") % {"name": saved.name},
                    )
                return self.list_redirect()
        return self.render_form(request, form, item, name)

    def save(
        self, request: HttpRequest, item: CatalogItem | None, data: dict[str, Any]
    ) -> CatalogItem:
        if self.creating:
            return services.create_catalog_item(request.user, self.catalog, data)
        return services.update_catalog_item(request.user, item, data)


class CatalogCreateView(CatalogFormView):
    permission_action = "add"
    creating = True


class CatalogUpdateView(CatalogFormView):
    permission_action = "change"
    creating = False


class CatalogStateView(CatalogMixin, View):
    """Desactivar o reactivar un ítem. Solo acepta POST (un GET responde 405)."""

    permission_action = "change"
    http_method_names = ["post", "options"]
    service: Callable[..., CatalogItem]
    message: Any

    def post(self, request: HttpRequest, slug: str, pk: int) -> HttpResponse:
        item = self.get_item()
        try:
            saved = self.service(request.user, item)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
        else:
            messages.success(request, self.message % {"name": saved.name})
        return self.list_redirect()


class CatalogDeactivateView(CatalogStateView):
    service = staticmethod(services.deactivate_catalog_item)
    message = gettext_lazy("Se desactivó %(name)s.")


class CatalogReactivateView(CatalogStateView):
    service = staticmethod(services.reactivate_catalog_item)
    message = gettext_lazy("Se reactivó %(name)s.")


# Festivos (SPEC 07, §3.10)

HOLIDAY_LIST = "parametros:holiday_list"


def selected_year(raw: str | None, current: int) -> int:
    """El año de `?anio=`. Uno no numérico o fuera de rango vuelve al actual."""
    try:
        year = int(raw or "")
    except ValueError:
        return current
    return year if MIN_YEAR <= year <= MAX_YEAR else current


def holiday_date_cell(holiday: Holiday) -> SafeString:
    """
    La fecha con el formato de los parámetros y su día de la semana.

    La fecha ISO va primero y oculta: DataTables ordena por el texto de la
    celda, y así el orden es cronológico aunque el formato sea `d/m/Y`.
    """
    return format_html(
        '<span class="d-none">{}</span>{} <span class="text-gray-600">({})</span>',
        holiday.date.isoformat(),
        format_date(holiday.date),
        Weekday(holiday.date.isoweekday()).label,
    )


def list_redirect_for(holiday: Holiday) -> HttpResponse:
    """Vuelve al listado en el año del festivo."""
    return redirect(f"{reverse(HOLIDAY_LIST)}?anio={holiday.date.year}")


class HolidayListView(PermissionRequiredMixin, View):
    """Los festivos de un año, activos e inactivos, de los dos orígenes."""

    permission_required = "parametros.view_holiday"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        current = timezone.localdate().year
        year = selected_year(request.GET.get("anio"), current)
        holidays = Holiday.objects.filter(date__year=year).order_by("date", "pk")
        can_change = request.user.has_perm("parametros.change_holiday")
        loaded_years = {day.year for day in Holiday.objects.dates("date", "year")}
        years = sorted(loaded_years | {current, current + 1, year})
        return render(
            request,
            "parametros/holiday_list.html",
            {
                "year": year,
                "years": years,
                "missing_years": services.missing_official_years(
                    [current, current + 1]
                ),
                "can_add": request.user.has_perm("parametros.add_holiday"),
                "table_title": _("Festivos de %(year)s") % {"year": year},
                "table_columns": [
                    _("Fecha"),
                    _("Nombre"),
                    _("Origen"),
                    _("Estado"),
                    _("Acciones"),
                ],
                "table_rows": [
                    self.row(request, holiday, can_change) for holiday in holidays
                ],
            },
        )

    def row(self, request: HttpRequest, holiday: Holiday, can_change: bool) -> list:
        actions = ""
        if can_change:
            actions = render_to_string(
                "parametros/includes/holiday_actions.html",
                {"holiday": holiday},
                request=request,
            )
        return [
            holiday_date_cell(holiday),
            holiday.name,
            holiday.get_origin_display(),
            active_badge(holiday.is_active),
            actions,
        ]


class HolidayFormView(PermissionRequiredMixin, View):
    """Crear un festivo propio o editar uno. Llama al servicio, nunca a `save()`."""

    http_method_names = ["get", "post", "head", "options"]
    creating = True

    def get_instance(self) -> Holiday | None:
        if self.creating:
            return None
        return get_object_or_404(Holiday, pk=self.kwargs["pk"])

    def render_form(
        self, request: HttpRequest, form: HolidayForm, holiday: Holiday | None
    ) -> HttpResponse:
        # El título usa el festivo guardado: el formulario con errores no lo cambia.
        saved = Holiday.objects.get(pk=holiday.pk) if holiday else None
        return render(
            request,
            "parametros/holiday_form.html",
            {"form": form, "holiday": saved, "creating": self.creating},
        )

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        holiday = self.get_instance()
        return self.render_form(request, HolidayForm(instance=holiday), holiday)

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        holiday = self.get_instance()
        previous_update = holiday.updated_at if holiday else None
        form = HolidayForm(request.POST, instance=holiday)
        if form.is_valid():
            try:
                if self.creating:
                    saved = services.create_holiday(request.user, form.cleaned_data)
                else:
                    saved = services.update_holiday(
                        request.user, holiday, form.cleaned_data
                    )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                if self.creating or saved.updated_at != previous_update:
                    messages.success(
                        request, _("Se guardó %(name)s.") % {"name": saved.name}
                    )
                else:
                    messages.info(
                        request,
                        _("No hubo cambios en %(name)s.") % {"name": saved.name},
                    )
                return list_redirect_for(saved)
        return self.render_form(request, form, holiday)


class HolidayCreateView(HolidayFormView):
    permission_required = "parametros.add_holiday"
    creating = True


class HolidayUpdateView(HolidayFormView):
    permission_required = "parametros.change_holiday"
    creating = False


class HolidayStateView(PermissionRequiredMixin, View):
    """Desactivar o reactivar un festivo. Solo acepta POST (un GET responde 405)."""

    permission_required = "parametros.change_holiday"
    http_method_names = ["post", "options"]
    service: Callable[..., Holiday]
    message: Any

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        holiday = get_object_or_404(Holiday, pk=pk)
        try:
            saved = self.service(request.user, holiday)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
            return list_redirect_for(holiday)
        messages.success(request, self.message % {"name": saved.name})
        return list_redirect_for(saved)


class HolidayDeactivateView(HolidayStateView):
    service = staticmethod(services.deactivate_holiday)
    message = gettext_lazy("Se desactivó %(name)s.")


class HolidayReactivateView(HolidayStateView):
    service = staticmethod(services.reactivate_holiday)
    message = gettext_lazy("Se reactivó %(name)s.")
