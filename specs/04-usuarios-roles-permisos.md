# SPEC 04 — Usuarios, roles y permisos

> **Estado:** Aprobado
> **Depende de:** SPEC 02, SPEC 03
> **Fecha:** 2026-11-11
> **Objetivo:** Que el administrador cree, edite, desactive y desbloquee usuarios desde la aplicación, cada uno con exactamente uno de los cuatro roles de la §6.2, cuyos permisos se definen en el código y se verifican en cada vista y en cada servicio.

---

## 1. Por qué existe esta spec

Hasta la SPEC 03, los usuarios solo se crean desde el admin de Django o por consola, no hay grupos y ningún permiso está asignado. La §6.1 exige que el registro lo haga un administrador. La §6.2 define cuatro roles con grupos de Django y prohíbe que alguien cambie su propio nivel de acceso. La §6.3 pide permisos explícitos, la invalidación de sesiones y que los usuarios se desactiven en vez de borrarse.

Esta spec deja cuatro contratos que reutilizan las specs siguientes:

- **`apps/accounts/roles.py`:** el mapa único de rol a permisos. Cada spec que cree un módulo (clientes, créditos, pagos...) agrega ahí sus permisos, y `sync_roles` deja los grupos iguales al mapa.
- **La definición de "cobrador":** un usuario activo, que no es superusuario, con el rol `Cajero/Cobrador` (`User.objects.collectors()`). Créditos, pagos, cierre de caja y dashboard filtran por ella.
- **`apps/accounts/permissions.py`:** las utilidades para verificar permisos en vistas y servicios.
- **Los servicios de gestión de usuarios** en `apps/accounts/services.py`. Reciben siempre al `actor`, y la SPEC 05 (auditoría base) los audita desde ahí.

---

## 2. Alcance

**Entra:**

- **Los cuatro roles** como grupos de Django: `Administrador`, `Supervisor`, `Cajero/Cobrador` y `Consulta`. Cada usuario que no es superusuario tiene **exactamente un** rol.
- **El mapa declarativo `ROLE_PERMISSIONS`** en `apps/accounts/roles.py`. En esta spec solo el Administrador recibe permisos (los de gestión de usuarios). Los otros tres roles quedan vacíos hasta que lleguen sus módulos.
- **`sync_roles`**, en modo estricto: en los cuatro grupos deja exactamente los permisos del mapa. Se ejecuta con un receptor de `post_migrate` y con el comando `manage.py sync_roles`, y se documenta en el **ADR-002**.
- **Los datos nuevos del usuario:** teléfono, tipo y número de documento, y los campos de la desactivación (`deactivated_at`, `deactivated_by` y `deactivation_reason`).
- **Los permisos del modelo `User`:** `view_user`, `add_user` y `change_user`, más los propios `deactivate_user`, `unlock_user`, `reset_user_password` y `logout_user_sessions`. Se quita `delete_user`, porque los usuarios no se borran (§6.3).
- **Las utilidades de permisos** para vistas (mixin y decorador con 403) y para servicios (`require_perms`).
- **Los helpers de rol:** `get_role(user)`, `has_role(user, role)`, `User.objects.with_role(role)` y `User.objects.collectors()`.
- **Los servicios de gestión** con sus reglas: crear, editar (incluido el rol), desactivar con motivo, reactivar, desbloquear, restablecer la contraseña y cerrar las sesiones.
- **La contraseña temporal generada por el sistema** al crear un usuario y al restablecer su contraseña. Se muestra una sola vez y deja `must_change_password=True`.
- **Las protecciones:**
  - Nadie cambia su propio rol ni se aplica a sí mismo las acciones de desactivar, restablecer la contraseña, desbloquear o cerrar sesiones.
  - Siempre queda al menos un usuario activo con el rol Administrador que no es superusuario.
  - Los superusuarios se ven en el listado, pero nadie puede editarlos ni aplicarles acciones desde la aplicación.
  - Un administrador puede editar y desactivar a otro administrador, siempre que se cumpla la regla anterior.
- **Las pantallas del módulo de Usuarios**, solo para el Administrador: listado con DataTables, ficha, creación, edición, desactivación con motivo y la pantalla de la contraseña temporal.
- **La entrada "Usuarios"** en una sección nueva "Administración" del menú, filtrada por el permiso `accounts.view_user`.
- **El admin de Django** muestra los campos nuevos y no permite borrar usuarios. Sigue siendo solo para superusuarios.
- **La actualización de la documentación:** `CLAUDE.md`, `README.md` (cómo crear el primer Administrador) y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- La auditoría de las acciones sobre usuarios. La SPEC 05 la agrega sobre los servicios de esta spec.
- Los permisos de clientes, créditos, pagos, mora, reportes y parámetros. Cada spec los agrega a `ROLE_PERMISSIONS` cuando crea su módulo.
- La relación entre un supervisor y "sus" cobradores. Todo supervisor ve a todos los cobradores (D1).
- Pasar el tipo de documento al catálogo administrable. Lo decide la SPEC 06.
- Editar los permisos de los grupos desde una pantalla, o crear roles nuevos.
- Permisos individuales por usuario (`user_permissions`). La aplicación no los gestiona.
- El envío de la contraseña temporal por correo o SMS.
- El cierre de sesión por inactividad y la duración parametrizable de la sesión.
- La foto de perfil del usuario y el historial de cambios del usuario en pantalla.

