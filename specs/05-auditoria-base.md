# SPEC 05 — Auditoría base (registro)

> **Estado:** Implementado
> **Depende de:** SPEC 03, SPEC 04
> **Fecha:** 2026-11-11
> **Objetivo:** Que cada ingreso, cambio de contraseña y acción sobre usuarios quede en un registro de auditoría inmutable, con quién, cuándo, qué, sobre qué entidad, los valores que cambiaron y desde qué IP.

---

## 1. Por qué existe esta spec

La §14 exige un registro de auditoría inmutable para las acciones sobre datos financieros y personales. La sección 5 de la información adicional define qué se guarda (usuario, fecha y hora, acción, entidad, valores anteriores y nuevos, e IP) y que los registros no pueden editarse ni borrarse desde la aplicación. La §8.1 pide que las transiciones de estado del crédito queden auditadas.

Hasta la SPEC 04 nada de eso existe: los servicios de usuarios reciben al `actor`, pero no dejan rastro. Esta spec deja el registro temprano, antes de los módulos de negocio, para que cada spec siguiente audite desde su primer día.

Esta spec deja tres contratos que reutilizan las specs siguientes:

- **`apps/auditoria/services.py`:** la función `record(...)`, que cada servicio llama dentro de su transacción.
- **`apps/auditoria/actions.py`:** el catálogo único de acciones, cada una con su categoría. Cada spec que cree un módulo agrega ahí sus acciones, como hace con `ROLE_PERMISSIONS`.
- **El contexto de la petición** (IP, user agent, ruta, método, ID de petición y origen), que llena un middleware y que `record` toma sin que el servicio reciba el `request`.

---

## 2. Alcance

**Entra:**

- **La app `apps/auditoria`** con el modelo `AuditEvent`.
- **La inmutabilidad en dos capas:**
  - En la aplicación, el modelo y su `QuerySet` rechazan la edición y el borrado.
  - En PostgreSQL, un trigger rechaza `UPDATE` y `DELETE` sobre la tabla.
- **El catálogo de acciones** (`AuditAction`) con su categoría fija: acceso, seguridad, datos personales u operación financiera.
- **El servicio `record(...)`**, que escribe en la misma transacción de la operación. Si la escritura falla, la operación completa se revierte.
- **Las utilidades `snapshot(...)` y `diff(...)`**, que guardan solo los campos que cambiaron y ocultan los campos sensibles.
- **El contexto de la petición:** el `AuditContextMiddleware` y el administrador de contexto `audit_context(...)` para comandos de gestión.
- **La IP del cliente** desde `REMOTE_ADDR`, o desde `X-Forwarded-For` solo cuando la variable `AUDIT_TRUSTED_PROXIES` lo indica.
- **La auditoría de accesos:**
  - Ingreso exitoso, ingreso fallido (con el texto escrito), intento durante un bloqueo, bloqueo de la cuenta y cierre de sesión.
  - Cambio de contraseña (el obligatorio y el voluntario).
  - Solicitud de recuperación y restablecimiento completado.
- **La auditoría de la gestión de usuarios:** los siete servicios de la SPEC 04.
- **La auditoría del admin de Django sobre usuarios:** crear, editar y cambiar la contraseña desde el admin.
- **El admin de Django de solo lectura** para `AuditEvent`, solo para superusuarios.
- **El ADR-004**, que documenta las señales de autenticación y el trigger.
- **La actualización de la documentación:** `CLAUDE.md`, `.env.example` y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- La pantalla de consulta para administradores, con filtros por usuario, fecha y entidad (SPEC 25, la 024 de la hoja tentativa).
- La retención y la depuración por categoría (SPEC 25, D11 y P5). Esa spec abre una vía controlada para que la depuración pase el trigger.
- El permiso `auditoria.view_auditevent` en algún rol. Lo asigna la SPEC 25.
- La auditoría de clientes, créditos, pagos, parámetros y demás módulos. Cada spec agrega sus acciones y llama a `record`.
- El historial de cambios del usuario en su ficha.
- La auditoría de `sync_roles` y de los cambios de grupos o permisos hechos en el admin de Django.
- La auditoría de lecturas (quién vio qué) y de las exportaciones. Las exportaciones llegan con la spec de reportes.
- El bloqueo de `TRUNCATE` y el usuario de base de datos con mínimos privilegios (spec de endurecimiento).
- Enviar la auditoría a un sistema externo (SIEM, archivo de log centralizado).

---

## 3. Modelo de datos

### 3.1 Catálogo de acciones (`apps/auditoria/actions.py`)

