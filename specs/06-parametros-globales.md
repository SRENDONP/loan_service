# SPEC 06 — Parámetros globales

> **Estado:** Implementado
> **Depende de:** SPEC 02, SPEC 03, SPEC 04, SPEC 05
> **Fecha:** 2026-11-12
> **Objetivo:** Que el Administrador edite desde `/parametros/` la identidad del negocio, los formatos, los días de cobro, el redondeo y las políticas de seguridad y sesión, y que el sistema los lea de un registro único de configuración en lugar de constantes y settings.

---

## 1. Por qué existe esta spec

La §2.1 exige parametrizar antes que codificar, y la §10.1 enumera los parámetros globales. El ADR-001 (D1) decidió guardarlos en un registro único de configuración, leído siempre a través de un servicio, para que el día que haya varios negocios solo cambie ese servicio.

Hoy esos valores están fijos en dos lugares que se escribieron pensando en esta spec:

- **`apps/accounts/policy.py`** lee de los settings los intentos antes del bloqueo, la duración del bloqueo, la longitud mínima de la contraseña y la vigencia del enlace de recuperación.
- **`apps/core/context_processors.branding`** devuelve un nombre del negocio y un icono fijos.

Esta spec cambia esos dos puntos para que lean del registro, sin tocar a quienes los usan.

También cierra una deuda de la SPEC 03: **el cierre de sesión por inactividad (§6.1)**, que quedó pendiente de ubicar. Como el tiempo de sesión es un parámetro de esta spec, aquí se implementa el comportamiento.

La 005 de la hoja tentativa incluía los catálogos. **Se dividió en dos:** esta spec trae los parámetros globales, y los catálogos con los festivos van en la SPEC 07.

---

## 2. Alcance

**Entra:**

- **La app `apps/parametros`** con el modelo `GlobalSettings`: un registro único (`pk=1`), creado por una migración de datos con los valores de hoy.
- **El servicio de lectura** `apps/parametros/services.py`, que es la única forma de leer los parámetros (ADR-001).
- **Cuatro grupos de parámetros:**
  - **Negocio y formatos:** nombre del negocio, icono de la marca, código, símbolo y decimales de la moneda, y formato de fecha.
  - **Cobro y días no hábiles:** días de cobro, horario de cobro, días de la semana no hábiles y regla de corrimiento (D5 y D13).
  - **Redondeo:** múltiplo y modo del redondeo por defecto.
  - **Seguridad y sesión:** intentos antes del bloqueo, duración del bloqueo, longitud mínima de la contraseña, vigencia del enlace de recuperación, minutos de inactividad y duración máxima de la sesión.
- **La pantalla `/parametros/`**, solo para el Administrador, con una tarjeta y un formulario por grupo.
- **La auditoría de cada grupo**, con su propia acción y su categoría.
- **`apps/accounts/policy.py`** lee del servicio. Sus funciones no cambian de nombre ni de firma.
- **`branding`** lee el nombre y el icono del servicio. Las plantillas no cambian.
- **El cierre de sesión por inactividad y por duración máxima**, con el middleware `SessionPolicyMiddleware`, su mensaje en el login y su registro de auditoría.
- **El formato de dinero y fechas:** `format_money`, `format_date` y `format_datetime` en Python, y los filtros `moneda`, `fecha` y `fecha_hora` en las plantillas.
- **`is_business_day(fecha)`**, que por ahora solo mira los días de la semana no hábiles.
- **La actualización de la documentación:** `CLAUDE.md` y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- Los catálogos (tipos de documento, ocupaciones, destinos de crédito, motivos de anulación y de rechazo, tipos de relación de terceros) y los **festivos de Colombia** con su carga inicial (SPEC 07). La SPEC 07 también amplía `is_business_day` con los festivos.
- El logo como imagen subida. Llega con la spec de documentos y fotos, que trae el almacenamiento privado y la validación de archivos. Aquí solo se elige un icono.
- La zona horaria editable. Sigue fija en `America/Bogota` y la pantalla la muestra solo como lectura.
- Los separadores de miles y de decimales editables. Salen del locale `es-co`.
- Aplicar el horario y los días de cobro (por ejemplo, rechazar un pago fuera de horario). Lo decide la spec de pagos.
- Aplicar la regla de redondeo y la regla de corrimiento. Las usan el motor de amortización y su calendario, que las reciben como parámetros.
- Un aviso antes del cierre por inactividad (modal con temporizador).
- Cambiar los validadores de complejidad de la contraseña. Siguen fijos (SPEC 03); solo la longitud mínima es editable.
- Un historial de valores consultable desde la pantalla. El historial queda en la auditoría.
- Los parámetros por negocio (multi-tenant, fase 2).
- El tipo de documento de los usuarios internos. Sigue con la lista fija de la SPEC 04.

---

## 3. Modelo de datos

### 3.1 El registro único (`apps/parametros/models.py`)

