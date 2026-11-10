# SPEC 01 — Fundación del proyecto

> **Estado:** Aprobado
> **Depende de:** ninguna
> **Fecha:** 2026-11-10
> **Objetivo:** Convertir el esqueleto de `django-admin startproject` en una base reproducible (configuración por entorno, PostgreSQL en Docker, calidad de código, pruebas y CI) que cumpla la constitución antes de escribir la primera funcionalidad.

---

## 1. Por qué existe esta spec

El esqueleto actual contradice la constitución en casi todo lo estructural: un único `settings.py`, SQLite, `SECRET_KEY` en el código, `DEBUG=True`, idioma `en-us` y nada de pruebas, linters, Docker ni CI (ver la tabla de diferencias de `CLAUDE.md`). Todas las specs siguientes dependen de esta base. Si se construye sobre el esqueleto, cada spec tendría que corregirlo a medias.

Esta spec también formaliza D2 (Python 3.14 y Django 6.1) con una enmienda de la §4 y registra D1 (un solo negocio) en el primer ADR.

---

## 2. Alcance

**Entra:**

- Renombrar la rama `master` a `main` antes del primer commit.
- Renombrar el paquete `loan_service/` a `config/`, con settings separados en `config/settings/base.py`, `dev.py` y `prod.py`.
- Secretos y configuración por variables de entorno con **django-environ**, y un `.env.example` versionado.
- **PostgreSQL 18** como único motor, también en las pruebas. SQLite desaparece del proyecto.
- `docker-compose.yml` con dos servicios: `web` (Django con `runserver`) y `db` (PostgreSQL 18), más un `Dockerfile` de desarrollo basado en uv.
- La base de i18n: `es-co`, `America/Bogota`, `USE_I18N`, `USE_TZ`, `LANGUAGES` y `LOCALE_PATHS`, con la carpeta `locale/` vacía.
- La carpeta `apps/` con una primera app, `apps/core`, que solo expone el endpoint `GET /health/`.
- Las pruebas en `tests/` en la raíz, organizadas por app, con pytest, pytest-django y pytest-cov.
- Ruff y Black configurados en `pyproject.toml`, y pre-commit ejecutándolos.
- CI en GitHub Actions: Ruff, Black, verificación de migraciones, `manage.py check` y pytest contra PostgreSQL 18.
- `prod.py` con un mínimo seguro: `DEBUG=False`, secretos obligatorios y cookies seguras.
- `docs/decisiones/` con una plantilla de ADR y el **ADR-001: un solo negocio preparado para crecer** (D1).
- **Enmienda de la §4** de la constitución (versión 1.3) para Python 3.14+, Django 6.1 y django-environ (D2).
- Un `README.md` en español y la actualización de `CLAUDE.md` al nuevo estado.
- Versionar `references/` (la plantilla SB Admin 2) en el repositorio.

**Fuera de alcance (para specs futuras):**

- Copiar SB Admin 2 a `static/`, `base.html`, las plantillas de error y el menú modular. Van en la **SPEC 02**.
- Cualquier modelo de negocio, autenticación, Argon2 o grupos de usuarios. Van en las **SPEC 03 y 04**.
- `LocaleMiddleware`, archivos `.po`/`.mo` y gettext en la imagen Docker. Llegan cuando haya textos de interfaz (SPEC 02 en adelante).
- El ADR de la librería de PDF. Se decide en la spec de desembolso y plan de pagos.
- El `Dockerfile` de producción, gunicorn, HSTS, CSP, respaldos y el usuario de base de datos con mínimos privilegios. Van en la spec de endurecimiento de seguridad.
- mypy, django-stubs y factory-boy. Se agregan cuando aporten (los primeros servicios y modelos).
- Las demás enmiendas de la sección 5 de `docs/specs-tentativas.md` (§19, §9.1, §10.2, §7.1, §3.2). Cada una se hace en la spec que la necesite.
- Los umbrales de cobertura por módulo (100 % en `amortizacion`, 90 % en servicios). Se imponen en las specs de esos módulos.

---

## 3. Modelo de datos

Esta spec no introduce modelos de Django ni tablas propias. Las únicas tablas son las de las apps de `django.contrib` que ya están en `INSTALLED_APPS`, creadas por `migrate` en PostgreSQL.

Las estructuras nuevas son de configuración.

### 3.1 Estructura de carpetas resultante