```python
class AuditCategory(models.TextChoices):
    ACCESS = "access", _("Acceso")
    SECURITY = "security", _("Seguridad")
    PERSONAL_DATA = "personal_data", _("Datos personales")
    FINANCIAL = "financial", _("Operación financiera")


class AuditAction(models.TextChoices):
    # Acceso
    LOGIN_SUCCEEDED = "auth.login_succeeded", _("Ingreso exitoso")
    LOGIN_FAILED = "auth.login_failed", _("Ingreso fallido")
    LOGIN_BLOCKED = "auth.login_blocked", _("Intento durante un bloqueo")
    ACCOUNT_LOCKED = "auth.account_locked", _("Cuenta bloqueada por intentos fallidos")
    LOGOUT = "auth.logout", _("Cierre de sesión")
    PASSWORD_CHANGED = "auth.password_changed", _("Cambio de contraseña")
    PASSWORD_RESET_REQUESTED = "auth.password_reset_requested", _("Solicitud de recuperación de contraseña")
    PASSWORD_RESET_COMPLETED = "auth.password_reset_completed", _("Contraseña restablecida con el enlace")
    # Seguridad
    USER_CREATED = "users.created", _("Usuario creado")
    USER_UPDATED = "users.updated", _("Usuario editado")
    USER_DEACTIVATED = "users.deactivated", _("Usuario desactivado")
    USER_REACTIVATED = "users.reactivated", _("Usuario reactivado")
    USER_UNLOCKED = "users.unlocked", _("Usuario desbloqueado")
    USER_PASSWORD_RESET = "users.password_reset", _("Contraseña restablecida por un administrador")
    USER_SESSIONS_CLOSED = "users.sessions_closed", _("Sesiones cerradas por un administrador")


ACTION_CATEGORIES: dict[AuditAction, AuditCategory] = {
    AuditAction.LOGIN_SUCCEEDED: AuditCategory.ACCESS,
    # ... las ocho acciones de acceso con ACCESS ...
    AuditAction.USER_CREATED: AuditCategory.SECURITY,
    # ... las siete acciones de usuarios con SECURITY ...
}
```

Reglas:

- **La categoría la decide el catálogo, no quien llama.** `record` la toma de `ACTION_CATEGORIES`, así nadie etiqueta mal un registro.
- **Toda acción tiene categoría.** Una prueba verifica que cada valor de `AuditAction` está en `ACTION_CATEGORIES`.
- **`PERSONAL_DATA` y `FINANCIAL` existen desde ya,** sin acciones. Las agregan clientes, terceros, créditos y pagos.
- **El valor de la acción no cambia nunca** después de usarse, porque los registros guardados lo referencian. Renombrar solo la etiqueta sí se permite.

### 3.2 El registro (`apps/auditoria/models.py`)

```python
class AuditSource(models.TextChoices):
    WEB = "web", _("Aplicación web")
    ADMIN = "admin", _("Admin de Django")
    COMMAND = "command", _("Comando de gestión")
    SYSTEM = "system", _("Sistema")


class AuditEvent(models.Model):
    occurred_at = models.DateTimeField(_("fecha y hora"), default=timezone.now, db_index=True)
    category = models.CharField(_("categoría"), max_length=20, choices=AuditCategory.choices, db_index=True)
    action = models.CharField(_("acción"), max_length=64, choices=AuditAction.choices, db_index=True)
    source = models.CharField(_("origen"), max_length=10, choices=AuditSource.choices)

    # Quién
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name=_("usuario"),
                              null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    actor_username = models.CharField(_("nombre de usuario"), max_length=150, blank=True)
    identifier = models.CharField(_("identificador escrito"), max_length=150, blank=True)

    # Sobre qué
    content_type = models.ForeignKey(ContentType, verbose_name=_("tipo de entidad"),
                                     null=True, blank=True, on_delete=models.PROTECT, related_name="+")
    object_id = models.CharField(_("id de la entidad"), max_length=64, blank=True)
    object_repr = models.CharField(_("entidad"), max_length=200, blank=True)

    # Qué cambió
    changes = models.JSONField(_("cambios"), default=dict, blank=True, encoder=DjangoJSONEncoder)
    extra = models.JSONField(_("contexto adicional"), default=dict, blank=True, encoder=DjangoJSONEncoder)

    # Desde dónde
    ip_address = models.GenericIPAddressField(_("dirección IP"), null=True, blank=True)
    user_agent = models.CharField(_("navegador"), max_length=255, blank=True)
    request_method = models.CharField(_("método HTTP"), max_length=10, blank=True)
    request_path = models.CharField(_("ruta"), max_length=255, blank=True)
    request_id = models.UUIDField(_("id de la petición"), null=True, blank=True, db_index=True)

    objects = AuditEventQuerySet.as_manager()

    class Meta:
        verbose_name = _("registro de auditoría")
        verbose_name_plural = _("registros de auditoría")
        ordering = ["-occurred_at", "-id"]
        default_permissions = ("view",)
        indexes = [
            models.Index(fields=["content_type", "object_id"], name="auditoria_entity_idx"),
            models.Index(fields=["actor", "occurred_at"], name="auditoria_actor_idx"),
        ]
```

Reglas de los campos:

