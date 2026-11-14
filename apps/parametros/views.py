"""
Pantallas de parámetros globales (SPEC 06, §3.9), de catálogos (SPEC 07, §3.10)
y de productos de crédito y topes de tasa (SPEC 08, §3.9).

Parámetros globales: una página con una tarjeta y un formulario por grupo. Cada
formulario envía a su propia ruta, que solo acepta POST y llama al servicio de
edición del grupo.

Catálogos: una sola familia de vistas sirve a los seis catálogos de texto. El
catálogo sale del `slug` de la ruta y el permiso, de su modelo.
"""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
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
from django.utils.translation import gettext_lazy, ngettext
from django.views import View

from apps.accounts.permissions import PermissionRequiredMixin
from apps.parametros import services
from apps.parametros.catalogs import (
    RATE_CAP_CATALOG,
    RATE_CAP_USURY,
    Catalog,
    get_catalog,
)
from apps.parametros.formatting import format_date, format_money, format_percent
from apps.parametros.forms import (
    BusinessForm,
    CollectionForm,
    CreditProductForm,
    HolidayForm,
    RateCapValueForm,
    RateVersionForm,
    RoundingForm,
    SecurityForm,
    catalog_item_form,
    global_rounding_label,
)
from apps.parametros.holidays import MAX_YEAR, MIN_YEAR
from apps.parametros.models import (
    CatalogItem,
    CreditProduct,
    GlobalSettings,
    Holiday,
    InitialChargeType,
    Periodicity,
    ProductRateVersion,
    RateCapType,
    RateCapValue,
    RateUnit,
    ValidityVersion,
    Weekday,
)

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


# Historial de vigencia: común a las tasas y a los topes (SPEC 08, §3.9)


def date_cell(value: date | None) -> SafeString:
    """La fecha con formato, con la ISO oculta antes para que DataTables ordene."""
    if value is None:
        return format_html("{}", "—")
    return format_html(
        '<span class="d-none">{}</span>{}', value.isoformat(), format_date(value)
    )


def version_status(
    version: ValidityVersion, today: date, current_pk: int | None
) -> tuple[str, SafeString]:
    """El estado de una versión como (clave, insignia). La plantilla no calcula."""
    if version.voided_at is not None:
        key, css, label = "voided", "badge-dark", _("Anulada")
    elif version.valid_from > today:
        key, css, label = "scheduled", "badge-info", _("Programada")
    elif version.pk == current_pk:
        key, css, label = "current", "badge-success", _("Vigente")
    else:
        key, css, label = "previous", "badge-secondary", _("Anterior")
    return key, format_html('<span class="badge {}">{}</span>', css, label)


def creator_name(version: ValidityVersion) -> str:
    user = version.created_by
    return user.get_full_name() or user.get_username()


def version_rows[V: ValidityVersion](
    request: HttpRequest,
    versions: list[V],
    current: V | None,
    cells: Callable[[V], list[Any]],
    void_url: Callable[[V], str] | None,
    confirm: Callable[[V], str],
) -> list[list[Any]]:
    """
    Las filas de un historial, de la más reciente a la más antigua.

    Solo la última versión programada lleva el botón "Anular", porque el
    servicio solo anula esa. `void_url` es `None` si el usuario no puede anular.
    """
    today = timezone.localdate()
    current_pk = current.pk if current else None
    live = [version for version in versions if version.voided_at is None]
    latest_pk = max(live, key=lambda version: version.valid_from).pk if live else None
    rows = []
    for version in sorted(versions, key=lambda v: (v.valid_from, v.pk), reverse=True):
        key, badge = version_status(version, today, current_pk)
        actions = ""
        if void_url is not None and key == "scheduled" and version.pk == latest_pk:
            actions = render_to_string(
                "parametros/includes/version_actions.html",
                {"void_url": void_url(version), "confirm": confirm(version)},
                request=request,
            )
        rows.append(
            [
                date_cell(version.valid_from),
                date_cell(version.valid_to),
                *cells(version),
                badge,
                creator_name(version),
                actions,
            ]
        )
    return rows