```
loan_service/                    # raíz del repositorio
├── .github/workflows/ci.yml
├── .env.example
├── .pre-commit-config.yaml
├── Dockerfile
├── docker-compose.yml
├── README.md
├── manage.py                    # por defecto: config.settings.dev
├── pyproject.toml
├── uv.lock
├── config/
│   ├── __init__.py
│   ├── asgi.py                  # por defecto: config.settings.prod
│   ├── wsgi.py                  # por defecto: config.settings.prod
│   ├── urls.py
│   └── settings/
│       ├── __init__.py
│       ├── base.py
│       ├── dev.py
│       └── prod.py
├── apps/
│   ├── __init__.py
│   └── core/
│       ├── __init__.py
│       ├── apps.py              # name = "apps.core"
│       ├── urls.py
│       └── views.py             # health()
├── tests/
│   ├── __init__.py
│   ├── conftest.py
│   ├── config/test_settings.py
│   └── core/test_health.py
├── locale/.gitkeep
├── templates/.gitkeep
├── docs/
│   ├── specs-tentativas.md
│   └── decisiones/
│       ├── plantilla.md
│       └── 001-un-solo-negocio.md
├── specs/
│   ├── .spec-config.yml
│   └── 01-fundacion-proyecto.md
└── references/                  # SB Admin 2, solo lectura, ahora versionada
```

### 3.2 Variables de entorno (`.env.example`)

```dotenv
DJANGO_SETTINGS_MODULE=config.settings.dev
SECRET_KEY=cambia-esto-en-tu-env-local
DEBUG=True
ALLOWED_HOSTS=localhost,127.0.0.1
DATABASE_URL=postgres://loan:loan@localhost:5432/loan_service

# Usadas por el servicio db de docker-compose
POSTGRES_DB=loan_service
POSTGRES_USER=loan
POSTGRES_PASSWORD=loan
```

Convenciones:

- `base.py` lee `.env` si existe, con `environ.Env.read_env()`. En Docker y en CI las variables llegan por el entorno.
- `DATABASE_URL` se lee con `env.db()`. Dentro de docker-compose, el servicio `web` la sobrescribe con el host `db`.
- `dev.py` tiene valores por defecto inofensivos para `SECRET_KEY` y `DEBUG`. `prod.py` no tiene valores por defecto: si falta `SECRET_KEY`, `ALLOWED_HOSTS` o `DATABASE_URL`, Django falla al arrancar con `ImproperlyConfigured`.

### 3.3 Contrato de `GET /health/`

| Situación | Código | Cuerpo JSON |
|---|---|---|
| La base de datos responde a `SELECT 1` | 200 | `{"status": "ok", "database": "ok"}` |
| La base de datos no responde | 503 | `{"status": "error", "database": "error"}` |

- Solo acepta `GET`. Cualquier otro método recibe 405.
- No requiere autenticación y no expone versiones, hosts ni mensajes de excepción.

### 3.4 Dependencias en `pyproject.toml`

- `dependencies`: `django>=6.1.3`, `django-environ`, `psycopg[binary]` (psycopg 3).
- `[dependency-groups] dev`: `pytest`, `pytest-django`, `pytest-cov`, `ruff`, `black`, `pre-commit`.
- Las versiones exactas quedan fijadas en `uv.lock`.

---

## 4. Plan de implementación

Cada paso deja el proyecto funcionando. El agente no hace commits: después de cada paso, la persona revisa el diff y hace el commit.

