# ADR-002 — Sincronizar los roles con `post_migrate`

> **Estado:** Propuesto
> **Fecha:** 2026-11-11
> **Spec relacionada:** SPEC 04 (usuarios, roles y permisos)
> **Reemplaza a:** ninguno

## Contexto

La constitución define cuatro roles fijos con grupos de Django (§6.2): Administrador,
Supervisor, Cajero/Cobrador y Consulta. Cada módulo nuevo (clientes, créditos, pagos...)
trae permisos que hay que asignar a esos grupos. La SPEC 04 decidió que la matriz de rol a
permisos vive en un solo lugar del código, `ROLE_PERMISSIONS` en `apps/accounts/roles.py`,
y que una función `sync_roles` deja los grupos exactamente iguales a esa matriz.

Falta decidir **cuándo** corre `sync_roles`. Hay dos restricciones:

1. Django crea los permisos de cada modelo en la señal `post_migrate`, después de aplicar
   todas las migraciones. Una migración de datos que corre en una base nueva no puede
   asignar permisos de modelos cuyas filas en `auth_permission` todavía no existen.
2. `CLAUDE.md` prohíbe esconder reglas de negocio en señales, y pide un ADR para cualquier
   excepción.

## Decisión

**`sync_roles` corre en un receptor de `post_migrate`**, conectado en
`AccountsConfig.ready()`, y también con el comando `uv run python manage.py sync_roles`.

Detalle:

- Django emite `post_migrate` una vez por cada app con modelos, en el orden de
  `INSTALLED_APPS`. El receptor de `django.contrib.auth` que crea los permisos de cada app
  se conecta antes que el nuestro, porque `auth` está antes en `INSTALLED_APPS`.
- El receptor se conecta sin `sender` y con `dispatch_uid="accounts.sync_roles"`. Solo actúa
  cuando la señal viene de **la última app de `INSTALLED_APPS` que tiene modelos**. En ese
  momento ya existen todos los permisos del proyecto, y la sincronización corre una sola vez
  por `migrate`.
- La sincronización es **estricta** en los cuatro grupos: agrega los permisos que faltan y
  quita los que sobran. No toca otros grupos ni los permisos individuales de los usuarios.
  Es idempotente.
- Si `ROLE_PERMISSIONS` nombra un permiso que no existe, `sync_roles` lanza
  `ImproperlyConfigured` antes de cambiar nada. Un error de escritura en el mapa hace fallar
  `migrate` en CI, en lugar de dejar un rol sin permiso en silencio.

Esto no contradice la regla de `CLAUDE.md`: la matriz de permisos es configuración de
acceso, no una regla de negocio. Las reglas sobre usuarios (quién puede desactivar a quién,
siempre queda un administrador...) siguen en `services.py`.

## Alternativas consideradas

- **Solo el comando manual.** No usa señales, pero hay que acordarse de correrlo después de
  cada `migrate` en local, en CI, en Docker y en producción. Basta olvidarlo una vez para que
  un rol quede sin los permisos de un módulo nuevo.
- **Una migración de datos por spec.** Cada spec agregaría una migración que asigna sus
  permisos. La matriz quedaría repartida en muchas migraciones, y al reproducirlas en una base
  nueva los permisos todavía no existen. Habría que llamar a `create_permissions` a mano
  dentro de cada migración, lo que es frágil.
- **Editar los permisos de los grupos en pantalla.** La §6.2 define los roles de forma fija, y
  un cambio manual podría romper un rol sin que quede en el código.

## Consecuencias

- **Positivas:** cada `migrate` (local, CI, Docker, producción, y también `flush` en las
  pruebas transaccionales) deja los grupos correctos. La matriz completa se lee y se prueba en
  un solo archivo.
- **Negativas:** un cambio hecho a mano a uno de los cuatro grupos, por ejemplo desde el admin
  de Django, se pierde en el siguiente `migrate`. El receptor depende de que `auth` esté antes
  que las apps del proyecto en `INSTALLED_APPS`.
- **Acciones derivadas:**
  - Cada spec que crea un módulo agrega los permisos de sus modelos a `ROLE_PERMISSIONS` en
    la misma rama, con una prueba que verifique la matriz.
  - Los permisos de los grupos se cambian solo en `roles.py`, nunca a mano.
  - El ADR de la librería de PDF que preveía `docs/specs-tentativas.md` como ADR-002 pasa a
    ser el ADR-003.
