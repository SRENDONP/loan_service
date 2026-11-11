# SPEC 02 — Layout base y menú modular

> **Estado:** Implementado
> **Depende de:** SPEC 01
> **Fecha:** 2026-11-10
> **Objetivo:** Construir el layout común derivado de SB Admin 2, los componentes compartidos y un menú lateral que se arma solo con lo que cada app declara en su `menu.py`.

---

## 1. Por qué existe esta spec

Todas las pantallas del sistema van a heredar del mismo layout y a usar los mismos mensajes, tablas, formularios y confirmaciones. Si cada spec los resuelve por su cuenta, la interfaz se va a desviar de SB Admin 2 (§13) y el menú va a terminar como una lista fija que hay que editar cada vez que llega un módulo.

Esta spec deja tres contratos que las siguientes reutilizan sin tocarlos:

- **`base.html`:** el layout del que hereda cada pantalla.
- **El registro de módulos:** una app nueva aparece en el menú con solo agregar su `menu.py` (§2 de la información adicional de la constitución).
- **El context processor `branding`:** es el único punto que luego cambia la spec de parámetros para leer el nombre del negocio (ADR-001).

---

## 2. Alcance

**Entra:**

- **Recursos de la plantilla:** copiar a `static/` solo los distribuibles que se usan, en sus versiones `.min`:
  - `sb-admin-2.min.css` y `sb-admin-2.min.js`.
  - Bootstrap 4.3.1 (`bootstrap.bundle.min.js`), jQuery 3.3.1 y jQuery Easing.
  - Font Awesome Free 5.8.1 (`css/all.min.css` y `webfonts/`).
  - DataTables 1.10.19 (bs4) y Chart.js 2.8.0.
- **Estilos y scripts propios:** `static/css/app.css`, cargado después de `sb-admin-2.min.css`, y `static/js/app.js`.
- **La fuente Nunito** se sigue cargando desde Google Fonts, como en la plantilla.
- **`templates/base.html`**, derivado de `blank.html`:
  - La barra lateral, con el menú generado y el botón para colapsarla.
  - Una topbar con **solo el menú del usuario**. El menú del usuario y el modal de cierre de sesión solo se muestran si `user.is_authenticated`.
  - El pie de página y el botón para volver arriba.
  - Los bloques `title`, `page_heading`, `content`, `extra_css` y `extra_js`.
- **El context processor `apps.core.context_processors.branding`:** entrega `business_name` (provisional: "Gestión de préstamos", con gettext) y `brand_icon`.
- **El registro de módulos** en `apps/core/navigation.py`, con los dataclasses `MenuSection` y `MenuItem`:
  - Al arrancar, `apps.core` descubre los `menu.py` de cada app con `autodiscover_modules("menu")`.
  - Soporta secciones con encabezado, entradas directas y submenús de un nivel.
  - Marca como activa la entrada que corresponde a la URL actual.
  - Filtra las entradas con `user.has_perms`.
  - Algunas entradas pueden ser visibles solo con DEBUG.
- **La etiqueta de plantilla `{% sidebar_menu %}`**, en `apps/core/templatetags/navigation.py`, que pinta el menú.
- **`apps/core/menu.py`** con dos entradas: "Inicio", en la sección principal, y "Componentes", en la sección "Desarrollo" y solo con DEBUG.
- **La página "Inicio" en `/`**, basada en `blank.html`, con el título y un texto de bienvenida.
- **Las páginas de error** basadas en `404.html`:
  - `403.html`, `403_csrf.html` y `404.html` usan el layout completo.
  - `500.html` es independiente: no usa context processors ni el menú.
- **Componentes compartidos:**
  - **Mensajes:** los mensajes de Django se muestran como alertas de Bootstrap que se pueden cerrar.
  - **Tablas:** un include para tablas con DataTables (bs4), con los textos en español entregados por el servidor.
  - **Formularios:** un renderizador propio (`FORM_RENDERER`) con plantillas en `templates/forms/`, que aplica `form-group`, `form-control`, `is-invalid` e `invalid-feedback` de Bootstrap 4. *Ajuste durante la implementación (paso 8):* el renderizador es `apps.core.forms.BootstrapFormRenderer`, una subclase de `TemplatesSetting`, porque `TemplatesSetting` por sí solo no lee `templates/forms/`.
  - **Confirmación:** un modal global en `base.html`. Cualquier formulario con `data-confirm` lo abre antes de enviarse.
