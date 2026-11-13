"""
Carga inicial de los seis catálogos de texto (SPEC 07, §3.4).

Los datos van escritos aquí, no importados del código de la app, para que esta
migración siga creando lo mismo aunque el código cambie. `display_order` va de
10 en 10 en el orden de cada lista. Solo "Codeudor" y "Referencia personal" son
ítems de sistema. No audita: no hay actor, como la 0002. La reversa no hace
nada: al revertir 0003 las tablas desaparecen con los ítems.
"""

from django.db import migrations

SYSTEM_CODES = {"CODEUDOR", "REFERENCIA_PERSONAL"}

CATALOGS = {
    "DocumentType": [
        ("CC", "Cédula de ciudadanía"),
        ("CE", "Cédula de extranjería"),
        ("PPT", "Permiso por protección temporal"),
        ("PA", "Pasaporte"),
        ("TI", "Tarjeta de identidad"),
    ],
    "Occupation": [
        ("COMERCIANTE", "Comerciante"),
        ("TENDERO", "Tendero"),
        ("VENDEDOR_AMBULANTE", "Vendedor ambulante"),
        ("EMPLEADO", "Empleado"),
        ("INDEPENDIENTE", "Independiente"),
        ("TRANSPORTADOR", "Transportador"),
        ("AMA_DE_CASA", "Ama de casa"),
        ("OTRA", "Otra"),
    ],
    "CreditPurpose": [
        ("CAPITAL_TRABAJO", "Capital de trabajo"),
        ("COMPRA_MERCANCIA", "Compra de mercancía"),
        ("GASTOS_PERSONALES", "Gastos personales"),
        ("VIVIENDA", "Vivienda"),
        ("SALUD", "Salud"),
        ("EDUCACION", "Educación"),
        ("PAGO_DEUDAS", "Pago de deudas"),
        ("OTRO", "Otro"),
    ],
    "VoidReason": [
        ("ERROR_DIGITACION", "Error de digitación"),
        ("PAGO_DUPLICADO", "Pago duplicado"),
        ("VALOR_INCORRECTO", "Valor incorrecto"),
        ("CREDITO_EQUIVOCADO", "Crédito equivocado"),
        ("OTRO", "Otro"),
    ],
    "RejectionReason": [
        ("CAPACIDAD_PAGO", "Capacidad de pago insuficiente"),
        ("REFERENCIAS_NO_VERIFICADAS", "Referencias no verificadas"),
        ("DOCUMENTACION_INCOMPLETA", "Documentación incompleta"),
        ("HISTORIAL_MORA", "Historial de mora"),
        ("OTRO", "Otro"),
    ],
    "ThirdPartyRelationType": [
        ("CODEUDOR", "Codeudor"),
        ("REFERENCIA_PERSONAL", "Referencia personal"),
        ("FAMILIAR", "Familiar"),
        ("OTRO", "Otro"),
    ],
}


def create_initial_catalogs(apps, schema_editor):
    alias = schema_editor.connection.alias
    for model_name, items in CATALOGS.items():
        model = apps.get_model("parametros", model_name)
        for position, (code, name) in enumerate(items, start=1):
            model.objects.using(alias).get_or_create(
                code=code,
                defaults={
                    "name": name,
                    "display_order": position * 10,
                    "is_system": code in SYSTEM_CODES
                    and model_name == "ThirdPartyRelationType",
                },
            )


class Migration(migrations.Migration):

    dependencies = [
        ("parametros", "0003_catalogs"),
    ]

    operations = [
        migrations.RunPython(create_initial_catalogs, migrations.RunPython.noop),
    ]
