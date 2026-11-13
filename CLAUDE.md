# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado del proyecto

Sistema web para gestionar préstamos "gota a gota" (microcrédito con cuotas frecuentes, Colombia). La **SPEC 01 (fundación del proyecto)** dejó la base técnica: settings por entorno en `config/settings/` (`base`, `dev`, `prod`) con django-environ, PostgreSQL 18 en Docker, la app `apps/core` con `GET /health/`, pruebas en `tests/`, Ruff, Black, pre-commit y CI en GitHub Actions. La **SPEC 02 (layout base y menú modular)** dejó la interfaz común: `templates/base.html` derivado de SB Admin 2, los recursos de la plantilla en `static/`, el menú lateral que se arma con el `menu.py` de cada app, las páginas de error, los componentes compartidos (mensajes, formularios, tablas con DataTables y modal de confirmación) y el catálogo `/componentes/`, que solo existe con DEBUG. La **SPEC 03 (autenticación)** dejó la app `apps/accounts`: el modelo de usuario propio (`AUTH_USER_MODEL = "accounts.User"`), el inicio de sesión con usuario o correo, el bloqueo temporal tras intentos fallidos, el cambio obligatorio de contraseña en el primer ingreso, la recuperación por correo simulado, Argon2 y la sesión obligatoria en todo el sistema (`LoginRequiredMiddleware`). La **SPEC 04 (usuarios, roles y permisos)** dejó los cuatro roles como grupos de Django, sincronizados desde el código (`apps/accounts/roles.py`, ADR-002), las utilidades de permisos, los servicios de gestión de usuarios y el módulo `/usuarios/` para el Administrador. La **SPEC 05 (auditoría base)** dejó la app `apps/auditoria`: el registro inmutable `AuditEvent` (protegido en la aplicación y con un trigger de PostgreSQL), el catálogo de acciones con su categoría, el servicio `record`, el contexto de la petición, la auditoría de los accesos y de la gestión de usuarios, y un admin de solo lectura. La **SPEC 06 (parámetros globales)** dejó la app `apps/parametros`: el registro único `GlobalSettings` (negocio y formatos, cobro y días no hábiles, redondeo, y seguridad y sesión), su servicio de lectura y edición, la pantalla `/parametros/` para el Administrador, el formato de dinero y fechas, y el cierre de sesión por inactividad y por duración máxima. La **SPEC 07 (catálogos y festivos)** sumó a `apps/parametros` los seis catálogos de texto (tipos de documento, ocupaciones, destinos de crédito, motivos de anulación y de rechazo, y tipos de relación de terceros), los festivos de Colombia (oficiales calculados y propios) con su carga inicial de 2026 a 2030 y el comando `cargar_festivos`, `is_business_day` con festivos y las pantallas del submenú "Catálogos". Todavía no hay modelos de negocio.

La hoja de ruta tentativa de specs, con las decisiones de negocio ya tomadas (D1 a D16), está en `docs/specs-tentativas.md`. Léela antes de escribir una spec.

`constitution.md` es el documento rector del proyecto y prevalece sobre cualquier spec, plan o tarea. Lee la sección correspondiente antes de diseñar o implementar cualquier funcionalidad.

## Comandos

Las dependencias se gestionan con **uv** (`pyproject.toml` + `uv.lock`, entorno virtual en `.venv/`). Requiere Python >= 3.14. La configuración local va en `.env` (copiado de `.env.example`, nunca versionado).

```bash
# Docker: levanta web (Django, puerto 8000) y db (PostgreSQL 18)
docker compose up                        # -d para segundo plano
docker compose up -d db                  # solo la base de datos, para trabajar con uv
docker compose ps                        # estado y healthchecks
docker compose logs -f web
docker compose down                      # -v borra también la base de datos

# Django en local (contra el PostgreSQL del contenedor)
uv sync
uv run python manage.py runserver        # usa config.settings.dev
uv run python manage.py makemigrations
uv run python manage.py migrate
uv run python manage.py check
uv run python manage.py sync_roles       # grupos = ROLE_PERMISSIONS (también corre con migrate)

# Pruebas y calidad (los mismos pasos que el CI)
uv run pytest                            # requiere el PostgreSQL de compose
uv run pytest --cov
uv run pytest tests/core/test_health.py::test_health_ok_when_database_responds
uv run ruff check .
uv run black .                           # black --check . para solo verificar
uv run python manage.py makemigrations --check --dry-run
uv run pre-commit run --all-files
```

Notas:

