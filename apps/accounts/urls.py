from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import path

from . import views

app_name = "accounts"

# Las vistas de recuperación de Django ya vienen marcadas con
# @login_not_required; se marcan aquí también para que se vea qué es público.
urlpatterns = [
    # Gestión de usuarios (SPEC 04).
    path("usuarios/", views.UserListView.as_view(), name="user_list"),
    path("usuarios/nuevo/", views.UserCreateView.as_view(), name="user_create"),
    path("usuarios/<int:pk>/", views.UserDetailView.as_view(), name="user_detail"),
    path(
        "usuarios/<int:pk>/editar/",
        views.UserUpdateView.as_view(),
        name="user_update",
    ),
    path(
        "usuarios/<int:pk>/desactivar/",
        views.UserDeactivateView.as_view(),
        name="user_deactivate",
    ),
    path(
        "usuarios/<int:pk>/reactivar/",
        views.UserReactivateView.as_view(),
        name="user_reactivate",
    ),
    path(
        "usuarios/<int:pk>/desbloquear/",
        views.UserUnlockView.as_view(),
        name="user_unlock",
    ),
    path(
        "usuarios/<int:pk>/restablecer-contrasena/",
        views.UserResetPasswordView.as_view(),
        name="user_reset_password",
    ),
    path(
        "usuarios/<int:pk>/cerrar-sesiones/",
        views.UserLogoutSessionsView.as_view(),
        name="user_logout_sessions",
    ),
    # Autenticación (SPEC 03).
    path("ingresar/", views.LoginView.as_view(), name="login"),
    path("salir/", views.LogoutView.as_view(), name="logout"),
    path(
        "contrasena/cambiar/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "contrasena/recuperar/",
        login_not_required(views.PasswordResetView.as_view()),
        name="password_reset",
    ),
    path(
        "contrasena/recuperar/enviado/",
        login_not_required(
            auth_views.PasswordResetDoneView.as_view(
                template_name="accounts/password_reset_done.html",
            )
        ),
        name="password_reset_done",
    ),
    path(
        "contrasena/restablecer/<uidb64>/<token>/",
        login_not_required(views.PasswordResetConfirmView.as_view()),
        name="password_reset_confirm",
    ),
    path(
        "contrasena/restablecer/listo/",
        login_not_required(
            auth_views.PasswordResetCompleteView.as_view(
                template_name="accounts/password_reset_complete.html",
            )
        ),
        name="password_reset_complete",
    ),
]
