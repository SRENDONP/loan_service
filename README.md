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

```bash
cp .env.example .env
docker compose up
```

Esto levanta dos servicios:

| Servicio | Qué es | Puerto en tu equipo |
|---|---|---|
| `web` | Django con `runserver`. Aplica las migraciones al arrancar. | 8000 |
| `db` | PostgreSQL 18, con los datos en el volumen `postgres_data` | `POSTGRES_PORT` (5432 por defecto) |

Comprueba que todo está bien en <http://localhost:8000/health/>. Debe responder
`{"status": "ok", "database": "ok"}`. Si la base de datos no responde, devuelve 503.

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

## Estructura

```
config/              Settings (base, dev, prod), urls, wsgi y asgi
apps/                Apps de Django (por ahora, core con /health/)
tests/               Pruebas con pytest, una carpeta por app
templates/           Plantillas compartidas
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
