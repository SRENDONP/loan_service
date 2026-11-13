"""Rutas de los parámetros globales (SPEC 06, §3.9) y de los catálogos (SPEC 07)."""

from django.urls import path

from apps.parametros import views
from apps.parametros.catalogs import CATALOGS

app_name = "parametros"

# Un listado con nombre propio por catálogo, para el menú (ver
# `Catalog.list_url_name`). Un `slug` que no está aquí responde 404 porque no
# hay ruta.
catalog_list_patterns = [
    path(
        f"catalogos/{catalog.slug}/",
        views.CatalogListView.as_view(),
        {"slug": catalog.slug},
        name=catalog.list_url_name.removeprefix("parametros:"),
    )
    for catalog in CATALOGS
]

catalog_patterns = [
    path(
        "catalogos/<slug:slug>/nuevo/",
        views.CatalogCreateView.as_view(),
        name="catalog_create",
    ),
    path(
        "catalogos/<slug:slug>/<int:pk>/editar/",
        views.CatalogUpdateView.as_view(),
        name="catalog_update",
    ),
    path(
        "catalogos/<slug:slug>/<int:pk>/desactivar/",
        views.CatalogDeactivateView.as_view(),
        name="catalog_deactivate",
    ),
    path(
        "catalogos/<slug:slug>/<int:pk>/reactivar/",
        views.CatalogReactivateView.as_view(),
        name="catalog_reactivate",
    ),
]

urlpatterns = [
    path("", views.GlobalSettingsView.as_view(), name="global"),
    path(
        "negocio/",
        views.GroupUpdateView.as_view(group_key="business"),
        name="update_business",
    ),
    path(
        "cobro/",
        views.GroupUpdateView.as_view(group_key="collection"),
        name="update_collection",
    ),
    path(
        "redondeo/",
        views.GroupUpdateView.as_view(group_key="rounding"),
        name="update_rounding",
    ),
    path(
        "seguridad/",
        views.GroupUpdateView.as_view(group_key="security"),
        name="update_security",
    ),
    *catalog_list_patterns,
    *catalog_patterns,
    path("festivos/", views.HolidayListView.as_view(), name="holiday_list"),
    path("festivos/nuevo/", views.HolidayCreateView.as_view(), name="holiday_create"),
    path(
        "festivos/<int:pk>/editar/",
        views.HolidayUpdateView.as_view(),
        name="holiday_update",
    ),
    path(
        "festivos/<int:pk>/desactivar/",
        views.HolidayDeactivateView.as_view(),
        name="holiday_deactivate",
    ),
    path(
        "festivos/<int:pk>/reactivar/",
        views.HolidayReactivateView.as_view(),
        name="holiday_reactivate",
    ),
]
