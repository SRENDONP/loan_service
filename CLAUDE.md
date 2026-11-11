# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado del proyecto

Sistema web para gestionar préstamos "gota a gota" (microcrédito con cuotas frecuentes, Colombia). La **SPEC 01 (fundación del proyecto)** dejó la base técnica: settings por entorno en `config/settings/` (`base`, `dev`, `prod`) con django-environ, PostgreSQL 18 en Docker, la app `apps/core` con `GET /health/`, pruebas en `tests/`, Ruff, Black, pre-commit y CI en GitHub Actions. La **SPEC 02 (layout base y menú modular)** dejó la interfaz común: `templates/base.html` derivado de SB Admin 2, los recursos de la plantilla en `static/`, el menú lateral que se arma con el `menu.py` de cada app, las páginas de error, los componentes compartidos (mensajes, formularios, tablas con DataTables y modal de confirmación) y el catálogo `/componentes/`, que solo existe con DEBUG. Todavía no hay modelos de negocio ni inicio de sesión propio.

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
| Recuperación de contraseña por correo (§6.1) | Correo por consola solo en `dev`; `prod` usa el SMTP por defecto de Django, sin configurar | Spec de autenticación |
| HSTS, CSP, respaldos y mínimo privilegio en BD (§14) | `prod` tiene un mínimo seguro; `check --deploy` solo avisa `security.W004` | Spec de endurecimiento |

## Flujo de trabajo obligatorio: desarrollo guiado por especificaciones (SDD)

Ninguna funcionalidad se implementa sin una spec aprobada (constitución §2.7, §16). Si una tarea contradice la constitución, se corrige la tarea. Las preguntas abiertas de la §19 deben resolverse antes de escribir la spec correspondiente. El orden de implementación sugerido está en la §16.3 y en `docs/specs-tentativas.md`.

El flujo es:

1. **`/spec <descripción en una frase>`:** escribe la spec en `specs/NN-slug.md` después de su fase de preguntas. La spec incluye el plan de implementación y los criterios de aceptación. No hay `plan.md` ni `tasks.md` separados (constitución §16.2).
2. **La persona revisa la spec** y cambia su estado de `Borrador` a `Aprobado`. Nunca cambies tú el estado a `Aprobado`.
3. **`/spec-impl NN-slug`:** crea la rama `spec-NN-slug` e implementa paso a paso, con una pausa para revisar el diff después de cada paso. Nunca hagas commits automáticos.
4. **Verificación:** se revisan los criterios de aceptación con `uv run pytest` y, si la spec tiene interfaz, con el MCP de Playwright. Si todo pasa, el estado cambia a `Implementado`.

Convenciones de las specs:

- Están escritas en español y usan los estados en español: `Borrador`, `En revisión`, `Aprobado`, `Implementado` y `Obsoleto`. La plantilla de la skill trae los estados en inglés; usa siempre los equivalentes en español.
- La numeración es de dos dígitos y empieza en `01`. La spec 000 de la hoja tentativa pasa a ser `01`, la 001 pasa a ser `02`, y así con las demás.
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
- **Tablas:** usa `includes/datatable.html`. Su comentario dice qué recursos cargar en `extra_css` y `extra_js`, incluido `{% datatables_i18n %}`.
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
- **Pruebas:** usan un `MenuRegistry` aislado, como `tests/core/test_navigation.py`. No registran entradas en el registro global.

## Convenciones de código

- Identificadores del código en inglés; textos de la interfaz en español (Colombia), envueltos en `gettext`.
- Anotaciones de tipo explícitas en los servicios y en el motor de amortización.
- Nunca editar migraciones ya aplicadas.
- Commits convencionales (`feat:`, `fix:`, `docs:`, `test:`).
- Nada de `print()` ni `breakpoint()` en el código que se integra.
- Nunca desactivar las protecciones de Django contra CSRF, XSS e inyección SQL.



