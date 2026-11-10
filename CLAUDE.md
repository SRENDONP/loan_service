# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado del proyecto

Sistema web para gestionar préstamos "gota a gota" (microcrédito con cuotas frecuentes, Colombia). Por ahora el repositorio es **el esqueleto recién creado con `django-admin startproject`**: solo existe el paquete de configuración `loan_service/` y una carpeta `templates/` vacía. Todavía no hay apps, modelos ni pruebas. Ya es un repositorio git, todavía sin commits.

La hoja de ruta tentativa de specs, con las decisiones de negocio ya tomadas (D1 a D16), está en `docs/specs-tentativas.md`. Léela antes de escribir una spec.

`constitution.md` es el documento rector del proyecto y prevalece sobre cualquier spec, plan o tarea. Lee la sección correspondiente antes de diseñar o implementar cualquier funcionalidad.

## Comandos

Las dependencias se gestionan con **uv** (`pyproject.toml` + `uv.lock`, entorno virtual en `.venv/`). Requiere Python >= 3.14.

```bash
uv sync                                  # instalar dependencias
uv run python manage.py runserver        # servidor de desarrollo
uv run python manage.py makemigrations   # crear migraciones
uv run python manage.py migrate
uv run python manage.py startapp <nombre>
uv run python manage.py check
```

La constitución exige pytest + pytest-django, Black y Ruff, pero aún no están instalados ni configurados. Cuando se agreguen, los comandos previstos son `uv run pytest`, `uv run pytest ruta/al/test_archivo.py::test_nombre` para una sola prueba, `uv run ruff check .` y `uv run black .`.

## Diferencias entre la constitución y el código actual

La constitución pide cosas que el esqueleto todavía no tiene. No elijas un lado en silencio: señala el conflicto cuando sea relevante.

| Constitución | Código actual |
|---|---|
| Python 3.12+, Django 5.x LTS | Python >= 3.14, Django 6.1.3 |
| Solo PostgreSQL 16+ | SQLite (`db.sqlite3`) |
| Paquete `config/` con settings separados (base/dev/prod) | un único `loan_service/settings.py` |
| Secretos por variables de entorno (django-environ / python-decouple) | `SECRET_KEY` escrito en el código, `DEBUG=True` |
| Apps dentro de `apps/`, specs dentro de `specs/` | no existe ninguna de las dos |
| Docker / docker-compose | no hay |
| Interfaz en es-CO, lista para i18n | `LANGUAGE_CODE='en-us'`, `TIME_ZONE='UTC'` |

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

## Convenciones de código

- Identificadores del código en inglés; textos de la interfaz en español (Colombia), envueltos en `gettext`.
- Anotaciones de tipo explícitas en los servicios y en el motor de amortización.
- Nunca editar migraciones ya aplicadas.
- Commits convencionales (`feat:`, `fix:`, `docs:`, `test:`).
- Nada de `print()` ni `breakpoint()` en el código que se integra.
- Nunca desactivar las protecciones de Django contra CSRF, XSS e inyección SQL.



