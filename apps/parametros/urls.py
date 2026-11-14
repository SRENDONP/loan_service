"""
Rutas de los parámetros globales (SPEC 06, §3.9), de los catálogos (SPEC 07) y de
los productos y los topes de tasa (SPEC 08).
"""

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

# Topes de tasa (SPEC 08, §3.9)
urlpatterns += [
    path("topes/", views.RateCapListView.as_view(), name="ratecap_list"),
    path("topes/nuevo/", views.RateCapCreateView.as_view(), name="ratecap_create"),
    path("topes/<int:pk>/", views.RateCapDetailView.as_view(), name="ratecap_detail"),
    path(
        "topes/<int:pk>/editar/",
        views.RateCapUpdateView.as_view(),
        name="ratecap_update",
    ),
    path(
        "topes/<int:pk>/desactivar/",
        views.RateCapDeactivateView.as_view(),
        name="ratecap_deactivate",
    ),
    path(
        "topes/<int:pk>/reactivar/",
        views.RateCapReactivateView.as_view(),
        name="ratecap_reactivate",
    ),
    path(
        "topes/<int:pk>/valores/nuevo/",
        views.RateCapValueCreateView.as_view(),
        name="ratecap_value_create",
    ),
    path(
        "topes/<int:pk>/valores/<int:value_pk>/anular/",
        views.RateCapValueVoidView.as_view(),
        name="ratecap_value_void",
    ),
]

# Productos de crédito (SPEC 08, §3.9)
urlpatterns += [
    path("productos/", views.ProductListView.as_view(), name="product_list"),
    path("productos/nuevo/", views.ProductCreateView.as_view(), name="product_create"),
    path(
        "productos/<int:pk>/", views.ProductDetailView.as_view(), name="product_detail"
    ),
    path(
        "productos/<int:pk>/editar/",
        views.ProductUpdateView.as_view(),
        name="product_update",
    ),
    path(
        "productos/<int:pk>/desactivar/",
        views.ProductDeactivateView.as_view(),
        name="product_deactivate",
    ),
    path(
        "productos/<int:pk>/reactivar/",
        views.ProductReactivateView.as_view(),
        name="product_reactivate",
    ),
    path(
        "productos/<int:pk>/tasas/nueva/",
        views.RateVersionCreateView.as_view(),
        name="rate_version_create",
    ),
    path(
        "productos/<int:pk>/tasas/<int:version_pk>/anular/",
        views.RateVersionVoidView.as_view(),
        name="rate_version_void",
    ),
]
