"""Comando para sincronizar los grupos con `ROLE_PERMISSIONS` (SPEC 04)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.db import DEFAULT_DB_ALIAS

from apps.accounts.roles import sync_roles


class Command(BaseCommand):
    help = (
        "Deja los grupos Administrador, Supervisor, Cajero/Cobrador y Consulta "
        "con exactamente los permisos de apps/accounts/roles.py. "
        "También corre solo después de cada migrate."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Base de datos que se sincroniza.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        sync_roles(using=options["database"])
        self.stdout.write(self.style.SUCCESS("Roles sincronizados."))
