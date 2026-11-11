# ADR-004 — Auditar los accesos con señales y proteger el registro con un trigger

> **Estado:** Propuesto
> **Fecha:** 2026-11-11
> **Spec relacionada:** SPEC 05 (auditoría base)
> **Reemplaza a:** ninguno

## Contexto

La §14 de la constitución exige un registro de auditoría inmutable, y la SPEC 05 lo crea en
`apps/auditoria` con el modelo `AuditEvent` y el servicio `record`. Para eso hay que tomar
dos decisiones que se salen de las reglas generales del proyecto:

1. **Cómo auditar los ingresos.** `CLAUDE.md` prohíbe esconder reglas de negocio en señales
   y pide un ADR para cualquier excepción. La regla general de la SPEC 05 es que cada
   servicio llame a `record` de forma explícita. Pero un ingreso puede llegar por varios
   caminos: el login propio, el admin de Django o cualquier código que llame a `login()` o a
   `authenticate()`. Si se audita solo desde `LoginView`, un camino nuevo puede quedar sin
   rastro.
2. **Cómo garantizar la inmutabilidad.** El modelo y su `QuerySet` rechazan la edición y el
   borrado, pero eso no cubre el SQL directo, el shell de la base de datos ni un error en el
   código que use otro camino del ORM.

## Decisión

**Los ingresos, los fallos de ingreso y los cierres de sesión se auditan con las señales de
autenticación de Django. La tabla `auditoria_auditevent` tiene un trigger de PostgreSQL que
rechaza `UPDATE` y `DELETE`.**

Señales:

- `user_logged_in`, `user_login_failed` y `user_logged_out` se conectan en
  `AuditoriaConfig.ready()`, cada una con su `dispatch_uid`. Los receptores están en
  `apps/auditoria/receivers.py`.
- Los receptores **solo llaman a `record`**. No deciden nada del negocio ni cambian datos.
- `user_login_failed` entrega las credenciales con la contraseña ya enmascarada por Django.
  El receptor solo lee `username`.
- Lo que Django no emite como señal se audita de forma explícita, desde el servicio o la
  vista que lo hace:
  - El intento durante un bloqueo, en `authenticate_with_lockout`. En ese caso no se llama a
    `authenticate()`.
  - El bloqueo de la cuenta, en `register_failed_attempt`.
  - Los cambios de contraseña, en las vistas de cambio y de recuperación.
- La gestión de usuarios y todo lo que venga después (clientes, créditos, pagos...) **no** usa
  señales: cada servicio llama a `record` dentro de su transacción.

Trigger (migración `auditoria/0002_immutable_trigger.py`):

- La función `auditoria_auditevent_block_changes()` lanza el error
  `auditoria_auditevent es inmutable`.
- El trigger `auditoria_auditevent_immutable` la ejecuta `BEFORE UPDATE OR DELETE ... FOR EACH
  ROW`.
- La migración se puede revertir: la reversa borra el trigger y la función.
- **No cubre `TRUNCATE`.** `flush`, que usan las pruebas transaccionales, vacía las tablas con
  `TRUNCATE`.

## Alternativas consideradas

- **Llamar a `record` desde `LoginView` y `LogoutView`.** No usa señales, pero un ingreso por
  el admin o por un camino nuevo quedaría sin auditar.
- **Señales genéricas `pre_save` y `post_save` para todo.** No distinguen la acción de negocio
  (desactivar no es lo mismo que editar), auditarían ruido como `last_login` y esconderían la
  lógica en señales.
- **Un esquema mixto: servicios explícitos y señales como red de seguridad.** Duplicaría
  registros y haría difícil saber cuál es el bueno.
- **Inmutabilidad solo en la aplicación.** Un `QuerySet.update()` olvidado o una consulta por
  SQL bastarían para alterar el registro.
- **Bloquear solo `UPDATE` y dejar `DELETE` abierto para la depuración futura.** Dejaría el
  borrado libre hasta la SPEC 25.
- **Bloquear también `TRUNCATE` con el trigger.** Rompería `flush` en las pruebas
  transaccionales.

## Consecuencias

- **Positivas:**
  - Cualquier camino de ingreso queda auditado sin que cada vista lo recuerde.
  - Ningún camino, ni siquiera el SQL directo, puede editar ni borrar un registro.
  - Las reglas de negocio siguen en `services.py`: las señales solo cubren la autenticación,
    que es de Django.
- **Negativas:**
  - Si la escritura del registro falla, el ingreso también falla. Es intencional: sin
    auditoría no hay acción.
  - Mientras el usuario de la aplicación tenga permiso de `TRUNCATE`, la tabla se puede vaciar
    entera.
  - Para depurar registros viejos hará falta una vía controlada que pase el trigger.
- **Acciones derivadas:**
  - La SPEC 25 (consulta y retención) diseña la vía controlada para que la depuración pase el
    trigger.
  - La spec de endurecimiento le quita el permiso de `TRUNCATE` al usuario de base de datos de
    la aplicación.
  - Una spec que necesite auditar algo sin señal de Django lo hace con `record` explícito,
    nunca con una señal nueva sin su propio ADR.