# Topes de tasa (SPEC 08, §3.9)


def percent_with_unit(value: Decimal, unit: str) -> str:
    return f"{format_percent(value)} {unit}"


def ratecap_status(cap_type: RateCapType) -> SafeString:
    """El estado del tipo de tope; la usura lleva además la insignia "Sistema"."""
    return catalog_status(cap_type)


def ratecap_detail_redirect(cap_type: RateCapType) -> HttpResponse:
    return redirect("parametros:ratecap_detail", pk=cap_type.pk)


class RateCapListView(PermissionRequiredMixin, View):
    """Los tipos de tope, con su valor vigente hoy."""

    permission_required = "parametros.view_ratecaptype"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        today = timezone.localdate()
        can_change = request.user.has_perm("parametros.change_ratecaptype")
        cap_types = RateCapType.objects.all()
        rows = [
            self.row(
                request,
                cap_type,
                services.get_rate_cap_value(cap_type, today),
                can_change,
            )
            for cap_type in cap_types
        ]
        usury = services.get_item_by_code(RateCapType, RATE_CAP_USURY)
        columns = [
            _("Nombre"),
            _("Código"),
            _("Valor vigente"),
            _("Desde"),
            _("Estado"),
        ]
        if can_change:
            columns.append(_("Acciones"))
        return render(
            request,
            "parametros/ratecap_list.html",
            {
                "can_add": request.user.has_perm("parametros.add_ratecaptype"),
                "usury_missing": services.get_rate_cap_value(usury, today) is None,
                "table_title": _("Topes de tasa"),
                "table_columns": columns,
                "table_rows": rows,
            },
        )

    def row(
        self,
        request: HttpRequest,
        cap_type: RateCapType,
        value: RateCapValue | None,
        can_change: bool,
    ) -> list[Any]:
        """Una fila. Sin `change`, la fila no lleva la columna de acciones."""
        if value is None:
            value_cell = format_html(
                '<span class="badge badge-warning">{}</span>', _("Sin valor vigente")
            )
            since = date_cell(None)
        else:
            value_cell = percent_with_unit(value.annual_effective_rate, _("% EA"))
            since = date_cell(value.valid_from)
        cells = [
            format_html(
                '<a href="{}">{}</a>',
                reverse("parametros:ratecap_detail", args=[cap_type.pk]),
                cap_type.name,
            ),
            cap_type.code,
            value_cell,
            since,
            ratecap_status(cap_type),
        ]
        if can_change:
            cells.append(
                render_to_string(
                    "parametros/includes/ratecap_actions.html",
                    {"cap_type": cap_type},
                    request=request,
                )
            )
        return cells


class RateCapDetailView(PermissionRequiredMixin, View):
    """Un tipo de tope: sus datos, los productos que lo usan y sus valores."""

    permission_required = "parametros.view_ratecaptype"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        cap_type = get_object_or_404(RateCapType, pk=pk)
        today = timezone.localdate()
        current = services.get_rate_cap_value(cap_type, today)
        can_void = request.user.has_perm("parametros.change_ratecapvalue")
        values = list(cap_type.values.select_related("created_by"))
        rows = version_rows(
            request,
            values,
            current,
            cells=lambda value: [
                percent_with_unit(value.annual_effective_rate, _("% EA")),
                value.reference,
            ],
            void_url=(
                (
                    lambda value: reverse(
                        "parametros:ratecap_value_void", args=[cap_type.pk, value.pk]
                    )
                )
                if can_void
                else None
            ),
            confirm=lambda value: _(
                "El valor de %(cap)s que iba a regir desde el %(date)s queda anulado "
                "y no se aplicará. ¿Anular?"
            )
            % {"cap": cap_type.name, "date": format_date(value.valid_from)},
        )
        return render(
            request,
            "parametros/ratecap_detail.html",
            {
                "cap_type": cap_type,
                "status": ratecap_status(cap_type),
                "is_usury": cap_type.code == RATE_CAP_USURY,
                "products": cap_type.products.order_by("name"),
                "current": current,
                "current_value": (
                    percent_with_unit(current.annual_effective_rate, _("% EA"))
                    if current
                    else ""
                ),
                "can_change": request.user.has_perm("parametros.change_ratecaptype"),
                "can_add_value": request.user.has_perm("parametros.add_ratecapvalue"),
                "table_title": _("Valores"),
                "table_columns": [
                    _("Desde"),
                    _("Hasta"),
                    _("Valor"),
                    _("Referencia"),
                    _("Estado"),
                    _("Creado por"),
                    _("Acciones"),
                ],
                "table_rows": rows,
            },
        )