- **`id`** es el `BigAutoField` del proyecto. Sirve como orden de desempate y nunca se reutiliza.
- **`actor`** es el usuario que hizo la acción. Es `None` en el ingreso fallido, en la solicitud de recuperación y en los procesos sin usuario. `PROTECT` es coherente con que los usuarios nunca se borran.
- **`actor_username`** copia el `username` del actor al momento del registro. Así el registro se lee sin unir tablas.
- **`identifier`** guarda el texto que la persona escribió en el ingreso fallido (usuario o correo) o en la solicitud de recuperación (correo). Se recorta a 150 caracteres. Se llena aunque ese usuario no exista.
- **`content_type`, `object_id` y `object_repr`** identifican la entidad afectada. `object_repr` es `str(target)` recortado a 200 caracteres en el momento del registro. En los accesos, la entidad es el usuario que ingresó o intentó ingresar, si existe.
- **`changes`** guarda solo los campos que cambiaron, como `{"campo": [antes, después]}`. Al crear, `antes` es `null`.
- **`extra`** guarda contexto que no es un cambio de campo: el motivo de la desactivación, si el cambio de contraseña era obligatorio, cuántas sesiones se cerraron.
- **`user_agent`** se recorta a 255 caracteres, y **`request_path`** también. La ruta no guarda la cadena de consulta, para no dejar tokens en el registro.
- **`request_id`** es un UUID por petición. Agrupa los registros que genera una misma acción.

Valores en `changes` y `extra`:

- Fechas y fechas con hora en ISO 8601, `Decimal` como texto y claves foráneas como su `pk`. Lo resuelve `DjangoJSONEncoder` más la conversión de `snapshot`.
- El rol aparece como el campo `role` con el valor de `Role` (por ejemplo, `"Supervisor"`).
- Los campos sensibles nunca guardan su valor. Si cambiaron, quedan como `{"password": ["[oculto]", "[oculto]"]}`. La lista está en `SENSITIVE_FIELDS = frozenset({"password"})`, y cada spec la amplía si trae otro campo secreto.

### 3.3 Inmutabilidad

**En la aplicación:**

| Operación | Resultado |
|---|---|
| `AuditEvent(...).save()` sobre un registro nuevo | Se permite. Es la única forma de escribir. |
| `save()` sobre un registro que ya existe | Lanza `ImmutableAuditEventError`. |
| `instance.delete()` | Lanza `ImmutableAuditEventError`. |
| `AuditEvent.objects.filter(...).update(...)` | Lanza `ImmutableAuditEventError` (`AuditEventQuerySet.update`). |
| `AuditEvent.objects.filter(...).delete()` | Lanza `ImmutableAuditEventError` (`AuditEventQuerySet.delete`). |
| `bulk_update` | Lanza `ImmutableAuditEventError`. |

`ImmutableAuditEventError` es una subclase de `PermissionDenied`, definida en `apps/auditoria/exceptions.py`.

**En PostgreSQL** (migración `0002_immutable_trigger.py`, con `RunSQL` y su reversa):

- La función `auditoria_auditevent_block_changes()` lanza una excepción con el mensaje `"auditoria_auditevent es inmutable"`.
- El trigger `auditoria_auditevent_immutable` la ejecuta `BEFORE UPDATE OR DELETE ... FOR EACH ROW`.
- El trigger no cubre `TRUNCATE`. `flush`, que usan las pruebas transaccionales, vacía las tablas con `TRUNCATE`. El permiso de `TRUNCATE` se le quita al usuario de la aplicación en la spec de endurecimiento.

### 3.4 Contexto de la petición (`apps/auditoria/context.py`)

```python
@dataclass(frozen=True)
class AuditContext:
    source: AuditSource = AuditSource.SYSTEM
    ip_address: str | None = None
    user_agent: str = ""
    request_method: str = ""
    request_path: str = ""
    request_id: uuid.UUID | None = None
```

| Utilidad | Qué hace |
|---|---|
| `get_context() -> AuditContext` | Devuelve el contexto actual. Sin petición ni `audit_context`, devuelve el contexto por defecto: origen `system` y sin IP. |
| `audit_context(**fields)` | Administrador de contexto que fija el contexto dentro de un bloque. Los comandos de gestión lo usan con `source=AuditSource.COMMAND`. |
| `context_from_request(request) -> AuditContext` | Arma el contexto de una petición: IP, user agent, método, ruta sin cadena de consulta y un `uuid4` nuevo. El origen es `admin` si la ruta empieza por la del admin de Django (`reverse("admin:index")`) y `web` en otro caso. |
| `get_client_ip(request) -> str \| None` | Ver la §3.5. |

El estado vive en un `contextvars.ContextVar`, así que no se cruza entre hilos ni entre peticiones.

**`AuditContextMiddleware`** (`apps/auditoria/middleware.py`) fija el contexto al empezar cada petición y lo restablece al terminar, aunque la vista lance una excepción. Va en `MIDDLEWARE` justo después de `AuthenticationMiddleware`.

### 3.5 IP del cliente

