"""Pruebas del cierre de sesión por inactividad y por duración (SPEC 06, §3.5)."""

import pytest
from django.conf import settings
from django.contrib.messages import get_messages
from django.urls import reverse

from apps.accounts import middleware
from apps.accounts.middleware import LAST_ACTIVITY_KEY, SESSION_STARTED_KEY
from apps.auditoria.actions import AuditAction
from apps.auditoria.models import AuditEvent

pytestmark = pytest.mark.django_db

HOME = reverse("core:home")
LOGIN = reverse("accounts:login")
LOGOUT = reverse("accounts:logout")
PASSWORD_CHANGE = reverse("accounts:password_change")
MINUTE = 60
HOUR = 60 * MINUTE
START = 1_800_000_000


class Clock:
    """Reloj controlado de `SessionPolicyMiddleware`."""

    def __init__(self) -> None:
        self.now = START

    def advance(self, seconds: int) -> None:
        self.now += seconds


@pytest.fixture
def clock(monkeypatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(middleware, "_now", lambda: clock.now)
    return clock


@pytest.fixture
def session_client(auth_client, clock):
    """Cliente con sesión, ya marcado por el middleware en el instante START."""
    assert auth_client.get(HOME).status_code == 200
    return auth_client


def is_logged_in(client) -> bool:
    return "_auth_user_id" in client.session


def logout_events():
    return AuditEvent.objects.filter(action=AuditAction.LOGOUT)


def messages_of(response) -> list[str]:
    return [str(message) for message in get_messages(response.wsgi_request)]


# Configuración


def test_middleware_runs_between_audit_context_and_login_required():
    stack = settings.MIDDLEWARE
    audit = stack.index("apps.auditoria.middleware.AuditContextMiddleware")
    login_required = stack.index(
        "django.contrib.auth.middleware.LoginRequiredMiddleware"
    )

    assert stack[audit + 1] == "apps.accounts.middleware.SessionPolicyMiddleware"
    assert stack[login_required - 1] == (
        "apps.accounts.middleware.SessionPolicyMiddleware"
    )


def test_session_settings_are_the_hard_ceiling():
    assert settings.SESSION_COOKIE_AGE == 24 * HOUR
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is True


def test_policy_getters_follow_the_parameters(global_settings):
    from datetime import timedelta

    from apps.accounts import policy

    assert policy.get_session_idle_timeout() == timedelta(minutes=30)
    assert policy.get_session_max_duration() == timedelta(hours=12)

    global_settings.session_idle_timeout_minutes = 10
    global_settings.session_max_hours = 2
    global_settings.save()

    assert policy.get_session_idle_timeout() == timedelta(minutes=10)
    assert policy.get_session_max_duration() == timedelta(hours=2)


# Marcas en la sesión


def test_first_request_marks_the_session(session_client):
    assert session_client.session[SESSION_STARTED_KEY] == START
    assert session_client.session[LAST_ACTIVITY_KEY] == START


def test_session_without_start_mark_is_not_closed_and_gets_marked(auth_client, clock):
    # Una sesión abierta antes de esta spec no tiene las marcas.
    clock.advance(10 * HOUR)

    response = auth_client.get(HOME)

    assert response.status_code == 200
    assert auth_client.session[SESSION_STARTED_KEY] == clock.now


def test_requests_within_a_minute_do_not_rewrite_last_activity(session_client, clock):
    clock.advance(30)
    session_client.get(HOME)
    clock.advance(30)
    session_client.get(HOME)

    assert session_client.session[LAST_ACTIVITY_KEY] == START


def test_request_after_a_minute_rewrites_last_activity(session_client, clock):
    clock.advance(61)
    session_client.get(HOME)

    assert session_client.session[LAST_ACTIVITY_KEY] == START + 61


# Inactividad


def test_request_29_minutes_later_keeps_the_session(session_client, clock):
    clock.advance(29 * MINUTE)

    response = session_client.get(HOME)

    assert response.status_code == 200
    assert is_logged_in(session_client)


def test_request_31_minutes_later_closes_the_session(session_client, clock, user):
    clock.advance(31 * MINUTE)

    response = session_client.get(HOME)

    assert response.status_code == 302
    assert response.url == f"{LOGIN}?next={HOME}"
    assert not is_logged_in(session_client)
    assert messages_of(response) == ["Tu sesión se cerró por inactividad."]

    [event] = logout_events()
    assert event.actor == user
    assert event.extra == {"reason": "inactivity"}


def test_inactivity_message_is_shown_on_the_login_page(session_client, clock):
    clock.advance(31 * MINUTE)

    response = session_client.get(HOME, follow=True)

    assert response.redirect_chain[-1][0] == f"{LOGIN}?next={HOME}"
    assert "Tu sesión se cerró por inactividad." in response.content.decode()


def test_next_keeps_the_query_string(session_client, clock):
    clock.advance(31 * MINUTE)

    response = session_client.get(reverse("accounts:user_list") + "?q=ana")

    assert response.status_code == 302
    assert response.url.startswith(f"{LOGIN}?next=")
    assert "%3Fq%3Dana" in response.url


def test_post_after_inactivity_redirects_without_next_and_does_not_run(
    session_client, clock, global_settings
):
    clock.advance(31 * MINUTE)

    response = session_client.post(
        reverse("parametros:update_rounding"),
        {"rounding_multiple": "100", "rounding_mode": "half_up"},
    )

    assert response.status_code == 302
    assert response.url == LOGIN
    global_settings.refresh_from_db()
    assert global_settings.rounding_multiple == 50


def test_activity_keeps_the_session_open(session_client, clock):
    for _ in range(5):
        clock.advance(20 * MINUTE)
        assert session_client.get(HOME).status_code == 200

    assert is_logged_in(session_client)


def test_lowering_the_idle_timeout_applies_to_open_sessions(
    session_client, clock, global_settings
):
    clock.advance(20 * MINUTE)
    global_settings.session_idle_timeout_minutes = 15
    global_settings.save()

    response = session_client.get(HOME)

    assert response.status_code == 302
    assert logout_events().get().extra == {"reason": "inactivity"}


def test_public_view_does_not_close_but_counts_as_activity(session_client, clock):
    clock.advance(31 * MINUTE)

    # La página de login es pública (@login_not_required).
    session_client.get(LOGIN)

    assert is_logged_in(session_client)
    assert session_client.session[LAST_ACTIVITY_KEY] == clock.now
    assert not logout_events().exists()


# Duración máxima


def test_max_duration_closes_an_active_session(
    session_client, clock, global_settings, user
):
    global_settings.session_max_hours = 1
    global_settings.session_idle_timeout_minutes = 30
    global_settings.save()

    # Activa cada 5 minutos durante la hora.
    for _ in range(12):
        clock.advance(5 * MINUTE)
        assert session_client.get(HOME).status_code == 200

    clock.advance(5 * MINUTE)
    response = session_client.get(HOME)

    assert response.status_code == 302
    assert response.url == f"{LOGIN}?next={HOME}"
    assert messages_of(response) == [
        "Tu sesión llegó a su duración máxima. Ingresa de nuevo."
    ]
    [event] = logout_events()
    assert event.actor == user
    assert event.extra == {"reason": "max_duration"}


# Cierre voluntario


def test_voluntary_logout_has_no_reason(session_client):
    session_client.post(LOGOUT)

    [event] = logout_events()
    assert event.extra == {}


def test_anonymous_requests_are_not_touched(client, clock):
    response = client.get(LOGIN)

    assert response.status_code == 200
    assert SESSION_STARTED_KEY not in client.session