class RateCapFormView(PermissionRequiredMixin, View):
    """
    Crear o editar un tipo de tope, con el formulario de un ítem de catálogo
    (SPEC 07) y sus servicios. Al guardar, va al detalle del tipo.
    """

    http_method_names = ["get", "post", "head", "options"]
    creating = True

    def get_instance(self) -> RateCapType | None:
        if self.creating:
            return None
        return get_object_or_404(RateCapType, pk=self.kwargs["pk"])

    def get_form(self, data: Any = None, instance: RateCapType | None = None):
        form_class = catalog_item_form(RateCapType, creating=self.creating)
        return form_class(data, instance=instance)

    def render_form(
        self, request: HttpRequest, form: Any, cap_type: RateCapType | None
    ) -> HttpResponse:
        # El título usa el tipo guardado: el formulario con errores no lo cambia.
        saved = RateCapType.objects.get(pk=cap_type.pk) if cap_type else None
        return render(
            request,
            "parametros/ratecap_form.html",
            {"form": form, "cap_type": saved, "creating": self.creating},
        )

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        cap_type = self.get_instance()
        return self.render_form(request, self.get_form(instance=cap_type), cap_type)

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        cap_type = self.get_instance()
        previous_update = cap_type.updated_at if cap_type else None
        form = self.get_form(request.POST, instance=cap_type)
        if form.is_valid():
            try:
                if self.creating:
                    saved = services.create_catalog_item(
                        request.user, RATE_CAP_CATALOG, form.cleaned_data
                    )
                else:
                    saved = services.update_catalog_item(
                        request.user, cap_type, form.cleaned_data
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
                return ratecap_detail_redirect(saved)
        return self.render_form(request, form, cap_type)


class RateCapCreateView(RateCapFormView):
    permission_required = "parametros.add_ratecaptype"
    creating = True


class RateCapUpdateView(RateCapFormView):
    permission_required = "parametros.change_ratecaptype"
    creating = False


class RateCapStateView(PermissionRequiredMixin, View):
    """Desactivar o reactivar un tipo de tope. Solo acepta POST."""

    permission_required = "parametros.change_ratecaptype"
    http_method_names = ["post", "options"]
    service: Callable[..., RateCapType]
    message: Any

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        cap_type = get_object_or_404(RateCapType, pk=pk)
        try:
            saved = self.service(request.user, cap_type)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
        else:
            messages.success(request, self.message % {"name": saved.name})
        return redirect("parametros:ratecap_list")


class RateCapDeactivateView(RateCapStateView):
    service = staticmethod(services.deactivate_catalog_item)
    message = gettext_lazy("Se desactivó %(name)s.")


class RateCapReactivateView(RateCapStateView):
    service = staticmethod(services.reactivate_catalog_item)
    message = gettext_lazy("Se reactivó %(name)s.")


class RateCapValueCreateView(PermissionRequiredMixin, View):
    """Programar un valor de un tope. Muestra el vigente como referencia."""

    permission_required = "parametros.add_ratecapvalue"
    http_method_names = ["get", "post", "head", "options"]

    def render_form(
        self, request: HttpRequest, form: RateCapValueForm, cap_type: RateCapType
    ) -> HttpResponse:
        current = services.get_rate_cap_value(cap_type)
        return render(
            request,
            "parametros/ratecap_value_form.html",
            {
                "form": form,
                "cap_type": cap_type,
                "current": current,
                "current_value": (
                    percent_with_unit(current.annual_effective_rate, _("% EA"))
                    if current
                    else ""
                ),
            },
        )

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        cap_type = get_object_or_404(RateCapType, pk=pk)
        form = RateCapValueForm(initial={"valid_from": timezone.localdate()})
        return self.render_form(request, form, cap_type)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        cap_type = get_object_or_404(RateCapType, pk=pk)
        form = RateCapValueForm(request.POST)
        if form.is_valid():
            try:
                value = services.schedule_rate_cap_value(
                    request.user, cap_type, form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    _("Se programó el valor de %(cap)s desde el %(date)s.")
                    % {"cap": cap_type.name, "date": format_date(value.valid_from)},
                )
                return ratecap_detail_redirect(cap_type)
        return self.render_form(request, form, cap_type)


class RateCapValueVoidView(PermissionRequiredMixin, View):
    """Anular un valor programado. Un valor de otro tope responde 404."""

    permission_required = "parametros.change_ratecapvalue"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int, value_pk: int) -> HttpResponse:
        cap_type = get_object_or_404(RateCapType, pk=pk)
        value = get_object_or_404(RateCapValue, pk=value_pk, cap_type=cap_type)
        try:
            services.void_rate_cap_value(request.user, value)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
        else:
            messages.success(
                request,
                _("Se anuló el valor de %(cap)s que iba a regir desde el %(date)s.")
                % {"cap": cap_type.name, "date": format_date(value.valid_from)},
            )
        return ratecap_detail_redirect(cap_type)


