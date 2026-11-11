"""Las páginas exigen sesión (SPEC 03, paso 6)."""

from urllib.parse import quote

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

LOGIN = reverse("accounts:login")


@pytest.mark.parametrize("url", ["/", "/componentes/"])
def test_anonymous_is_redirected_to_login_with_next(client, settings, url):
    settings.DEBUG = True

    response = client.get(url)

    assert response.status_code == 302
    assert response.url == f"{LOGIN}?next={quote(url)}"


def test_after_login_user_reaches_the_requested_page(client, settings, user, password):
    settings.DEBUG = True
    login_url = client.get("/componentes/").url

    response = client.post(
        login_url,
        {"username": user.username, "password": password, "next": "/componentes/"},
        follow=True,
    )

    assert response.redirect_chain[-1] == ("/componentes/", 302)
    assert response.status_code == 200


def test_login_page_keeps_next_in_the_form(client):
    html = client.get(f"{LOGIN}?next=/componentes/").content.decode()

    assert '<input type="hidden" name="next" value="/componentes/">' in html


def test_login_page_is_public(client):
    assert client.get(LOGIN).status_code == 200


def test_health_is_public(client):
    assert client.get(reverse("core:health")).status_code == 200


def test_anonymous_post_is_redirected_too(client):
    response = client.post("/")

    assert response.status_code == 302
    assert response.url.startswith(LOGIN)