- Una app nueva se crea dentro de `apps/`: `mkdir apps/<nombre>` y `uv run python manage.py startapp <nombre> apps/<nombre>`. Después, en su `apps.py`, `name = "apps.<nombre>"`. Sus pruebas van en `tests/<nombre>/`, con `__init__.py`.
- En esta máquina, el servicio de Windows `postgresql-x64-18` ocupa el puerto 5432. Por eso el `.env` local usa `POSTGRES_PORT=5433` y `DATABASE_URL=...localhost:5433/...`. Si `migrate` o pytest fallan por autenticación, revisa eso primero.
- `wsgi.py` y `asgi.py` cargan `config.settings.prod` por defecto, y `prod` no arranca sin `SECRET_KEY`, `ALLOWED_HOSTS` y `DATABASE_URL`.

## Diferencias entre la constitución y el código actual

La SPEC 01 resolvió las diferencias estructurales (stack, PostgreSQL, settings por entorno, secretos, `apps/` y `specs/`, Docker e idioma). La §4 se enmendó en la versión 1.3 de la constitución. No elijas un lado en silencio ante un conflicto nuevo: señálalo.

Lo que sigue pendiente a propósito, con la spec que lo resuelve:

| Constitución | Estado actual | Dónde se resuelve |
|---|---|---|
| i18n con `gettext` | Los textos usan `gettext` y `{% translate %}` con msgid en español. Todavía no hay `LocaleMiddleware` ni catálogos `.po` (decisión de la SPEC 02) | Cuando haya un segundo idioma |
| Recuperación de contraseña por correo (§6.1) | Funciona, pero el correo es simulado en todos los entornos: `EMAIL_BACKEND` elige `console` o `file`, sin SMTP. Por eso `check --deploy` con `prod` da el error `mail.E001` (se dejó visible a propósito) | Spec que agregue el envío real de correos |
| HSTS, CSP, respaldos y mínimo privilegio en BD (§14) | `prod` tiene un mínimo seguro; `check --deploy` avisa `security.W004` (además del `mail.E001` del correo simulado) | Spec de endurecimiento |

## Flujo de trabajo obligatorio: desarrollo guiado por especificaciones (SDD)

Ninguna funcionalidad se implementa sin una spec aprobada (constitución §2.7, §16). Si una tarea contradice la constitución, se corrige la tarea. Las preguntas abiertas de la §19 deben resolverse antes de escribir la spec correspondiente. El orden de implementación sugerido está en la §16.3 y en `docs/specs-tentativas.md`.

El flujo es:

1. **`/spec <descripción en una frase>`:** escribe la spec en `specs/NN-slug.md` después de su fase de preguntas. La spec incluye el plan de implementación y los criterios de aceptación. No hay `plan.md` ni `tasks.md` separados (constitución §16.2).
2. **La persona revisa la spec** y cambia su estado de `Borrador` a `Aprobado`. Nunca cambies tú el estado a `Aprobado`.
3. **`/spec-impl NN-slug`:** crea la rama `spec-NN-slug` e implementa paso a paso, con una pausa para revisar el diff después de cada paso. Nunca hagas commits automáticos.
4. **Verificación:** se revisan los criterios de aceptación con `uv run pytest` y, si la spec tiene interfaz, con el MCP de Playwright. Si todo pasa, el estado cambia a `Implementado`.

Convenciones de las specs:

- Están escritas en español y usan los estados en español: `Borrador`, `En revisión`, `Aprobado`, `Implementado` y `Obsoleto`. La plantilla de la skill trae los estados en inglés; usa siempre los equivalentes en español.
- La numeración es de dos dígitos y empieza en `01`. La spec 000 de la hoja tentativa pasa a ser `01`, la 001 pasa a ser `02`, y así hasta la 004 (`05`). La 005 se dividió en la `06` (parámetros globales) y la `07` (catálogos y festivos), así que desde la 006 se suman dos: la 006 pasa a ser `08`, y la 024 pasa a ser `26`.
- `/spec` y `/spec-impl` solo se ejecutan cuando la persona las invoca (`disable-model-invocation`). Si alguien pide escribir o implementar una spec sin usarlas, recuérdale que debe invocarlas.

## Skills y MCP obligatorios (constitución §16.5)

Su uso es **indispensable** para construir el proyecto. Las skills están en `.agents/skills/`, enlazadas desde `.claude/skills/` y registradas en `skills-lock.json`. El MCP `playwright` está configurado para este proyecto.