- **La página de componentes `/componentes/`**, que solo responde con DEBUG. Muestra cada componente con datos de ejemplo y sirve de catálogo para las specs siguientes.
- **Pruebas** con pytest del registro, del menú, de las vistas, de las páginas de error, del renderizador de formularios y de los recursos estáticos.
- **Verificación con Playwright** contra `blank.html`, `404.html` y `tables.html`, en escritorio y a 375 px, revisando la consola.

**Fuera de alcance (para specs futuras):**

- **Autenticación:** login, logout, exigir sesión en las páginas y las pantallas `login.html` y `forgot-password.html`. Van en la spec de autenticación.
- **Roles y grupos:** definirlos y asignarles permisos. Esta spec solo filtra con `has_perms`; los grupos van en la spec de usuarios, roles y permisos.
- **La búsqueda, las alertas y los mensajes de la topbar.** Se agregan en la spec que les dé un uso.
- **El dashboard con tarjetas y gráficas.** Va en su propia spec y reemplaza la página "Inicio". Chart.js se copia a `static/`, pero ninguna página lo carga todavía.
- **Leer el nombre y el logo del negocio desde los parámetros.** Va en la spec de parámetros globales, que solo cambia el context processor `branding`.
- **`LocaleMiddleware`, catálogos `.po` y otros idiomas.**
- **Servir los estáticos en producción** (`collectstatic`, WhiteNoise u otro servidor). Va en la spec de endurecimiento.
- **Descargar Nunito a `static/`.** Si se quisiera, requiere un ADR.
- **Submenús de más de un nivel.**

---

## 3. Modelo de datos

Esta spec no crea modelos ni migraciones. Las estructuras nuevas viven en memoria y se construyen al arrancar Django.

### 3.1 Registro de módulos (`apps/core/navigation.py`)

```python
@dataclass(frozen=True)
class MenuSection:
    key: str              # "principal", "desarrollo", ...
    label: str            # gettext_lazy; "" = sin encabezado
    order: int

@dataclass(frozen=True)
class MenuItem:
    key: str                              # único en todo el registro
    label: str                            # gettext_lazy
    icon: str                             # clases de Font Awesome, p. ej. "fas fa-fw fa-home"
    section: str                          # MenuSection.key
    order: int
    url_name: str | None = None           # p. ej. "core:home"; None si tiene children
    permissions: tuple[str, ...] = ()     # p. ej. ("clientes.view_cliente",); () = visible para todos
    children: tuple["MenuItem", ...] = () # un solo nivel
    debug_only: bool = False
```

API del registro. El registro es una clase, `MenuRegistry`, con una instancia global `registry`. Las funciones de módulo operan sobre esa instancia, y las pruebas crean instancias propias:

- `register_section(section)` y `register(item)`. Ambas fallan con `ImproperlyConfigured` si la clave está repetida, si la sección no existe, si un hijo tiene hijos o si una entrada no tiene `url_name` ni `children`.
- `build_menu(request) -> list[RenderedSection]` devuelve solo lo visible para `request.user`:
  - **Orden:** las secciones se ordenan por `order` y, dentro de cada una, las entradas por `order` y después por `key`.
  - **Permisos:** una entrada es visible si `user.has_perms(permissions)` es verdadero.
  - **Padres:** una entrada con hijos es visible si al menos un hijo es visible.
  - **DEBUG:** las entradas `debug_only` solo aparecen con DEBUG.
  - **Secciones vacías:** no se muestran.
  - **Entrada activa:** es la que tiene `url_name == request.resolver_match.view_name`. Si un hijo está activo, su padre también queda activo y desplegado.

`apps/core/menu.py` registra:

| Sección | `key` | `label` | `order` |
|---|---|---|---|
| Principal | `principal` | (sin encabezado) | 0 |
| Desarrollo | `desarrollo` | "Desarrollo" | 1000 |

