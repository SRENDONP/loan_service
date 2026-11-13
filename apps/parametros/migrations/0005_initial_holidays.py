"""
Carga los festivos oficiales de Colombia de 2026 a 2030 (SPEC 07, §3.4).

Usa `colombian_holidays`, que es lógica pura y no depende de los modelos
(riesgo aceptado en la §7 de la spec: si la función cambia, no se edita esta
migración, se agrega otra). Sigue la regla de `load_official_holidays`: no
duplica un festivo oficial que ya existe y, si la fecha ya tiene un festivo
activo, crea el nuevo desactivado. Por eso, en 2030, San Pedro y San Pablo
queda desactivado: cae el mismo día que el Sagrado Corazón.

No audita: no hay actor, como la 0002. La reversa no hace nada: al revertir
0003 la tabla desaparece con los festivos.
"""

from django.db import migrations

from apps.parametros.holidays import colombian_holidays

YEARS = range(2026, 2031)


def create_initial_holidays(apps, schema_editor):
    Holiday = apps.get_model("parametros", "Holiday")
    holidays = Holiday.objects.using(schema_editor.connection.alias)

    for year in YEARS:
        for official in colombian_holidays(year):
            exists = holidays.filter(
                origin="official", official_year=year, official_code=official.code
            ).exists()
            if exists:
                continue
            taken = holidays.filter(date=official.date, is_active=True).exists()
            holidays.create(
                date=official.date,
                name=official.name,
                origin="official",
                official_code=official.code,
                official_year=year,
                is_active=not taken,
            )


class Migration(migrations.Migration):

    dependencies = [
        ("parametros", "0004_initial_catalogs"),
    ]

    operations = [
        migrations.RunPython(create_initial_holidays, migrations.RunPython.noop),
    ]
