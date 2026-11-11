# Sistema de gestión de préstamos gota a gota

Sistema web para gestionar préstamos "gota a gota" (microcrédito con cuotas frecuentes) en
Colombia: clientes, créditos, tabla de amortización, pagos, mora, cierre de caja y reportes.

El documento rector es [`constitution.md`](constitution.md). Las funcionalidades se
construyen con desarrollo guiado por especificaciones (SDD): ver [Flujo de trabajo](#flujo-de-trabajo-sdd).

## Stack

- Python 3.14+ y Django 6.1, con plantillas renderizadas en el servidor.
- PostgreSQL (mínimo 16; se usa la 18 en Docker y en CI). Es el único motor, también en las pruebas.
- Dependencias con [uv](https://docs.astral.sh/uv/) (`pyproject.toml` + `uv.lock`).
- pytest + pytest-django + pytest-cov, Ruff, Black y pre-commit.
- Docker y docker compose para el entorno de desarrollo.
- Interfaz basada en la plantilla SB Admin 2 (`references/`, de solo lectura).

## Requisitos

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (o Docker Engine con el plugin compose).
- Para trabajar fuera del contenedor: [uv](https://docs.astral.sh/uv/getting-started/installation/).
  uv instala Python 3.14 si no lo tienes.

## Puesta en marcha con Docker

1. Abre Docker Desktop y espera a que diga que el motor está corriendo.
2. Desde la raíz del repositorio, crea tu archivo de configuración local (solo la primera
   vez) y levanta el stack:

   ```bash
   cp .env.example .env
   docker compose up
   ```

   La primera vez tarda unos minutos, porque construye la imagen de `web` y descarga
   PostgreSQL. Está listo cuando `docker compose ps` muestra los dos servicios como
   `(healthy)`.

3. Crea un usuario administrador para entrar al admin de Django (solo la primera vez, o
   después de un `docker compose down -v`):

   ```bash
   docker compose exec web python manage.py createsuperuser
   ```

Esto levanta dos servicios:

| Servicio | Qué es | Puerto en tu equipo |
|---|---|---|
| `web` | Django con `runserver`. Aplica las migraciones al arrancar. | 8000 |
| `db` | PostgreSQL 18, con los datos en el volumen `postgres_data` | `POSTGRES_PORT` (5432 por defecto) |

### Qué puedes ver hoy

La interfaz usa el layout de SB Admin 2 (SPEC 02). Todavía no hay módulos de negocio ni
inicio de sesión propio, así que las páginas son públicas. Puedes abrir:

| URL | Qué muestra |
|---|---|
| <http://localhost:8000/> | La página "Inicio", dentro del layout: barra lateral con el menú, topbar y pie de página. |
| <http://localhost:8000/componentes/> | El catálogo de componentes compartidos (mensajes, formulario, modal de confirmación, botones y tabla con DataTables), con datos de ejemplo. **Solo existe con `DEBUG=True`**; sin DEBUG responde 404 y no aparece en el menú. |
| <http://localhost:8000/health/> | `{"status": "ok", "database": "ok"}`. Si la base de datos no responde, devuelve 503. |
| <http://localhost:8000/admin/> | El admin de Django, en español. Entra con el usuario que creaste con `createsuperuser`. Con esa sesión, el layout muestra el menú del usuario y "Cerrar sesión". |

### Si `web` se detiene

`runserver` se recarga cada vez que cambia un archivo. Si cambias de rama con git mientras
corre, puede recargarse a mitad del cambio, no encontrar un módulo y terminar con
`Exited (1)`. Vuelve a levantarlo con:

```bash
docker compose up -d
```

Para ver el motivo, revisa `docker compose logs web`.

Comandos útiles:

```bash
docker compose up -d                 # en segundo plano
docker compose ps                    # estado y healthcheck de cada servicio
docker compose logs -f web           # logs de Django
docker compose exec web python manage.py createsuperuser
docker compose down                  # detener (conserva los datos)
docker compose down -v               # detener y BORRAR la base de datos
```

## Desarrollo local con uv

Puedes ejecutar Django y las pruebas en tu equipo, usando el PostgreSQL del contenedor:

```bash
uv sync                              # instala dependencias (incluidas las de desarrollo)
docker compose up -d db              # solo la base de datos
uv run python manage.py migrate
uv run python manage.py runserver
```

### Si el puerto 5432 ya está ocupado

Si tienes otro PostgreSQL en tu equipo (por ejemplo, el servicio de Windows
`postgresql-x64-NN` u otro contenedor), Django se conectará a ese y fallará la
autenticación. Publica el contenedor en otro puerto cambiando **las dos** variables de tu
`.env`:

```dotenv
POSTGRES_PORT=5433
DATABASE_URL=postgres://loan:loan@localhost:5433/loan_service
```

Luego ejecuta `docker compose up -d db` para recrear el contenedor. Dentro de compose, el
servicio `web` siempre se conecta a `db:5432`, así que no se ve afectado.

## Variables de entorno

Se leen con django-environ. En local vienen de `.env` (nunca se versiona); en Docker y en
CI, del entorno. La referencia es [`.env.example`](.env.example).

| Variable | Uso | Obligatoria en producción |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.dev` o `config.settings.prod` | Sí |
| `SECRET_KEY` | Clave secreta de Django | Sí, sin valor por defecto |
| `DEBUG` | Solo se usa en desarrollo; en producción siempre es `False` | No |
| `ALLOWED_HOSTS` | Hosts permitidos, separados por comas | Sí, sin valor por defecto |
| `DATABASE_URL` | `postgres://usuario:clave@host:puerto/base` | Sí, sin valor por defecto |
| `SECURE_SSL_REDIRECT` | Redirigir a HTTPS en producción (por defecto `True`) | No |
| `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_PORT` | Configuran el servicio `db` de compose | No aplica |

`manage.py` usa `config.settings.dev` por defecto. `wsgi.py` y `asgi.py` usan
`config.settings.prod`: si falta alguna variable obligatoria, la aplicación no arranca.

## Pruebas y calidad

```bash
uv run pytest                                    # toda la suite (requiere el PostgreSQL de compose)
uv run pytest --cov                              # con cobertura de apps/ y config/
uv run pytest tests/core/test_health.py::test_health_ok_when_database_responds
uv run ruff check .                              # linter
uv run black .                                   # formatear (black --check . para solo verificar)
uv run python manage.py makemigrations --check --dry-run
uv run pre-commit install                        # ejecutar Ruff y Black en cada commit
uv run pre-commit run --all-files
```

El CI (GitHub Actions, `.github/workflows/ci.yml`) ejecuta Ruff, Black, la verificación de
migraciones, `manage.py check` y pytest contra PostgreSQL 18 en cada push a `main` y en
cada pull request. Un cambio que falle no se integra (constitución §15.3).

## Interfaz

Todas las pantallas heredan de `templates/base.html`, derivado de `blank.html` de SB Admin 2,
y definen los bloques `title`, `page_heading`, `content` y, si los necesitan, `extra_css` y
`extra_js`. Los recursos de la plantilla están copiados en `static/` (nunca se enlaza
`references/`), y las personalizaciones van en `static/css/app.css` y `static/js/app.js`.

Antes de construir una pantalla, revisa los componentes que ya existen en
<http://localhost:8000/componentes/> (solo con `DEBUG=True`):

- **Mensajes:** los de `django.contrib.messages` salen como alertas de Bootstrap.
- **Formularios:** `{{ form }}` ya produce las clases de Bootstrap 4 (`form-control`,
  `is-invalid`, `invalid-feedback`), gracias a `apps.core.forms.BootstrapFormRenderer` y a las
  plantillas de `templates/forms/`.
- **Tablas:** `{% include "includes/datatable.html" %}`. El comentario al principio del archivo
  explica qué recursos debe cargar la página.
- **Confirmación:** agrega `data-confirm="¿Pregunta?"` (y, si quieres,
  `data-confirm-button="Texto del botón"`) a un `<form>` para que pida confirmación antes de
  enviarse.

### Agregar un módulo al menú

El menú lateral se arma solo: cada app declara sus secciones y entradas en su propio
`menu.py`, y `apps.core` lo descubre al arrancar. No hay que editar `apps/core` ni los
settings. Por ejemplo, `apps/clientes/menu.py`:

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

- **Secciones:** `label=""` crea una sección sin encabezado. Se ordenan por `order`, y una
  sección sin entradas visibles no se muestra.
- **Entradas:** se ordenan por `order` y luego por `key`, que debe ser única. Solo las ve quien
  tiene todos los `permissions`; con `()` las ve cualquiera.
- **Submenús:** usa `children=(MenuItem(...), ...)` y deja `url_name=None` en el padre. Solo
  hay un nivel, y el padre se oculta si ningún hijo es visible.
- **Solo desarrollo:** `debug_only=True` muestra la entrada solo con DEBUG.
- **Validación:** una clave repetida, una sección que no existe, un hijo con hijos o una
  entrada sin `url_name` ni `children` lanzan `ImproperlyConfigured` al arrancar.

La entrada cuyo `url_name` coincide con la página actual se marca como activa.

## Estructura

```
config/              Settings (base, dev, prod), urls, wsgi y asgi
apps/                Apps de Django (por ahora, core: layout, menú y /health/)
tests/               Pruebas con pytest, una carpeta por app
templates/           Plantillas compartidas: base.html, includes/, forms/ y páginas de error
static/              Recursos de SB Admin 2 copiados de references/, más app.css y app.js
locale/              Catálogos de traducción (gettext)
specs/               Specs SDD (NN-slug.md)
docs/                Hoja de ruta de specs y decisiones (ADR) en docs/decisiones/
references/          Plantilla SB Admin 2, de solo lectura
```

## Flujo de trabajo SDD

Ninguna funcionalidad se implementa sin una spec aprobada (constitución §2.7 y §16):

1. `/spec <descripción>` escribe la spec en `specs/NN-slug.md`, en estado `Borrador`.
2. Una persona la revisa y la cambia a `Aprobado`.
3. `/spec-impl NN-slug` crea la rama `spec-NN-slug` e implementa paso a paso. Los commits
   los hace la persona.
4. Se verifican los criterios de aceptación con pytest (y con Playwright si hay interfaz).
   Si todo pasa, la spec cambia a `Implementado`.

La hoja de ruta tentativa está en [`docs/specs-tentativas.md`](docs/specs-tentativas.md) y
las decisiones de arquitectura en [`docs/decisiones/`](docs/decisiones/).