```python
class RoundingMode(models.TextChoices):
    HALF_UP = "half_up", _("Al más cercano")
    UP = "up", _("Siempre hacia arriba")
    DOWN = "down", _("Siempre hacia abajo")


class ShiftRule(models.TextChoices):
    CASCADE = "cascade", _("Correr también las cuotas siguientes")
    AFFECTED_ONLY = "affected_only", _("Correr solo la cuota afectada")


class DateFormat(models.TextChoices):
    DMY_SLASH = "d/m/Y", _("31/12/2026")
    DMY_DASH = "d-m-Y", _("31-12-2026")
    ISO = "Y-m-d", _("2026-12-31")
    LONG = r"j \d\e F \d\e Y", _("31 de diciembre de 2026")


class Weekday(models.IntegerChoices):  # ISO 8601: lunes = 1
    MONDAY = 1, _("Lunes")
    # ...
    SUNDAY = 7, _("Domingo")


ROUNDING_MULTIPLES = [1, 10, 50, 100, 500, 1000]
BRAND_ICONS = [  # Font Awesome Free 5.8.1, estilo solid
    "fas fa-hand-holding-usd", "fas fa-coins", "fas fa-money-bill-wave",
    "fas fa-piggy-bank", "fas fa-wallet", "fas fa-store", "fas fa-handshake",
    "fas fa-university",
]


class GlobalSettings(models.Model):
    # Negocio y formatos
    business_name = models.CharField(max_length=100, default="Gestión de préstamos")
    brand_icon = models.CharField(max_length=40, choices=..., default="fas fa-hand-holding-usd")
    currency_code = models.CharField(max_length=3, default="COP")
    currency_symbol = models.CharField(max_length=5, default="$")
    currency_decimals = models.PositiveSmallIntegerField(choices=[(0, "0"), (2, "2")], default=0)
    date_format = models.CharField(max_length=20, choices=DateFormat.choices, default=DateFormat.DMY_SLASH)

    # Cobro y días no hábiles
    collection_weekdays = ArrayField(models.PositiveSmallIntegerField(choices=Weekday.choices),
                                     default=[1, 2, 3, 4, 5, 6])
    collection_start_time = models.TimeField(default=time(6, 0))
    collection_end_time = models.TimeField(default=time(20, 0))
    non_business_weekdays = ArrayField(models.PositiveSmallIntegerField(choices=Weekday.choices),
                                       default=[7], blank=True)
    holiday_shift_rule = models.CharField(max_length=20, choices=ShiftRule.choices, default=ShiftRule.CASCADE)

    # Redondeo
    rounding_multiple = models.PositiveIntegerField(choices=..., default=50)
    rounding_mode = models.CharField(max_length=10, choices=RoundingMode.choices, default=RoundingMode.HALF_UP)

    # Seguridad y sesión
    max_failed_attempts = models.PositiveSmallIntegerField(default=5)          # 3 a 10
    lockout_minutes = models.PositiveSmallIntegerField(default=15)             # 5 a 120
    password_min_length = models.PositiveSmallIntegerField(default=8)          # 8 a 64
    password_reset_timeout_minutes = models.PositiveSmallIntegerField(default=60)  # 15 a 1.440
    session_idle_timeout_minutes = models.PositiveSmallIntegerField(default=30)    # 5 a 240
    session_max_hours = models.PositiveSmallIntegerField(default=12)           # 1 a 24

    # Trazabilidad mínima en la fila
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="+")

    class Meta:
        verbose_name = _("parámetros globales")
        verbose_name_plural = _("parámetros globales")
        default_permissions = ("view", "change")
        constraints = [
            models.CheckConstraint(condition=Q(pk=1), name="parametros_globalsettings_singleton"),
            # más un CheckConstraint por cada rango de la §3.2
        ]
```

Todos los campos llevan `verbose_name` y `help_text` en español con `gettext_lazy`. El snippet los omite para que se lea.

Reglas del registro:

- **Solo existe la fila `pk=1`.** `save()` fija `pk=1`, y el `CheckConstraint` impide cualquier otra fila. `delete()` lanza `PermissionDenied`, y no existe el permiso `delete`.
- **Los valores por defecto son los de hoy.** Los de seguridad coinciden con los de la SPEC 03 y con la §6.1 (30 minutos de inactividad). Instalar esta spec no cambia el comportamiento, salvo que la inactividad empieza a aplicarse.
- **La migración `0002_initial_settings.py`** crea la fila con los valores por defecto. Su reversa no hace nada.
- **`GlobalSettings` no se registra en el admin de Django.** Así no queda un camino para editar sin auditoría.

### 3.2 Validaciones

| Campo | Regla | Mensaje (resumen) |
|---|---|---|
| `business_name` | No vacío después de quitar espacios | "Escribe el nombre del negocio." |
| `currency_code` | Tres letras, se guarda en mayúsculas | "Usa el código de tres letras, por ejemplo COP." |
| `currency_symbol` | No vacío | — |
| `collection_weekdays` | Al menos un día | "Elige al menos un día de cobro." |
| `collection_start_time`, `collection_end_time` | El inicio es anterior al fin | "La hora de inicio debe ser anterior a la de fin." |
| `non_business_weekdays` | No puede incluir los siete días | "Debe haber al menos un día hábil." |
| `max_failed_attempts` | 3 a 10 | — |
| `lockout_minutes` | 5 a 120 | — |
| `password_min_length` | 8 a 64 | — |
| `password_reset_timeout_minutes` | 15 a 1.440 | — |
| `session_idle_timeout_minutes` | 5 a 240, y menor que la duración máxima de la sesión | "La inactividad debe ser menor que la duración máxima." |
| `session_max_hours` | 1 a 24 | — |

- Los rangos están en el modelo (`MinValueValidator`, `MaxValueValidator` y `CheckConstraint`), así que valen también fuera del formulario.
- Las reglas entre campos están en `GlobalSettings.clean()`, y los servicios llaman a `full_clean()` antes de guardar.
- Un día que es a la vez de cobro y no hábil se permite. La spec de pagos decide qué pasa en ese caso.

### 3.3 Servicio (`apps/parametros/services.py`)

```python
@dataclass(frozen=True)
class RoundingRule:
    multiple: Decimal
    mode: RoundingMode


def get_settings() -> GlobalSettings: ...
def get_rounding_rule() -> RoundingRule: ...
def is_business_day(day: date) -> bool: ...

def update_business(actor: User, data: Mapping[str, Any]) -> GlobalSettings: ...
def update_collection(actor: User, data: Mapping[str, Any]) -> GlobalSettings: ...
def update_rounding(actor: User, data: Mapping[str, Any]) -> GlobalSettings: ...
def update_security(actor: User, data: Mapping[str, Any]) -> GlobalSettings: ...
```