| Entrada | `key` | `section` | `url_name` | `icon` | `debug_only` |
|---|---|---|---|---|---|
| Inicio | `core.home` | `principal` | `core:home` | `fas fa-fw fa-home` | No |
| Componentes | `core.components` | `desarrollo` | `core:components` | `fas fa-fw fa-puzzle-piece` | Sí |

Cada app nueva registra sus propias secciones (por ejemplo, "Operación" o "Configuración") en su `menu.py`.

### 3.2 Contexto de plantillas

| Variable | Origen | Valor en esta spec |
|---|---|---|
| `business_name` | `apps.core.context_processors.branding` | `gettext_lazy("Gestión de préstamos")` |
| `brand_icon` | `apps.core.context_processors.branding` | `"fas fa-hand-holding-usd"` |

### 3.3 Archivos nuevos

```
static/
├── css/sb-admin-2.min.css          # copiado de references/
├── css/app.css                     # propio, se carga después
├── js/sb-admin-2.min.js            # copiado
├── js/app.js                       # propio: modal de confirmación e inicio de DataTables
├── img/                            # copiado (undraw_posting_photo.svg)
└── vendor/
    ├── bootstrap/js/bootstrap.bundle.min.js
    ├── jquery/jquery.min.js
    ├── jquery-easing/jquery.easing.min.js
    ├── fontawesome-free/css/all.min.css
    ├── fontawesome-free/webfonts/  # solo las fuentes
    ├── fontawesome-free/LICENSE.txt
    ├── datatables/jquery.dataTables.min.js
    ├── datatables/dataTables.bootstrap4.min.js
    ├── datatables/dataTables.bootstrap4.min.css
    └── chart.js/Chart.min.js
templates/
├── base.html
├── 403.html  403_csrf.html  404.html  500.html
├── includes/sidebar.html  topbar.html  footer.html  messages.html
├── includes/logout_modal.html  confirm_modal.html  datatable.html
├── forms/                          # plantillas del FORM_RENDERER
└── core/home.html  core/components.html  core/menu.html
apps/core/
├── navigation.py  menu.py  context_processors.py  forms.py
├── templatetags/__init__.py  templatetags/navigation.py
└── apps.py (ready → autodiscover_modules("menu"))  views.py  urls.py
tests/core/
├── test_navigation.py  test_views.py  test_error_pages.py  test_forms.py  test_static.py
```

### 3.4 Cambios en la configuración (`config/settings/base.py`)

- `STATICFILES_DIRS = [BASE_DIR / "static"]`.
- `"django.forms"` en `INSTALLED_APPS`, y `FORM_RENDERER = "apps.core.forms.BootstrapFormRenderer"`. *Ajuste durante la implementación (paso 8):* la spec decía `"django.forms.renderers.TemplatesSetting"`, pero esa clase busca las plantillas de Django por su nombre (`django/forms/...`) y no las de `templates/forms/`. La subclase usa `forms/form.html` y `forms/field.html`, y cambia `django/forms/<ruta>` por `forms/<ruta>` cuando la plantilla existe.
- `"apps.core.context_processors.branding"` en `TEMPLATES[0]["OPTIONS"]["context_processors"]`.
- `MESSAGE_TAGS = {messages.ERROR: "danger"}`, para que coincidan con las clases de alerta de Bootstrap.

---

## 4. Plan de implementación

Cada paso deja el sistema funcionando. Antes de los pasos con plantillas o estilos se carga la skill `frontend-design`, y antes de los pasos con código de Django, la skill `django-patterns` (§16.5).