# Productos de crédito (SPEC 08, §3.9)


def rate_with_unit(value: Decimal, product: CreditProduct) -> str:
    """Una tasa con la unidad de su producto, por ejemplo "10 % por crédito"."""
    return f"{format_percent(value)} {product.rate_unit.label}"


def product_detail_redirect(product: CreditProduct) -> HttpResponse:
    return redirect("parametros:product_detail", pk=product.pk)


def periodicity_labels(product: CreditProduct) -> str:
    return ", ".join(
        str(Periodicity(value).label) for value in product.allowed_periodicities
    )


def days(value: int) -> str:
    return ngettext("%(count)s día", "%(count)s días", value) % {"count": value}


def periods(value: int) -> str:
    return ngettext("%(count)s periodo", "%(count)s periodos", value) % {"count": value}


def product_conditions(product: CreditProduct) -> list[tuple[str, list]]:
    """Las condiciones del producto por tarjeta, ya formateadas (§3.9)."""
    if product.initial_charge_type == InitialChargeType.FIXED:
        charge = format_money(product.initial_charge_value)
    elif product.initial_charge_type == InitialChargeType.PERCENT:
        charge = _("%(value)s %% del monto") % {
            "value": format_percent(product.initial_charge_value)
        }
    else:
        charge = _("Sin gasto inicial")
    if product.rounding_multiple is not None:
        rounding = _("%(multiple)s, %(mode)s") % {
            "multiple": product.get_rounding_multiple_display(),
            "mode": product.get_rounding_mode_display().lower(),
        }
    else:
        rounding = global_rounding_label()
    cap = product.additional_rate_cap
    return [
        (
            _("Método y periodicidad"),
            [
                (_("Método de interés"), product.get_interest_method_display()),
                (_("Unidad de la tasa"), product.rate_unit.label),
                (_("Periodicidades permitidas"), periodicity_labels(product)),
                (
                    _("Periodicidad por defecto"),
                    product.get_default_periodicity_display(),
                ),
            ],
        ),
        (
            _("Monto y cuotas"),
            [
                (_("Monto mínimo"), format_money(product.min_amount)),
                (_("Monto máximo"), format_money(product.max_amount)),
                (_("Cuotas mínimas"), product.min_installments),
                (_("Cuotas por defecto"), product.default_installments),
                (_("Cuotas máximas"), product.max_installments),
            ],
        ),
        (
            _("Gracia"),
            [
                (_("Por defecto"), periods(product.default_grace_periods)),
                (_("Máximo"), periods(product.max_grace_periods)),
            ],
        ),
        (
            _("Mora y castigo"),
            [
                (
                    _("Mora diaria"),
                    _("%(value)s %% diario sobre el valor vencido")
                    % {"value": format_percent(product.late_fee_daily_rate)},
                ),
                (
                    _("Tope de la mora"),
                    _("%(value)s %% del valor vencido de la cuota")
                    % {"value": format_percent(product.late_fee_cap_percent)},
                ),
                (_("Días de tolerancia"), days(product.late_tolerance_days)),
                (
                    _("Días de mora para castigar"),
                    days(product.write_off_min_days_past_due),
                ),
            ],
        ),
        (_("Gasto inicial"), [(_("Gasto inicial"), charge)]),
        (
            _("Límite y redondeo"),
            [
                (
                    _("Créditos activos por cliente"),
                    product.max_active_credits_per_client,
                ),
                (_("Redondeo"), rounding),
            ],
        ),
        (
            _("Tope adicional"),
            [(_("Tope adicional"), cap.name if cap else _("Ninguno"))],
        ),
    ]