---

## 3. Modelo de datos

### 3.1 Roles (`apps/accounts/roles.py`)

```python
class Role(models.TextChoices):
    # El valor es el nombre exacto del grupo de Django.
    ADMINISTRATOR = "Administrador", _("Administrador")
    SUPERVISOR = "Supervisor", _("Supervisor")
    COLLECTOR = "Cajero/Cobrador", _("Cajero/Cobrador")
    VIEWER = "Consulta", _("Consulta")


USER_MANAGEMENT_PERMISSIONS = frozenset({
    "accounts.view_user",
    "accounts.add_user",
    "accounts.change_user",
    "accounts.deactivate_user",
    "accounts.unlock_user",
    "accounts.reset_user_password",
    "accounts.logout_user_sessions",
})

ROLE_PERMISSIONS: dict[Role, frozenset[str]] = {
    Role.ADMINISTRATOR: USER_MANAGEMENT_PERMISSIONS,
    Role.SUPERVISOR: frozenset(),
    Role.COLLECTOR: frozenset(),
    Role.VIEWER: frozenset(),
}
```

Funciones públicas:

| Función | Qué hace |
|---|---|
| `get_role(user) -> Role \| None` | El rol del usuario según su grupo. Devuelve `None` si no tiene ninguno (por ejemplo, un superusuario). |
| `has_role(user, role) -> bool` | Indica si el usuario tiene ese rol. |
| `sync_roles(*, using: str = "default") -> None` | Crea los cuatro grupos si faltan y deja en cada uno exactamente los permisos del mapa. Un permiso del mapa que no existe en la base de datos produce `ImproperlyConfigured`. No toca otros grupos ni los `user_permissions`. Es idempotente. |

`sync_roles` se ejecuta en dos lugares:

- **El receptor de `post_migrate`**, conectado en `AccountsConfig.ready()` sin `sender` y con `dispatch_uid`. Como Django emite `post_migrate` para cada app con modelos en el orden de `INSTALLED_APPS`, el receptor solo actúa con la señal de la última de esas apps. Así corre una sola vez y ya existen todos los permisos. El detalle queda en el ADR-002.
- **El comando `uv run python manage.py sync_roles`**, para correrlo a mano.

### 3.2 Cambios en el usuario (`apps/accounts/models.py`)

```python
class DocumentType(models.TextChoices):
    CC = "CC", _("Cédula de ciudadanía")
    CE = "CE", _("Cédula de extranjería")
    PPT = "PPT", _("Permiso por protección temporal")
    PA = "PA", _("Pasaporte")
    TI = "TI", _("Tarjeta de identidad")


class User(AbstractUser):
    # ... campos de la SPEC 03 ...
    phone = models.CharField(_("teléfono celular"), max_length=10, blank=True,
                             validators=[colombian_mobile_validator])
    document_type = models.CharField(_("tipo de documento"), max_length=3,
                                     choices=DocumentType.choices, blank=True)
    document_number = models.CharField(_("número de documento"), max_length=20,
                                       blank=True, validators=[document_number_validator])
    deactivated_at = models.DateTimeField(_("desactivado el"), null=True, blank=True)
    deactivated_by = models.ForeignKey("self", verbose_name=_("desactivado por"),
                                       null=True, blank=True, on_delete=models.PROTECT,
                                       related_name="+")
    deactivation_reason = models.TextField(_("motivo de desactivación"),
                                           max_length=500, blank=True)

    class Meta:
        default_permissions = ("add", "change", "view")
        permissions = [
            ("deactivate_user", _("Puede desactivar y reactivar usuarios")),
            ("unlock_user", _("Puede desbloquear usuarios")),
            ("reset_user_password", _("Puede restablecer la contraseña de otros usuarios")),
            ("logout_user_sessions", _("Puede cerrar las sesiones de otros usuarios")),
        ]
        constraints = [
            # La de la SPEC 03 (correo único sin distinguir mayúsculas), más:
            # documento: los dos campos llenos o los dos vacíos.
            CheckConstraint(name="accounts_user_document_complete", ...),
            # (tipo, número) único cuando hay número.
            UniqueConstraint(fields=["document_type", "document_number"],
                             condition=~Q(document_number=""),
                             name="accounts_user_document_unique"),
        ]
```

Reglas de los campos:

- **`phone`:** es opcional. Si se escribe, debe ser un celular colombiano de 10 dígitos que empiece por `3` (`^3\d{9}$`).
- **`document_number`:** tiene de 3 a 20 letras o dígitos, sin espacios ni puntos, y se guarda en mayúsculas.
- **Nombres y apellidos:** son obligatorios en los formularios de la aplicación. En la base de datos siguen siendo `blank=True`, como en `AbstractUser`, para no romper `createsuperuser`.
- **`username`:** no se puede cambiar después de crear el usuario. El formulario de edición no lo incluye.
- **Los campos de la desactivación:** se llenan al desactivar y se vacían al reactivar.