1. **Recursos estáticos.** Copiar a `static/` los archivos de la §3.3 desde `references/`, sin modificarlos. Crear `static/css/app.css` y `static/js/app.js` vacíos, con un comentario de cabecera. Configurar `STATICFILES_DIRS`. Verificación: `uv run python manage.py findstatic css/sb-admin-2.min.css vendor/jquery/jquery.min.js` encuentra los dos archivos.
2. **Context processor `branding`.** Crear `apps/core/context_processors.py` y registrarlo en `TEMPLATES`. Verificación: una prueba confirma que `business_name` y `brand_icon` llegan al contexto.
3. **Registro de módulos.** Crear `apps/core/navigation.py`, con `MenuSection`, `MenuItem`, `register_section`, `register` y `build_menu`, y sus validaciones. Agregar `ready()` en `CoreConfig` con `autodiscover_modules("menu")`. Crear `tests/core/test_navigation.py`, con un registro aislado por prueba, que cubra:
   - El orden de secciones y entradas.
   - El filtrado por permisos, con un usuario con permisos, uno sin permisos y el anónimo.
   - Los padres sin hijos visibles y las secciones vacías.
   - Las entradas `debug_only`.
   - La entrada activa y el padre activo.
   - Cada error de validación.

   Verificación: `uv run pytest tests/core/test_navigation.py`.
4. **`base.html` y sus includes.** Derivar `base.html` de `blank.html`, reemplazando el contenido estático por etiquetas de plantilla y conservando la estructura y las clases:
   - `includes/sidebar.html`, con la marca desde `branding`, el menú y el botón para colapsar.
   - `includes/topbar.html`, con el botón del menú en móvil y el menú del usuario si hay sesión.
   - `includes/footer.html`, con el año actual y `business_name`.
   - `includes/logout_modal.html`.

   Crear la etiqueta `{% sidebar_menu %}` y `core/menu.html`. Todos los textos van con `{% translate %}` y los recursos con `{% static %}`.
5. **Página "Inicio".** Crear la vista `home`, que solo renderiza, la ruta `/` (`core:home`) y `core/home.html`. Registrar "Inicio" en `apps/core/menu.py`. Verificación: `/` responde 200 dentro del layout, con "Inicio" activo en el menú.
6. **Páginas de error.** Crear `403.html`, `403_csrf.html` y `404.html` sobre `base.html`, a partir de la estructura de `404.html`. Crear `500.html` independiente: HTML completo con los mismos CSS, sin el menú ni variables de context processors. Crear `tests/core/test_error_pages.py`, con `DEBUG=False`:
   - Un 404 en una URL que no existe.
   - Un 403 en una vista de prueba que lanza `PermissionDenied`.
   - Un 403 por CSRF.
   - Un 500 renderizando `500.html` con un contexto vacío.

   En todos los casos se comprueban el código, el texto en español y que no se filtran detalles.
7. **Mensajes.** Crear `includes/messages.html`, con alertas de Bootstrap que se pueden cerrar, una por mensaje, con la clase según el nivel. Incluirlo en `base.html` y configurar `MESSAGE_TAGS`. Verificación: una prueba agrega un mensaje de cada nivel y comprueba `alert-success`, `alert-info`, `alert-warning` y `alert-danger`.
8. **Renderizador de formularios.** Agregar `django.forms` y `FORM_RENDERER`. Crear las plantillas de `templates/forms/` (grupo de campo, etiqueta, texto de ayuda, errores del campo, errores no ligados a un campo, y widgets de texto, select, checkbox y textarea) con las clases de Bootstrap 4. Crear `tests/core/test_forms.py` con un formulario de ejemplo (`apps/core/forms.py`, `ComponentsDemoForm`), válido e inválido: comprueba `form-control`, `is-invalid`, `invalid-feedback`, que la etiqueta apunta al `id` del campo y que los errores generales salen como alerta.
9. **Tablas con DataTables.** Crear `includes/datatable.html` (una tabla `table table-bordered` con `data-datatable` y la estructura de `tables.html`). En `app.js`, iniciar DataTables en cada `table[data-datatable]`, con los textos en español que entrega el servidor por `json_script` (`datatables-i18n`). Las páginas que usan tablas cargan los recursos de DataTables con `extra_css` y `extra_js`. El JavaScript no calcula valores, solo ordena, busca y pagina lo que ya está en la tabla.
10. **Modal de confirmación.** Crear `includes/confirm_modal.html` (un único modal en `base.html`). En `app.js`, interceptar el envío de cualquier `form[data-confirm]` y mostrar el modal con el texto de `data-confirm` y el botón de `data-confirm-button` (por defecto, "Confirmar"). Al aceptar se envía el formulario, y al cancelar no. Sin JavaScript, el formulario se envía normalmente.
11. **Página de componentes.** Crear la vista `components`, que lanza `Http404` si `DEBUG` es falso, la ruta `/componentes/` (`core:components`) y `core/components.html`, con:
    - Un mensaje de cada nivel.
    - Una tabla de ejemplo con DataTables (unas 15 filas de datos ficticios fijos, para que se vea la paginación).
    - `ComponentsDemoForm`, que al enviarse con errores se vuelve a mostrar con los errores; si es válido redirige con un mensaje de éxito.
    - Un formulario de prueba con `data-confirm`.
    - Los botones de `buttons.html` más usados.

    Registrar "Componentes" en `apps/core/menu.py` con `debug_only=True`. Crear `tests/core/test_views.py` (`/componentes/` 200 con DEBUG y 404 sin DEBUG; la entrada solo aparece en el menú con DEBUG; el POST inválido y el válido).
