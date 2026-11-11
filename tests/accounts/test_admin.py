"""Pruebas del admin de Django con el login propio (SPEC 03, paso 10)."""

from urllib.parse import quote

import pytest
from django.contrib import admin
from django.urls import reverse

from apps.accounts.admin import UserAdmin
from apps.accounts.models import User
from apps.accounts.sites import SuperuserAdminSite

pytestmark = pytest.mark.django_db

ADMIN = reverse("admin:index")
ADMIN_LOGIN = "/admin/login/"
LOGIN = reverse("accounts:login")
USER_ADD = reverse("admin:accounts_user_add")


@pytest.fixture
def superuser(password):
    return User.objects.create_superuser("admin", "admin@example.com", password)


def test_admin_site_requires_superuser():
    assert isinstance(admin.site, SuperuserAdminSite)
    assert isinstance(admin.site._registry[User], UserAdmin)


def test_anonymous_ends_on_own_login(client):
    response = client.get(ADMIN, follow=True)

    assert response.redirect_chain[-1][0] == f"{LOGIN}?next={quote(ADMIN)}"
    assert response.status_code == 200
    assert "accounts/login.html" in [t.name for t in response.templates]


def test_admin_login_redirects_to_own_login_keeping_next(client):
    response = client.get(f"{ADMIN_LOGIN}?next=/admin/accounts/user/")

    assert response.status_code == 302
    assert response.url == f"{LOGIN}?next={quote('/admin/accounts/user/')}"


def test_admin_login_without_next_goes_to_admin_index(client):
    response = client.get(ADMIN_LOGIN)

    assert response.url == f"{LOGIN}?next={quote(ADMIN)}"


def test_superuser_enters_admin(client, superuser):
    client.force_login(superuser)

    response = client.get(ADMIN)

    assert response.status_code == 200


def test_superuser_logs_in_through_own_login_and_reaches_admin(
    client, superuser, password
):
    login_url = client.get(ADMIN, follow=True).redirect_chain[-1][0]

    response = client.post(
        login_url,
        {"username": "admin", "password": password, "next": ADMIN},
        follow=True,
    )

    assert response.redirect_chain[-1] == (ADMIN, 302)
    assert response.status_code == 200


def test_staff_without_superuser_gets_403_without_redirect_loop(client, make_user):
    client.force_login(make_user("staff", is_staff=True))

    response = client.get(ADMIN, follow=True)

    assert response.status_code == 403
    assert len(response.redirect_chain) == 1
    assert response.redirect_chain[0][0].startswith(ADMIN_LOGIN)


def test_regular_user_gets_403(client, make_user):
    client.force_login(make_user("cobrador"))

    response = client.get(ADMIN, follow=True)

    assert response.status_code == 403


def test_inactive_superuser_cannot_enter(rf, superuser):
    superuser.is_active = False
    request = rf.get(ADMIN)
    request.user = superuser

    assert admin.site.has_permission(request) is False


def test_user_created_from_admin_must_change_password(client, superuser):
    client.force_login(superuser)

    response = client.post(
        USER_ADD,
        {
            "username": "cobrador1",
            "email": "cobrador1@example.com",
            "usable_password": "true",
            "password1": "cuota2027",
            "password2": "cuota2027",
        },
    )

    assert response.status_code == 302
    user = User.objects.get(username="cobrador1")
    assert user.must_change_password is True
    assert user.email == "cobrador1@example.com"
    assert user.check_password("cuota2027")


def test_admin_add_form_applies_username_and_password_rules(client, superuser):
    client.force_login(superuser)

    response = client.post(
        USER_ADD,
        {
            "username": "ana@example.com",
            "usable_password": "true",
            "password1": "12345678",
            "password2": "12345678",
        },
    )

    assert response.status_code == 200
    errors = response.context["adminform"].form.errors
    assert "username" in errors
    assert "password2" in errors
    assert not User.objects.filter(username="ana@example.com").exists()


def test_admin_change_page_shows_access_fields(client, superuser, make_user):
    client.force_login(superuser)
    user = make_user("cobrador1")

    html = client.get(reverse("admin:accounts_user_change", args=[user.pk])).content
    html = html.decode()

    # locked_until usa el widget de fecha y hora separadas del admin.
    for name in (
        "must_change_password",
        "failed_login_attempts",
        "locked_until_0",
        "locked_until_1",
    ):
        assert f'name="{name}"' in html


def test_admin_user_list_shows_access_columns(client, superuser):
    client.force_login(superuser)

    html = client.get(reverse("admin:accounts_user_changelist")).content.decode()

    assert "column-must_change_password" in html
    assert "column-locked_until" in html


def test_admin_does_not_allow_deleting_users(client, superuser, make_user):
    target = make_user("ana")
    client.force_login(superuser)

    delete = client.get(reverse("admin:accounts_user_delete", args=[target.pk]))
    changelist = client.get(reverse("admin:accounts_user_changelist"))

    assert delete.status_code == 403
    assert "delete_selected" not in changelist.content.decode()
    assert User.objects.filter(pk=target.pk).exists()


def test_admin_change_page_shows_profile_and_deactivation_fields(
    client, superuser, make_user
):
    target = make_user("ana")
    client.force_login(superuser)

    response = client.get(reverse("admin:accounts_user_change", args=[target.pk]))

    content = response.content.decode()
    for field in (
        "phone",
        "document_type",
        "document_number",
        "deactivated_at",
        "deactivated_by",
        "deactivation_reason",
    ):
        assert f'name="{field}' in content