- **La variable de entorno `AUDIT_TRUSTED_PROXIES`** es un entero, por defecto `0`. Se lee en `config/settings/base.py` y se documenta en `.env.example`.
- **Con `0`**, la IP es `REMOTE_ADDR`. Se ignora `X-Forwarded-For`, para que un cliente no pueda falsificar su IP.
- **Con `N > 0`**, se separa `X-Forwarded-For` por comas y se toma la entrada número `N` contando desde la derecha. Si la cabecera tiene menos de `N` entradas, se usa `REMOTE_ADDR`.
- **Un valor que no es una IP válida** (se verifica con `ipaddress.ip_address`) se guarda como `None`.

### 3.6 Servicio (`apps/auditoria/services.py`)

```python
def record(
    action: AuditAction,
    *,
    actor: User | None = None,
    target: models.Model | None = None,
    changes: Mapping[str, Sequence[Any]] | None = None,
    extra: Mapping[str, Any] | None = None,
    identifier: str = "",
) -> AuditEvent: ...

def snapshot(instance: models.Model, fields: Iterable[str]) -> dict[str, Any]: ...

def diff(before: Mapping[str, Any], after: Mapping[str, Any]) -> dict[str, list[Any]]: ...
```

| Función | Qué hace |
|---|---|
| `record` | Crea un `AuditEvent` con la categoría de `ACTION_CATEGORIES`, el contexto de `get_context()`, el `actor` y su `username`, la entidad de `target` y los cambios. Lanza `ValueError` si la acción no está en el catálogo. No abre su propia transacción: escribe en la transacción de quien llama. |
| `snapshot` | Devuelve `{campo: valor}` de los campos pedidos, convertidos a valores serializables. Una clave foránea se guarda como su `pk`. |
| `diff` | Compara dos snapshots y devuelve `{campo: [antes, después]}` solo con lo que cambió. Los campos de `SENSITIVE_FIELDS` quedan como `"[oculto]"`. Si no cambió nada, devuelve `{}`. |

Reglas:

- **Quien llama decide el actor.** `record` no lo saca del contexto ni de `request.user`. Los servicios ya reciben al `actor`.
- **Un fallo de `record` revierte la operación.** Como escribe dentro de la transacción del servicio, una excepción deshace también el cambio. No se atrapan excepciones en `record`.
- **Una edición sin cambios no genera registro.** `update_user` solo llama a `record` si `diff` no está vacío.

### 3.7 Qué se audita y desde dónde

**Accesos (categoría `access`):**

| Acción | Dónde se registra | Actor | Entidad | `identifier` | `changes` / `extra` |
|---|---|---|---|---|---|
| `auth.login_succeeded` | Receptor de `user_logged_in` | El usuario | El usuario | — | — |
| `auth.login_failed` | Receptor de `user_login_failed` | `None` | El usuario, si el texto corresponde a uno | El texto escrito | — |
| `auth.login_blocked` | `authenticate_with_lockout`, cuando la cuenta ya está bloqueada | `None` | El usuario | El texto escrito | `extra`: `locked_until` |
| `auth.account_locked` | `register_failed_attempt`, cuando el intento bloquea la cuenta | `None` | El usuario | — | `extra`: `locked_until` y `attempts` |
| `auth.logout` | Receptor de `user_logged_out` | El usuario | El usuario | — | — |
| `auth.password_changed` | `PasswordChangeView.form_valid` | El usuario | El usuario | — | `changes`: `password` oculto; `extra`: `forced` |
| `auth.password_reset_requested` | La vista de recuperación, al enviar el formulario | `None` | El usuario, si el correo corresponde a uno | El correo escrito | — |
| `auth.password_reset_completed` | `PasswordResetConfirmView.form_valid` | El usuario | El usuario | — | `changes`: `password` oculto |

- Las tres señales de autenticación de Django (`user_logged_in`, `user_logged_out` y `user_login_failed`) se conectan en `AuditoriaConfig.ready()` con `dispatch_uid`, en `apps/auditoria/receivers.py`. Los receptores solo llaman a `record`. La decisión queda en el ADR-004.
- `user_login_failed` entrega las credenciales con la contraseña ya enmascarada por Django. El receptor solo toma `username`.
- Durante un bloqueo, `authenticate_with_lockout` no llama a `authenticate()`, así que `user_login_failed` no se emite. Por eso ese caso se registra explícitamente como `auth.login_blocked`.
- Un `user_logged_out` sin usuario (cerrar sesión sin tener sesión) no genera registro.
- La pantalla de recuperación sigue respondiendo lo mismo exista o no el correo. El registro no cambia lo que ve la persona.

**Gestión de usuarios (categoría `security`):**

| Acción | Servicio | `changes` / `extra` |
|---|---|---|
| `users.created` | `create_user` | `changes`: los campos del perfil y el `role`, con `antes` en `null`. La contraseña no aparece. |
| `users.updated` | `update_user` | `changes`: solo los campos que cambiaron, incluido `role`. Sin registro si nada cambió. |
| `users.deactivated` | `deactivate_user` | `changes`: `is_active`; `extra`: `reason` y `sessions_closed` |
| `users.reactivated` | `reactivate_user` | `changes`: `is_active` y `must_change_password` |
| `users.unlocked` | `unlock_user` | `changes`: `failed_login_attempts` y `locked_until` |
| `users.password_reset` | `reset_user_password` | `changes`: `password` oculto y `must_change_password`; `extra`: `sessions_closed` |
| `users.sessions_closed` | `logout_user_sessions` | `extra`: `count` |