12. **Recursos y reglas de la plantilla.** Crear `tests/core/test_static.py`:
    - Cada archivo que `base.html` y `includes/datatable.html` cargan con `{% static %}` existe para `finders.find`.
    - Ninguna plantilla de `templates/` contiene `references/`.
    - `app.css` se carga después de `sb-admin-2.min.css`.

    Revisar que `references/` no tenga cambios (`git status references/` limpio).
13. **Verificación en el navegador.** Con el stack de Docker levantado, recorrer con el MCP de Playwright `/`, `/componentes/`, una URL inexistente y la acción que da 403:
    - Comparar cada pantalla con `blank.html`, `tables.html` y `404.html` de la referencia, en escritorio (1280 px) y en celular (375 px).
    - Probar en celular que el botón del menú abre y cierra la barra lateral.
    - Probar que el modal de confirmación cancela y acepta.
    - Probar que DataTables pagina y busca.
    - Leer la consola en busca de errores.

    Dejar las capturas en el scratchpad y anotar en la spec cualquier diferencia encontrada.
14. **Documentación.** Agregar a `README.md` y a `CLAUDE.md` cómo se agrega un módulo al menú (un `menu.py` de ejemplo) y la existencia de `/componentes/`. Actualizar en `CLAUDE.md` la tabla de pendientes (la fila de SB Admin 2 en `static/` queda resuelta).

---

## 5. Criterios de aceptación