Propiedad de solo lectura `status`, que devuelve `"inactive"`, `"locked"` o `"active"` en ese orden de prioridad. El listado y la ficha la muestran como "Inactivo", "Bloqueado" o "Activo".

Migración nueva: `0002_user_profile_and_permissions.py`, con los campos, las restricciones y los permisos. `delete_user` deja de crearse, aunque la fila que ya existe en `auth_permission` no se borra.

### 3.3 Manager (`apps/accounts/managers.py`)

- `with_role(role)`: usuarios del grupo de ese rol.
- `collectors()`: `with_role(Role.COLLECTOR)`, filtrado a `is_active=True` y `is_superuser=False`. Es la definición oficial de "cobrador".
- `active_administrators()`: usuarios activos con el rol Administrador que no son superusuarios. La usa la regla de que siempre quede un administrador.

### 3.4 Utilidades de permisos (`apps/accounts/permissions.py`)

| Utilidad | Uso |
|---|---|
| `require_perms(user, *perms) -> None` | En los servicios. Lanza `PermissionDenied` si al usuario le falta alguno de los permisos. |
| `PermissionRequiredMixin` | En las vistas basadas en clases. Es una subclase del mixin de Django con `raise_exception=True`, así que un usuario sin permiso recibe 403 y no una redirección al login. |
| `permission_required(*perms)` | En las vistas de función. Envuelve al decorador de Django con `raise_exception=True`. |

### 3.5 Servicios (`apps/accounts/services.py`)

Todos reciben al `actor` como primer argumento, verifican su permiso con `require_perms` y se ejecutan dentro de `transaction.atomic()`. Cuando se rompe una regla de negocio lanzan `UserRuleError`, una subclase de `ValidationError` con un mensaje para el usuario.

| Servicio | Permiso | Qué hace |
|---|---|---|
| `create_user(actor, *, data, role) -> tuple[User, str]` | `add_user` | Crea al usuario con el rol, una contraseña temporal y `must_change_password=True`. Devuelve el usuario y la contraseña en claro. |
| `update_user(actor, user, *, data, role) -> User` | `change_user` | Actualiza los datos y el rol. Ignora `username`. |
| `deactivate_user(actor, user, *, reason) -> None` | `deactivate_user` | Pide un motivo que no esté vacío. Pone `is_active=False`, llena los campos de la desactivación y cierra las sesiones del usuario. |
| `reactivate_user(actor, user) -> None` | `deactivate_user` | Pone `is_active=True`, vacía los campos de la desactivación y deja `must_change_password=True`. |
| `unlock_user(actor, user) -> None` | `unlock_user` | Llama a `clear_failed_attempts` (SPEC 03). |
| `reset_user_password(actor, user) -> str` | `reset_user_password` | Asigna una contraseña temporal nueva, deja `must_change_password=True`, desbloquea la cuenta y cierra las sesiones. Devuelve la contraseña en claro. |
| `logout_user_sessions(actor, user) -> int` | `logout_user_sessions` | Borra las sesiones abiertas del usuario y devuelve cuántas borró. |
| `generate_temporary_password() -> str` | — | Genera 12 caracteres con `secrets`: letras y dígitos sin los ambiguos (`0`, `O`, `o`, `1`, `l`, `I`), con al menos una letra y un dígito. La longitud es la mayor entre 12 y la de `policy.get_password_min_length()`. Repite el intento hasta que la contraseña pase `validate_password`. |

Reglas comunes, que verifican los servicios y no solo las vistas:

1. **El objetivo no puede ser un superusuario.** Ningún servicio actúa sobre uno, ni siquiera si el actor también lo es.
2. **Ninguna acción sobre uno mismo.** El actor no puede cambiar su propio rol ni desactivarse, reactivarse, desbloquearse, restablecer su propia contraseña o cerrar sus propias sesiones desde este módulo. Sí puede editar sus nombres, correo, teléfono y documento.
3. **Siempre queda un administrador.** Desactivar al último usuario de `active_administrators()`, o quitarle el rol, lanza `UserRuleError`. La cuenta se hace con `select_for_update()` sobre esos usuarios, para que dos administradores no puedan desactivarse entre sí al mismo tiempo.
4. **Sobre un usuario inactivo** solo se permiten editar sus datos y reactivarlo.
5. **El rol se asigna** vaciando los grupos del usuario y agregando el del rol (`_set_role`). Así siempre queda exactamente uno.

Para cerrar las sesiones se recorren las sesiones no vencidas de `django.contrib.sessions` y se borran las que tienen `_auth_user_id` igual al del usuario. Es una búsqueda lineal, aceptable para el tamaño de un negocio.

### 3.6 Rutas (en `apps/accounts/urls.py`, `app_name = "accounts"`)