| Función | Qué hace |
|---|---|
| `get_settings` | Devuelve la fila `pk=1` con `get_or_create`. Si la fila no existe (por ejemplo, después de un `flush` en las pruebas), la crea con los valores por defecto. No usa caché: se consulta en cada uso, así un cambio aplica en la siguiente petición sin reiniciar. |
| `get_rounding_rule` | Devuelve el múltiplo como `Decimal` y el modo. El motor de amortización no importa `parametros`: quien lo llama le pasa esta regla. |
| `is_business_day` | `False` si el día de la semana está en `non_business_weekdays`. La SPEC 07 agrega los festivos sin cambiar la firma. |
| `update_*` | Verifican `parametros.change_globalsettings` con `require_perms`, toman un `snapshot` de los campos del grupo, asignan solo esos campos, llaman a `full_clean()`, guardan con `updated_by=actor` y llaman a `record` dentro de la misma `transaction.atomic()`. Si `diff` está vacío, no guardan ni registran. Lanzan `ValidationError` con los errores por campo. |

Reglas:

- **Ningún código lee `GlobalSettings` directamente** fuera de `services.py` y de sus pruebas. Vistas, plantillas, `policy.py` y `branding` pasan por el servicio (ADR-001).
- **Cada servicio de edición solo toca los campos de su grupo.** Un dato de otro grupo en `data` se ignora.
- **Los servicios de edición toman la fila con `select_for_update()`.** Dos administradores que guardan grupos distintos al mismo tiempo no se pisan.

### 3.4 Lectura desde `accounts` y `core`

**`apps/accounts/policy.py`** conserva sus cuatro funciones con la misma firma:

| Función | Antes | Después |
|---|---|---|
| `get_max_failed_attempts()` | `settings.ACCOUNTS_MAX_FAILED_ATTEMPTS` | `get_settings().max_failed_attempts` |
| `get_lockout_duration()` | `settings.ACCOUNTS_LOCKOUT_MINUTES` | `timedelta(minutes=get_settings().lockout_minutes)` |
| `get_password_min_length()` | `settings.ACCOUNTS_PASSWORD_MIN_LENGTH` | `get_settings().password_min_length` |
| `get_password_reset_timeout()` | `settings.PASSWORD_RESET_TIMEOUT` | `get_settings().password_reset_timeout_minutes * 60` |

Y agrega dos:

- `get_session_idle_timeout() -> timedelta`
- `get_session_max_duration() -> timedelta`

`ACCOUNTS_MAX_FAILED_ATTEMPTS`, `ACCOUNTS_LOCKOUT_MINUTES`, `ACCOUNTS_PASSWORD_MIN_LENGTH` y `PASSWORD_RESET_TIMEOUT` se quitan de `config/settings/base.py`. El generador de tokens propio ya lee la vigencia de `policy.py` (SPEC 03), así que el valor de Django no se usa.

**`apps/core/context_processors.branding`** devuelve `business_name` y `brand_icon` desde `get_settings()`. Las plantillas siguen usando las mismas variables. Las constantes `BUSINESS_NAME` y `BRAND_ICON` desaparecen.

### 3.5 Cierre de sesión por inactividad y por duración

**`SessionPolicyMiddleware`** (`apps/accounts/middleware.py`) va en `MIDDLEWARE` justo después de `AuditContextMiddleware` y antes de `LoginRequiredMiddleware`.

En cada petición con usuario autenticado:

1. Lee de la sesión `_session_started_at` y `_last_activity` (segundos desde la época, como enteros).
2. Si falta `_session_started_at`, lo fija en ahora. Así quedan cubiertas las sesiones abiertas antes de esta spec.
3. Si pasó más de `get_session_max_duration()` desde `_session_started_at`, cierra la sesión con el motivo `max_duration`.
4. Si pasó más de `get_session_idle_timeout()` desde `_last_activity`, cierra la sesión con el motivo `inactivity`.
5. Si no cerró la sesión, actualiza `_last_activity` solo si el valor guardado tiene más de 60 segundos. Así la sesión no se escribe en cada petición.

Al cerrar la sesión:

- Fija `request.audit_logout_reason` y llama a `django.contrib.auth.logout(request)`.
- El receptor `audit_logout` (SPEC 05) lee ese atributo y guarda `extra={"reason": "inactivity"}` o `extra={"reason": "max_duration"}`. El cierre voluntario sigue sin `extra`, como hoy.
- Agrega el mensaje "Tu sesión se cerró por inactividad." o "Tu sesión llegó a su duración máxima. Ingresa de nuevo." con `messages.info`.
- Redirige al login con `?next=` igual a la ruta pedida si es un `GET`. Para cualquier otro método, redirige al login sin `next`.

Reglas:

- **Las rutas públicas** (`@login_not_required`) no cierran sesión por inactividad, pero sí actualizan `_last_activity` si hay un usuario autenticado.
- **`SESSION_EXPIRE_AT_BROWSER_CLOSE = True` se mantiene.** `SESSION_COOKIE_AGE` pasa a 24 horas, el máximo del rango, como tope duro aunque falle el middleware.
- **Un cambio del parámetro aplica a las sesiones abiertas** en su siguiente petición, porque los tiempos se comparan con el valor vigente.

### 3.6 Formato de dinero y fechas (`apps/parametros/formatting.py`)

```python
def format_money(value: Decimal | int | None) -> str: ...
def format_date(value: date | None) -> str: ...
def format_datetime(value: datetime | None) -> str: ...
```

