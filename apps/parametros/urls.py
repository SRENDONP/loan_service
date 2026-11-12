"""Rutas de los parámetros globales (SPEC 06, §3.9)."""

from django.urls import path

from apps.parametros import views

app_name = "parametros"

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
]