| Ruta | Nombre | Método | Permiso |
|---|---|---|---|
| `usuarios/` | `user_list` | GET | `view_user` |
| `usuarios/nuevo/` | `user_create` | GET, POST | `add_user` |
| `usuarios/<int:pk>/` | `user_detail` | GET | `view_user` |
| `usuarios/<int:pk>/editar/` | `user_update` | GET, POST | `change_user` |
| `usuarios/<int:pk>/desactivar/` | `user_deactivate` | GET, POST | `deactivate_user` |
| `usuarios/<int:pk>/reactivar/` | `user_reactivate` | POST | `deactivate_user` |
| `usuarios/<int:pk>/desbloquear/` | `user_unlock` | POST | `unlock_user` |
| `usuarios/<int:pk>/restablecer-contrasena/` | `user_reset_password` | POST | `reset_user_password` |
| `usuarios/<int:pk>/cerrar-sesiones/` | `user_logout_sessions` | POST | `logout_user_sessions` |

- Las acciones sin formulario solo aceptan POST (405 con GET) y usan `data-confirm`.
- Una acción que rompe una regla redirige a la ficha con un mensaje `danger`, sin cambiar nada.
- **La contraseña temporal no pasa por redirección.** El POST de `user_create` y el de `user_reset_password` renderizan directamente `accounts/users/temporary_password.html` con `Cache-Control: no-store`. La contraseña no se guarda en mensajes, en la sesión ni en los logs.

### 3.7 Pantallas (`templates/accounts/users/`)

| Plantilla | Referencia de SB Admin 2 | Contenido |
|---|---|---|
| `list.html` | `tables.html` | Una tabla con `includes/datatable.html` y las columnas Usuario, Nombre, Rol, Estado, Último ingreso y Acciones. El botón "Nuevo usuario" va en el encabezado. El rol y el estado se muestran con `badge`, y los superusuarios con el badge "Superusuario" y sin acciones. |
| `detail.html` | `blank.html` y `cards.html` | Una tarjeta con los datos, el rol, el estado, la fecha del último ingreso, si debe cambiar la contraseña y, si está inactivo, el motivo, la fecha y el autor de la desactivación. Los botones de acción que se muestran dependen del estado y de los permisos. |
| `form.html` | `register.html`, como modelo | Lo usan la creación y la edición, con `{{ form }}`. En la edición no aparece `username`, y el rol queda deshabilitado si el usuario se edita a sí mismo. |
| `deactivate.html` | `blank.html` | Un formulario con el motivo (obligatorio, máximo 500 caracteres) y un texto que explica que las sesiones del usuario se cierran. |
| `temporary_password.html` | `cards.html` | La contraseña en una tarjeta `border-left-warning`, en fuente monoespaciada, con el aviso de que solo se muestra esta vez y el enlace a la ficha. |

### 3.8 Menú (`apps/accounts/menu.py`)

```python
register_section(MenuSection(key="administracion", label=_("Administración"), order=900))
register(MenuItem(key="accounts.users", label=_("Usuarios"), icon="fas fa-fw fa-users-cog",
                  section="administracion", order=10, url_name="accounts:user_list",
                  permissions=("accounts.view_user",)))
```

### 3.9 Archivos nuevos y modificados

| Archivo | Cambio |
|---|---|
| `apps/accounts/models.py` | `DocumentType`, los campos nuevos, `status`, los permisos y las restricciones |
| `apps/accounts/validators.py` | `colombian_mobile_validator` y `document_number_validator` |
| `apps/accounts/managers.py` | `with_role`, `collectors` y `active_administrators` |
| `apps/accounts/roles.py` | Nuevo: `Role`, `ROLE_PERMISSIONS`, `get_role`, `has_role` y `sync_roles` |
| `apps/accounts/permissions.py` | Nuevo: `require_perms`, `PermissionRequiredMixin` y `permission_required` |
| `apps/accounts/apps.py` | Conecta el receptor de `post_migrate` |
| `apps/accounts/management/commands/sync_roles.py` | Nuevo |
| `apps/accounts/migrations/0002_user_profile_and_permissions.py` | Nueva |
| `apps/accounts/services.py` | `UserRuleError` y los servicios de la §3.5 |
| `apps/accounts/forms.py` | `UserCreateForm`, `UserUpdateForm` y `UserDeactivateForm` |
| `apps/accounts/views.py` | Las vistas de la §3.6 |
| `apps/accounts/urls.py` | Las rutas de la §3.6 |
| `apps/accounts/menu.py` | Nuevo |
| `apps/accounts/admin.py` | Los campos nuevos y `has_delete_permission = False` |
| `templates/accounts/users/*.html` | Nuevas, según la §3.7 |
| `tests/conftest.py` | `make_user(role=...)` |
| `tests/accounts/test_roles.py`, `test_permissions.py`, `test_user_services.py`, `test_user_views.py` y `test_user_menu.py` | Nuevas |
| `docs/decisiones/002-sincronizacion-de-roles.md` | ADR-002 |
| `CLAUDE.md`, `README.md` y `docs/specs-tentativas.md` | Documentación |

---

## 4. Plan de implementación

