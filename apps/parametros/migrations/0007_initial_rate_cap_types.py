"""
Carga inicial de los tipos de tope de tasa (SPEC 08, §3.4).

Solo crea "Usura" (`USURA`), de sistema y **sin ningún valor**: el Administrador
carga el valor certificado vigente desde la pantalla. La migración no inventa
una cifra legal. El código va escrito aquí, no importado de la app, para que
esta migración siga creando lo mismo aunque el código cambie. No audita: no hay
actor, como la 0004. La reversa no hace nada: al revertir 0006 la tabla
desaparece con el ítem.
"""

from django.db import migrations


def create_usury(apps, schema_editor):
    RateCapType = apps.get_model("parametros", "RateCapType")
    RateCapType.objects.using(schema_editor.connection.alias).get_or_create(
        code="USURA",
        defaults={"name": "Usura", "display_order": 10, "is_system": True},
    )


class Migration(migrations.Migration):

    dependencies = [
        ("parametros", "0006_credit_products"),
    ]

    operations = [
        migrations.RunPython(create_usury, migrations.RunPython.noop),
    ]