class ProductListView(PermissionRequiredMixin, View):
    """Los productos, activos e inactivos, con su tasa por defecto vigente hoy."""

    permission_required = "parametros.view_creditproduct"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest) -> HttpResponse:
        today = timezone.localdate()
        can_change = request.user.has_perm("parametros.change_creditproduct")
        columns = [
            _("Nombre"),
            _("Método"),
            _("Periodicidades"),
            _("Monto"),
            _("Cuotas"),
            _("Tasa por defecto"),
            _("Estado"),
        ]
        if can_change:
            columns.append(_("Acciones"))
        rows = [
            self.row(request, product, today, can_change)
            for product in CreditProduct.objects.order_by("name")
        ]
        return render(
            request,
            "parametros/product_list.html",
            {
                "can_add": request.user.has_perm("parametros.add_creditproduct"),
                "table_title": _("Productos de crédito"),
                "table_columns": columns,
                "table_rows": rows,
            },
        )

    def row(
        self,
        request: HttpRequest,
        product: CreditProduct,
        today: date,
        can_change: bool,
    ) -> list[Any]:
        """Una fila. Sin `change`, la fila no lleva la columna de acciones."""
        version = services.get_rate_version(product, today)
        if version is None:
            rate = format_html(
                '<span class="badge badge-warning">{}</span>', _("Sin tasa vigente")
            )
        else:
            rate = rate_with_unit(version.default_rate, product)
        cells = [
            format_html(
                '<a href="{}">{}</a>',
                reverse("parametros:product_detail", args=[product.pk]),
                product.name,
            ),
            product.get_interest_method_display(),
            periodicity_labels(product),
            f"{format_money(product.min_amount)} – {format_money(product.max_amount)}",
            f"{product.min_installments} – {product.max_installments}",
            rate,
            active_badge(product.is_active),
        ]
        if can_change:
            cells.append(
                render_to_string(
                    "parametros/includes/product_actions.html",
                    {"product": product},
                    request=request,
                )
            )
        return cells