1. **Datos del usuario.** Agregar `DocumentType`, los campos nuevos, los validadores, `status`, `default_permissions`, los permisos propios y las restricciones. Generar la migración `0002`. Mostrar los campos en el admin y desactivar el borrado. Pruebas de los validadores y de las restricciones del documento. Verificación: `migrate` y `pytest` pasan.
2. **Roles y sincronización.** Crear `roles.py` con `Role`, `ROLE_PERMISSIONS`, `get_role`, `has_role` y `sync_roles`. Agregar el receptor de `post_migrate` y el comando `sync_roles`. Escribir el ADR-002. Pruebas: los cuatro grupos existen después de `migrate`, el Administrador tiene exactamente los siete permisos, un permiso agregado a mano a un grupo administrado desaparece al sincronizar, un grupo ajeno no se toca y un permiso inexistente en el mapa lanza `ImproperlyConfigured`.
3. **Utilidades de permisos y helpers de rol.** Crear `permissions.py`, y agregar `with_role`, `collectors` y `active_administrators` al manager. Agregar `role` a `make_user` en `tests/conftest.py`. Pruebas de `require_perms`, del mixin (403 y no redirección) y de `collectors()` (excluye inactivos, superusuarios y otros roles).
4. **Servicios de creación y edición.** `UserRuleError`, `generate_temporary_password`, `_set_role`, `create_user` y `update_user`, con las reglas 1, 2, 3 y 5 de la §3.5. Pruebas de cada regla, de la contraseña generada (longitud, caracteres y que pasa `validate_password`) y de que un actor sin permiso recibe `PermissionDenied`.
5. **Servicios de las acciones.** `deactivate_user`, `reactivate_user`, `unlock_user`, `reset_user_password` y `logout_user_sessions`, con las reglas 1 a 4. Pruebas: desactivar cierra las sesiones abiertas, reactivar vacía los campos, restablecer desbloquea y cierra las sesiones, no se puede desactivar al último administrador y ninguna acción se aplica a uno mismo ni a un superusuario.
6. **Listado, ficha y menú.** `menu.py`, las vistas `user_list` y `user_detail`, y sus plantillas. Pruebas: el Administrador ve "Usuarios" en el menú, los otros tres roles no lo ven y reciben 403 en `/usuarios/`, y un superusuario aparece en el listado sin acciones.
7. **Creación y edición.** Los formularios, las vistas `user_create` y `user_update`, `form.html` y `temporary_password.html`. Pruebas: crear muestra la contraseña una sola vez con `Cache-Control: no-store`, el usuario creado entra con ella y es llevado al cambio obligatorio, y el rol propio no se puede cambiar ni manipulando el POST.
8. **Vistas de las acciones.** `user_deactivate` con `deactivate.html`, y las vistas POST de reactivar, desbloquear, restablecer y cerrar sesiones, con `data-confirm` en la ficha. Pruebas de los 405, de los mensajes y de que una regla rota no cambia nada.
9. **Verificación en el navegador con Playwright**, a 1280 px y a 375 px: el listado contra `tables.html`, la ficha y los formularios contra `blank.html` y `register.html`, el flujo completo de crear, entrar con la contraseña temporal, desactivar y reactivar, y la consola sin errores. El resultado se anota en esta spec, como en la SPEC 03.
10. **Documentación.** Actualizar `CLAUDE.md` (roles, `ROLE_PERMISSIONS`, cómo agrega una spec sus permisos, definición de cobrador y utilidades de permisos), `README.md` (crear el superusuario, entrar y crear el primer Administrador desde `/usuarios/`) y `docs/specs-tentativas.md` (marcar la 003 como implementada como SPEC 04 y anotar que el ADR de la librería de PDF pasa a ser el ADR-003).


### 4.1 Resultado de la verificación en el navegador (paso 9)

Se recorrió con Playwright, con el stack de Docker, el 2026-11-11. Se usaron unos usuarios `demo_` creados en la base local: un Administrador, un Cajero/Cobrador bloqueado y un usuario de Consulta. El recorrido fue:

1. Entrar como Administrador y ver el listado.
2. Crear un Supervisor y leer su contraseña temporal.
3. Ver su ficha y cerrar sus sesiones con el modal de confirmación.
4. Desactivarlo con motivo y reactivarlo.
5. Revisar la edición de la propia cuenta.
6. Entrar como el usuario creado con la contraseña temporal, cambiarla y comprobar lo que ve un Supervisor.

- **Estructura:** el listado tiene la estructura de `tables.html`: un encabezado `h3`, un párrafo y la tarjeta `card shadow mb-4` con `table-bordered` y DataTables en español. La ficha y los formularios tienen la de `blank.html`, con tarjetas `card shadow mb-4` y `card-header py-3`. Los botones de acción son `btn-icon-split`, como en `buttons.html`.
- **Flujo:**
  - Crear muestra la contraseña una sola vez.
  - El usuario nuevo entra con ella y termina en `/contrasena/cambiar/`.
  - Desactivar deja la tarjeta de desactivación con la fecha, el autor y el motivo, y la única acción disponible es reactivar.
  - Reactivar devuelve el estado Activo.
  - Al editarse a sí mismo, el rol queda deshabilitado con el texto "No puedes cambiar tu propio rol.".
  - Un Supervisor no ve la sección "Administración" y recibe 403 en `/usuarios/`.
