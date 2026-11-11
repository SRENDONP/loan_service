from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("componentes/", views.components, name="components"),
    path("health/", views.health, name="health"),
]