| Herramienta | Cuándo usarla |
|---|---|
| `/spec` | Siempre que se defina una funcionalidad nueva |
| `/spec-impl` | Siempre que se implemente una spec `Aprobado` |
| `django-patterns` | Antes de diseñar o escribir modelos, servicios, vistas, formularios, consultas ORM, middleware, comandos de gestión o pruebas de Django |
| `frontend-design` | Antes de escribir plantillas, componentes, formularios o estilos |
| MCP `playwright` | Para verificar en el navegador cada spec con interfaz: recorrer los flujos de sus criterios de aceptación, comparar con la referencia SB Admin 2, revisar la vista en celular (unos 375 px) y leer la consola en busca de errores |

Límites, porque la constitución prevalece sobre las skills:

- **`frontend-design`** propone estéticas propias. Aquí **no se rediseña**: se reproduce SB Admin 2 con sus clases y su estructura. Usa la skill solo para la calidad de la ejecución (jerarquía, legibilidad, responsive y accesibilidad). Una desviación visual necesita aprobación explícita.
- **`django-patterns`** incluye DRF, caché y señales. **No uses DRF** (no está en el stack y la interfaz es SSR). No escondas reglas de negocio en señales: la lógica va en `services.py`. Cualquier excepción necesita un ADR en `docs/decisiones/`.
- **Playwright** no reemplaza a pytest. Las pruebas automatizadas que exige la §15 siguen siendo de pytest.
- Para agregar, quitar o actualizar una skill o un servidor MCP hace falta un ADR.

## Arquitectura objetivo (constitución §5)

Apps de Django previstas: `accounts`, `clientes`, `creditos`, `amortizacion`, `pagos`, `mora`, `reportes`, `parametros`, `auditoria`.

- **`amortizacion` es lógica pura.** No debe importar modelos de Django ni consultar la base de datos: recibe parámetros y devuelve la tabla. Requiere 100% de cobertura de pruebas, incluidos los casos límite (1 cuota, tasa cero, montos muy pequeños, redondeos, festivos). La suma del capital de todas las cuotas debe ser exactamente igual al monto desembolsado y el saldo final debe ser exactamente 0.
- **Servicios sobre vistas.** La lógica de negocio vive en el `services.py` de cada app. Las vistas solo validan, llaman a los servicios y renderizan.
- Las operaciones que tocan varias tablas (desembolso, pago, anulación) se ejecutan dentro de `transaction.atomic()`.
- Nada de cálculos financieros en plantillas ni en JavaScript; el frontend solo muestra resultados calculados en el servidor.
- Plantillas de Django renderizadas en el servidor con JavaScript vanilla. Sin frameworks SPA.

## Reglas de negocio innegociables

- **El dinero siempre es `Decimal`, nunca `float`.** El redondeo sigue una regla explícita y configurable.
- **Parametrizar, no fijar en el código.** Tasas, número de cuotas, periodicidad, método de amortización, días de cobro, multas, redondeo, intentos antes del bloqueo, tiempo de sesión y valores similares vienen del módulo `parametros`. Las tasas guardan historial de vigencia y cada crédito conserva la tasa vigente cuando fue aprobado. Las tasas se validan contra un tope de usura configurable.
- **No se borran físicamente los registros financieros.** Pagos, créditos y usuarios se anulan o desactivan con motivo, y todo cambio queda auditado (quién, cuándo, qué).
- Un crédito desembolsado no puede cambiar su tasa, monto ni cuotas. Una reestructuración crea un crédito nuevo vinculado al anterior. La tabla de amortización se guarda como un snapshot inmutable al desembolsar.
- Las transiciones de estado del crédito están restringidas y auditadas (diagrama del ciclo de vida en la §8.1).
- Los permisos usan grupos de Django (Administrador, Supervisor, Cajero/Cobrador, Consulta) y se verifican en cada vista **y** en cada servicio sensible.
- Los números de recibo son consecutivos y sin huecos. El cierre diario de caja es inmutable; los errores se corrigen con ajustes.

## Interfaz

**Todo el HTML, CSS y JavaScript se construye con la plantilla SB Admin 2**, ubicada en `references/startbootstrap-sb-admin-2-gh-pages/` (constitución §13 y §13.1). Es obligatoria: no uses otra plantilla, otro framework CSS ni otra librería de componentes. Antes de escribir una pantalla, abre la página de referencia que le corresponde y parte de su HTML.