| Función | Resultado con los valores por defecto |
|---|---|
| `format_money(Decimal("1234567.5"))` | `"$1.234.568"`: símbolo sin espacio, separadores de `es-co`, `currency_decimals` decimales con redondeo `ROUND_HALF_UP` |
| `format_money(Decimal("-1500"))` | `"-$1.500"` |
| `format_date(date(2026, 12, 31))` | `"31/12/2026"` según `date_format` |
| `format_datetime(...)` | La fecha según `date_format`, un espacio y la hora local con el `TIME_FORMAT` de `es-co` (`H:i`), por ejemplo `"31/12/2026 14:05"` |

- Con `None`, las tres devuelven `""`.
- `format_money` nunca convierte a `float`. Un `float` recibido lanza `TypeError`.
- Este redondeo es solo para mostrar. No reemplaza la regla de redondeo de los cálculos.

Los filtros `moneda`, `fecha` y `fecha_hora` (`apps/parametros/templatetags/formato.py`, se cargan con `{% load formato %}`) llaman a esas funciones.

`format_datetime` de `apps/accounts/views.py` se reemplaza por el de `parametros`. Así, la ficha del usuario ya muestra las fechas con el formato elegido.

### 3.7 Auditoría

| Acción | Valor | Etiqueta | Categoría | Servicio |
|---|---|---|---|---|
| `SETTINGS_BUSINESS_UPDATED` | `parametros.business_updated` | "Parámetros del negocio editados" | `SECURITY` | `update_business` |
| `SETTINGS_COLLECTION_UPDATED` | `parametros.collection_updated` | "Parámetros de cobro editados" | `FINANCIAL` | `update_collection` |
| `SETTINGS_ROUNDING_UPDATED` | `parametros.rounding_updated` | "Regla de redondeo editada" | `FINANCIAL` | `update_rounding` |
| `SETTINGS_SECURITY_UPDATED` | `parametros.security_updated` | "Políticas de seguridad editadas" | `SECURITY` | `update_security` |

- El actor es el `actor` del servicio y la entidad es la fila de `GlobalSettings`.
- `changes` guarda solo los campos del grupo que cambiaron. Las horas van en ISO 8601 y las listas de días como listas de enteros.
- Ningún campo de esta spec es secreto, así que `SENSITIVE_FIELDS` no cambia.
- El cierre de sesión por inactividad usa la acción `auth.logout` que ya existe, con `extra.reason`.

### 3.8 Permisos y menú

- En `ROLE_PERMISSIONS`, el Administrador recibe `parametros.view_globalsettings` y `parametros.change_globalsettings`. Ningún otro rol recibe permisos de `parametros`.
- `apps/parametros/menu.py` registra la sección `configuracion` ("Configuración", orden 800, antes de "Administración") y la entrada `parametros.global` ("Parámetros globales", icono `fas fa-fw fa-sliders-h`, `url_name="parametros:global"`, permiso `parametros.view_globalsettings`). La SPEC 07 agrega ahí los catálogos.

### 3.9 Pantalla

| Ruta | Método | Vista | Permiso |
|---|---|---|---|
| `/parametros/` | GET | `GlobalSettingsView` | `parametros.view_globalsettings` |
| `/parametros/negocio/` | POST | `update_business` | `parametros.change_globalsettings` |
| `/parametros/cobro/` | POST | `update_collection` | `parametros.change_globalsettings` |
| `/parametros/redondeo/` | POST | `update_rounding` | `parametros.change_globalsettings` |
| `/parametros/seguridad/` | POST | `update_security` | `parametros.change_globalsettings` |

- **La plantilla `templates/parametros/global_settings.html`** parte de `blank.html`, extiende `base.html` y muestra cuatro tarjetas (`card shadow mb-4` con `card-header` como en `cards.html`), una por grupo, cada una con su formulario y su botón Guardar. Debajo del título va la fecha de la última edición y quién la hizo.
- **La zona horaria** aparece en la tarjeta de negocio como un dato de solo lectura ("America/Bogota").
- **Los días** se eligen con casillas. Las horas, con `<input type="time">`. El icono, con un `select` que muestra el nombre del icono; al lado se ve una vista previa con el icono vigente.
- **Al guardar bien**, se redirige a `/parametros/` con el mensaje "Se guardaron los parámetros de <grupo>." Si no hubo cambios, el mensaje es "No hubo cambios en <grupo>."
- **Al guardar con errores**, la vista vuelve a mostrar la página completa con el formulario de ese grupo con sus errores, y los demás con los valores guardados. La respuesta es 200.
- **Los formularios** son `ModelForm` por grupo (`apps/parametros/forms.py`) con `{{ form }}` y el renderizador de la SPEC 02. La vista llama al servicio, nunca a `form.save()`.
- **Una petición GET a una ruta de guardado** responde 405.
- **En celular (unos 375 px)**, las tarjetas se apilan en una sola columna.

### 3.10 Archivos nuevos y modificados

**Nuevos:**

- `apps/parametros/__init__.py`, `apps.py`, `models.py`, `services.py`, `formatting.py`, `forms.py`, `views.py`, `urls.py` y `menu.py`.
- `apps/parametros/templatetags/__init__.py` y `formato.py`.
- `apps/parametros/migrations/0001_initial.py` y `0002_initial_settings.py`.
- `templates/parametros/global_settings.html`.
- `tests/parametros/__init__.py`, `test_models.py`, `test_services.py`, `test_formatting.py`, `test_views.py` y `test_audit.py`.
- `tests/accounts/test_session_policy.py`.
- Agregados durante la implementación (ver §6.1):
  - `apps/auditoria/migrations/0003_settings_actions.py`.
  - `templates/forms/widgets/checkbox_select.html` y `time.html`.

**Modificados:**