1. **Rama y dependencias.** Ejecutar `git branch -m master main`. Agregar a `pyproject.toml` las dependencias de la §3.4 y una descripción real del proyecto. Ejecutar `uv sync`. Verificación: `uv run python manage.py check` sigue pasando con el esqueleto actual.
2. **PostgreSQL en Docker.** Crear `docker-compose.yml` solo con el servicio `db` (`postgres:18`, volumen nombrado montado en `/var/lib/postgresql`, puerto 5432 publicado y un healthcheck con `pg_isready`) y crear `.env.example`. Verificación: `docker compose up -d db` deja el contenedor en estado `healthy`.
3. **Paquete `config/` y settings por entorno.** Renombrar `loan_service/` a `config/`. Crear `config/settings/base.py` (django-environ, `DATABASE_URL`, `TEMPLATES` apuntando a `templates/`, `LANGUAGE_CODE="es-co"`, `TIME_ZONE="America/Bogota"`, `USE_I18N`, `USE_TZ`, `LANGUAGES`, `LOCALE_PATHS`) y `dev.py`. Actualizar `manage.py`, `wsgi.py`, `asgi.py` y `ROOT_URLCONF`. Borrar `db.sqlite3` si existe. Verificación: con `.env` copiado de `.env.example`, `uv run python manage.py migrate` crea las tablas en PostgreSQL.
4. **`prod.py` con mínimo seguro.** `DEBUG=False`. `SECRET_KEY`, `ALLOWED_HOSTS` y `DATABASE_URL` obligatorios y sin valor por defecto. `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` (configurable por entorno, activo por defecto), `SECURE_PROXY_SSL_HEADER` y `SECURE_CONTENT_TYPE_NOSNIFF`. Verificación: `manage.py check --deploy --settings=config.settings.prod` con variables de prueba solo reporta advertencias de HSTS (`security.W004`).
5. **App `apps/core` y `/health/`.** Crear `apps/__init__.py` y `apps/core` con `apps.py` (`name = "apps.core"`), la vista `health` según el contrato de la §3.3 (con `require_GET`) y `urls.py`. Registrarla en `INSTALLED_APPS` y en `config/urls.py`. Verificación: `curl localhost:8000/health/` devuelve 200 con el JSON esperado, y con `db` detenido devuelve 503.
6. **pytest.** Configurar `[tool.pytest.ini_options]` en `pyproject.toml` (`DJANGO_SETTINGS_MODULE = "config.settings.dev"`, `testpaths = ["tests"]`, `--strict-markers`) y `[tool.coverage]` con `source = ["apps", "config"]`. Crear `tests/conftest.py`, `tests/core/test_health.py` (200 con base de datos, 503 simulando un fallo de conexión y 405 en `POST`) y `tests/config/test_settings.py` (idioma, zona horaria, que el motor sea PostgreSQL y que `prod` falle sin `SECRET_KEY`). Verificación: `uv run pytest --cov` pasa.
7. **Ruff, Black y pre-commit.** Configurar `[tool.ruff]` (`target-version = "py314"`, `line-length = 88`, reglas `E`, `F`, `I`, `B`, `UP`, `DJ`, con `migrations` excluidas) y `[tool.black]` en `pyproject.toml`. Crear `.pre-commit-config.yaml` con los hooks de Ruff y Black en versiones fijas. Formatear todo el código. Verificación: `uv run ruff check .`, `uv run black --check .` y `uv run pre-commit run --all-files` pasan sin cambios.
8. **Servicio `web` en Docker.** Crear el `Dockerfile` de desarrollo (`python:3.14-slim`, uv copiado de su imagen oficial, `uv sync --frozen`, usuario no root) y `.dockerignore`. Agregar a `docker-compose.yml` el servicio `web`: `depends_on` con `db` en `service_healthy`, `migrate` antes de `runserver 0.0.0.0:8000`, el código montado como volumen, el puerto 8000 publicado y un healthcheck contra `/health/`. Verificación: `docker compose up` desde cero deja los dos servicios en `healthy`.
9. **CI en GitHub Actions.** Crear `.github/workflows/ci.yml`, que se dispara con `push` a `main` y con `pull_request`. Usa un servicio `postgres:18`, Python 3.14 y uv con caché, y ejecuta `uv sync --frozen`, `ruff check .`, `black --check .`, `manage.py makemigrations --check --dry-run`, `manage.py check` y `pytest --cov`. Verificación: el YAML es válido. La ejecución real se comprueba cuando exista el remoto.
10. **ADRs.** Crear `docs/decisiones/plantilla.md` (contexto, decisión, alternativas, consecuencias y estado) y `docs/decisiones/001-un-solo-negocio.md` con D1: no se agrega `tenant` a los modelos en la v1, y los parámetros globales se guardan como un registro único en la base de datos y no como constantes, para poder convertirlos en "por negocio" más adelante.
11. **Enmienda de la §4.** En `constitution.md`, cambiar las filas de la tabla de la §4: Python 3.14+, Django 6.1, PostgreSQL 16+ (18 en Docker y CI) y django-environ como librería de variables de entorno. Agregar la fila 1.3 al registro de enmiendas, con la fecha, las secciones, el motivo (D2) y quien aprueba. Cambiar el pie a "Versión 1.3".
12. **Documentación.** Escribir `README.md` en español (requisitos, `cp .env.example .env`, `docker compose up`, el desarrollo local con uv contra el Postgres del contenedor, los comandos de pruebas y calidad, la estructura de carpetas y el flujo SDD). Actualizar `CLAUDE.md`: el estado del proyecto, los comandos reales, los comandos de Docker y la tabla de diferencias, de la que se quitan las filas resueltas. Crear `templates/.gitkeep` y `locale/.gitkeep`. Confirmar que `references/` no está en `.gitignore`.

---

## 5. Criterios de aceptación