| Pantalla | Página de referencia |
|---|---|
| Layout principal y dashboard | `index.html` |
| Cualquier página interna nueva | `blank.html` |
| Inicio de sesión y recuperación de contraseña | `login.html` y `forgot-password.html` |
| Formularios (solo como modelo, no hay registro público) | `register.html` |
| Listados | `tables.html` (DataTables) |
| Gráficas | `charts.html` (Chart.js) |
| Tarjetas de indicadores y botones | `cards.html` y `buttons.html` |
| Clases utilitarias | `utilities-*.html` |
| Errores 403, 404 y 500 | `404.html` |

Reglas:

- **`references/` es de solo lectura.** Copia los recursos a `static/` (`css/sb-admin-2.min.css`, `js/sb-admin-2.min.js`, `img/` y `vendor/`) y sírvelos con `{% static %}`. Nunca enlaces archivos dentro de `references/`.
- Las plantillas de Django se construyen reemplazando el contenido estático por etiquetas de plantilla. Conserva la estructura HTML y las clases CSS base, y no rediseñes sin aprobación.
- **Las librerías son las que trae la plantilla:** Bootstrap 4.3.1, jQuery 3.3.1, jQuery Easing, Font Awesome Free 5.8.1, Chart.js 2.8.0 y DataTables 1.10.19 (bs4). No agregues librerías nuevas. Para actualizar dentro de la misma versión mayor hace falta un ADR.
- **Las personalizaciones** van en un CSS propio (por ejemplo, `static/css/app.css`) cargado después de `sb-admin-2.min.css`. No edites el CSS de la plantilla.
- **`js/demo/` solo sirve de ejemplo.** Las gráficas y tablas reciben sus datos del servidor, y el JavaScript nunca calcula valores financieros.
- **Componentes nuevos:** si hace falta uno que la plantilla no trae, constrúyelo con clases de Bootstrap 4 y de SB Admin 2, siguiendo el estilo de la plantilla.
- **Verificación con Playwright:** compara cada pantalla con su página de referencia, también en celular (unos 375 px).

Lo que dejó la SPEC 02, y que toda pantalla nueva reutiliza:

- **Layout:** extiende `base.html` y usa los bloques `title`, `page_heading`, `content`, `extra_css` y `extra_js`. `500.html` es independiente a propósito: no uses en ella context processors, el menú ni variables.
- **Catálogo:** antes de construir una pantalla, revisa `/componentes/` (solo con DEBUG). Ahí están todos los componentes compartidos.
- **Formularios:** `{{ form }}` ya produce las clases de Bootstrap 4 gracias a `apps.core.forms.BootstrapFormRenderer` y a `templates/forms/`. No agregues django-crispy-forms ni clases a mano en los widgets.
- **Mensajes:** usa `django.contrib.messages`; `base.html` los muestra como alertas.
- **Tablas:** usa `includes/datatable.html`. Su comentario dice qué recursos cargar en `extra_css` y `extra_js`, incluido `{% datatables_i18n %}`. DataTables ordena por la primera columna al cargar; si el listado tiene su propio orden, pasa `keep_order=True` (SPEC 07). Una fecha con formato `d/m/Y` no se ordena bien como texto: pon antes la fecha ISO en un `<span class="d-none">`, como la lista de festivos.
- **Confirmación:** agrega `data-confirm` a un `<form>` para que pida confirmación. La protección real (permisos y validación) sigue en el servidor.
- **Nombre del negocio:** sale del context processor `apps.core.context_processors.branding`. No lo escribas fijo en las plantillas.

### Agregar un módulo al menú

Cada app declara su menú en `apps/<app>/menu.py`, y `apps.core` lo descubre al arrancar con `autodiscover_modules("menu")`. No se edita `apps/core` ni los settings:

```python
from django.utils.translation import gettext_lazy as _

from apps.core.navigation import MenuItem, MenuSection, register, register_section

register_section(MenuSection(key="operacion", label=_("Operación"), order=10))

register(
    MenuItem(
        key="clientes.list",
        label=_("Clientes"),
        icon="fas fa-fw fa-users",
        section="operacion",
        order=10,
        url_name="clientes:list",
        permissions=("clientes.view_cliente",),
    )
)
```

- **Permisos:** el menú filtra con `user.has_perms(permissions)`. Ocultar una entrada no protege la vista: la vista y el servicio siguen verificando permisos.
- **Opciones:** `children` crea un submenú de un solo nivel (con `url_name=None` en el padre), y `debug_only=True` muestra la entrada solo con DEBUG.
- **Rutas con argumentos:** el menú hace `reverse(url_name)` sin argumentos y marca la entrada activa por el nombre de la ruta. Si varias entradas comparten una vista con argumentos, registra una ruta con nombre propio por entrada, como `Catalog.list_url_name` (SPEC 07).
- **Submenús en celular:** el submenú de la página activa se abre en escritorio. Por debajo de 768 px, `static/js/app.js` lo cierra al cargar, porque SB Admin 2 lo dibuja flotando sobre el contenido (SPEC 07).
- **Pruebas:** usan un `MenuRegistry` aislado, como `tests/core/test_navigation.py`. No registran entradas en el registro global.

