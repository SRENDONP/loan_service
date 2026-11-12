"""Pruebas de la recuperación de contraseña (SPEC 03, paso 9)."""

import re
from datetime import datetime, timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.tokens import password_reset_token_generator

pytestmark = pytest.mark.django_db

PASSWORD_RESET = reverse("accounts:password_reset")
PASSWORD_RESET_DONE = reverse("accounts:password_reset_done")
PASSWORD_RESET_COMPLETE = reverse("accounts:password_reset_complete")
LOGIN = reverse("accounts:login")
NEW_PASSWORD = "cuota2027"
LINK = re.compile(r"https?://[^/\s]+(/contrasena/restablecer/[^/\s]+/[^/\s]+/)")


def request_reset(client, email: str):
    return client.post(PASSWORD_RESET, {"email": email})


def reset_link(message) -> str:
    match = LINK.search(message.body)
    assert match, message.body
    return match.group(1)


def set_new_password(client, link: str, password: str = NEW_PASSWORD):
    """Abre el enlace y guarda la contraseña nueva. Devuelve la respuesta final."""
    form_url = client.get(link).url
    return client.post(form_url, {"new_password1": password, "new_password2": password})


# Pantallas ---------------------------------------------------------------


def test_reset_page_uses_auth_layout(client):
    response = client.get(PASSWORD_RESET)

    assert response.status_code == 200
    assert "accounts/auth_base.html" in [t.name for t in response.templates]
    html = response.content.decode()
    assert '<body class="bg-gradient-primary">' in html
    assert 'class="form-control form-control-user"' in html
    assert 'type="email"' in html
    assert 'placeholder="Correo electrónico"' in html
    for removed in ("bg-password-image", "bg-login-image", "register"):
        assert removed not in html


def test_login_links_to_password_reset(client):
    html = client.get(LOGIN).content.decode()

    assert f'href="{PASSWORD_RESET}"' in html
    assert "¿Olvidaste tu contraseña?" in html


@pytest.mark.parametrize(
    "url",
    [
        PASSWORD_RESET,
        PASSWORD_RESET_DONE,
        PASSWORD_RESET_COMPLETE,
        reverse(
            "accounts:password_reset_confirm",
            kwargs={"uidb64": "MQ", "token": "no-sirve"},
        ),
    ],
)
def test_reset_pages_are_public(client, url):
    assert client.get(url).status_code == 200


# Pedir el enlace -----------------------------------------------------------


def test_registered_email_receives_one_message_with_working_link(
    client, make_user, mailoutbox
):
    make_user("ana", email="ana@example.com")

    response = request_reset(client, "ANA@example.com")

    assert response.status_code == 302
    assert response.url == PASSWORD_RESET_DONE
    assert len(mailoutbox) == 1
    message = mailoutbox[0]
    assert message.to == ["ana@example.com"]
    assert message.subject == "Crea tu contraseña nueva"
    assert "Hola, ana:" in message.body
    assert "/contrasena/restablecer/" in reset_link(message)
    assert client.get(reset_link(message), follow=True).context["validlink"]


def test_unknown_email_gets_nothing_and_the_same_screen(client, make_user, mailoutbox):
    make_user("ana", email="ana@example.com")

    known = request_reset(client, "ana@example.com")
    unknown = request_reset(client, "nadie@example.com")

    assert len(mailoutbox) == 1
    assert unknown.status_code == known.status_code == 302
    assert unknown.url == known.url == PASSWORD_RESET_DONE


def test_done_page_does_not_reveal_whether_the_email_exists(client):
    html = client.get(PASSWORD_RESET_DONE).content.decode()

    assert "Si el correo pertenece a un usuario" in html


def test_user_without_email_gets_nothing(client, make_user, mailoutbox):
    make_user("sin_correo")

    request_reset(client, "sin_correo@example.com")

    assert mailoutbox == []


def test_inactive_user_gets_nothing(client, make_user, mailoutbox):
    make_user("ana", email="ana@example.com", is_active=False)

    request_reset(client, "ana@example.com")

    assert mailoutbox == []


