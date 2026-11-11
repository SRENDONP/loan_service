# ADR-001 — Un solo negocio, preparado para crecer

> **Estado:** Propuesto
> **Fecha:** 2026-11-10
> **Spec relacionada:** SPEC 01 (fundación del proyecto)
> **Reemplaza a:** ninguno

## Contexto

La constitución dejaba abierta la pregunta de si el sistema maneja un solo negocio o
varios negocios en la misma instancia (§19.2). La decisión D1 de
`docs/specs-tentativas.md` la resolvió: **un solo negocio en la versión 1, con la
posibilidad de ampliarse en el futuro**.

Un sistema multi-tenant desde el inicio obliga a agregar un `tenant` a casi todos los
modelos, a filtrar por él en cada consulta y en cada permiso, y a probar el aislamiento
entre negocios. Es un costo alto para una necesidad que hoy no existe. Pero si la v1 se
construye sin ningún cuidado, convertirla después en multi-tenant puede obligar a rehacer
la lógica de parametrización, que es transversal (constitución §2.1 y §10).

## Decisión

**En la v1 no se agrega `tenant` ni `business` a los modelos.** Todo el sistema
pertenece a un único negocio.

Para no cerrar la puerta al crecimiento:

1. **Los parámetros globales se guardan en la base de datos como un registro único**
   (un modelo de configuración con una sola fila), administrable desde el módulo
   `parametros`. No se guardan como constantes en el código ni en `settings`.
2. **El código lee los parámetros a través de un servicio** (por ejemplo,
   `apps.parametros.services`), nunca consultando el modelo directamente desde vistas o
   plantillas. Así, el día que existan varios negocios, solo cambia ese servicio, que
   pasaría a recibir el negocio activo.
3. **Los datos del negocio** (nombre, logo, moneda, formatos) son parte de ese registro de
   configuración, no textos fijos en las plantillas.

## Alternativas consideradas

- **Multi-tenant desde la v1** (un campo `tenant` en cada modelo, o un esquema de
  PostgreSQL por negocio). Se descarta porque no hay un segundo negocio a la vista y
  multiplica el costo de cada spec: consultas, permisos, pruebas de aislamiento y
  reportes.
- **Parámetros como constantes o en `settings`.** Se descarta porque contradice la §2.1
  ("parametrizar antes que codificar"). Además, cambiar un valor exigiría un despliegue, y
  no habría forma de tener valores distintos por negocio en el futuro.
- **Parámetros como pares clave-valor genéricos.** Se descarta por ahora porque pierde
  los tipos (`Decimal`, enteros, booleanos) y las validaciones del modelo. La forma exacta
  del modelo se decide en la spec de parámetros globales.

## Consecuencias

- **Positivas:** las specs de la v1 no cargan con la complejidad del multi-tenant, y la
  migración futura se concentra en el modelo de configuración y en su servicio.
- **Negativas:** pasar a multi-tenant seguirá requiriendo una migración de datos y
  agregar el negocio a los modelos operativos (clientes, créditos y pagos). Este ADR
  reduce ese costo, pero no lo elimina.
- **Acciones derivadas:**
  - La spec de parámetros globales y catálogos implementa el registro único y su servicio
    de lectura.
  - Ninguna spec debe fijar en el código un valor que la §10 declare parametrizable.
  - La opción multi-tenant queda listada en la fase 2 de `docs/specs-tentativas.md`.