## Autenticación (SPEC 03)

- **Toda vista exige sesión** (`LoginRequiredMiddleware`). Una vista pública se marca con `@login_not_required`; hoy solo lo son el login, la recuperación de contraseña y `/health/`.
- **Usuario:** usa `get_user_model()` o `settings.AUTH_USER_MODEL` (`accounts.User`), nunca `django.contrib.auth.models.User`. El nombre de usuario no admite `@` ni `+`, y el correo es opcional pero único sin distinguir mayúsculas.
- **Políticas:** los intentos antes del bloqueo, la duración del bloqueo, la longitud mínima de la contraseña y la vigencia del enlace de recuperación solo se leen con `apps/accounts/policy.py`, que desde la SPEC 06 los toma de los parámetros globales. Las pruebas los cambian con el fixture `global_settings`, nunca con `override_settings`.
- **Servicios:** el bloqueo y el desbloqueo están en `apps/accounts/services.py` (`authenticate_with_lockout`, `clear_failed_attempts`, `mark_password_changed`). La SPEC 04 los reutiliza para desbloquear. La SPEC 05 registra ahí el bloqueo y el intento durante un bloqueo, porque Django no emite señales para esos casos.
- **Sesión (SPEC 06):** `SessionPolicyMiddleware` cierra la sesión por inactividad (30 minutos por defecto) y al llegar a su duración máxima (12 horas por defecto), los dos tiempos leídos de `policy.py`. Deja `auth.logout` con `extra.reason` (`inactivity` o `max_duration`) y un mensaje en el login. Una vista `@login_not_required` no cierra la sesión, pero cuenta como actividad. `SESSION_COOKIE_AGE` (24 horas) es solo el tope duro.
- **Cambio obligatorio:** mientras `must_change_password` sea verdadero, `ForcePasswordChangeMiddleware` lleva al usuario a `/contrasena/cambiar/` desde cualquier ruta.
- **Admin de Django:** solo para superusuarios y con el login propio. Es una herramienta técnica: los usuarios se gestionan en `/usuarios/` (SPEC 04), y el admin no permite borrarlos.
- **Pruebas:** usan el hasher MD5 (fixture `autouse` en `tests/conftest.py`). Para pedir páginas usa los fixtures `auth_client`, `user` y `make_user`; `make_user` crea el usuario con `must_change_password=False` salvo que se indique otra cosa.

## Usuarios, roles y permisos (SPEC 04)

- **Roles:** `Role` en `apps/accounts/roles.py` (`ADMINISTRATOR`, `SUPERVISOR`, `COLLECTOR`, `VIEWER`). El valor es el nombre exacto del grupo de Django. Cada usuario que no es superusuario tiene **exactamente un** rol; se asigna solo con los servicios. Usa `get_role(user)` y `has_role(user, role)`. Los superusuarios son cuentas técnicas sin rol y no se gestionan desde la aplicación.
- **Permisos de cada rol:** solo en `ROLE_PERMISSIONS` de `roles.py`. `sync_roles` deja los cuatro grupos exactamente iguales al mapa: agrega lo que falta y **quita lo que sobra**. Corre sola después de cada `migrate` (receptor de `post_migrate`, ADR-002) y a mano con `uv run python manage.py sync_roles`. Nunca cambies los permisos de esos grupos a mano ni con una migración de datos.
- **Cuando una spec cree un módulo:** agrega los permisos de sus modelos a `ROLE_PERMISSIONS` en la misma rama, con una prueba de la matriz. Un permiso que no existe hace fallar `migrate` con `ImproperlyConfigured`.
- **Quién es cobrador:** `User.objects.collectors()`: activo, no superusuario y con el rol `Cajero/Cobrador`. No hay relación entre supervisor y cobradores: todo supervisor ve a todos. También existen `User.objects.with_role(role)` y `User.objects.active_administrators()`.
- **Verificar permisos** (`apps/accounts/permissions.py`): en servicios, `require_perms(user, *perms)`; en vistas de clase, `PermissionRequiredMixin` (pon `permission_required`); en vistas de función, `permission_required(*perms)`. Las tres responden 403, nunca redirigen al login.
- **Servicios de gestión** (`apps/accounts/services.py`): `create_user`, `update_user`, `deactivate_user`, `reactivate_user`, `unlock_user`, `reset_user_password` y `logout_user_sessions`. Reciben siempre al `actor` primero, verifican su permiso y lanzan `UserRuleError` (subclase de `ValidationError`) cuando una regla lo impide: nada sobre uno mismo ni sobre un superusuario, siempre queda un Administrador activo que no es superusuario y sobre un inactivo solo se edita o se reactiva. Cada uno deja su registro de auditoría (SPEC 05).
- **Contraseñas temporales:** las genera `generate_temporary_password()` y se muestran una sola vez con `temporary_password_response` (renderizada desde el POST, con `no-store`). Nunca las pongas en `messages`, en la sesión ni en logs.
- **Usuarios nunca se borran:** el modelo no tiene permiso `delete_user` y el admin no ofrece el borrado. Se desactivan con motivo (`deactivated_at`, `deactivated_by`, `deactivation_reason`).
- **Pruebas:** `make_user(role=Role.X)` crea el usuario con ese rol. Los grupos ya existen en la base de pruebas porque `migrate` corre `sync_roles`.

