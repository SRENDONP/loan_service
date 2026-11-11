"""
Inmutabilidad del registro de auditoría en PostgreSQL (SPEC 05, §3.3 y ADR-004).

El trigger rechaza `UPDATE` y `DELETE` sobre cada fila, venga de donde venga
(la aplicación, el shell o SQL directo). No cubre `TRUNCATE`, que usa `flush`
en las pruebas transaccionales; ese permiso se le quita al usuario de la
aplicación en la spec de endurecimiento.
"""

from django.db import migrations

CREATE_SQL = """
CREATE OR REPLACE FUNCTION auditoria_auditevent_block_changes()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'auditoria_auditevent es inmutable';
END;
$$;

CREATE TRIGGER auditoria_auditevent_immutable
BEFORE UPDATE OR DELETE ON auditoria_auditevent
FOR EACH ROW
EXECUTE FUNCTION auditoria_auditevent_block_changes();
"""

DROP_SQL = """
DROP TRIGGER IF EXISTS auditoria_auditevent_immutable ON auditoria_auditevent;
DROP FUNCTION IF EXISTS auditoria_auditevent_block_changes();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("auditoria", "0001_initial"),
    ]

    operations = [
        migrations.RunSQL(sql=CREATE_SQL, reverse_sql=DROP_SQL),
    ]