En todas, el actor es el `actor` del servicio y la entidad es el usuario afectado. Los campos auditables del usuario son `first_name`, `last_name`, `email`, `phone`, `document_type`, `document_number`, `is_active`, `must_change_password`, `failed_login_attempts`, `locked_until`, `role` y `password` (oculto). `last_login` no se audita como cambio: el ingreso ya tiene su propio registro.

**Admin de Django (origen `admin`):**

- `UserAdmin.save_model` toma un `snapshot` antes de guardar y registra `users.created` o `users.updated` con el `diff`. El actor es `request.user`.
- El rol se deduce de los grupos, así que el cambio de grupos en el admin aparece como `role` en `changes`. Se compara después de `save_related`, en `UserAdmin.save_related`.
- El cambio de contraseña del admin (`user_change_password`) registra `users.password_reset` con `password` oculto.
- Esas escrituras corren dentro de la transacción del admin de Django, así que un fallo de `record` también revierte el cambio.

### 3.8 Admin de la auditoría (`apps/auditoria/admin.py`)

- `AuditEventAdmin` registrado en el sitio de admin del proyecto, que ya es solo para superusuarios (SPEC 03).
- `list_display`: fecha y hora, categoría, acción, usuario, entidad, IP y origen.
- `list_filter`: categoría, acción, origen y fecha.
- `search_fields`: `actor_username`, `identifier`, `object_repr`, `ip_address` y `request_id`.
- Todos los campos son de solo lectura. `changes` y `extra` se muestran como JSON con sangría.
- `has_add_permission`, `has_change_permission` y `has_delete_permission` devuelven `False`. Se quita la acción "Eliminar seleccionados".
- `date_hierarchy = "occurred_at"` y `list_select_related = ("actor", "content_type")`.

### 3.9 Archivos nuevos y modificados

**Nuevos:**

- `apps/auditoria/__init__.py`, `apps.py` (`AuditoriaConfig`, conecta los receptores), `actions.py`, `models.py`, `exceptions.py`, `context.py`, `middleware.py`, `services.py`, `receivers.py` y `admin.py`.
- `apps/auditoria/migrations/0001_initial.py` y `0002_immutable_trigger.py`.
- `tests/auditoria/__init__.py`, `test_actions.py`, `test_models.py`, `test_trigger.py`, `test_context.py`, `test_middleware.py`, `test_services.py`, `test_receivers.py` y `test_admin.py`.
- `tests/accounts/test_audit.py`, con la auditoría de los servicios, las vistas de contraseña y el admin de usuarios.
- `docs/decisiones/004-auditoria-senales-y-trigger.md`.

**Modificados:**

- `config/settings/base.py`: `"apps.auditoria"` en `INSTALLED_APPS` (después de `apps.accounts`), el middleware y `AUDIT_TRUSTED_PROXIES`.
- `.env.example`: `AUDIT_TRUSTED_PROXIES=0` con su comentario.
- `apps/accounts/services.py`: `record` en los siete servicios de gestión, en `register_failed_attempt` y en `authenticate_with_lockout`.
- `apps/accounts/views.py`: `record` en `PasswordChangeView`, `PasswordResetConfirmView` y una subclase nueva `PasswordResetView`.
- `apps/accounts/urls.py`: la ruta `password_reset` usa la nueva `PasswordResetView` en lugar de la de Django.
- `apps/accounts/admin.py`: `save_model`, `save_related` y `user_change_password` del `UserAdmin`.
- `CLAUDE.md`, `docs/specs-tentativas.md`.

---

## 4. Plan de implementación

1. **App y modelo.** Crear `apps/auditoria`, registrarla en `INSTALLED_APPS`, escribir `actions.py`, `models.py` y `exceptions.py` con la inmutabilidad en la aplicación, y generar `0001_initial.py`. Pruebas de `test_actions.py` y `test_models.py`. Verificar que `migrate` sobre una base vacía sigue corriendo `sync_roles` (ahora la última app con modelos es `auditoria`).
2. **Trigger.** Escribir `0002_immutable_trigger.py` con `RunSQL` y su reversa. Prueba de `test_trigger.py`: un `UPDATE` y un `DELETE` por SQL directo fallan, y la migración se puede revertir.
3. **Contexto y middleware.** Escribir `context.py`, `middleware.py` y `AUDIT_TRUSTED_PROXIES` en los settings y en `.env.example`. Pruebas de `test_context.py` y `test_middleware.py`, incluida la cabecera `X-Forwarded-For` falsificada con `AUDIT_TRUSTED_PROXIES=0`.
4. **Servicio.** Escribir `services.py` con `record`, `snapshot` y `diff`. Pruebas de `test_services.py`: categoría tomada del catálogo, acción desconocida, campos ocultos, `diff` vacío y contexto por defecto.
5. **Admin de la auditoría.** Escribir `admin.py` de solo lectura. Pruebas de `test_admin.py`.
6. **Accesos por señales.** Escribir `receivers.py` y conectarlo en `AuditoriaConfig.ready()`. Pruebas de `test_receivers.py` con el login y el logout reales del cliente de pruebas.
7. **Bloqueo.** Agregar `record` en `register_failed_attempt` y en `authenticate_with_lockout`. Pruebas en `tests/accounts/test_audit.py`.
8. **Contraseñas.** Agregar `record` en `PasswordChangeView`, `PasswordResetConfirmView` y la nueva `PasswordResetView`, y cambiar `urls.py`. Pruebas en `tests/accounts/test_audit.py`.
9. **Gestión de usuarios.** Agregar `snapshot`, `diff` y `record` en los siete servicios de la SPEC 04. Pruebas en `tests/accounts/test_audit.py`, incluida la reversión cuando `record` falla.
10. **Admin de usuarios.** Agregar la auditoría en `UserAdmin`. Pruebas en `tests/accounts/test_audit.py`.
11. **Documentación.** Escribir el ADR-004 y actualizar `CLAUDE.md` (sección "Auditoría (SPEC 05)" y estado del proyecto) y `docs/specs-tentativas.md` (la 004 implementada como SPEC 05, con las decisiones que afectan a las specs siguientes).