- `config/settings/base.py`: `"apps.parametros"` en `INSTALLED_APPS` (después de `apps.auditoria`), `SessionPolicyMiddleware` en `MIDDLEWARE`, `SESSION_COOKIE_AGE` a 24 horas, y sin los cuatro settings de políticas.
- `config/urls.py`: `path("parametros/", include("apps.parametros.urls"))`.
- `apps/accounts/policy.py`, `middleware.py`, `views.py` y `roles.py`.
- `apps/core/context_processors.py`.
- `apps/auditoria/actions.py` y `receivers.py`.
- `templates/core/components.html`: un ejemplo de los filtros `moneda`, `fecha` y `fecha_hora`.
- `tests/conftest.py`: el fixture `global_settings`, que devuelve la fila y permite cambiar valores en una prueba.
- Las pruebas que hoy usan `override_settings(ACCOUNTS_...)` o `override_settings(PASSWORD_RESET_TIMEOUT=...)` (`tests/accounts/test_policy.py`, `test_audit.py`, `test_services.py`, `test_user_services.py`, `test_validators.py` y `test_password_reset.py`) pasan a usar el fixture.
- `CLAUDE.md` y `docs/specs-tentativas.md`.
- Modificados durante la implementación (ver §6.1):
  - `config/settings/base.py`: también `"django.contrib.postgres"` en `INSTALLED_APPS`.
  - `apps/core/views.py`: los valores de ejemplo de `/componentes/`.
  - `templates/forms/field.html` y `field_errors.html`: el error de un campo dentro de un `fieldset` queda visible.
  - `static/css/app.css`: la leyenda de un grupo de casillas con el tamaño de una etiqueta.
  - `tests/auditoria/test_models.py` y `test_actions.py`, `tests/accounts/test_roles.py`, `test_settings.py` y `test_user_views.py`, `tests/core/test_views.py` y `test_health.py`.

---

## 4. Plan de implementación

1. **App y modelo.** Crear `apps/parametros`, registrarla en `INSTALLED_APPS`, escribir `models.py` con las validaciones de la §3.2 y generar `0001_initial.py` y `0002_initial_settings.py`. Pruebas de `test_models.py`: una sola fila, `delete()` rechazado, rangos y reglas entre campos. Verificar que `migrate` sobre una base vacía sigue dejando los grupos de `sync_roles`.
2. **Servicio de lectura.** Escribir `get_settings`, `get_rounding_rule` e `is_business_day`, y el fixture `global_settings`. Pruebas en `test_services.py`, incluida la fila recreada cuando no existe.
3. **Políticas de cuentas.** Cambiar `policy.py` para leer del servicio, quitar los cuatro settings y pasar las pruebas de `accounts` al fixture. Toda la suite de `accounts` sigue pasando.
4. **Marca.** Cambiar `branding` para leer del servicio. Prueba: cambiar el nombre en la fila cambia el título y el panel lateral.
5. **Formato.** Escribir `formatting.py` y los filtros, reemplazar `format_datetime` en `accounts/views.py` y agregar el ejemplo a `/componentes/`. Pruebas en `test_formatting.py`.
6. **Servicios de edición y auditoría.** Agregar las cuatro acciones a `AuditAction` y `ACTION_CATEGORIES`, y escribir los cuatro `update_*`. Pruebas en `test_services.py` y `test_audit.py`: permiso, campos de otro grupo ignorados, sin cambios sin registro y reversión si `record` falla.
7. **Permisos y menú.** Agregar los permisos a `ROLE_PERMISSIONS` con su prueba de la matriz, y escribir `menu.py`.
8. **Pantalla.** Escribir `forms.py`, `views.py`, `urls.py` y la plantilla. Pruebas en `test_views.py`: permisos por rol, guardado bien, con errores, sin cambios y 405.
9. **Sesión.** Escribir `SessionPolicyMiddleware`, agregar los dos getters a `policy.py`, cambiar `SESSION_COOKIE_AGE` y leer `audit_logout_reason` en el receptor. Pruebas en `tests/accounts/test_session_policy.py`, moviendo el reloj con `unittest.mock.patch` sobre la función que da la hora en el middleware. No se agrega `freezegun`, que no está en el proyecto.
10. **Verificación en el navegador.** Recorrer `/parametros/` con el MCP de Playwright como Administrador, en escritorio y a unos 375 px, y comparar con `blank.html` y `cards.html`.
11. **Documentación.** Actualizar `CLAUDE.md` (estado del proyecto, una sección "Parámetros globales (SPEC 06)", la fila de inactividad fuera de la tabla de diferencias) y `docs/specs-tentativas.md` (la 005 dividida en SPEC 06 y SPEC 07, la inactividad ubicada aquí y la numeración siguiente corrida en uno).

---

## 5. Criterios de aceptación

**Modelo**

- [ ] Después de `migrate` sobre una base vacía existe exactamente una fila de `GlobalSettings`, con `pk=1` y los valores por defecto de la §3.1.
- [ ] Crear una segunda fila por el ORM o por SQL falla con `parametros_globalsettings_singleton`.
- [ ] `delete()` sobre la fila lanza `PermissionDenied` y la fila sigue existiendo.
- [ ] La tabla solo tiene los permisos `view_globalsettings` y `change_globalsettings`.
- [ ] Cada rango de la §3.2 rechaza el valor inmediatamente inferior y el inmediatamente superior, y acepta los dos extremos.
- [ ] `full_clean()` rechaza: ningún día de cobro, la hora de inicio igual o posterior a la de fin, los siete días como no hábiles, y una inactividad de 60 minutos con una duración máxima de 1 hora.
- [ ] `migrate` sobre una base vacía deja los cuatro grupos con sus permisos, y el Administrador tiene `view_globalsettings` y `change_globalsettings`.

**Lectura**