## Auditoría (SPEC 05)

Toda acción sobre datos financieros, personales o de seguridad deja un registro inmutable (§14). **Cada spec que cree un módulo audita sus acciones desde su primer día**, e incluye criterios de aceptación de esa auditoría.

**Cómo auditar una acción nueva:**

1. Agrégala a `AuditAction` en `apps/auditoria/actions.py` con un valor `"modulo.accion"` y una etiqueta con `gettext_lazy`.
2. Asígnale una categoría en `ACTION_CATEGORIES`: `ACCESS`, `SECURITY`, `PERSONAL_DATA` o `FINANCIAL`. La categoría la fija el catálogo, no quien llama.
3. En el servicio, toma un `snapshot` antes de la operación y otro después, y llama a `record` **dentro de la misma `transaction.atomic()`**:

```python
from apps.auditoria.actions import AuditAction
from apps.auditoria.services import diff, record, snapshot

FIELDS = ("amount", "status")

with transaction.atomic():
    before = snapshot(credit, FIELDS)
    # ... la operación ...
    record(
        AuditAction.CREDIT_DISBURSED,
        actor=actor,
        target=credit,
        changes=diff(before, snapshot(credit, FIELDS)),
        extra={"reason": reason},
    )
```

Reglas:

- **El valor de una acción no cambia nunca** después de usarse; la etiqueta sí. Una prueba exige que toda acción tenga categoría.
- **El actor es siempre el `actor` del servicio.** `record` no lo saca del `request` ni del contexto.
- **Si `record` falla, la operación se revierte.** No atrapes sus errores: una acción sin rastro es justo lo que la §14 prohíbe.
- **Una edición sin cambios no se registra:** llama a `record` solo si `diff` no está vacío. Una acción explícita, como desbloquear o cerrar sesiones, sí se registra aunque no cambie campos.
- **`changes`** guarda solo lo que cambió, como `{"campo": [antes, después]}`. **`extra`** guarda el contexto: el motivo, cuántas sesiones se cerraron.
- **Campos secretos:** los de `SENSITIVE_FIELDS` (`apps/auditoria/services.py`) quedan como `"[oculto]"`. Si tu modelo trae otro campo secreto, agrégalo ahí. Nunca pongas en `extra` una contraseña, un token ni un hash.
- **Usuarios:** `user_audit_snapshot(user)` en `apps/accounts/services.py` toma los campos auditables más el `role`.
- **Señales:** solo los ingresos, los fallos de ingreso y los cierres de sesión se auditan con las señales de autenticación de Django (`apps/auditoria/receivers.py`, ADR-004). Todo lo demás llama a `record` desde el servicio.

**Contexto de la petición:**

- `AuditContextMiddleware` fija en un `ContextVar` la IP, el user agent, el método, la ruta sin cadena de consulta, un `request_id` y el origen. El origen es `web`, o `admin` bajo la ruta del admin. `record` lo toma solo, así que los servicios no reciben el `request`.
- Un comando de gestión que audite envuelve su trabajo en `with audit_context(source=AuditSource.COMMAND):`. Sin petición ni `audit_context`, el origen es `system` y no hay IP.
- **La IP** sale de `REMOTE_ADDR`. `X-Forwarded-For` solo se lee si `AUDIT_TRUSTED_PROXIES` es mayor que 0 (variable de entorno, por defecto `0`; detrás de un nginx propio, `1`).