- [x] `GET /` responde 200 y usa `base.html`. El HTML contiene `id="accordionSidebar"`, `class="navbar navbar-expand navbar-light bg-white topbar`, `class="sticky-footer` y el `business_name` "Gestión de préstamos".
- [x] En `/`, la entrada "Inicio" del menú tiene la clase `active`.
- [x] Con un usuario anónimo, la topbar no muestra `id="userDropdown"` ni el modal `id="logoutModal"`. Con un usuario autenticado, los dos aparecen.
- [x] La topbar no contiene `alertsDropdown`, `messagesDropdown` ni el formulario de búsqueda.
- [x] Una app de prueba que registra una entrada en su `menu.py` aparece en el menú sin editar `apps/core` (prueba con un registro aislado).
- [x] Una entrada con `permissions=("app.perm",)` se muestra al usuario que tiene ese permiso y se oculta al que no lo tiene y al anónimo.
- [x] Una entrada con hijos se oculta si ningún hijo es visible. Si un hijo está activo, el padre tiene `active` y su submenú tiene la clase `show`.
- [x] Una sección sin entradas visibles no muestra su encabezado.
- [x] Registrar una clave repetida, una sección inexistente, un hijo con hijos o una entrada sin `url_name` ni `children` lanza `ImproperlyConfigured`.
- [x] Con `DEBUG=True`, `/componentes/` responde 200 y la entrada "Componentes" aparece bajo el encabezado "Desarrollo". Con `DEBUG=False`, `/componentes/` responde 404 y la entrada no aparece.
- [x] Con `DEBUG=False`, una URL inexistente responde 404 con `404.html`, dentro del layout y con texto en español.
- [x] Con `DEBUG=False`, `PermissionDenied` responde 403 con `403.html`, y un POST sin token CSRF responde 403 con `403_csrf.html`.
- [x] `500.html` se renderiza con un contexto vacío sin errores y no contiene el menú lateral.
- [x] Un mensaje de cada nivel (`success`, `info`, `warning` y `error`) se muestra con `alert-success`, `alert-info`, `alert-warning` y `alert-danger`, respectivamente.
- [x] Un formulario inválido renderizado con `{{ form }}` produce `form-control is-invalid` en el campo con error, un `invalid-feedback` con el mensaje y un `<label for>` que apunta al `id` del campo.
- [x] En `/componentes/`, enviar el formulario de ejemplo con errores devuelve 200 con los errores, y enviarlo válido redirige y muestra un mensaje de éxito.
- [x] Todos los archivos que cargan `base.html` e `includes/datatable.html` existen para `django.contrib.staticfiles.finders.find`.
- [x] Ninguna plantilla de `templates/` contiene la cadena `references/`, y `git status references/` no muestra cambios.
- [x] En `base.html`, `css/app.css` se carga después de `css/sb-admin-2.min.css`.
- [x] Todos los textos visibles de las plantillas nuevas están envueltos en `{% translate %}` o `{% blocktranslate %}`.
- [x] `uv run pytest --cov`, `uv run ruff check .`, `uv run black --check .` y `uv run python manage.py check` pasan.
- [x] En Playwright, a 1280 px, `/` y `/componentes/` muestran la barra lateral, la topbar y el pie de página con la misma estructura que `blank.html`.
- [x] En Playwright, a 375 px, la página no tiene desplazamiento horizontal, y el botón `#sidebarToggleTop` colapsa y expande la barra lateral.
- [x] En Playwright, en `/componentes/`, el modal de confirmación se abre al enviar el formulario con `data-confirm`. "Cancelar" no envía el formulario y "Confirmar" sí lo envía.
- [x] En Playwright, en `/componentes/`, la tabla muestra la paginación y la búsqueda en español, y buscar un valor filtra las filas.
- [x] En Playwright, la consola del navegador no muestra errores en `/`, `/componentes/` ni en la página 404. *Verificado el 2026-11-11: sin errores en `/` y `/componentes/`. En la 404, el único mensaje es el que Chrome registra siempre por el estado 404 del propio documento; ningún recurso falla (ver §8).*
- [x] `README.md` y `CLAUDE.md` explican cómo agregar una entrada al menú con `menu.py`.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** las páginas son públicas en esta spec. El menú del usuario y el modal de cierre de sesión ya están en el layout, pero solo se muestran con sesión. La spec de autenticación conecta el login y el logout y vuelve obligatoria la sesión.
- **No:** exigir sesión ya con el login del admin de Django. Adelantaría parte de la spec de autenticación y mezclaría dos estilos de pantalla.
- **Sí:** la topbar conserva solo el menú del usuario. Así no quedan controles que no hacen nada. La búsqueda, las alertas y los mensajes se agregan en la spec que les dé un uso.
- **No:** conservar todos los elementos de la topbar como marcadores vacíos.
- **Sí:** `/` es una página "Inicio" basada en `blank.html`. El dashboard la reemplaza en su propia spec.
- **No:** el dashboard de `index.html` sin datos. Se vería roto y adelantaría una spec.
- **Sí:** el nombre del negocio sale de un context processor (`branding`) con un valor provisional. La spec de parámetros solo cambia ese context processor (ADR-001).
- **No:** escribir el nombre fijo en la plantilla.
- **Sí:** cada app declara su menú en `menu.py`, y `apps.core` lo descubre con `autodiscover_modules`, el mismo mecanismo del admin de Django. Así, agregar un módulo no toca `core`.
- **No:** una lista central en settings, porque obliga a editar los settings por cada app. **No:** un atributo en el `AppConfig`, porque mezcla la configuración de la app con la interfaz.
- **Sí:** secciones con encabezado, entradas directas y submenús de un nivel, como en SB Admin 2.
- **No:** solo entradas planas, porque se quedan cortas con Configuración y Reportes. **No:** submenús de varios niveles, porque la plantilla no los trae.
- **Sí:** el menú filtra con `user.has_perms` desde ya. La spec de roles solo asigna permisos a los grupos y el menú ya responde.
- **No:** guardar el campo `permissions` sin aplicarlo.
- **Sí:** el menú se pinta con una etiqueta de plantilla (`{% sidebar_menu %}`) y no con un context processor. Así solo se calcula en las páginas que lo usan, y `500.html` no depende de él.
- **Sí:** se copian solo los distribuibles mínimos de la plantilla (unos 3 MB) y no `vendor/` completo (unos 19 MB). Las versiones no cambian.
- **Sí:** Chart.js se copia ahora, aunque todavía no lo carga ninguna página, para que `static/` tenga desde el inicio todas las librerías de la plantilla.
- **Sí:** Nunito se sigue cargando desde Google Fonts, como en la plantilla.
- **No:** descargar Nunito a `static/`. Se aparta de la plantilla y necesitaría un ADR.
- **Sí:** se verifica con una página de componentes que solo existe con DEBUG. Es lo único que permite probar los componentes en el navegador antes de que haya pantallas reales, y sirve de catálogo.
- **No:** vistas de prueba solo en `tests/`, porque Playwright no podría verificar los componentes.
- **Sí:** los formularios se renderizan con un `FORM_RENDERER` y plantillas propias en `templates/forms/`. No se agregan librerías como django-crispy-forms (§13.1).
- **No:** un include por campo (muy repetitivo). **No:** un mixin que agrega clases a los widgets, porque los errores tendrían que pintarse a mano en cada plantilla.
- **Sí:** un modal de confirmación global que se activa con `data-confirm`. Está en `static/js/app.js`, sin librerías nuevas y sin cálculos.
- **No:** un modal por pantalla, porque duplicaría el mismo código en cada plantilla.
- **Sí:** con JavaScript desactivado, un formulario con `data-confirm` se envía sin confirmar. La protección real de las acciones sensibles (permisos y validación) vive en el servidor.
- **Sí:** los textos de DataTables los entrega el servidor por `json_script`, con gettext. El JavaScript no tiene textos fijos.
- **Sí:** los msgid se escriben en español y no se generan catálogos. Con un solo idioma, `.po` y `LocaleMiddleware` no aportan nada todavía.
- **No:** msgid en inglés con un catálogo es-co, porque obligaría a mantener el catálogo desde ya.
- **Sí:** `403.html`, `403_csrf.html` y `404.html` usan el layout completo, como `404.html` de la referencia. `500.html` es independiente, porque un error del servidor puede venir justamente del menú o de un context processor.
- **Sí:** se agrega `403_csrf.html`, aunque la hoja tentativa solo menciona 403, 404 y 500. Sin ella, un fallo de CSRF mostraría la página en inglés de Django.
- **Sí:** `MESSAGE_TAGS` convierte `error` en `danger`, para usar las clases de alerta de Bootstrap.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| `autodiscover_modules` importa `menu.py` antes de que las URLs estén listas, y `reverse` falla al arrancar. | El registro guarda `url_name` como texto y solo hace `reverse` al pintar el menú. Una prueba recorre todas las entradas registradas y comprueba que cada `url_name` se puede resolver. |
| El registro es global, así que las pruebas que registran entradas se contaminan entre sí. | `navigation.py` expone un registro como objeto (`MenuRegistry`), y las pruebas usan una instancia aislada mediante una fixture. |
| `500.html` falla al renderizarse y Django muestra una página en blanco. | `500.html` no usa context processors, ni el menú, ni variables. Solo usa `{% load static i18n %}`. Una prueba lo renderiza con un contexto vacío. |
| Font Awesome busca sus fuentes en `../webfonts/` y los iconos salen como cuadros. | Se copia `webfonts/` junto a `css/` con la misma estructura relativa. Playwright revisa que los iconos se vean y que la consola no muestre errores 404. |
| La entrada "Componentes" o su página se cuelan en producción. | La vista lanza `Http404` sin DEBUG, la entrada es `debug_only`, y lo cubren dos pruebas. |
| En Windows, los archivos copiados de `references/` cambian de fin de línea, o se edita `references/` por error. | `.gitattributes` ya fija LF y marca los binarios. El paso 12 comprueba que `git status references/` está limpio. |
| Google Fonts no carga (red lenta en campo) y cambia la tipografía. | La pila de fuentes de `sb-admin-2.min.css` tiene alternativas del sistema. Descargar Nunito queda como mejora futura, con un ADR. |