- [ ] `get_settings()` devuelve la fila, y si la fila no existe la crea con los valores por defecto.
- [ ] `get_rounding_rule()` devuelve `RoundingRule(multiple=Decimal("50"), mode=RoundingMode.HALF_UP)` con los valores por defecto.
- [ ] Con los valores por defecto, `is_business_day` devuelve `False` para un domingo y `True` para un lunes.
- [ ] Ningún módulo fuera de `apps/parametros` importa `GlobalSettings` (una prueba lo verifica recorriendo los módulos de `apps/`).
- [ ] Los settings `ACCOUNTS_MAX_FAILED_ATTEMPTS`, `ACCOUNTS_LOCKOUT_MINUTES`, `ACCOUNTS_PASSWORD_MIN_LENGTH` y `PASSWORD_RESET_TIMEOUT` ya no existen en `config/settings/`.

**Efecto de los parámetros**

- [ ] Con `max_failed_attempts=3`, el tercer intento fallido bloquea la cuenta, sin reiniciar el servidor.
- [ ] Con `lockout_minutes=30`, el `locked_until` del bloqueo queda 30 minutos después del intento.
- [ ] Con `password_min_length=12`, una contraseña de 11 caracteres se rechaza al cambiarla, y el mensaje dice 12.
- [ ] Con `password_reset_timeout_minutes=15`, un enlace de recuperación de hace 16 minutos ya no sirve.
- [ ] Cambiar `business_name` cambia el `<title>`, el panel lateral, el pie de página y la pantalla de login en la siguiente petición.
- [ ] Cambiar `brand_icon` cambia el icono del panel lateral y del login.
- [ ] Con `date_format="Y-m-d"`, la ficha de un usuario muestra su último ingreso como `AAAA-MM-DD HH:MM`.

**Formato**

- [ ] `format_money(Decimal("1234567.5"))` devuelve `"$1.234.568"` con 0 decimales y `"$1.234.567,50"` con 2.
- [ ] `format_money(Decimal("-1500"))` devuelve `"-$1.500"`, `format_money(None)` devuelve `""` y `format_money(1.5)` lanza `TypeError`.
- [ ] `format_date` y `format_datetime` producen el resultado de la §3.6 con cada una de las cuatro opciones de `date_format`, y `format_datetime` usa la hora local de `America/Bogota`.
- [ ] `/componentes/` muestra un ejemplo de `moneda`, `fecha` y `fecha_hora`.

**Pantalla y permisos**

- [ ] El Administrador ve "Parámetros globales" en la sección "Configuración" del menú, y la página `/parametros/` responde 200 con las cuatro tarjetas.
- [ ] Supervisor, Cajero/Cobrador y Consulta no ven la entrada del menú, y `/parametros/` y las cuatro rutas de guardado les responden 403.
- [ ] Guardar un grupo con datos válidos redirige a `/parametros/` con el mensaje de éxito y cambia solo los campos de ese grupo.
- [ ] Enviar en `/parametros/redondeo/` un campo de otro grupo (por ejemplo, `business_name`) no cambia ese campo.
- [ ] Guardar con errores responde 200, muestra los errores en la tarjeta de ese grupo y no cambia la fila.
- [ ] Guardar sin cambios muestra "No hubo cambios en <grupo>." y no crea registros de auditoría.
- [ ] Un GET a una ruta de guardado responde 405.
- [ ] La tarjeta de negocio muestra la zona horaria `America/Bogota` sin campo editable.
- [ ] La página muestra la fecha de la última edición y el usuario que la hizo.
- [ ] Con Playwright, la página se ve con la estructura de `blank.html` y las tarjetas de `cards.html`, a unos 375 px las tarjetas quedan en una columna sin desplazamiento horizontal, y la consola no muestra errores.

**Auditoría**

- [ ] Cada servicio de edición crea su acción de la §3.7 con su categoría, el `actor` como actor, la fila como entidad y solo los campos cambiados del grupo en `changes`.
- [ ] Cambiar los días de cobro deja en `changes` las listas de enteros antes y después, y cambiar el horario deja las horas en ISO 8601.
- [ ] Si `record` lanza una excepción dentro de un `update_*`, la fila no cambia.
- [ ] Un `update_*` llamado por un usuario sin `change_globalsettings` lanza `PermissionDenied` y no crea registros.

**Sesión**

- [ ] Con `session_idle_timeout_minutes=30`, una petición 29 minutos después de la anterior sigue con sesión.
- [ ] Una petición 31 minutos después de la anterior cierra la sesión, redirige al login con `?next=` y muestra "Tu sesión se cerró por inactividad."
- [ ] Ese cierre crea `auth.logout` con `extra.reason="inactivity"`, y el cierre voluntario sigue sin `extra.reason`.
- [ ] Con `session_max_hours=1`, una sesión activa cada 5 minutos se cierra en la primera petición después de la hora, con `extra.reason="max_duration"` y su mensaje.
- [ ] Un POST después de la inactividad redirige al login sin `next` y no ejecuta la acción.
- [ ] Una sesión sin `_session_started_at` (abierta antes de esta spec) no se cierra en su siguiente petición, y queda con `_session_started_at` fijado.
- [ ] Dos peticiones seguidas en menos de 60 segundos no reescriben `_last_activity`.
- [ ] Bajar `session_idle_timeout_minutes` cierra por inactividad, en su siguiente petición, una sesión abierta que ya superó el nuevo valor.
- [ ] `SESSION_COOKIE_AGE` es de 24 horas y `SESSION_EXPIRE_AT_BROWSER_CLOSE` sigue en `True`.

**Calidad y documentación**

