"""Comando para cargar los festivos oficiales de uno o más años (SPEC 07, §3.7)."""

from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.auditoria.context import audit_context
from apps.auditoria.models import AuditSource
from apps.parametros.holidays import MAX_YEAR, MIN_YEAR
from apps.parametros.services import load_official_holidays


class Command(BaseCommand):
    help = (
        "Agrega los festivos oficiales de Colombia que falten en los años "
        "indicados. No toca los que ya existen, aunque estén desactivados o "
        "con otra fecha."
    )

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "years",
            nargs="+",
            type=int,
            metavar="año",
            help=f"Años que se cargan, de {MIN_YEAR} a {MAX_YEAR}.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        years = list(dict.fromkeys(options["years"]))  # sin repetidos, en orden

        # Se validan todos antes de cargar ninguno.
        invalid = [year for year in years if not MIN_YEAR <= year <= MAX_YEAR]
        if invalid:
            raise CommandError(
                _("Año fuera de rango (%(min)s a %(max)s): %(years)s.")
                % {
                    "min": MIN_YEAR,
                    "max": MAX_YEAR,
                    "years": ", ".join(str(year) for year in invalid),
                }
            )

        with audit_context(source=AuditSource.COMMAND):
            for year in years:
                created = load_official_holidays(year)
                if created:
                    message = ngettext(
                        "%(year)s: %(count)d festivo creado.",
                        "%(year)s: %(count)d festivos creados.",
                        created,
                    ) % {"year": year, "count": created}
                    self.stdout.write(self.style.SUCCESS(message))
                else:
                    self.stdout.write(
                        _("%(year)s: no faltaba ningún festivo.") % {"year": year}
                    )