---

## 5. Criterios de aceptación

**Modelo e inmutabilidad**

- [ ] Existe la tabla `auditoria_auditevent` con los campos de la §3.2 y los índices `auditoria_entity_idx` y `auditoria_actor_idx`.
- [ ] Cada valor de `AuditAction` tiene una categoría en `ACTION_CATEGORIES`.
- [ ] Guardar de nuevo un `AuditEvent` existente, borrarlo, y llamar a `update()`, `delete()` o `bulk_update()` sobre su `QuerySet` lanzan `ImmutableAuditEventError`, y el registro no cambia.
- [ ] Un `UPDATE` y un `DELETE` ejecutados por SQL directo sobre `auditoria_auditevent` fallan con el mensaje `auditoria_auditevent es inmutable`.
- [ ] `migrate auditoria 0001` revierte el trigger sin errores, y volver a `migrate` lo crea de nuevo.
- [ ] `auditoria.view_auditevent` existe, y la tabla no tiene permisos `add`, `change` ni `delete`.
- [ ] Ningún grupo de `ROLE_PERMISSIONS` tiene permisos de `auditoria`.
- [ ] `migrate` sobre una base vacía deja los cuatro grupos con sus permisos, igual que antes de esta spec.

**Servicio y contexto**

- [ ] `record` guarda la categoría del catálogo, el `actor_username`, la entidad con `content_type`, `object_id` y `object_repr`, y el contexto de la petición.
- [ ] `record` con una acción que no está en el catálogo lanza `ValueError`.
- [ ] Fuera de una petición y sin `audit_context`, el registro tiene origen `system`, IP `None` y `request_id` `None`.
- [ ] Dentro de `audit_context(source=AuditSource.COMMAND)`, el registro tiene origen `command`.
- [ ] `diff` devuelve solo los campos que cambiaron, y `password` queda como `["[oculto]", "[oculto]"]`. Ningún registro contiene un hash de contraseña ni una contraseña temporal.
- [ ] Los registros creados en una misma petición comparten `request_id`, y dos peticiones distintas tienen `request_id` distintos.
- [ ] `request_path` no incluye la cadena de consulta.
- [ ] Una petición a una ruta del admin de Django deja registros con origen `admin`, y una a `/usuarios/` con origen `web`.

**IP**

- [ ] Con `AUDIT_TRUSTED_PROXIES=0`, una petición con `X-Forwarded-For: 1.2.3.4` y `REMOTE_ADDR` `10.0.0.1` guarda `10.0.0.1`.
- [ ] Con `AUDIT_TRUSTED_PROXIES=1`, la misma petición guarda `1.2.3.4`.
- [ ] Con `AUDIT_TRUSTED_PROXIES=2` y una cabecera de una sola entrada, se guarda `REMOTE_ADDR`.
- [ ] Una IP inválida en la cabecera se guarda como `None` y la petición no falla.

**Accesos**

- [ ] Un ingreso correcto crea `auth.login_succeeded` con el usuario como actor y como entidad, y con su IP.
- [ ] Un ingreso con contraseña incorrecta crea `auth.login_failed` con actor `None`, el texto escrito en `identifier` y el usuario como entidad.
- [ ] Un ingreso con un usuario que no existe crea `auth.login_failed` sin entidad y con el texto escrito, recortado a 150 caracteres.
- [ ] El intento que alcanza el máximo de fallos crea `auth.login_failed` y `auth.account_locked`, este último con `locked_until` y `attempts` en `extra`.
- [ ] Un intento durante el bloqueo, con la contraseña correcta o incorrecta, crea `auth.login_blocked` y no crea `auth.login_succeeded`.
- [ ] Cerrar sesión crea `auth.logout` con el usuario como actor.
- [ ] El cambio obligatorio de contraseña crea `auth.password_changed` con `extra.forced` en `true`, y el voluntario con `false`.
- [ ] Enviar el formulario de recuperación crea `auth.password_reset_requested` con el correo escrito, exista o no. La respuesta es la misma en los dos casos.
- [ ] Restablecer la contraseña con el enlace crea `auth.password_reset_completed` con el usuario como actor.