- [ ] `uv run pytest --cov` pasa, y `apps/parametros` tiene al menos 90 % de cobertura.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] Todos los textos visibles nuevos están envueltos en `gettext`, `gettext_lazy` o `{% translate %}`.
- [ ] `CLAUDE.md` explica cómo leer un parámetro (solo por `apps/parametros/services.py`) y ya no lista la inactividad como diferencia pendiente.
- [ ] `docs/specs-tentativas.md` registra la división de la 005 en SPEC 06 y SPEC 07.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** dividir la 005 de la hoja tentativa en dos specs. Los parámetros globales y los siete catálogos con los festivos no cabían en una spec que se verifique en pocos días.
- **No:** una sola spec con todo. Habría juntado un registro único y unos siete CRUD con su carga inicial.
- **Sí:** un modelo con un campo tipado por parámetro, en una sola fila con `pk=1` (ADR-001). Conserva los tipos y las validaciones, y la auditoría compara campo por campo.
- **No:** pares clave-valor genéricos. Pierden los tipos y las validaciones, como ya descartó el ADR-001.
- **No:** una librería de "singleton" (como django-solo). Es una dependencia nueva para lo que resuelven un `CheckConstraint` y `get_or_create`.
- **Sí:** el servicio consulta la fila en cada uso, sin caché. Un cambio aplica en la siguiente petición en todos los procesos, y una consulta por clave primaria cuesta poco.
- **No:** la caché de Django con invalidación al guardar. Con varios procesos de Gunicorn y sin Redis, la invalidación no llega a todos.
- **Sí:** `policy.py` y `branding` cambian por dentro y conservan su interfaz. Así lo previeron la SPEC 02 y la SPEC 03, y nadie más tiene que cambiar.
- **Sí:** el icono de la marca se elige de una lista cerrada de Font Awesome 5.8.1. Evita clases inventadas o inyectadas en el HTML y deja el logo como imagen para la spec de documentos.
- **No:** subir una imagen ahora. Obligaría a configurar `MEDIA`, a validar archivos y a agregar Pillow antes de la spec que trae todo eso.
- **Sí:** la zona horaria fija en `America/Bogota`, visible como lectura. Cambiarla en caliente movería los cortes del día de la mora y del cierre de caja.
- **Sí:** los separadores de miles y de decimales salen del locale `es-co`, y la hora usa el `TIME_FORMAT` de `es-co` (`H:i`). Solo la moneda, sus decimales y el formato de fecha son editables.
- **Sí:** el formato de fecha se elige entre cuatro opciones. Un texto libre con códigos de Django sería confuso y fácil de romper.
- **Sí:** el redondeo es un múltiplo (1, 10, 50, 100, 500 o 1.000) más un modo. Por defecto, al múltiplo de 50 más cercano, lo habitual en el gota a gota.
- **No:** solo decimales. No permite redondear a múltiplos de 50 o 100 pesos.
- **No:** un múltiplo libre. Abre valores sin sentido como 7 o 333.
- **Sí:** `parametros` entrega la regla de redondeo como un `RoundingRule`, y el motor la recibe como parámetro. El motor sigue siendo lógica pura sin importar Django (§5).
- **Sí:** los días de cobro, el horario, los días no hábiles y la regla de corrimiento solo se guardan en esta spec. Sus consumidores (el calendario del motor y los pagos) todavía no existen.
- **Sí:** los días no hábiles son días de la semana (domingo por defecto), y los festivos llegan en la SPEC 07. `is_business_day` no cambia de firma cuando los festivos lleguen.
- **Sí:** la cascada es la regla de corrimiento por defecto (D13), con la opción de correr solo la cuota afectada.
- **Sí:** solo el Administrador ve y edita los parámetros. La §6.2 le da la parametrización, y el resto del sistema lee los valores por el servicio sin necesitar permisos.
- **Sí:** una página con una tarjeta y un formulario por grupo. Un error en un grupo no bloquea los demás, y cada grupo deja su propio registro.
- **No:** un solo formulario con un solo botón. Un error en cualquier campo impediría guardar todo, y la auditoría mezclaría grupos.
- **Sí:** una acción de auditoría por grupo, con la categoría de las cuatro que ya existen: `SECURITY` para negocio y seguridad, y `FINANCIAL` para cobro y redondeo, porque cambian cómo se calcula y cobra.
- **No:** una quinta categoría "Configuración". Cambiaría una decisión de la SPEC 05 y obligaría a definir su retención.
- **No:** todo en `SECURITY`. Un cambio en el redondeo quedaría con la retención de seguridad y no con la financiera.
- **Sí:** `GlobalSettings` no se registra en el admin de Django. Sería un camino para editar sin pasar por los servicios ni por la auditoría.
- **Sí:** los rangos de seguridad y sesión (3–10 intentos, 5–120 min de bloqueo, 8–64 caracteres, 15–1.440 min de enlace, 5–240 min de inactividad y 1–24 h de sesión). Impiden dejar el sistema inseguro por un error de digitación.
- **Sí:** el cierre por inactividad entra en esta spec. Cierra la deuda de la SPEC 03 con la §6.1, y un parámetro que no hace nada confundiría al Administrador.
- **Sí:** el cierre se detecta en la siguiente petición, con un mensaje en el login, sin JavaScript.
- **No:** un modal con temporizador que avisa antes. Agrega JavaScript y una ruta para renovar la sesión; puede llegar en otra spec.
- **Sí:** el cierre por inactividad usa la acción `auth.logout` con `extra.reason`. Pasa por el mismo `logout()` de Django y por el receptor de la SPEC 05, sin una acción nueva.
- **Sí:** `_last_activity` se reescribe como mucho una vez por minuto. Evita guardar la sesión en cada petición, a cambio de un margen de un minuto.
- **Sí:** `SESSION_COOKIE_AGE` de 24 horas como tope duro. Si el middleware fallara, ninguna sesión duraría más que el máximo del rango.
- **Sí:** el tipo de documento de los usuarios internos sigue con la lista fija de la SPEC 04. El catálogo de la SPEC 07 lo usan clientes y terceros.
- **Sí:** la fila guarda `updated_at` y `updated_by`, además de la auditoría. La pantalla muestra quién editó por última vez sin consultar la auditoría, que ningún rol puede ver todavía.