**Inmutabilidad:**

- `AuditEvent` solo se crea. `save()` sobre uno existente, `delete()`, `update()` y `bulk_update()` lanzan `ImmutableAuditEventError`, y el trigger `auditoria_auditevent_immutable` rechaza `UPDATE` y `DELETE` por SQL.
- `TRUNCATE` no está bloqueado, porque `flush` lo usa en las pruebas transaccionales. Ninguna prueba borra registros de auditoría con `DELETE`.
- **Consulta:** por ahora, solo en el admin de Django (`/admin/auditoria/auditevent/`), de solo lectura y para superusuarios. Ningún rol tiene `auditoria.view_auditevent`; lo asigna la SPEC 26 (la 024 de la hoja tentativa).

**Pruebas:** usa `AuditEvent.objects.filter(action=...)` para verificar el registro. `force_login` también emite `user_logged_in` y crea un `auth.login_succeeded`, así que no supongas que el registro que buscas es el único.

## Parámetros globales (SPEC 06)

Los valores que la constitución declara parametrizables (§10.1) viven en un registro único, `GlobalSettings` (`apps/parametros/models.py`, fila `pk=1`), y **solo se leen con `apps/parametros/services.py`** (ADR-001). Ningún módulo fuera de `apps/parametros` importa `GlobalSettings`; una prueba lo verifica.

- **Leer:** `get_settings()` devuelve la fila (la crea con los valores por defecto si falta). No hay caché: un cambio aplica en la siguiente petición. También existen `get_rounding_rule()` (un `RoundingRule` con el múltiplo como `Decimal` y el modo, que el motor recibe como parámetro) e `is_business_day(fecha)` (los días de la semana no hábiles y, desde la SPEC 07, los festivos activos).
- **Editar:** `update_business`, `update_collection`, `update_rounding` y `update_security` reciben al `actor`, verifican `parametros.change_globalsettings`, tocan solo los campos de su grupo, validan con `full_clean()`, guardan `updated_by` y auditan su acción (`parametros.*_updated`: negocio y seguridad en `SECURITY`, cobro y redondeo en `FINANCIAL`). Sin cambios no guardan ni registran.
- **Un parámetro nuevo** va como campo tipado en `GlobalSettings`, con su valor por defecto, sus validadores y su `CheckConstraint` si tiene rango, en el grupo que le corresponda (`*_FIELDS` en `services.py` y su formulario en `forms.py`). Nunca como constante ni en `settings`.
- **Permisos:** solo el Administrador ve y edita `/parametros/` (`PARAMETROS_PERMISSIONS` en `roles.py`). El resto del sistema lee los valores por el servicio, sin permisos. `GlobalSettings` no está en el admin de Django, para que nadie edite sin auditoría.
- **Importación:** `accounts.policy` importa `parametros.services` mientras se cargan los modelos de `accounts`. Por eso `services.py` importa `require_perms` dentro de la función de edición; no lo subas al nivel del módulo.
- **Formato:** para mostrar dinero y fechas usa `format_money`, `format_date` y `format_datetime` (`apps/parametros/formatting.py`) o los filtros `moneda`, `fecha` y `fecha_hora` (`{% load formato %}`). `format_money` solo acepta `Decimal` o `int`. Los separadores y la hora (`H:i`) salen de `es-co`, y el mes del formato largo va en minúscula. Ese redondeo es solo para mostrar.
- **Formularios:** el renderizador ya dibuja las listas de casillas (`CheckboxSelectMultiple`, en línea y dentro de un `fieldset`) y las horas (`TimeInput` con `type="time"`).
- **Pruebas:** cambia un parámetro con el fixture `global_settings` (atributos y `save()`); el cambio se revierte con la transacción de la prueba. Las pruebas que validan contraseñas o renderizan `base.html` necesitan base de datos, porque la longitud mínima y el nombre del negocio salen de ahí.

## Catálogos y festivos (SPEC 07)

Los catálogos administrables de la §10.4 y los festivos viven en `apps/parametros`. Solo el Administrador los ve y los edita (`CATALOG_PERMISSIONS` en `roles.py`); el resto del sistema los lee por el servicio, sin permisos.

**Catálogos de texto:**