**Gestión de usuarios**

- [ ] Cada uno de los siete servicios de la SPEC 04 crea su registro de la §3.7, con el `actor` del servicio como actor, el usuario afectado como entidad y categoría `security`.
- [ ] `users.created` incluye el `role` y los campos del perfil, y no incluye `password`.
- [ ] Cambiar el rol con `update_user` deja `{"role": ["Cajero/Cobrador", "Supervisor"]}` (o los roles que correspondan) en `changes`.
- [ ] `update_user` sin cambios reales no crea registros.
- [ ] `users.deactivated` guarda el motivo en `extra.reason`.
- [ ] Si `record` lanza una excepción dentro de `create_user`, `deactivate_user` o `update_user`, el usuario no se crea o no cambia.
- [ ] Un servicio que lanza `UserRuleError` o `PermissionDenied` no crea registros.
- [ ] Crear y editar un usuario desde el admin de Django crea `users.created` y `users.updated` con origen `admin`, y cambiar sus grupos deja `role` en `changes`.
- [ ] Cambiar la contraseña de un usuario desde el admin de Django crea `users.password_reset` con origen `admin`.

**Admin de la auditoría**

- [ ] Un superusuario ve la lista de registros en `/admin/auditoria/auditevent/`, con los filtros por categoría, acción, origen y fecha.
- [ ] La ficha de un registro no tiene campos editables ni botones de guardar o eliminar, y la lista no ofrece la acción "Eliminar seleccionados".
- [ ] Las rutas de agregar y eliminar del admin responden 403.
- [ ] Un usuario con rol Administrador que no es superusuario no entra al admin.

**Calidad y documentación**