---

## 8. Verificación con Playwright (paso 13)

Se recorrió con el MCP de Playwright el 2026-11-11, con el stack de Docker (`DEBUG=True`) y un `runserver --insecure` local con `DEBUG=False` para ver las páginas de error. La referencia se sirvió en solo lectura con `python -m http.server`.

**Lo que pasó:**

- A 1280 px, `/` y `/componentes/` tienen la misma estructura que `blank.html`: la barra lateral con su degradado, la marca, los encabezados de sección, el botón para colapsar, la topbar con sombra, el encabezado `h3` y el pie de página.
- La página 404 (con `DEBUG=False`) coincide con `404.html`: el número con su efecto, el título, el texto y el enlace para volver. Está en español.
- Un `POST` sin token CSRF desde el navegador muestra `403_csrf.html` dentro del layout. Como en la aplicación todavía no hay ninguna vista que lance `PermissionDenied`, esta fue la acción que da 403. El 403 por `PermissionDenied` lo cubre pytest.
- A 375 px no hay desplazamiento horizontal en `/`, `/componentes/` ni en la 404. La tabla se desplaza dentro de su `table-responsive`, como en `tables.html`. `#sidebarToggleTop` oculta la barra lateral (ancho 0) y la vuelve a mostrar (6,5 rem).
- **Modal de confirmación:** "Cancelar" cierra el modal sin enviar el formulario (la página no se recarga). "Ejecutar" envía el formulario, que redirige con el mensaje "Acción de prueba confirmada.".
- **DataTables:** los textos están en español. Buscar "mora" deja 4 de 15 registros ("filtrados de 15 registros en total"), y "Siguiente" muestra los registros 11 a 15.