- **375 px:** el listado, la ficha, la creación, la edición y la desactivación no tienen desplazamiento horizontal. Los botones de acción bajan de línea sin salirse de la tarjeta.
- **Consola:** no hay errores ni avisos en las pantallas del módulo. El único error registrado fue el 403 de una petición hecha a propósito como Supervisor.

Ajustes hechos durante la verificación:

- **Botones de acción alineados.** El botón "Desactivar", que es un enlace, quedaba unos píxeles más arriba que los botones dentro de formularios. La tarjeta de acciones pasó a `d-flex flex-wrap`.
- **Etiquetas iguales a las de la ficha.** El formulario decía "Nombre" (el texto de Django) y la ficha "Nombres". El formulario ahora dice "Nombres" y "Apellidos".
- **Mensaje sin sesiones.** Cerrar sesiones a un usuario sin sesiones abiertas mostraba "Cerraste 0 sesiones". Ahora muestra un mensaje informativo: "… no tenía sesiones abiertas.".

Observaciones, ninguna bloqueante:

- **Controles de DataTables a 375 px.** "Mostrar N registros" y "Buscar" quedan dentro del contenedor desplazable de la tabla, así que hay que desplazar la tabla para verlos completos. La página no se desplaza. Es el comportamiento de `tables.html` en la plantilla.
- **La entrada "Usuarios" del menú no queda activa en la ficha ni en los formularios.** El menú de la SPEC 02 solo marca la ruta exacta.
- **Chrome muestra un aviso `VERBOSE`** en el cambio de contraseña de la SPEC 03, igual que se anotó en esa spec.

---

## 5. Criterios de aceptación

**Roles y permisos**

- [ ] Después de `migrate` en una base vacía existen los grupos `Administrador`, `Supervisor`, `Cajero/Cobrador` y `Consulta`.
- [ ] El grupo `Administrador` tiene exactamente los siete permisos de `USER_MANAGEMENT_PERMISSIONS`, y los otros tres grupos no tienen ninguno.
- [ ] Si se agrega a mano un permiso al grupo `Consulta`, `manage.py sync_roles` lo quita. Un grupo que no es uno de los cuatro conserva sus permisos.
- [ ] Correr `sync_roles` dos veces seguidas no cambia nada la segunda vez.
- [ ] Un permiso en `ROLE_PERMISSIONS` que no existe en la base de datos hace fallar `sync_roles` con `ImproperlyConfigured`.
- [ ] El permiso `accounts.delete_user` no está asignado a ningún grupo, y el admin de Django no muestra la opción de borrar usuarios.
- [ ] `get_role` devuelve el rol de un usuario con grupo y `None` para un superusuario sin grupo.
- [ ] `User.objects.collectors()` devuelve solo usuarios activos con el rol `Cajero/Cobrador` que no son superusuarios.
- [ ] `require_perms` lanza `PermissionDenied` si falta un permiso, y una vista con `PermissionRequiredMixin` responde 403 a un usuario autenticado sin permiso.

**Datos del usuario**

- [ ] Un teléfono `3001234567` es válido, y `300123456`, `6011234567` y `300-123-4567` son inválidos.
- [ ] Guardar un tipo de documento sin número, o un número sin tipo, falla con la restricción `accounts_user_document_complete`.
- [ ] Dos usuarios no pueden tener el mismo tipo y número de documento, pero sí el mismo número con tipos distintos.
- [ ] El formulario de la aplicación rechaza un usuario sin nombres o sin apellidos.

**Servicios y reglas**

- [ ] `create_user` deja al usuario con un solo grupo, `must_change_password=True` y una contraseña que coincide con la que devuelve.
- [ ] La contraseña temporal tiene al menos 12 caracteres, no tiene `0`, `O`, `o`, `1`, `l` ni `I`, tiene al menos una letra y un dígito, y pasa `validate_password`.
- [ ] Cambiar el rol de un usuario lo deja con exactamente un grupo.
- [ ] Ningún servicio permite a un actor cambiar su propio rol ni desactivarse, desbloquearse, restablecer su propia contraseña o cerrar sus propias sesiones, aunque se llame al servicio directamente.
- [ ] Ningún servicio actúa sobre un superusuario.
- [ ] Desactivar o quitar el rol al único Administrador activo que no es superusuario lanza `UserRuleError`, aunque exista un superusuario activo.
- [ ] Desactivar sin motivo, o con un motivo que solo tiene espacios, lanza `UserRuleError`.
- [ ] Después de desactivar a un usuario con sesión abierta, su siguiente petición lo lleva a `/ingresar/`, y el usuario tiene `deactivated_at`, `deactivated_by` y `deactivation_reason` llenos.
- [ ] Reactivar vacía los tres campos de la desactivación y deja `must_change_password=True`.
- [ ] `reset_user_password` desbloquea la cuenta, deja `must_change_password=True` y cierra todas las sesiones del usuario.
- [ ] `logout_user_sessions` cierra todas las sesiones del usuario, devuelve cuántas cerró y no toca las sesiones de otros usuarios.
- [ ] Sobre un usuario inactivo, desbloquear, restablecer la contraseña y cerrar sesiones lanzan `UserRuleError`.
- [ ] Cada servicio lanza `PermissionDenied` si el actor no tiene el permiso de la tabla de la §3.5.