class ProductDetailView(PermissionRequiredMixin, View):
    """Un producto: sus condiciones, su historial de tasas y sus topes."""

    permission_required = "parametros.view_creditproduct"
    http_method_names = ["get", "head", "options"]

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        product = get_object_or_404(
            CreditProduct.objects.select_related("additional_rate_cap"), pk=pk
        )
        today = timezone.localdate()
        current = services.get_rate_version(product, today)
        can_void = request.user.has_perm("parametros.change_productrateversion")
        versions = list(product.rate_versions.select_related("created_by"))
        rows = version_rows(
            request,
            versions,
            current,
            cells=lambda version: [
                rate_with_unit(version.min_rate, product),
                rate_with_unit(version.default_rate, product),
                rate_with_unit(version.max_rate, product),
            ],
            void_url=(
                (
                    lambda version: reverse(
                        "parametros:rate_version_void", args=[product.pk, version.pk]
                    )
                )
                if can_void
                else None
            ),
            confirm=lambda version: _(
                "La tasa de %(product)s que iba a regir desde el %(date)s queda "
                "anulada y no se aplicará. ¿Anular?"
            )
            % {"product": product.name, "date": format_date(version.valid_from)},
        )
        caps = [
            {
                "name": cap.cap_type.name,
                "value": cap.value,
                "display": (
                    percent_with_unit(cap.value.annual_effective_rate, _("% EA"))
                    if cap.value
                    else ""
                ),
            }
            for cap in services.get_applicable_caps(product, today)
        ]
        return render(
            request,
            "parametros/product_detail.html",
            {
                "product": product,
                "status": active_badge(product.is_active),
                "conditions": product_conditions(product),
                "current": current,
                "current_rates": (
                    [
                        (_("Mínima"), rate_with_unit(current.min_rate, product)),
                        (
                            _("Por defecto"),
                            rate_with_unit(current.default_rate, product),
                        ),
                        (_("Máxima"), rate_with_unit(current.max_rate, product)),
                    ]
                    if current
                    else []
                ),
                "caps": caps,
                "can_change": request.user.has_perm("parametros.change_creditproduct"),
                "can_add_rate": request.user.has_perm(
                    "parametros.add_productrateversion"
                ),
                "table_title": _("Historial de tasas"),
                "table_columns": [
                    _("Desde"),
                    _("Hasta"),
                    _("Mínima"),
                    _("Por defecto"),
                    _("Máxima"),
                    _("Estado"),
                    _("Creada por"),
                    _("Acciones"),
                ],
                "table_rows": rows,
            },
        )


def apply_service_errors(error: ValidationError, *forms_: Any) -> None:
    """
    Pone cada error del servicio en el formulario que tiene ese campo; los que
    no son de ningún campo van al primero.
    """
    if not hasattr(error, "error_dict"):
        forms_[0].add_error(None, error)
        return
    for field, errors in error.error_dict.items():
        target = next((form for form in forms_ if field in form.fields), None)
        if target is None:
            forms_[0].add_error(None, errors)
        else:
            target.add_error(field, errors)


