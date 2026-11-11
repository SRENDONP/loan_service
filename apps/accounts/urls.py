from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_not_required
from django.urls import path, reverse_lazy

from . import views
from .forms import PasswordResetForm
from .tokens import password_reset_token_generator

app_name = "accounts"

# Las vistas de recuperación de Django ya vienen marcadas con
# @login_not_required; se marcan aquí también para que se vea qué es público.
urlpatterns = [
    path("ingresar/", views.LoginView.as_view(), name="login"),
    path("salir/", views.LogoutView.as_view(), name="logout"),
    path(
        "contrasena/cambiar/",
        views.PasswordChangeView.as_view(),
        name="password_change",
    ),
    path(
        "contrasena/recuperar/",
        login_not_required(
            auth_views.PasswordResetView.as_view(
                form_class=PasswordResetForm,
                template_name="accounts/password_reset.html",
                email_template_name="accounts/email/password_reset_email.txt",
                subject_template_name="accounts/email/password_reset_subject.txt",
                token_generator=password_reset_token_generator,
                success_url=reverse_lazy("accounts:password_reset_done"),
            )
        ),
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