- [ ] `uv run pytest --cov` pasa, y `apps/auditoria` tiene al menos 90 % de cobertura.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] Todos los textos visibles nuevos (etiquetas de acciones, categorías, orígenes y campos) están envueltos en `gettext` o `gettext_lazy`.
- [ ] Existe `docs/decisiones/004-auditoria-senales-y-trigger.md`.
- [ ] `CLAUDE.md` explica cómo auditar una acción nueva (agregarla a `AuditAction` y a `ACTION_CATEGORIES`, y llamar a `record` dentro de la transacción del servicio).
- [ ] `.env.example` documenta `AUDIT_TRUSTED_PROXIES`.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** la inmutabilidad en la aplicación y en PostgreSQL. La aplicación da errores claros y la base de datos cierra el paso a cualquier otro camino (shell, SQL directo, un error en el código).
- **No:** solo en la aplicación. Un `QuerySet.update()` olvidado o un acceso por SQL bastarían para alterar el registro.
- **No:** bloquear solo `UPDATE` y dejar `DELETE` abierto para la depuración futura. La SPEC 25 diseña una vía controlada; abrirla ahora sería dejar el borrado libre durante meses.
- **No:** bloquear `TRUNCATE` con el trigger. Rompería `flush` en las pruebas transaccionales. Se cierra con los privilegios del usuario de base de datos en la spec de endurecimiento.
- **Sí:** cada servicio llama a `record` explícitamente, con los valores antes y después. Sabe la acción de negocio (desactivar no es lo mismo que editar), y la lógica no se esconde en señales.
- **No:** señales genéricas `pre_save` y `post_save`. No distinguen acciones, auditarían ruido como `last_login` y esconderían lógica en señales.
- **No:** un esquema mixto con señales como red de seguridad. Duplicaría registros y haría difícil saber cuál es el bueno.
- **Sí:** los accesos se enganchan con las señales de autenticación de Django (`user_logged_in`, `user_logged_out` y `user_login_failed`). No son reglas de negocio, y cubren cualquier camino de ingreso, incluido el del admin. Queda documentado en el ADR-004, como pide `CLAUDE.md` para usar señales.
- **No:** llamar a `record` desde `LoginView` y `LogoutView`. Un camino de ingreso nuevo podría quedar sin auditar.
- **Sí:** el bloqueo, el intento durante el bloqueo y los cambios de contraseña se auditan explícitamente. Django no emite señales para ellos.
- **Sí:** el registro se escribe en la misma transacción de la operación, y si falla, la operación se revierte. Ninguna acción queda sin rastro.
- **No:** atrapar el error y seguir. Habría acciones sin auditar, que es justo lo que la §14 prohíbe.
- **Sí:** `changes` guarda solo los campos que cambiaron, y `extra` guarda el contexto. Es compacto y se lee de un vistazo.
- **No:** snapshots completos antes y después. Pesan más y esconden el cambio entre campos que no se tocaron.
- **Sí:** los campos sensibles se marcan como `"[oculto]"` en vez de omitirse. Así se sabe que la contraseña cambió sin guardar ni el hash.
- **Sí:** el catálogo de acciones fija la categoría. Quien llama no puede equivocarse de categoría, y la SPEC 25 aplica la retención por categoría sin revisar cada registro.
- **Sí:** cuatro categorías: acceso, seguridad, datos personales y operación financiera. La gestión de usuarios no es solo un acceso ni solo datos personales, y la SPEC 25 puede darle su propia retención.
- **No:** solo las tres categorías de la hoja tentativa. La gestión de usuarios quedaría mezclada con los ingresos, con retención corta.
- **Sí:** la IP sale de `REMOTE_ADDR`, y `X-Forwarded-For` solo se lee con `AUDIT_TRUSTED_PROXIES`. Un cliente no puede falsificar su IP, y en producción detrás de nginx basta con poner `1`.
- **No:** leer siempre `X-Forwarded-For`. Cualquiera podría escribir la IP que quisiera.
- **Sí:** se guarda el texto escrito en el ingreso fallido, recortado a 150 caracteres. Permite detectar fuerza bruta y enumeración de usuarios.
- **No:** guardar solo la IP. No se sabría qué cuentas intentaron atacar.
- **Sí:** cada registro lleva user agent, método, ruta, ID de petición y origen. Ayudan a investigar un incidente y cuestan poco.
- **Sí:** la ruta se guarda sin la cadena de consulta. Así no quedan tokens ni datos de búsqueda en el registro.
- **Sí:** el contexto de la petición viaja en un `ContextVar` que llena un middleware. Los servicios no necesitan recibir el `request`, y el contexto no se cruza entre peticiones.
- **Sí:** se audita el admin de Django sobre usuarios. Es una puerta trasera para superusuarios y no debe quedar ciega.
- **No:** confiar en el `LogEntry` del admin. No guarda valores anteriores ni IP, y se puede borrar.
- **Sí:** mientras llega la SPEC 25, los registros se consultan en el admin de Django de solo lectura, solo para superusuarios.
- **No:** dar ya `view_auditevent` al Administrador. No tendría una pantalla de la aplicación donde usarlo.
- **Sí:** `actor_username` y `object_repr` copian los datos al momento del registro. El registro se lee igual aunque el usuario o la entidad cambien después.
- **Sí:** la entidad se guarda con `content_type` y `object_id` de texto. Sirve para cualquier modelo futuro, incluidos los que no usen enteros como clave.
- **No:** una clave foránea genérica (`GenericForeignKey`) con borrado en cascada. Un registro de auditoría no debe depender de que la entidad exista.
- **Sí:** el ADR de esta spec toma el número 004. El 003 sigue reservado para la librería de PDF.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| Agregar `apps.auditoria` cambia la última app con modelos, y el receptor de `sync_roles` (ADR-002) deja de correr. | El receptor ya busca la última app de `INSTALLED_APPS` con modelos. Una prueba corre `migrate` sobre una base vacía y revisa los grupos. |
| El trigger impide pruebas que limpian datos. | Las pruebas con `transaction=True` usan `flush`, que hace `TRUNCATE` y no dispara el trigger. Ninguna prueba borra registros de auditoría con `DELETE`. |
| Un servicio futuro olvida llamar a `record`. | `CLAUDE.md` lo pone como regla para cada spec, y cada spec incluye criterios de aceptación de su auditoría. |
| Un fallo al escribir la auditoría deja a la gente sin poder ingresar. | Es intencional: sin auditoría no hay acción. El riesgo real es una tabla llena o una base caída, que también tumbaría el resto. Se vigila con los respaldos y el endurecimiento. |
| El texto del ingreso fallido contiene una contraseña escrita por error en el campo de usuario. | Se recorta a 150 caracteres y solo lo ven los superusuarios. La SPEC 25 aplica la retención de la categoría de acceso. |
| La tabla crece rápido con un registro por ingreso. | Los índices por fecha, actor y entidad mantienen rápidas las consultas. La SPEC 25 depura según la retención. |
| `X-Forwarded-For` mal configurado guarda la IP del proxy o una IP falsa. | Por defecto se ignora la cabecera. `.env.example` explica cuándo poner `AUDIT_TRUSTED_PROXIES=1`. |
| Los cambios de grupos en el admin no se ven en `save_model`, porque los grupos se guardan después. | El rol se compara en `save_related`, que corre después de guardar los grupos. Una prueba cambia el grupo desde el admin. |

---

## Lo que **no** entra en esta spec

- La pantalla de consulta para administradores y la retención por categoría (SPEC 25).
- El permiso de ver la auditoría para algún rol.
- La auditoría de los módulos de negocio, que llega con cada spec.
- El historial de cambios del usuario en su ficha.
- La auditoría de `sync_roles` y de los grupos y permisos editados en el admin.
- La auditoría de lecturas y de exportaciones.
- El bloqueo de `TRUNCATE` y el usuario de base de datos con mínimos privilegios.
- El envío de la auditoría a un sistema externo.

Cada uno de estos puntos, si llega, va en su propia spec.
