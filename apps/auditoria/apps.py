from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class AuditoriaConfig(AppConfig):
    name = "apps.auditoria"
    verbose_name = _("Auditoría")

    def ready(self) -> None:
        # Los accesos se auditan con las señales de autenticación de Django
        # (SPEC 05 y ADR-004). No son reglas de negocio.
        from django.contrib.auth.signals import (
            user_logged_in,
            user_logged_out,
            user_login_failed,
        )

        from apps.auditoria import receivers

        user_logged_in.connect(
            receivers.audit_login_succeeded, dispatch_uid="auditoria.login_succeeded"
        )
        user_login_failed.connect(
            receivers.audit_login_failed, dispatch_uid="auditoria.login_failed"
        )
        user_logged_out.connect(receivers.audit_logout, dispatch_uid="auditoria.logout")