def test_invalid_email_shows_field_error(client, mailoutbox):
    response = request_reset(client, "no-es-correo")

    assert response.status_code == 200
    assert "email" in response.context["form"].errors
    assert mailoutbox == []


# Usar el enlace ------------------------------------------------------------


def test_link_sets_the_new_password(client, make_user, mailoutbox):
    user = make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")

    response = set_new_password(client, reset_link(mailoutbox[0]))

    assert response.status_code == 302
    assert response.url == PASSWORD_RESET_COMPLETE
    user.refresh_from_db()
    assert user.check_password(NEW_PASSWORD)
    assert "_auth_user_id" not in client.session


def test_new_password_must_follow_policy(client, make_user, mailoutbox, password):
    user = make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")

    response = set_new_password(client, reset_link(mailoutbox[0]), "12345678")

    assert response.status_code == 200
    assert "new_password2" in response.context["form"].errors
    user.refresh_from_db()
    assert user.check_password(password)


def test_link_works_only_once(client, make_user, mailoutbox):
    make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")
    link = reset_link(mailoutbox[0])
    set_new_password(client, link)

    response = client.get(link, follow=True)

    assert response.context["validlink"] is False
    assert "El enlace ya no sirve" in response.content.decode()


def test_link_expires_after_one_hour(client, make_user, mailoutbox, monkeypatch):
    make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")
    link = reset_link(mailoutbox[0])

    monkeypatch.setattr(
        password_reset_token_generator,
        "_now",
        lambda: datetime.now() + timedelta(hours=1, seconds=5),
    )

    assert client.get(link, follow=True).context["validlink"] is False


def test_link_still_works_before_one_hour(client, make_user, mailoutbox, monkeypatch):
    make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")
    link = reset_link(mailoutbox[0])

    monkeypatch.setattr(
        password_reset_token_generator,
        "_now",
        lambda: datetime.now() + timedelta(minutes=59),
    )

    assert client.get(link, follow=True).context["validlink"] is True


def test_link_duration_follows_policy(
    client, make_user, mailoutbox, monkeypatch, global_settings
):
    global_settings.password_reset_timeout_minutes = 15
    global_settings.save()
    make_user("ana", email="ana@example.com")
    request_reset(client, "ana@example.com")
    link = reset_link(mailoutbox[0])

    monkeypatch.setattr(
        password_reset_token_generator,
        "_now",
        lambda: datetime.now() + timedelta(minutes=16),
    )

    assert client.get(link, follow=True).context["validlink"] is False


def test_reset_unlocks_account_and_turns_off_mandatory_change(
    client, make_user, mailoutbox
):
    user = make_user(
        "ana",
        email="ana@example.com",
        must_change_password=True,
        failed_login_attempts=3,
        locked_until=timezone.now() + timedelta(minutes=10),
    )
    request_reset(client, "ana@example.com")

    set_new_password(client, reset_link(mailoutbox[0]))

    user.refresh_from_db()
    assert user.locked_until is None
    assert user.failed_login_attempts == 0
    assert user.must_change_password is False
    response = client.post(LOGIN, {"username": "ana", "password": NEW_PASSWORD})
    assert response.status_code == 302


def test_complete_page_links_to_login(client):
    html = client.get(PASSWORD_RESET_COMPLETE).content.decode()

    assert f'href="{LOGIN}"' in html
    assert "Contraseña guardada" in html


# Generador de tokens -------------------------------------------------------


def test_token_generator_rejects_malformed_tokens(make_user):
    user = make_user("ana")

    assert password_reset_token_generator.check_token(user, None) is False
    assert password_reset_token_generator.check_token(None, "abc-def") is False
    assert password_reset_token_generator.check_token(user, "sin-guion-extra-") is False
    assert password_reset_token_generator.check_token(user, "zz!-abc") is False
    assert password_reset_token_generator.check_token(user, "1-abc") is False


def test_token_generator_accepts_fresh_token(make_user):
    user = make_user("ana")
    token = password_reset_token_generator.make_token(user)

    assert password_reset_token_generator.check_token(user, token) is True