class ProductFormView(PermissionRequiredMixin, View):
    """
    Crear un producto con su tasa inicial, o editar sus condiciones. La vista
    llama al servicio, nunca a `form.save()`. Al guardar, va al detalle.
    """

    http_method_names = ["get", "post", "head", "options"]
    creating = True

    def get_instance(self) -> CreditProduct | None:
        if self.creating:
            return None
        return get_object_or_404(CreditProduct, pk=self.kwargs["pk"])

    def get_forms(
        self, product: CreditProduct | None, data: Any = None
    ) -> tuple[CreditProductForm, RateVersionForm | None]:
        product_form = CreditProductForm(data, instance=product, creating=self.creating)
        rate_form = None
        if self.creating:
            rate_form = RateVersionForm(
                data,
                prefix="rate",
                initial={"valid_from": timezone.localdate()},
            )
        return product_form, rate_form

    def render_form(
        self,
        request: HttpRequest,
        product_form: CreditProductForm,
        rate_form: RateVersionForm | None,
        product: CreditProduct | None,
    ) -> HttpResponse:
        # El título y los datos de solo lectura salen del producto guardado.
        saved = CreditProduct.objects.get(pk=product.pk) if product else None
        return render(
            request,
            "parametros/product_form.html",
            {
                "form": product_form,
                "rate_form": rate_form,
                "product": saved,
                "creating": self.creating,
                "periodicity_locked": bool(
                    saved and saved.rate_unit == RateUnit.PER_PERIOD
                ),
                "periodicities": periodicity_labels(saved) if saved else "",
            },
        )

    def get(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        product = self.get_instance()
        return self.render_form(request, *self.get_forms(product), product)

    def post(self, request: HttpRequest, pk: int | None = None) -> HttpResponse:
        product = self.get_instance()
        previous_update = product.updated_at if product else None
        product_form, rate_form = self.get_forms(product, request.POST)
        valid = product_form.is_valid()
        if rate_form is not None:
            valid = rate_form.is_valid() and valid
        if valid:
            try:
                if self.creating:
                    saved = services.create_product(
                        request.user, product_form.cleaned_data, rate_form.cleaned_data
                    )
                else:
                    saved = services.update_product(
                        request.user, product, product_form.cleaned_data
                    )
            except ValidationError as error:
                apply_service_errors(error, product_form, *filter(None, [rate_form]))
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
                return product_detail_redirect(saved)
        return self.render_form(request, product_form, rate_form, product)


class ProductCreateView(ProductFormView):
    permission_required = "parametros.add_creditproduct"
    creating = True


class ProductUpdateView(ProductFormView):
    permission_required = "parametros.change_creditproduct"
    creating = False


class ProductStateView(PermissionRequiredMixin, View):
    """Desactivar o reactivar un producto. Solo acepta POST."""

    permission_required = "parametros.change_creditproduct"
    http_method_names = ["post", "options"]
    service: Callable[..., CreditProduct]
    message: Any

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        product = get_object_or_404(CreditProduct, pk=pk)
        try:
            saved = self.service(request.user, product)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
        else:
            messages.success(request, self.message % {"name": saved.name})
        return product_detail_redirect(product)


class ProductDeactivateView(ProductStateView):
    service = staticmethod(services.deactivate_product)
    message = gettext_lazy("Se desactivó %(name)s.")


class ProductReactivateView(ProductStateView):
    service = staticmethod(services.reactivate_product)
    message = gettext_lazy("Se reactivó %(name)s.")


class RateVersionCreateView(PermissionRequiredMixin, View):
    """Programar una versión de tasa. Muestra la vigente como referencia."""

    permission_required = "parametros.add_productrateversion"
    http_method_names = ["get", "post", "head", "options"]

    def render_form(
        self, request: HttpRequest, form: RateVersionForm, product: CreditProduct
    ) -> HttpResponse:
        current = services.get_rate_version(product)
        return render(
            request,
            "parametros/rate_version_form.html",
            {
                "form": form,
                "product": product,
                "current": current,
                "current_rates": (
                    _("mínima %(min)s, por defecto %(default)s y máxima %(max)s")
                    % {
                        "min": rate_with_unit(current.min_rate, product),
                        "default": rate_with_unit(current.default_rate, product),
                        "max": rate_with_unit(current.max_rate, product),
                    }
                    if current
                    else ""
                ),
            },
        )

    def get_form(self, product: CreditProduct, data: Any = None) -> RateVersionForm:
        return RateVersionForm(
            data,
            unit=product.rate_unit.label,
            initial={"valid_from": timezone.localdate()},
        )

    def get(self, request: HttpRequest, pk: int) -> HttpResponse:
        product = get_object_or_404(CreditProduct, pk=pk)
        return self.render_form(request, self.get_form(product), product)

    def post(self, request: HttpRequest, pk: int) -> HttpResponse:
        product = get_object_or_404(CreditProduct, pk=pk)
        form = self.get_form(product, request.POST)
        if form.is_valid():
            try:
                version = services.schedule_rate_version(
                    request.user, product, form.cleaned_data
                )
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    _("Se programó la tasa de %(product)s desde el %(date)s.")
                    % {
                        "product": product.name,
                        "date": format_date(version.valid_from),
                    },
                )
                return product_detail_redirect(product)
        return self.render_form(request, form, product)


class RateVersionVoidView(PermissionRequiredMixin, View):
    """Anular una versión programada. Una versión de otro producto responde 404."""

    permission_required = "parametros.change_productrateversion"
    http_method_names = ["post", "options"]

    def post(self, request: HttpRequest, pk: int, version_pk: int) -> HttpResponse:
        product = get_object_or_404(CreditProduct, pk=pk)
        version = get_object_or_404(ProductRateVersion, pk=version_pk, product=product)
        try:
            services.void_rate_version(request.user, version)
        except ValidationError as error:
            for text in error.messages:
                messages.error(request, text)
        else:
            messages.success(
                request,
                _("Se anuló la tasa de %(product)s que iba a regir desde el %(date)s.")
                % {"product": product.name, "date": format_date(version.valid_from)},
            )
        return product_detail_redirect(product)