- **Modelos:** `DocumentType`, `Occupation`, `CreditPurpose`, `VoidReason`, `RejectionReason` y `ThirdPartyRelationType`, cada uno en su tabla sobre el modelo abstracto `CatalogItem` (`code`, `name`, `display_order`, `is_active`, `is_system`). El registro de los seis está en `CATALOGS` (`apps/parametros/catalogs.py`); las vistas, las rutas y el menú se arman desde ahí.
- **Leer:** `get_active_items(Modelo)` para los ítems activos en su orden, y `get_item_by_code(Modelo, código)` para uno concreto, activo o no. Nunca uses `Modelo.objects` para leer fuera de `apps/parametros`.
- **Apuntar a un catálogo:** una `ForeignKey` al modelo con `on_delete=models.PROTECT`. El formulario ofrece solo los activos (`get_active_items`), pero un registro que ya tiene un ítem desactivado lo sigue mostrando.
- **Nombre repetido:** `parametros.DocumentType` (el catálogo) no es `accounts.DocumentType` (la lista fija de los usuarios internos, que sigue así). Fuera de su app, impórtalo con alias: `from apps.parametros.models import DocumentType as DocumentTypeItem`.
- **Códigos:** no cambian después de crearse; el nombre y el orden sí. Si se crea sin código, el servicio lo genera del nombre (`generate_code`: "Pago de arriendo" → `PAGO_DE_ARRIENDO`, con `_2` si ya existe). Busca un ítem por su código, nunca por su nombre ni por su `pk`.
- **Ítems de sistema:** "Codeudor" y "Referencia personal" (`RELATION_CODEBTOR` y `RELATION_PERSONAL_REFERENCE` en `catalogs.py`) tienen `is_system=True`: se renombran, pero no se desactivan. Un ítem de sistema nuevo se crea con una migración de datos.
- **Nunca se borran:** no hay permiso `delete` y `delete()` lanza `PermissionDenied`. Se desactivan.
- **Servicios:** `create_catalog_item`, `update_catalog_item`, `deactivate_catalog_item` y `reactivate_catalog_item` reciben al `actor`, verifican el permiso del modelo y auditan (`catalogos.*`, categoría `SECURITY`). Una regla que lo impide lanza `CatalogRuleError` (subclase de `ValidationError`).
- **Un catálogo nuevo:** una subclase de `CatalogItem`, su migración, una línea en `CATALOGS` y sus permisos en `CATALOG_PERMISSIONS`.

**Festivos:**

- **Modelo:** `Holiday`, con origen `official` (calculado, identificado por `official_year` y `official_code`) o `custom` (un día que el negocio no abre). Solo hay un festivo activo por fecha.
- **Cálculo:** `colombian_holidays(año)` (`apps/parametros/holidays.py`, lógica pura con 100 % de cobertura) aplica la Ley 51 de 1983 y la Pascua. Sagrado Corazón y San Pedro y San Pablo pueden caer el mismo día; la carga deja el segundo desactivado.
- **Cargar un año:** `uv run python manage.py cargar_festivos 2031 2032`. Solo agrega lo que falta y nunca toca un festivo que ya existe, aunque esté desactivado o con otra fecha. La migración `0005_initial_holidays.py` cargó 2026 a 2030. Un año sin carga no tiene festivos, y `/parametros/festivos/` avisa si falta el año actual o el siguiente.
- **Leer:** `is_business_day(fecha)` descarta los días de la semana no hábiles y los festivos activos. `get_holidays(inicio, fin)` devuelve el `frozenset` de fechas que recibe el calendario del motor, que no importa `parametros`.
- **Servicios:** `create_holiday` (siempre propio), `update_holiday` (solo fecha y nombre), `deactivate_holiday`, `reactivate_holiday` y `load_official_holidays`. Auditan con `festivos.*`, categoría `FINANCIAL`.
- **Pruebas:** los ítems y los festivos de la carga inicial existen en la base de pruebas (las migraciones de datos ya corrieron). Usa fechas fuera de 2026–2030 o sin festivo para crear festivos de prueba, y recuerda que un lunes puede ser festivo. El fixture `catalog_editor` (`tests/parametros/conftest.py`) tiene `add` y `change` de los siete modelos.

## Convenciones de código

- Identificadores del código en inglés; textos de la interfaz en español (Colombia), envueltos en `gettext`.
- Anotaciones de tipo explícitas en los servicios y en el motor de amortización.
- Nunca editar migraciones ya aplicadas.
- Commits convencionales (`feat:`, `fix:`, `docs:`, `test:`).
- Nada de `print()` ni `breakpoint()` en el código que se integra.
- Nunca desactivar las protecciones de Django contra CSRF, XSS e inyección SQL.