- [ ] La rama actual se llama `main` y no existe `master`.
- [ ] El paquete `loan_service/` ya no existe. Existe `config/settings/` con `base.py`, `dev.py` y `prod.py`.
- [ ] `git grep -n "SECRET_KEY = \"django-insecure"` no devuelve resultados.
- [ ] `.env.example` está versionado y `.env` está ignorado por git.
- [ ] No existe `db.sqlite3`, y `git grep -n sqlite3 -- '*.py'` no devuelve resultados.
- [ ] Con `.env` copiado de `.env.example`, `docker compose up` desde un estado limpio (`docker compose down -v`) deja los servicios `web` y `db` en estado `healthy`.
- [ ] Con el stack levantado, `GET http://localhost:8000/health/` responde 200 con `{"status": "ok", "database": "ok"}`.
- [ ] Con el servicio `db` detenido, `GET /health/` responde 503 con `{"status": "error", "database": "error"}`.
- [ ] `POST /health/` responde 405.
- [ ] `uv run python manage.py check` pasa sin errores.
- [ ] `uv run python manage.py makemigrations --check --dry-run` informa que no hay cambios.
- [ ] `uv run pytest --cov` pasa contra PostgreSQL y reporta la cobertura de `apps` y `config`.
- [ ] Una prueba confirma que `settings.LANGUAGE_CODE == "es-co"`, `settings.TIME_ZONE == "America/Bogota"`, `USE_TZ` es verdadero y el motor de base de datos es `django.db.backends.postgresql`.
- [ ] Una prueba confirma que cargar `config.settings.prod` sin `SECRET_KEY` lanza `ImproperlyConfigured`.
- [ ] `uv run ruff check .` y `uv run black --check .` pasan sin advertencias.
- [ ] `uv run pre-commit run --all-files` pasa sin modificar archivos.
- [ ] Con `DJANGO_SETTINGS_MODULE=config.settings.prod` y variables de prueba, `manage.py check --deploy` no reporta advertencias distintas de `security.W004` (HSTS).
- [ ] Existe `.github/workflows/ci.yml` con los pasos de Ruff, Black, `makemigrations --check`, `manage.py check` y pytest, con un servicio `postgres:18`.
- [ ] Existen `docs/decisiones/plantilla.md` y `docs/decisiones/001-un-solo-negocio.md`.
- [ ] La §4 de `constitution.md` dice Python 3.14+ y Django 6.1, el registro de enmiendas tiene la fila 1.3 y el pie dice "Versión 1.3".
- [ ] `README.md` está en español y explica cómo levantar el proyecto con Docker y con uv.
- [ ] `CLAUDE.md` ya no lista como diferencias el stack, SQLite, los settings, los secretos, `apps/`/`specs/`, Docker ni el idioma.
- [ ] `git status` muestra `references/` como contenido para versionar (no ignorado).
- [ ] No hay `print()` ni `breakpoint()` en `apps/`, `config/` ni `tests/`.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** enmendar solo la §4 en esta spec. Sin ella, todo el stack contradice la constitución desde el primer día. Las demás enmiendas de la hoja tentativa se hacen en la spec que las necesita.
- **No:** una enmienda única con todos los ajustes de la sección 5 de la hoja tentativa. Mezclaría decisiones de dominio (métodos de interés, codeudor) con la fundación técnica.
- **Sí:** django-environ. Lee `DATABASE_URL` directamente y convierte tipos (`bool`, `list`).
- **No:** python-decouple. Necesita dj-database-url aparte para lo mismo.
- **Sí:** docker-compose con `web` y `db`. Cumple la §17 ("entorno reproducible con `docker-compose up`").
- **No:** Docker solo para la base de datos. No cumple la §17.
- **No:** un `Dockerfile` de producción con gunicorn ahora. Corresponde a la spec de endurecimiento.
- **Sí:** PostgreSQL 18. Es la última versión estable, en línea con D2, y cumple el mínimo 16+ de la §4.
- **Sí:** PostgreSQL también en las pruebas locales. La §4 lo declara como el único motor, y SQLite ocultaría diferencias (tipos `Decimal`, zonas horarias, bloqueos).
- **No:** SQLite para acelerar las pruebas locales.
- **Sí:** GitHub Actions como CI.
- **No:** CI solo con pre-commit en local. No cumple la §15.3.
- **Sí:** pytest-cov desde ahora, porque la §15.1 exige medir la cobertura. Los umbrales por módulo se imponen en sus specs.
- **Sí:** pre-commit con Ruff y Black, los mismos chequeos que el CI.
- **No (por ahora):** mypy y django-stubs. Son opcionales según la §4 y agregan fricción antes de que haya servicios que tipar.
- **No (por ahora):** factory-boy. No hay modelos todavía.
- **Sí:** el endpoint `/health/` en `apps/core`. Da una verificación objetiva de "la app está viva y llega a la base de datos" para pytest, para el healthcheck de Docker y para el CI. Además estrena el patrón `apps/`, que la SPEC 02 reutiliza.
- **Sí:** `/health/` público y sin autenticación. Es una excepción deliberada al "acceso autenticado obligatorio" de la §2.4. Se justifica porque no expone datos, versiones ni errores, y Docker lo necesita sin sesión.
- **No:** verificar solo con `/admin/`. No comprueba la base de datos de forma explícita.
- **Sí:** pruebas en `tests/<app>/` en la raíz, como muestra la §5.1.
- **No:** `apps/<app>/tests/`. Se aparta de la §5.1.
- **Sí:** pytest usa `config.settings.dev`. No se crea un `test.py`, porque la hoja tentativa pide solo `base`, `dev` y `prod`. Si las pruebas necesitan ajustes propios (por ejemplo, un hasher rápido), se decide en la spec que los requiera.
- **Sí:** `manage.py` usa `dev` por defecto, y `wsgi.py` y `asgi.py` usan `prod` por defecto. Un despliegue que olvide la variable falla de forma segura en lugar de arrancar con `DEBUG=True`.
- **Sí:** `prod.py` con un mínimo seguro. HSTS, CSP y el resto del endurecimiento quedan para su spec, y por eso se tolera `security.W004`.
- **Sí:** la i18n base sin catálogos. Todavía no hay textos que traducir. `LocaleMiddleware` llega con la interfaz.
- **Sí:** solo el ADR-001 (D1).
- **No:** el ADR-002 de la librería de PDF ahora. Se decide en la spec de desembolso y plan de pagos, cuando se pueda probar con un documento real. Además puede cambiar el `Dockerfile` (WeasyPrint necesita librerías del sistema).
- **Sí:** renombrar `master` a `main` antes del primer commit, porque el CI escucha `main`.
- **Sí:** versionar `references/`. El equipo y los agentes la necesitan como referencia visual obligatoria (§13.1).
- **Sí:** el ADR se nombra `NNN-slug.md` dentro de `docs/decisiones/`, con numeración de tres dígitos independiente de la de las specs.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| La imagen `postgres:18` cambió la ruta de datos (`PGDATA` vive en `/var/lib/postgresql/18/docker`). Montar el volumen en `/var/lib/postgresql/data`, como en versiones anteriores, hace que la imagen falle o pierda los datos. | El volumen se monta en `/var/lib/postgresql`. Un criterio de aceptación levanta el stack desde `down -v`. |
| La imagen `python:3.14-slim` o alguna dependencia todavía no tiene wheels para 3.14 (por ejemplo, `psycopg[binary]`). | Se verifica en el paso 1 con `uv sync`. Si falla, se usa `psycopg[c]` con `libpq-dev` en la imagen y se documenta en el README. |
| Renombrar `loan_service/` rompe referencias en `manage.py`, `wsgi.py`, `asgi.py` o en la configuración del IDE. | `git grep loan_service.settings` debe quedar vacío. `manage.py check` y pytest lo confirman. |
| El CI no se puede ejecutar porque no hay remoto en GitHub. | El criterio de aceptación exige que el workflow exista y sea válido. La primera ejecución real se verifica cuando se cree el remoto. |
| `.env` con secretos reales termina en el repositorio. | `.env` y `.env.*` ya están en `.gitignore`, con la excepción de `.env.example`. `prod.py` no tiene valores por defecto. |
| El endpoint público `/health/` se usa para enumerar información del sistema. | Responde solo `status` y `database`, sin versiones, hosts ni trazas. Lo cubre una prueba. |
| La enmienda de la §4 se hace sin la aprobación del responsable. | La fila 1.3 del registro de enmiendas queda con el campo "Aprobó" para que lo complete la persona al aprobar esta spec. |

---

## Lo que **no** entra en esta spec

- La plantilla SB Admin 2 en `static/`, `base.html`, las páginas de error y el menú (SPEC 02).
- Los modelos, la autenticación, los usuarios, los roles, Argon2 y la auditoría.
- `LocaleMiddleware` y los catálogos `.po`/`.mo`.
- El ADR de la librería de PDF.
- La imagen de producción, gunicorn, HSTS, CSP, los respaldos y los privilegios mínimos en PostgreSQL.
- mypy, django-stubs y factory-boy.
- Las enmiendas de la §19, §9.1, §10.2, §7.1 y §3.2.
- Los umbrales de cobertura por módulo.

Cada uno de estos puntos, si llega, va en su propia spec.