**Diferencias y hallazgos:**

| Hallazgo | Detalle | Estado |
|---|---|---|
| `favicon.ico` responde 404 | El navegador lo pide solo, y la consola registra un error en todas las páginas. La referencia tiene el mismo error, porque SB Admin 2 no trae favicon. | Resuelto: `base.html` y `500.html` declaran `<link rel="icon" href="data:,">`, una línea que no tiene la plantilla, y el navegador ya no pide el archivo. Verificado: consola sin errores en `/` y `/componentes/`. Un favicon propio puede llegar con la spec de parámetros, junto con el logo. |
| Estado de error en la consola | En la 404 y en la 403, Chrome registra el estado de la propia página como "Failed to load resource". Es propio del navegador ante cualquier respuesta 4xx, no un error de la página. | Esperado. Ningún otro error en esas páginas. |
| Marca en dos líneas | "Gestión de préstamos" ocupa dos líneas en la barra lateral, mientras que "SB Admin 2" cabe en una. Cabe en la altura de la marca y no rompe el diseño. | Aceptado como está. Se revisará cuando la spec de parámetros cambie el nombre. |
| Menú del usuario | El icono `fa-user-circle` reemplaza la foto de `source.unsplash.com`, y solo queda "Cerrar sesión" (paso 4). | Decidido en el paso 4. |
| Cierre de sesión | El modal envía un `POST` a `admin:logout` hasta la spec de autenticación (paso 4, opción 1). | Decidido en el paso 4. |

Las capturas quedaron en el scratchpad de la sesión de implementación (`playwright-spec02/`).

---

## Lo que **no** entra en esta spec

- El login, el logout, la sesión obligatoria y las pantallas de `login.html` y `forgot-password.html`.
- Los grupos y la asignación de permisos a roles.
- La búsqueda, las alertas y los mensajes de la topbar.
- El dashboard con tarjetas y gráficas, y cualquier uso de Chart.js.
- El nombre y el logo del negocio leídos desde los parámetros.
- `LocaleMiddleware`, los catálogos `.po` y otros idiomas.
- Servir los estáticos en producción.
- Nunito descargada en local.
- Los submenús de más de un nivel.

Cada uno de estos puntos, si llega, va en su propia spec.