### 6.1 Decisiones tomadas durante la implementación

- **Sí:** `"django.contrib.postgres"` en `INSTALLED_APPS`. Django 6.1 lo exige para usar `ArrayField` (error `postgres.E005`). Viene con Django; no es una librería nueva.
- **Sí:** la migración `auditoria/0003_settings_actions.py`. Las cuatro acciones nuevas cambian las `choices` de `AuditEvent.action`. Es una operación vacía en la base de datos (`sqlmigrate` da `no-op`) y no toca el trigger.
- **Sí:** las pruebas de "última app con modelos" y de los grupos después de `migrate` pasan de `tests/auditoria/test_models.py` a `tests/parametros/test_models.py`, comparando contra `ROLE_PERMISSIONS`. Ahora `parametros` es la última app con modelos.
- **Sí:** las pruebas de `accounts` que usaban valores fuera de los rangos nuevos los ajustan: 3 intentos en lugar de 2, una longitud de 10 en lugar de 6 y un enlace de 15 minutos en lugar de 60 segundos.
- **Sí:** `format_date` escribe el mes en minúscula ("31 de diciembre de 2026"). La traducción de Django lo trae con mayúscula ("Diciembre"); se reemplaza cada `F` sin escapar por el nombre del mes en minúscula, ya escapado. Decisión de la persona durante el paso 5.
- **Sí:** `require_perms` se importa dentro de la función de edición de `parametros/services.py`. Se presentó el ciclo previsto en la §7 (`accounts.models → validators → policy → parametros.services → accounts.permissions`) y se aplicó su mitigación.
- **Sí:** la vista distingue "Se guardaron…" de "No hubo cambios…" comparando `updated_at` antes y después del servicio. Así los servicios conservan la firma de la §3.3, que devuelve `GlobalSettings`.
- **Sí:** `menu.py` se escribe en el paso 8 y no en el 7. El menú hace `reverse` de `parametros:global` en cada página, y la ruta no existía hasta el paso 8. Decisión de la persona durante el paso 7.
- **Sí:** dos plantillas de widget nuevas en `templates/forms/widgets/` (`checkbox_select.html`, en línea con `form-check-inline`, y `time.html`) y el error visible dentro de un `fieldset` (`d-block`). Sin ellas, las casillas salían con `form-control` y el error quedaba oculto, porque Bootstrap solo lo muestra junto a un `.is-invalid` hermano.
- **Sí:** la leyenda de un grupo de casillas con el tamaño de una etiqueta, en `static/css/app.css`. Bootstrap le da el tamaño de un título. Se detectó en la verificación con Playwright.
- **Sí:** `SessionPolicyMiddleware` trabaja en `process_view`, para saber si la vista es `@login_not_required`. Consecuencia: una ruta que no existe (404) no revisa ni renueva la sesión; una sesión vencida se cierra en la siguiente petición a una página real.
- **Sí:** las pruebas que validan contraseñas o renderizan `base.html` (incluida la página 403 de CSRF) usan la base de datos, porque la longitud mínima y el nombre del negocio salen de ahí.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| Agregar `apps.parametros` cambia la última app con modelos, y el receptor de `sync_roles` (ADR-002) deja de correr. | El receptor ya busca la última app de `INSTALLED_APPS` con modelos. Un criterio verifica los grupos después de `migrate` sobre una base vacía. |
| Importación circular: `accounts.policy` importa `parametros.services`, y `parametros.services` importa `accounts.permissions`. | `parametros` no importa nada de `accounts` en el nivel del módulo que importe a su vez `policy`. Si aparece el ciclo, la importación de `require_perms` va dentro de los servicios de edición. |
| Las pruebas transaccionales vacían la tabla con `flush`, y la fila desaparece. | `get_settings()` recrea la fila con `get_or_create`. |
| Cada petición suma consultas (marca, middleware de sesión y, en el login, la política). | Son consultas por clave primaria. Si llegan a pesar, se agrega una memoria por petición sin cambiar la interfaz del servicio. |
| Un Administrador baja la inactividad y cierra las sesiones de todos, también la suya. | Es el comportamiento esperado. El rango mínimo de 5 minutos evita cerrar sesiones en segundos. |
| El mensaje de inactividad se pierde porque `logout()` vacía la sesión. | Los mensajes se agregan después de `logout()`. El almacenamiento por defecto de Django (`FallbackStorage`) usa primero la cookie. Un criterio verifica el mensaje en el login. |
| Subir la longitud mínima no obliga a cambiar las contraseñas que ya existen. | Es intencional: la regla aplica al siguiente cambio de contraseña. Se documenta en el `help_text` del campo. |
| Una prueba que cambia la fila contamina a las siguientes. | Las pruebas cambian la fila con el fixture `global_settings` dentro de la transacción de la prueba, que se revierte al terminar. |

---

## Lo que **no** entra en esta spec

- Los catálogos y los festivos de Colombia (SPEC 07).
- El logo como imagen subida.
- La zona horaria y los separadores editables.
- Aplicar el horario de cobro, el redondeo y la regla de corrimiento, que usan sus propias specs.
- El aviso previo al cierre por inactividad.
- Cambiar los validadores de complejidad de la contraseña.
- El historial de valores en la pantalla.
- Los parámetros por negocio.
- El tipo de documento de los usuarios internos en un catálogo.

Cada uno de estos puntos, si llega, va en su propia spec.
