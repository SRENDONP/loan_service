"""
Crea la fila única de parámetros globales con los valores por defecto (SPEC 06, §3.1).

Los valores por defecto del modelo son los que el sistema usaba hasta la SPEC 05,
así que esta migración no cambia el comportamiento. La reversa no hace nada: al
revertir 0001 la tabla desaparece con la fila.
"""

from django.db import migrations

SINGLETON_PK = 1


def create_initial_settings(apps, schema_editor):
    GlobalSettings = apps.get_model("parametros", "GlobalSettings")
    GlobalSettings.objects.using(schema_editor.connection.alias).get_or_create(
        pk=SINGLETON_PK
    )


class Migration(migrations.Migration):

    dependencies = [
        ("parametros", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(create_initial_settings, migrations.RunPython.noop),
    ]