**Pantallas**

- [ ] Un Administrador ve la sección "Administración" con la entrada "Usuarios" en el menú. Un Supervisor, un Cajero/Cobrador y un usuario de Consulta no la ven y reciben 403 en cada ruta de la §3.6.
- [ ] El listado muestra el rol y el estado (Activo, Inactivo o Bloqueado) de cada usuario, y los superusuarios con el badge "Superusuario" y sin botones de acción.
- [ ] Crear un usuario muestra su contraseña temporal una sola vez. La respuesta lleva `Cache-Control: no-store`, y recargar la ficha no la vuelve a mostrar.
- [ ] Un usuario creado desde la aplicación entra con su contraseña temporal y es llevado a `/contrasena/cambiar/`.
- [ ] El formulario de edición no incluye `username`, y enviar un `role` distinto al editarse a uno mismo no cambia el rol.
- [ ] Las rutas de reactivar, desbloquear, restablecer y cerrar sesiones responden 405 con GET.
- [ ] Una acción que rompe una regla redirige a la ficha con un mensaje de error y no cambia el usuario.
- [ ] Todos los textos visibles de las plantillas y de los formularios nuevos están envueltos en `{% translate %}`, `{% blocktranslate %}` o `gettext`.

**Calidad y verificación**

- [ ] `uv run pytest --cov` pasa, y `apps/accounts/services.py`, `roles.py` y `permissions.py` tienen al menos 90 % de cobertura.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] En Playwright, a 1280 px, el listado tiene la estructura de tarjeta y tabla de `tables.html` y la ficha la de `blank.html`.
- [ ] En Playwright, a 375 px, el listado, la ficha y los formularios no tienen desplazamiento horizontal.
- [ ] En Playwright, la consola no muestra errores en ninguna pantalla del módulo.
- [ ] Existe `docs/decisiones/002-sincronizacion-de-roles.md`, y `README.md` explica cómo crear el primer Administrador.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** cada usuario tiene exactamente un rol. El "nivel de acceso" de la §6.2 es ese rol, y así es simple definir quién es cobrador.
- **No:** varios roles por usuario. Suma permisos de forma difícil de razonar y complica la regla de no cambiar el propio nivel.
- **Sí:** los grupos de Django son la fuente de verdad del rol, y el servicio garantiza que haya uno solo.
- **No:** un campo `role` en el usuario sincronizado con los grupos. Serían dos fuentes de verdad para lo mismo.
- **Sí:** `is_superuser` queda solo para el soporte técnico. Los superusuarios no necesitan rol ni se gestionan desde la aplicación.
- **No:** convertir al Administrador en superusuario. Saltaría todas las verificaciones de permisos.
- **Sí:** un mapa declarativo de rol a permisos en `roles.py`, que cada spec futura amplía. Toda la matriz queda en un solo lugar y se puede probar.
- **No:** una migración de datos por spec. La matriz quedaría repartida, y una migración vieja no puede asignar permisos de modelos que todavía no existen en una base nueva.
- **No:** editar los permisos de los grupos en pantalla. La §6.2 define los roles de forma fija.
- **Sí:** `sync_roles` corre en `post_migrate`, documentado en el ADR-002. Es configuración de acceso y no una regla de negocio, y usa el mismo mecanismo con el que Django crea los permisos. Así, cada `migrate` deja los grupos correctos en local, en CI y en producción.
- **No:** solo el comando manual. Basta olvidarlo una vez para que los roles queden desactualizados.
- **Sí:** la sincronización es estricta en los cuatro grupos administrados. El código es la única fuente de verdad, y un permiso dado a mano desaparece en el siguiente `migrate`.
- **No:** una sincronización que solo agrega. Un permiso dado por error se quedaría para siempre.
- **Sí:** en esta spec solo el Administrador recibe permisos, y los otros roles quedan vacíos hasta que lleguen sus módulos. No se inventan permisos de modelos que no existen.
- **Sí:** no hay relación entre supervisor y cobradores. Hay un solo negocio (D1), y todo supervisor ve a todos los cobradores.
- **Sí:** "cobrador" es un usuario activo, que no es superusuario, con el rol `Cajero/Cobrador`.
- **Sí:** la contraseña temporal la genera el sistema y se muestra una sola vez. No hay claves débiles elegidas a mano, y funciona sin correo real.
- **No:** que el administrador escriba la contraseña. **No:** un enlace por correo, porque no sirve para cobradores sin correo y hoy el correo es simulado.
- **Sí:** la pantalla de la contraseña se renderiza desde el POST, sin redirección y con `no-store`. Así la contraseña no queda en mensajes ni en la sesión.
- **Sí:** el motivo de la desactivación se guarda en el usuario, junto con la fecha y el autor. La SPEC 05 conserva el historial completo en la auditoría.
- **No:** una tabla propia de historial de estados. Adelantaría la auditoría.
- **Sí:** desactivar también borra las sesiones en el momento. El backend ya rechaza a los inactivos en `get_user`, pero borrarlas no deja sesiones huérfanas.
- **Sí:** reactivar deja `must_change_password=True`. Quien vuelve después de una desactivación renueva su contraseña.
- **Sí:** las cuatro acciones (desactivar y reactivar, desbloquear, restablecer la contraseña y cerrar sesiones) tienen un permiso cada una. Así una spec futura puede darle, por ejemplo, el desbloqueo al Supervisor sin darle lo demás.
- **Sí:** el módulo de Usuarios es solo para el Administrador (§6.2).
- **No:** dar al Supervisor un acceso de lectura o de desbloqueo en esta spec.
- **Sí:** siempre queda un Administrador activo que no es superusuario, y la cuenta usa `select_for_update()`. Los superusuarios no cuentan, para que el negocio nunca dependa del soporte técnico.
- **Sí:** un administrador puede editar y desactivar a otro, dentro de la regla anterior.
- **Sí:** los superusuarios se ven en el listado sin acciones, para que el administrador sepa qué cuentas tienen acceso total.
- **No:** ocultarlos. **No:** que cuenten como administradores.
- **Sí:** las reglas se verifican en los servicios, no solo en las vistas (§6.3). Una prueba llama a cada servicio directamente.
- **Sí:** se agregan el teléfono y el documento con opciones fijas (`CC`, `CE`, `PPT`, `PA` y `TI`). La SPEC 06 decide si el tipo pasa al catálogo.
- **No:** esperar al catálogo para guardar el documento.
- **Sí:** las validaciones son estrictas. Se exigen nombres y apellidos, el celular debe ser colombiano de 10 dígitos y el `username` no cambia, porque es la identidad que aparecerá en la auditoría.
- **No:** un teléfono libre de 7 a 15 dígitos. **No:** un `username` editable.
- **Sí:** se quita `delete_user` con `default_permissions`, y el admin no permite borrar. Los usuarios se desactivan, nunca se eliminan (§6.3).
- **Sí:** cerrar sesiones recorre las sesiones no vencidas. Es suficiente para el tamaño de un negocio y no necesita otra tabla.
- **No:** un índice propio de sesiones por usuario. Sería sobreingeniería por ahora.
- **Sí:** el ADR de esta spec toma el número 002. El ADR de la librería de PDF que preveía la hoja tentativa pasa a ser el 003.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| El receptor de `post_migrate` corre antes de que existan los permisos de otras apps, y `sync_roles` falla con `ImproperlyConfigured`. | El receptor espera a la señal de la última app de `INSTALLED_APPS`. Una prueba corre `migrate` sobre una base vacía, y el ADR-002 lo explica. |
| Las pruebas con `transaction=True` vacían la base, y los grupos desaparecen. | `flush` vuelve a emitir `post_migrate`, así que los grupos se recrean. Una prueba transaccional lo comprueba. |
| Dos administradores se desactivan entre sí al mismo tiempo y el negocio queda sin administrador. | La regla bloquea a los administradores activos con `select_for_update()` dentro de `transaction.atomic()`. |
| La contraseña temporal queda guardada en la caché del navegador o en un mensaje. | Se renderiza desde el POST con `Cache-Control: no-store`, nunca va a `messages` ni a la sesión, y una prueba revisa la cabecera. |
| Un superusuario cambia los grupos desde el admin de Django y espera que el cambio se mantenga. | La sincronización estricta lo revierte en el siguiente `migrate`. El ADR-002 y `CLAUDE.md` dicen que los permisos se cambian en `roles.py`. |
| El superusuario rompe las reglas desde el admin de Django (por ejemplo, desactiva al último administrador). | El admin queda como herramienta técnica solo para superusuarios. `README.md` indica gestionar los usuarios desde `/usuarios/`. |
| Manipular el POST cambia el rol propio o el `username`. | El servicio ignora el `username` y rechaza el cambio del rol propio. Las pruebas envían el POST manipulado. |
| La fila de `delete_user` que ya existe en `auth_permission` confunde al revisar los permisos. | No está en ningún grupo y la sincronización estricta impide que se asigne. Se deja sin borrar para no tocar datos de Django. |

---

## Lo que **no** entra en esta spec

- La auditoría de las acciones sobre usuarios (SPEC 05).
- Los permisos de los módulos de negocio, que llegan con cada spec.
- La relación entre un supervisor y sus cobradores.
- El tipo de documento como catálogo administrable (SPEC 06).
- La edición de los permisos de los grupos en pantalla, los roles nuevos y los permisos individuales por usuario.
- El envío de la contraseña temporal por correo o SMS.
- El acceso del Supervisor al módulo de Usuarios.
- El cierre de sesión por inactividad.
- La foto de perfil y el historial de cambios del usuario en pantalla.

Cada uno de estos puntos, si llega, va en su propia spec.
