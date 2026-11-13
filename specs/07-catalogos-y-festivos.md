# SPEC 07 — Catálogos y festivos

> **Estado:** Implementado
> **Depende de:** SPEC 02, SPEC 04, SPEC 05, SPEC 06
> **Fecha:** 2026-11-13
> **Objetivo:** Que el Administrador mantenga desde `/parametros/` los seis catálogos de texto y los festivos de Colombia, cargados al instalar, y que `is_business_day` tenga en cuenta esos festivos.

---

## 1. Por qué existe esta spec

La §10.4 de la constitución exige catálogos administrables: tipos de documento, ocupaciones, destinos de crédito, motivos de anulación, motivos de rechazo y días festivos. La decisión D9 de la hoja tentativa agrega los tipos de relación de terceros (codeudor, referencia personal y otros).

La 005 de la hoja tentativa se dividió en dos. La SPEC 06 trajo los parámetros globales y dejó dos ganchos para esta:

- **`is_business_day(fecha)`** solo mira los días de la semana no hábiles. Esta spec le suma los festivos sin cambiar su firma.
- **La sección de menú `configuracion`**, donde esta spec agrega los catálogos.

Los catálogos tienen que existir antes de las specs que los usan: clientes (tipo de documento y ocupación), terceros (tipo de relación), solicitud de créditos (destino y motivo de rechazo) y anulación de pagos (motivo de anulación). El calendario del motor necesita los festivos como una lista de fechas.

---

## 2. Alcance

**Entra:**

- **Seis catálogos de texto**, cada uno en su tabla, sobre un modelo abstracto común `CatalogItem`:
  - Tipos de documento (`DocumentType`).
  - Ocupaciones (`Occupation`).
  - Destinos de crédito (`CreditPurpose`).
  - Motivos de anulación (`VoidReason`).
  - Motivos de rechazo (`RejectionReason`).
  - Tipos de relación de terceros (`ThirdPartyRelationType`).
- **Los festivos** (`Holiday`), con dos orígenes: oficial (calculado) y propio (un día que el negocio no abre, §9.2).
- **El cálculo de los festivos oficiales de Colombia** en una función pura, sin dependencias nuevas.
- **El comando `cargar_festivos <año>`**, que agrega los festivos oficiales que faltan de ese año.
- **La carga inicial por migración:** los ítems de la §3.4 y los festivos oficiales de 2026 a 2030.
- **Los ítems de sistema** (`is_system`): "Codeudor" y "Referencia personal". Se les cambia el nombre y el orden, pero no el código ni el estado.
- **Crear, editar, desactivar y reactivar** ítems y festivos. Nunca se borran.
- **El servicio de lectura:** los ítems activos de un catálogo, un ítem por su código, los festivos de un rango y `is_business_day` con los festivos.
- **Las pantallas**, solo para el Administrador: un submenú "Catálogos" con siete entradas, un listado con DataTables por catálogo y un formulario de creación y edición.
- **La auditoría** de cada acción, con categoría `SECURITY` para los catálogos de texto y `FINANCIAL` para los festivos.
- **La actualización de la documentación:** `CLAUDE.md` y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- Los modelos que usan los catálogos (cliente, tercero, crédito, pago). Cada spec agrega su `ForeignKey` con `on_delete=PROTECT` y filtra los ítems activos.
- Exigir un texto libre cuando se elige "Otro" u "Otra". Lo decide cada spec que usa el catálogo.
- Pasar el tipo de documento de los usuarios internos al catálogo. Sigue con la lista fija de la SPEC 04 (decisión de la SPEC 06).
- Aplicar los festivos al calendario de cuotas. Lo hace el motor (SPEC 10), que recibe la lista de fechas.
- Calcular festivos al vuelo para un año sin carga.
- Importar festivos de un archivo o de un servicio externo.
- Festivos por región o por ciudad.
- Restablecer los festivos oficiales de un año a su valor calculado.
- Ítems de sistema en otros catálogos. Si una spec futura necesita uno, lo agrega con su migración de datos.
- Traducir los nombres de los ítems. Son datos, no textos de la interfaz.

---

## 3. Modelo de datos

### 3.1 La base de los catálogos de texto (`apps/parametros/models.py`)

```python
CODE_VALIDATOR = RegexValidator(r"^[A-Z0-9_]+$", _("Usa letras mayúsculas sin tildes, números y guion bajo."))


class CatalogItemQuerySet(models.QuerySet):
    def active(self) -> Self: ...       # is_active=True, en el orden del catálogo


class CatalogItem(models.Model):
    code = models.CharField(max_length=30, validators=[CODE_VALIDATOR])
    name = models.CharField(max_length=100)
    display_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    is_system = models.BooleanField(default=False, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="+")

    objects = CatalogItemQuerySet.as_manager()

    class Meta:
        abstract = True
        ordering = ("display_order", "name")
        default_permissions = ("view", "add", "change")
        constraints = [
            models.UniqueConstraint(fields=["code"], name="%(app_label)s_%(class)s_unique_code"),
            models.UniqueConstraint(Lower("name"), name="%(app_label)s_%(class)s_unique_name"),
            models.CheckConstraint(condition=Q(is_system=False) | Q(is_active=True),
                                   name="%(app_label)s_%(class)s_system_active"),
        ]


class DocumentType(CatalogItem): ...            # "tipo de documento"
class Occupation(CatalogItem): ...              # "ocupación"
class CreditPurpose(CatalogItem): ...           # "destino de crédito"
class VoidReason(CatalogItem): ...              # "motivo de anulación"
class RejectionReason(CatalogItem): ...         # "motivo de rechazo"
class ThirdPartyRelationType(CatalogItem): ...  # "tipo de relación de terceros"
```

Cada subclase hereda el `Meta` de la base y fija su `verbose_name` y `verbose_name_plural`. Todos los campos llevan `verbose_name` y `help_text` en español con `gettext_lazy`.

Reglas de los ítems:

- **El código no cambia después de crearse.** Es la clave con la que el código y los datos de ejemplo buscan un ítem. El nombre y el orden sí cambian.
- **El código se escribe o se genera.** Si el formulario lo deja vacío, el servicio lo genera del nombre: mayúsculas, sin tildes, y los espacios y signos pasan a `_` ("Pago de arriendo" → `PAGO_DE_ARRIENDO`). Si ese código ya existe, agrega `_2`, `_3` y así.
- **El código se guarda en mayúsculas** aunque se escriba en minúsculas.
- **El nombre es único en su catálogo, sin distinguir mayúsculas**, después de quitar los espacios de los extremos.
- **Un ítem de sistema siempre está activo** (`CheckConstraint`). Ni el servicio ni la base permiten desactivarlo.
- **`is_system` solo lo fija una migración de datos.** El formulario no lo muestra y el servicio lo ignora.
- **No existe el permiso `delete`**, y `delete()` lanza `PermissionDenied`. Un ítem desactivado deja de ofrecerse en los formularios nuevos, pero los registros que ya lo usan lo siguen mostrando.

### 3.2 Los festivos (`apps/parametros/models.py`)

```python
class HolidayOrigin(models.TextChoices):
    OFFICIAL = "official", _("Oficial")
    CUSTOM = "custom", _("Propio")


class Holiday(models.Model):
    date = models.DateField()
    name = models.CharField(max_length=100)
    origin = models.CharField(max_length=10, choices=HolidayOrigin.choices,
                              default=HolidayOrigin.CUSTOM, editable=False)
    official_code = models.CharField(max_length=40, blank=True, default="", editable=False)
    official_year = models.PositiveSmallIntegerField(null=True, blank=True, editable=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ("date",)
        default_permissions = ("view", "add", "change")
        constraints = [
            # Un solo festivo activo por fecha.
            models.UniqueConstraint(fields=["date"], condition=Q(is_active=True),
                                    name="parametros_holiday_unique_active_date"),
            # Un festivo oficial se identifica por su año y su código.
            models.UniqueConstraint(fields=["official_year", "official_code"],
                                    condition=Q(origin="official"),
                                    name="parametros_holiday_unique_official"),
            # Oficial ⇔ tiene código y año; propio ⇔ no tiene ninguno de los dos.
            models.CheckConstraint(condition=(Q(origin="official") & ~Q(official_code="")
                                              & Q(official_year__isnull=False))
                                             | (Q(origin="custom") & Q(official_code="")
                                                & Q(official_year__isnull=True)),
                                   name="parametros_holiday_origin_fields"),
        ]
```

Reglas de los festivos:

- **Los festivos oficiales solo los crean la migración y el comando.** El formulario siempre crea festivos propios.
- **Un festivo oficial se puede editar** (fecha y nombre) **y desactivar.** Conserva su origen, su código y su año. Así se corrige un festivo que una ley cambió sin esperar a una spec.
- **`official_year` es el año para el que se calculó**, no el de la fecha. Si se edita la fecha de un oficial a otro año, el comando de su año sigue reconociéndolo.
- **No hay dos festivos activos en la misma fecha.** Crear, editar o reactivar uno en una fecha ocupada lanza `ValidationError` con "Ya hay un festivo activo el <fecha>."
- **No existe el permiso `delete`**, y `delete()` lanza `PermissionDenied`.

### 3.3 El cálculo de los festivos oficiales (`apps/parametros/holidays.py`)

Módulo de lógica pura: no importa Django ni consulta la base de datos.

```python
@dataclass(frozen=True)
class OfficialHoliday:
    code: str
    name: str
    date: date


def easter_sunday(year: int) -> date: ...                # algoritmo gregoriano anónimo (Meeus/Jones/Butcher)
def colombian_holidays(year: int) -> list[OfficialHoliday]: ...  # 18 festivos, ordenados por fecha
```

`colombian_holidays` aplica la Ley 51 de 1983 (Ley Emiliani). `P` es el Domingo de Pascua y "al lunes" significa el mismo día si es lunes o el lunes siguiente:

| Código | Nombre | Regla |
|---|---|---|
| `ano_nuevo` | Año Nuevo | 1 de enero |
| `reyes_magos` | Día de los Reyes Magos | 6 de enero, al lunes |
| `san_jose` | Día de San José | 19 de marzo, al lunes |
| `jueves_santo` | Jueves Santo | P − 3 días |
| `viernes_santo` | Viernes Santo | P − 2 días |
| `dia_trabajo` | Día del Trabajo | 1 de mayo |
| `ascension` | Ascensión del Señor | P + 43 días (lunes) |
| `corpus_christi` | Corpus Christi | P + 64 días (lunes) |
| `sagrado_corazon` | Sagrado Corazón | P + 71 días (lunes) |
| `san_pedro_san_pablo` | San Pedro y San Pablo | 29 de junio, al lunes |
| `independencia` | Día de la Independencia | 20 de julio |
| `batalla_boyaca` | Batalla de Boyacá | 7 de agosto |
| `asuncion` | La Asunción de la Virgen | 15 de agosto, al lunes |
| `dia_raza` | Día de la Raza | 12 de octubre, al lunes |
| `todos_santos` | Día de Todos los Santos | 1 de noviembre, al lunes |
| `independencia_cartagena` | Independencia de Cartagena | 11 de noviembre, al lunes |
| `inmaculada_concepcion` | Día de la Inmaculada Concepción | 8 de diciembre |
| `navidad` | Navidad | 25 de diciembre |

- Acepta años de 1984 a 2100. Fuera de ese rango lanza `ValueError`.
- Dos festivos pueden caer el mismo día: el Sagrado Corazón y San Pedro y San Pablo, cuando la Pascua es tardía (por ejemplo, el 30 de junio de 2025 y el 1 de julio de 2030). Es la única coincidencia posible. La función devuelve los dos; la carga guarda activo el primero de la tabla y deja el segundo desactivado (§3.6). Por eso 2030 queda con 18 festivos oficiales guardados y 17 activos.
- Requiere 100 % de cobertura, como el motor.

### 3.4 Carga inicial

**`0003_catalogs.py`** crea las siete tablas. **`0004_initial_catalogs.py`** crea los ítems, con `display_order` de 10 en 10 en el orden de la tabla. **`0005_initial_holidays.py`** carga los festivos oficiales de 2026 a 2030 con `colombian_holidays`. Las reversas de las dos migraciones de datos no hacen nada. Ninguna de las dos audita: no hay actor, como la `0002_initial_settings.py` de la SPEC 06.

| Catálogo | Ítems (código → nombre) |
|---|---|
| Tipos de documento | `CC` Cédula de ciudadanía · `CE` Cédula de extranjería · `PPT` Permiso por protección temporal · `PA` Pasaporte · `TI` Tarjeta de identidad |
| Ocupaciones | `COMERCIANTE` Comerciante · `TENDERO` Tendero · `VENDEDOR_AMBULANTE` Vendedor ambulante · `EMPLEADO` Empleado · `INDEPENDIENTE` Independiente · `TRANSPORTADOR` Transportador · `AMA_DE_CASA` Ama de casa · `OTRA` Otra |
| Destinos de crédito | `CAPITAL_TRABAJO` Capital de trabajo · `COMPRA_MERCANCIA` Compra de mercancía · `GASTOS_PERSONALES` Gastos personales · `VIVIENDA` Vivienda · `SALUD` Salud · `EDUCACION` Educación · `PAGO_DEUDAS` Pago de deudas · `OTRO` Otro |
| Motivos de anulación | `ERROR_DIGITACION` Error de digitación · `PAGO_DUPLICADO` Pago duplicado · `VALOR_INCORRECTO` Valor incorrecto · `CREDITO_EQUIVOCADO` Crédito equivocado · `OTRO` Otro |
| Motivos de rechazo | `CAPACIDAD_PAGO` Capacidad de pago insuficiente · `REFERENCIAS_NO_VERIFICADAS` Referencias no verificadas · `DOCUMENTACION_INCOMPLETA` Documentación incompleta · `HISTORIAL_MORA` Historial de mora · `OTRO` Otro |
| Tipos de relación de terceros | `CODEUDOR` Codeudor (sistema) · `REFERENCIA_PERSONAL` Referencia personal (sistema) · `FAMILIAR` Familiar · `OTRO` Otro |

Los códigos de los tipos de documento coinciden con los de la lista fija de los usuarios (SPEC 04).

Los códigos de los ítems de sistema quedan como constantes en `apps/parametros/catalogs.py` (`RELATION_CODEBTOR = "CODEUDOR"` y `RELATION_PERSONAL_REFERENCE = "REFERENCIA_PERSONAL"`), para que la SPEC 14 y la de terceros no escriban el texto a mano.

### 3.5 Registro de catálogos (`apps/parametros/catalogs.py`)

```python
@dataclass(frozen=True)
class Catalog:
    slug: str                 # parte de la URL
    model: type[CatalogItem]
    label: str                # "Tipos de documento", para el título y el menú
    order: int                # posición en el submenú


CATALOGS: tuple[Catalog, ...] = (
    Catalog("tipos-documento", DocumentType, _("Tipos de documento"), 10),
    Catalog("ocupaciones", Occupation, _("Ocupaciones"), 20),
    Catalog("destinos-credito", CreditPurpose, _("Destinos de crédito"), 30),
    Catalog("motivos-anulacion", VoidReason, _("Motivos de anulación"), 40),
    Catalog("motivos-rechazo", RejectionReason, _("Motivos de rechazo"), 50),
    Catalog("tipos-relacion", ThirdPartyRelationType, _("Tipos de relación de terceros"), 60),
)


def get_catalog(slug: str) -> Catalog: ...   # lanza KeyError si no existe
```

Las vistas, las URL, el menú y los permisos se arman recorriendo `CATALOGS`. Un catálogo de texto nuevo es una subclase de `CatalogItem`, su migración y una línea en `CATALOGS`.

### 3.6 Servicio (`apps/parametros/services.py`)

Las funciones de la SPEC 06 se conservan. Se agregan:

```python
# Lectura (sin permisos)
def get_active_items(model: type[CatalogItem]) -> QuerySet[CatalogItem]: ...
def get_item_by_code(model: type[CatalogItem], code: str) -> CatalogItem: ...
def get_holidays(start: date, end: date) -> frozenset[date]: ...
def is_business_day(day: date) -> bool: ...  # misma firma, ahora con festivos

# Catálogos de texto
def create_catalog_item(actor: User, catalog: Catalog, data: Mapping[str, Any]) -> CatalogItem: ...
def update_catalog_item(actor: User, item: CatalogItem, data: Mapping[str, Any]) -> CatalogItem: ...
def deactivate_catalog_item(actor: User, item: CatalogItem) -> CatalogItem: ...
def reactivate_catalog_item(actor: User, item: CatalogItem) -> CatalogItem: ...

# Festivos
def create_holiday(actor: User, data: Mapping[str, Any]) -> Holiday: ...
def update_holiday(actor: User, holiday: Holiday, data: Mapping[str, Any]) -> Holiday: ...
def deactivate_holiday(actor: User, holiday: Holiday) -> Holiday: ...
def reactivate_holiday(actor: User, holiday: Holiday) -> Holiday: ...
def load_official_holidays(year: int, *, actor: User | None = None) -> int: ...
def missing_official_years(years: Iterable[int]) -> list[int]: ...
```

| Función | Qué hace |
|---|---|
| `get_active_items` | Los ítems activos del catálogo, en el orden de `display_order` y `name`. |
| `get_item_by_code` | El ítem con ese código, activo o no. Lanza `model.DoesNotExist` si no existe. |
| `get_holidays` | Las fechas de los festivos activos entre `start` y `end`, los dos incluidos, de los dos orígenes. Lanza `ValueError` si `start` es posterior a `end`. Es lo que el calendario del motor recibe como lista de fechas. |
| `is_business_day` | `False` si el día de la semana está en `non_business_weekdays` o si hay un festivo activo en esa fecha. Un año sin festivos cargados solo descarta los días de la semana. |
| `create_catalog_item` | Verifica `parametros.add_<modelo>`, normaliza y genera el código (§3.1), valida con `full_clean()`, guarda con `updated_by=actor` y audita. |
| `update_catalog_item` | Verifica `parametros.change_<modelo>`. Solo toca `name` y `display_order`; un `code`, un `is_active` o un `is_system` en `data` se ignoran. Sin cambios no guarda ni registra. |
| `deactivate_catalog_item` | Verifica `change`. Lanza `CatalogRuleError` si el ítem es de sistema o ya está inactivo. |
| `reactivate_catalog_item` | Verifica `change`. Lanza `CatalogRuleError` si el ítem ya está activo. |
| `create_holiday` | Verifica `parametros.add_holiday`. Crea un festivo propio con `date` y `name`. |
| `update_holiday` | Verifica `parametros.change_holiday`. Solo toca `date` y `name`. Sin cambios no guarda ni registra. |
| `deactivate_holiday` y `reactivate_holiday` | Verifican `change`. Lanzan `CatalogRuleError` si el festivo ya está en ese estado. Reactivar en una fecha ocupada lanza `ValidationError`. |
| `load_official_holidays` | Calcula `colombian_holidays(year)` y crea cada festivo oficial que no exista con ese `official_year` y ese `official_code`. **No toca los que ya existen**, aunque estén desactivados o con otra fecha. Si la fecha ya tiene un festivo activo, crea el oficial desactivado. Devuelve cuántos creó y, si creó alguno, audita una sola vez. |
| `missing_official_years` | De los años recibidos, los que no tienen ningún festivo oficial. La pantalla lo usa para el aviso. |

Reglas:

- **`CatalogRuleError`** es una subclase de `ValidationError`, como `UserRuleError` de la SPEC 04. La vista muestra su mensaje con `messages.error`.
- **Todos los servicios de edición** toman la fila con `select_for_update()`, toman un `snapshot` antes y después, y llaman a `record` dentro de la misma `transaction.atomic()`.
- **`require_perms` se importa dentro de cada función de edición**, por el ciclo de importación que ya documentó la SPEC 06 (§6.1).
- **Fuera de `apps/parametros`, nadie consulta estos modelos con `objects` para leer**: pasan por `get_active_items` y `get_item_by_code`. Las specs futuras sí declaran `ForeignKey` a ellos.

### 3.7 Comando `cargar_festivos` (`apps/parametros/management/commands/cargar_festivos.py`)

```
uv run python manage.py cargar_festivos 2031
uv run python manage.py cargar_festivos 2031 2032
```

- Recibe uno o más años. Un año fuera de 1984 a 2100 termina con error sin cargar ninguno.
- Envuelve el trabajo en `with audit_context(source=AuditSource.COMMAND):` y llama a `load_official_holidays(year)` sin actor.
- Escribe por cada año "2031: 18 festivos creados." o "2031: no faltaba ningún festivo." con `self.stdout`.
- Correrlo dos veces con el mismo año no crea nada la segunda vez.

### 3.8 Auditoría

| Acción | Valor | Etiqueta | Categoría |
|---|---|---|---|
| `CATALOG_ITEM_CREATED` | `catalogos.item_created` | "Ítem de catálogo creado" | `SECURITY` |
| `CATALOG_ITEM_UPDATED` | `catalogos.item_updated` | "Ítem de catálogo editado" | `SECURITY` |
| `CATALOG_ITEM_DEACTIVATED` | `catalogos.item_deactivated` | "Ítem de catálogo desactivado" | `SECURITY` |
| `CATALOG_ITEM_REACTIVATED` | `catalogos.item_reactivated` | "Ítem de catálogo reactivado" | `SECURITY` |
| `HOLIDAY_CREATED` | `festivos.created` | "Festivo creado" | `FINANCIAL` |
| `HOLIDAY_UPDATED` | `festivos.updated` | "Festivo editado" | `FINANCIAL` |
| `HOLIDAY_DEACTIVATED` | `festivos.deactivated` | "Festivo desactivado" | `FINANCIAL` |
| `HOLIDAY_REACTIVATED` | `festivos.reactivated` | "Festivo reactivado" | `FINANCIAL` |
| `HOLIDAYS_LOADED` | `festivos.loaded` | "Festivos oficiales cargados" | `FINANCIAL` |

- La entidad es el ítem o el festivo. El catálogo queda identificado por el tipo de contenido de la entidad.
- `changes` de creación guarda todos los campos auditables con `None` como valor anterior. Los campos auditables son `code`, `name`, `display_order` e `is_active` en los ítems, y `date`, `name`, `origin` e `is_active` en los festivos. Las fechas van en ISO 8601.
- `festivos.loaded` no tiene entidad. Guarda `extra={"year": 2031, "created": 18}`. Desde el comando, no tiene actor y su origen es `command`.
- Ningún campo es secreto, así que `SENSITIVE_FIELDS` no cambia.
- La migración `apps/auditoria/migrations/0004_catalog_actions.py` actualiza las `choices` de `AuditEvent.action`, como la `0003` de la SPEC 06.

### 3.9 Permisos y menú

- En `ROLE_PERMISSIONS`, el Administrador recibe `view`, `add` y `change` de los siete modelos (`CATALOG_PERMISSIONS` en `roles.py`). Ningún otro rol recibe permisos de catálogos.
- `apps/parametros/menu.py` agrega a la sección `configuracion` la entrada `parametros.catalogos` ("Catálogos", icono `fas fa-fw fa-list`, orden 20, `url_name=None`) con siete hijas: las seis de `CATALOGS`, en su orden, y "Festivos" al final (orden 70). Cada hija pide el permiso `view` de su modelo. El menú ya oculta un padre sin hijas visibles.

### 3.10 Pantallas

| Ruta | Método | Vista | Permiso |
|---|---|---|---|
| `/parametros/catalogos/<slug>/` | GET | `CatalogListView` | `view_<modelo>` |
| `/parametros/catalogos/<slug>/nuevo/` | GET, POST | `CatalogCreateView` | `add_<modelo>` |
| `/parametros/catalogos/<slug>/<pk>/editar/` | GET, POST | `CatalogUpdateView` | `change_<modelo>` |
| `/parametros/catalogos/<slug>/<pk>/desactivar/` | POST | `CatalogDeactivateView` | `change_<modelo>` |
| `/parametros/catalogos/<slug>/<pk>/reactivar/` | POST | `CatalogReactivateView` | `change_<modelo>` |
| `/parametros/festivos/` | GET | `HolidayListView` | `view_holiday` |
| `/parametros/festivos/nuevo/` | GET, POST | `HolidayCreateView` | `add_holiday` |
| `/parametros/festivos/<pk>/editar/` | GET, POST | `HolidayUpdateView` | `change_holiday` |
| `/parametros/festivos/<pk>/desactivar/` | POST | `HolidayDeactivateView` | `change_holiday` |
| `/parametros/festivos/<pk>/reactivar/` | POST | `HolidayReactivateView` | `change_holiday` |

- **Un `slug` que no está en `CATALOGS`** responde 404. Un `pk` que no existe en ese catálogo, también.
- **Los permisos de las vistas de catálogo** se resuelven del modelo del `slug`, así que una sola clase sirve a los seis.

**Listado de un catálogo** (`templates/parametros/catalog_list.html`, desde `tables.html`):

- Título con el nombre del catálogo y el botón "Nuevo".
- Tabla con `includes/datatable.html`: código, nombre, orden, estado y acciones.
- El estado es una insignia "Activo" (`badge-success`) o "Inactivo" (`badge-secondary`). Un ítem de sistema lleva además la insignia "Sistema" (`badge-info`) y no tiene botón de desactivar.
- Se listan activos e inactivos, en el orden del catálogo.
- Desactivar y reactivar son formularios `POST` con `data-confirm`.

**Formulario de un ítem** (`templates/parametros/catalog_form.html`, desde `blank.html` con la tarjeta de `cards.html`):

- Al crear: código (opcional, con la ayuda "Si lo dejas vacío, se genera del nombre."), nombre y orden.
- Al editar: el código se muestra como texto de solo lectura, no como campo.
- Al guardar bien, se vuelve al listado con "Se guardó <nombre>." Si no hubo cambios, "No hubo cambios en <nombre>."
- Al guardar con errores, la misma página responde 200 con los errores en sus campos.

**Listado de festivos** (`templates/parametros/holiday_list.html`):

- Un selector de año (`?anio=2027`, por defecto el año actual) con los años que tienen festivos más el actual y el siguiente. Un año no numérico o fuera de 1984 a 2100 vuelve al actual.
- Tabla con fecha (`format_date` y el día de la semana), nombre, origen ("Oficial" o "Propio"), estado y acciones.
- **El aviso:** si el año actual o el siguiente no tienen festivos oficiales, una alerta `alert-warning` dice "No hay festivos oficiales cargados para <año>. Pide a soporte que corra `cargar_festivos <año>`."
- El botón "Nuevo" crea un festivo propio.

**Formulario de un festivo** (`templates/parametros/holiday_form.html`): fecha (`<input type="date">`) y nombre. Al editar un oficial, se muestra su origen y su código como solo lectura.

**Comunes:**

- Los formularios son `ModelForm` (`apps/parametros/forms.py`) con `{{ form }}` y el renderizador de la SPEC 02. La vista llama al servicio, nunca a `form.save()`.
- Un GET a desactivar o reactivar responde 405.
- En celular (unos 375 px), la tabla usa el desplazamiento propio de DataTables y la página no se desplaza a lo ancho.

### 3.11 Archivos nuevos y modificados

**Nuevos:**

- `apps/parametros/holidays.py` y `catalogs.py`.
- `apps/parametros/management/__init__.py`, `management/commands/__init__.py` y `management/commands/cargar_festivos.py`.
- `apps/parametros/migrations/0003_catalogs.py`, `0004_initial_catalogs.py` y `0005_initial_holidays.py`.
- `apps/auditoria/migrations/0004_catalog_actions.py`.
- `templates/parametros/catalog_list.html`, `catalog_form.html`, `holiday_list.html` y `holiday_form.html`.
- `tests/parametros/test_holidays.py`, `test_catalog_models.py`, `test_catalog_services.py`, `test_holiday_services.py`, `test_catalog_views.py`, `test_holiday_views.py`, `test_cargar_festivos.py` y `test_catalog_audit.py`.
- Agregados durante la implementación (ver §6.1):
  - `tests/parametros/conftest.py` (fixtures `catalog_editor` y `no_perms_user`) y `tests/parametros/test_initial_catalogs.py` (la carga inicial).
  - `templates/parametros/includes/catalog_actions.html` y `holiday_actions.html` (las acciones de cada fila).

**Modificados:**

- `apps/parametros/models.py`, `services.py`, `forms.py`, `views.py`, `urls.py` y `menu.py`.
- `apps/auditoria/actions.py`.
- `apps/accounts/roles.py` y `tests/accounts/test_roles.py`.
- `CLAUDE.md` y `docs/specs-tentativas.md`.
- Modificados durante la implementación (ver §6.1):
  - `tests/parametros/test_services.py`: las fechas de prueba pasan a la semana del 21 al 23 de noviembre de 2026, porque el lunes 16 es festivo. Las pruebas de `is_business_day` con festivos quedaron en `test_catalog_services.py`.
  - `templates/includes/datatable.html`: el parámetro opcional `keep_order`.
  - `static/css/app.css`: las entradas de un submenú se parten en dos líneas.
  - `static/js/app.js`: en celular, el submenú de la página activa se cierra al cargar.

---

## 4. Plan de implementación

1. **Cálculo de festivos.** Escribir `holidays.py` con `easter_sunday` y `colombian_holidays`. Pruebas en `test_holidays.py` con 100 % de cobertura: los 18 festivos de 2026, la Pascua de varios años conocidos, cada regla de "al lunes" (un día que ya es lunes y uno que no), una coincidencia de dos festivos y los años fuera de rango.
2. **Modelos de catálogos.** Escribir `CatalogItem`, las seis subclases y `Holiday` con sus restricciones, y generar `0003_catalogs.py`. Pruebas en `test_catalog_models.py`: código y nombre únicos, ítem de sistema siempre activo, `delete()` rechazado, permisos sin `delete`, y las tres restricciones de `Holiday`.
3. **Carga inicial.** Escribir `0004_initial_catalogs.py` y `0005_initial_holidays.py`. Pruebas: después de `migrate` existen los ítems de la §3.4 con sus códigos y los 90 festivos oficiales de 2026 a 2030.
4. **Registro y lectura.** Escribir `catalogs.py` y los servicios de lectura, y ampliar `is_business_day`. Pruebas en `test_catalog_services.py` y `test_services.py`.
5. **Auditoría y servicios de edición.** Agregar las nueve acciones a `AuditAction` y `ACTION_CATEGORIES`, generar `auditoria/0004_catalog_actions.py` y escribir los servicios de edición de ítems y festivos, incluido `load_official_holidays`. Pruebas en `test_catalog_services.py`, `test_holiday_services.py` y `test_catalog_audit.py`: permisos, campos ignorados, generación del código, sin cambios sin registro, reglas de `CatalogRuleError` y reversión si `record` falla.
6. **Comando.** Escribir `cargar_festivos`. Pruebas en `test_cargar_festivos.py`: un año, varios años, un año inválido, la segunda corrida sin cambios y el registro con origen `command`.
7. **Permisos.** Agregar `CATALOG_PERMISSIONS` a `ROLE_PERMISSIONS` con su prueba de la matriz.
8. **Pantallas de catálogos.** Escribir los formularios, las vistas genéricas, las URL, las plantillas y las seis entradas del menú. Pruebas en `test_catalog_views.py`: permisos por rol, 404 por `slug`, crear, editar, desactivar, reactivar, ítem de sistema sin desactivar y 405.
9. **Pantallas de festivos.** Escribir las vistas, las plantillas, la entrada del menú y el aviso de años sin carga. Pruebas en `test_holiday_views.py`.
10. **Verificación en el navegador.** Recorrer con el MCP de Playwright como Administrador un catálogo y los festivos, en escritorio y a unos 375 px, y comparar con `tables.html`, `blank.html` y `cards.html`.
11. **Documentación.** Actualizar `CLAUDE.md` (estado del proyecto y una sección "Catálogos y festivos (SPEC 07)" con cómo leer un catálogo, cómo apuntar a él con una `ForeignKey` y cómo correr `cargar_festivos`) y `docs/specs-tentativas.md` (la SPEC 07 implementada y sus decisiones para las specs siguientes).

---

## 5. Criterios de aceptación

**Cálculo de festivos**

- [ ] `colombian_holidays(2026)` devuelve exactamente estas 18 fechas: 1 ene, 12 ene, 23 mar, 2 abr, 3 abr, 1 may, 18 may, 8 jun, 15 jun, 29 jun, 20 jul, 7 ago, 17 ago, 12 oct, 2 nov, 16 nov, 8 dic y 25 dic.
- [ ] `easter_sunday` devuelve el 5 de abril de 2026, el 28 de marzo de 2027 y el 16 de abril de 2028.
- [ ] Un festivo "al lunes" que ya cae en lunes no se mueve, y uno que cae en martes pasa al lunes siguiente.
- [ ] `colombian_holidays(1983)` y `colombian_holidays(2101)` lanzan `ValueError`.
- [ ] `apps/parametros/holidays.py` no importa nada de `django` y tiene 100 % de cobertura.

**Modelo y carga inicial**

- [ ] Después de `migrate` sobre una base vacía, cada catálogo tiene exactamente los ítems de la §3.4, con sus códigos, activos y en ese orden.
- [ ] "Codeudor" y "Referencia personal" tienen `is_system=True`, y ningún otro ítem lo tiene.
- [ ] Después de `migrate` existen 90 festivos oficiales, 18 por cada año de 2026 a 2030.
- [ ] Crear dos ítems con el mismo código, o con nombres que solo difieren en mayúsculas, en el mismo catálogo falla. En catálogos distintos se permite.
- [ ] Desactivar un ítem de sistema por SQL falla con `..._system_active`.
- [ ] Dos festivos activos en la misma fecha fallan con `parametros_holiday_unique_active_date`; uno activo y uno inactivo en la misma fecha se permiten.
- [ ] Un festivo propio con `official_code` o un oficial sin `official_year` falla con `parametros_holiday_origin_fields`.
- [ ] `delete()` sobre un ítem o un festivo lanza `PermissionDenied`, y las siete tablas solo tienen los permisos `view`, `add` y `change`.

**Lectura**

- [ ] `get_active_items(Occupation)` no incluye un ítem desactivado y respeta `display_order`.
- [ ] `get_item_by_code(ThirdPartyRelationType, RELATION_CODEBTOR)` devuelve "Codeudor".
- [ ] `get_holidays(date(2026, 1, 1), date(2026, 3, 31))` devuelve 1 ene, 12 ene y 23 mar, e incluye un festivo propio activo del rango y no uno inactivo.
- [ ] Con los valores por defecto, `is_business_day` devuelve `False` el 12 de enero de 2026 (festivo en lunes), `False` un domingo, `True` el 13 de enero de 2026 y `True` el lunes 6 de enero de 2031 (Reyes Magos, pero de un año sin carga).
- [ ] Desactivar el festivo del 12 de enero de 2026 hace que `is_business_day(date(2026, 1, 12))` devuelva `True` en la siguiente llamada.

**Servicios de edición**

- [ ] Crear "Pago de arriendo" sin código en Destinos de crédito genera `PAGO_DE_ARRIENDO`; crear "Capital trabajo", cuyo código generado `CAPITAL_TRABAJO` ya existe, genera `CAPITAL_TRABAJO_2`; y crear "otro" falla por nombre repetido.
- [ ] Un código escrito como `vendedor_feria` se guarda como `VENDEDOR_FERIA`, y uno con tilde o espacio se rechaza.
- [ ] `update_catalog_item` con `code`, `is_active` o `is_system` en `data` no cambia esos campos.
- [ ] Desactivar un ítem de sistema o uno ya inactivo lanza `CatalogRuleError` y no crea registros de auditoría.
- [ ] Crear un festivo propio en una fecha con un festivo activo lanza `ValidationError` con el mensaje de la §3.2.
- [ ] Editar la fecha de un festivo oficial conserva su origen, su código y su año.
- [ ] `load_official_holidays(2031)` crea 18 festivos y devuelve 18; llamarlo otra vez devuelve 0 y no crea registros de auditoría.
- [ ] Si el Administrador desactiva un festivo oficial de 2027 y se carga 2027 otra vez, el festivo sigue desactivado y no aparece un duplicado.
- [ ] Si hay un festivo propio activo en una fecha que el cálculo da como oficial, la carga crea el oficial desactivado y el propio sigue activo.
- [ ] Un servicio de edición llamado por un usuario sin el permiso lanza `PermissionDenied` y no crea registros.

**Comando**

- [ ] `cargar_festivos 2031 2032` crea 36 festivos y escribe una línea por año.
- [ ] `cargar_festivos 2031 1980` termina con error y no crea ningún festivo de 2031.
- [ ] El registro `festivos.loaded` del comando tiene origen `command`, no tiene actor y guarda `year` y `created` en `extra`.

**Pantallas y permisos**

- [ ] El Administrador ve "Catálogos" en la sección "Configuración" con siete entradas, y cada listado responde 200.
- [ ] Supervisor, Cajero/Cobrador y Consulta no ven "Catálogos", y todas las rutas de la §3.10 les responden 403.
- [ ] `/parametros/catalogos/no-existe/` responde 404, y un `pk` de otro catálogo en la ruta de editar responde 404.
- [ ] Crear, editar, desactivar y reactivar un ítem desde la pantalla redirige al listado con su mensaje y deja el cambio guardado.
- [ ] El listado de Tipos de relación muestra la insignia "Sistema" en Codeudor y Referencia personal, sin botón de desactivar.
- [ ] Al editar un ítem, el código no es un campo del formulario; enviar `code` en el POST no lo cambia.
- [ ] Guardar con errores responde 200 y muestra el error en su campo. Guardar sin cambios muestra "No hubo cambios en <nombre>." y no crea registros de auditoría.
- [ ] Un GET a una ruta de desactivar o reactivar responde 405.
- [ ] `/parametros/festivos/?anio=2027` lista los 18 festivos de 2027 con su día de la semana, y `?anio=abc` muestra el año actual.
- [ ] Sin festivos oficiales del año siguiente, el listado de festivos muestra el aviso de la §3.10; con ellos cargados, no lo muestra.
- [ ] Con Playwright, los listados se ven con la estructura de `tables.html` y los formularios con la de `blank.html` y `cards.html`; a unos 375 px la página no se desplaza a lo ancho; y la consola no muestra errores.

**Auditoría**

- [ ] Cada servicio de edición crea su acción de la §3.8 con su categoría, el `actor` como actor y el ítem o festivo como entidad.
- [ ] La creación deja en `changes` los campos auditables con `None` como valor anterior, y la edición solo los que cambiaron.
- [ ] Si `record` lanza una excepción dentro de un servicio de edición, el ítem o el festivo no cambia.

**Calidad y documentación**

- [ ] `uv run pytest --cov` pasa, y `apps/parametros` tiene al menos 90 % de cobertura.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] Todos los textos visibles nuevos están envueltos en `gettext`, `gettext_lazy` o `{% translate %}`.
- [ ] `CLAUDE.md` explica cómo leer un catálogo, cómo apuntar a él con una `ForeignKey` y cómo cargar los festivos de un año.
- [ ] `docs/specs-tentativas.md` marca la SPEC 07 como implementada.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** un modelo abstracto `CatalogItem` y una tabla por catálogo. Las `ForeignKey` de clientes, terceros, créditos y pagos apuntan a la tabla correcta, y la base garantiza que un tipo de documento no sea una ocupación.
- **No:** una sola tabla con un campo `kind`. Una `ForeignKey` no puede limitarse a un `kind` en la base, y el error solo se evitaría en la aplicación.
- **Sí:** un registro `CATALOGS` con vistas, URL y menú genéricos. Los seis catálogos se comportan igual, y uno nuevo cuesta una subclase y una línea.
- **Sí:** el código no cambia después de crearse, y se genera del nombre si se deja vacío. El código es la clave estable de las specs futuras y de los datos de ejemplo, y el Administrador no tiene que inventarlo.
- **Sí:** `is_system` para los ítems que el código busca por su código: hoy "Codeudor" y "Referencia personal". Se les cambia el nombre, pero no se desactivan ni cambian de código, así la SPEC 14 no se rompe.
- **No:** ítems sin protección. Desactivar "Codeudor" dejaría sin forma de asociar codeudores.
- **Sí:** nunca se borra un ítem ni un festivo, solo se desactiva. Los registros financieros que los usen tienen que seguir mostrándolos, y la §2 prohíbe el borrado físico de lo que alimenta lo financiero.
- **No:** borrar mientras nadie lo use. Hoy todo sería borrable, y el comportamiento cambiaría en cuanto llegue la spec de clientes.
- **Sí:** la carga inicial propuesta de la §3.4, con los mismos códigos de documento que los usuarios internos y sin NIT. Son los valores habituales del gota a gota, y el Administrador los ajusta después.
- **Sí:** los festivos oficiales se calculan con una función pura propia (Ley 51 de 1983 y la Pascua). Son 18 reglas estables y verificables con pruebas.
- **No:** el paquete `holidays` de PyPI. Es una dependencia nueva que exigiría un ADR, y su calendario puede cambiar entre versiones sin que nadie lo revise.
- **No:** una lista de fechas escrita a mano en la migración. Hay que mantenerla cada año y es fácil equivocarse con la Pascua.
- **Sí:** la migración carga 2026 a 2030, y `cargar_festivos <año>` agrega más años. Cubre los créditos de hoy con margen.
- **Sí:** un año sin carga no tiene festivos, y la pantalla avisa cuando falta el año actual o el siguiente. Es predecible: `is_business_day` solo usa datos guardados que el Administrador controla.
- **No:** calcular al vuelo un año sin carga. Mezclaría datos guardados con calculados y no respetaría una desactivación manual.
- **Sí:** la carga solo agrega lo que falta y nunca toca un festivo oficial que ya existe. Una corrección manual (por ejemplo, un cambio de ley) no se deshace sin querer.
- **No:** una opción `--reset` para restablecer un año. Puede llegar en otra spec si hace falta.
- **Sí:** los días que el negocio no abre (§9.2) son festivos de origen "propio" en la misma tabla. Cuentan igual en `is_business_day`, y el comando no los toca.
- **Sí:** un solo festivo activo por fecha. Dos registros activos el mismo día no cambian nada y confundirían el listado; cuando el cálculo da dos festivos el mismo día, el segundo queda desactivado.
- **Sí:** un festivo oficial se puede editar y desactivar. Es la vía para corregir un festivo sin esperar a una spec, y su `official_year` y `official_code` lo siguen identificando.
- **Sí:** los festivos auditan con `FINANCIAL`, porque cambian el calendario de cobro (como la regla de corrimiento en la SPEC 06). Los catálogos de texto auditan con `SECURITY`, como el grupo de negocio de la SPEC 06.
- **No:** una categoría nueva "Configuración". Cambiaría una decisión de la SPEC 05 y obligaría a definir su retención.
- **Sí:** cuatro acciones genéricas para los seis catálogos de texto. El catálogo queda identificado por el tipo de contenido de la entidad, y no hace falta una acción por catálogo.
- **Sí:** solo el Administrador gestiona y ve los catálogos (§6.2). El resto del sistema lee los ítems activos por el servicio, sin permisos.
- **Sí:** un submenú "Catálogos" con siete entradas y una página por catálogo. Sigue los listados de `tables.html` y evita pestañas con JavaScript.
- **No:** una página con pestañas y modales. Más JavaScript y una página pesada.
- **Sí:** el tipo de documento de los usuarios internos sigue con la lista fija de la SPEC 04 (decisión de la SPEC 06). Los códigos coinciden, por si algún día se unifican.

### 6.1 Decisiones tomadas durante la implementación

- **Sí:** el ejemplo de coincidencia de la §3.3 se corrigió. San José (lunes) y Jueves Santo (jueves) nunca coinciden; la única coincidencia posible es el Sagrado Corazón con San Pedro y San Pablo (22 veces entre 1984 y 2100). Como pasa en 2030, ese año queda con 18 festivos oficiales guardados y 17 activos. Decisión de la persona durante el paso 1.
- **Sí:** `next_monday` y `generate_code` son funciones públicas, para probar la regla del lunes y la generación del código por separado. Un nombre sin letras ni números genera `ITEM`, y el código nunca pasa de 30 caracteres con su sufijo.
- **Sí:** la normalización del código (mayúsculas y sin espacios) está en `CatalogItem.clean_fields()` y no en `clean()`. Django valida los campos antes de `clean()`, y `vendedor_feria` se rechazaba antes de pasar a mayúsculas.
- **Sí:** las unicidades del nombre de un ítem y de la fecha de un festivo activo se revisan también en `clean()`, para que el error salga en su campo. La restricción de la base sigue de respaldo. `Holiday.clean()` importa `format_date` dentro de la función, por el ciclo `formatting → services → models`.
- **Sí:** la carga inicial de los catálogos (`0004`) lleva los datos escritos en la migración, sin importar el código de la app. La de festivos (`0005`) sí importa `colombian_holidays`, como dice la §3.4.
- **Sí:** `load_official_holidays` con un actor exige `parametros.add_holiday`. Sin actor (el comando) no verifica permisos.
- **Sí:** `cargar_festivos` valida todos los años antes de cargar ninguno, quita los repetidos y usa el singular con un solo festivo ("1 festivo creado.").
- **Sí:** `CATALOG_PERMISSIONS` escribe los nombres de los modelos en `roles.py` sin importar `parametros.catalogs`, para no arriesgar un ciclo al cargar `accounts`. Una prueba lo compara con `CATALOGS`.
- **Sí:** cada listado de catálogo tiene una ruta con nombre propio (`Catalog.list_url_name`, por ejemplo `parametros:catalog_ocupaciones`), aunque la URL siga siendo `catalogos/<slug>/`. El menú de la SPEC 02 resuelve cada entrada con `reverse(url_name)` sin argumentos y marca la activa por ese nombre. No se tocó `apps/core`.
- **Sí:** las acciones de cada fila se dibujan con una plantilla pequeña (`render_to_string` con `request`), para dejar el `csrf_token` y los textos de confirmación en plantillas.
- **Sí:** los mensajes de desactivar y reactivar son "Se desactivó <nombre>." y "Se reactivó <nombre>.". El botón de crear festivos dice "Nuevo festivo propio", y el año se cambia con un formulario GET y el botón "Ver año", sin JavaScript. Después de guardar un festivo se vuelve al listado en el año del festivo.
- **Sí:** `includes/datatable.html` acepta `keep_order`, que agrega `data-order="[]"` para que DataTables no reordene por la primera columna al cargar. Sin él, los catálogos salían por código y no en su orden. Las tablas que no lo pasan no cambian.
- **Sí:** la celda de fecha de los festivos lleva antes, oculta, la fecha ISO. DataTables ordena por el texto de la celda, y así el orden es cronológico aunque la fecha se muestre como `d/m/Y`.
- **Sí:** las entradas de un submenú pueden partirse en dos líneas (`static/css/app.css`). "Tipos de relación de terceros" se salía de la caja blanca. Se detectó en la verificación con Playwright.
- **Sí:** en pantallas de menos de 768 px, `static/js/app.js` cierra al cargar el submenú de la página activa. SB Admin 2 lo dibuja flotando sobre el contenido y solo lo cierra al cambiar el tamaño de la ventana. Se detectó en la verificación con Playwright; decisión de la persona durante el paso 10.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| `parametros.DocumentType` (modelo) tiene el mismo nombre que `accounts.DocumentType` (opciones fijas de los usuarios). | Viven en módulos distintos. Las importaciones fuera de su app usan el módulo completo o un alias (`from apps.parametros.models import DocumentType as DocumentTypeItem`), y `CLAUDE.md` lo advierte. |
| La migración `0005_initial_holidays.py` importa `colombian_holidays` del código de la app; si la función cambia, una base nueva se carga distinto que una vieja. | La función es pura y estable, con pruebas fijas por año. Si una ley cambia los festivos, se corrige la función y se ajustan los años ya cargados a mano o con una migración nueva, nunca editando la `0005`. |
| Una ley nueva agrega o mueve un festivo y nadie actualiza los datos. | El Administrador puede crear un festivo propio o editar el oficial desde la pantalla. La corrección del cálculo va en una spec nueva. |
| Nadie corre `cargar_festivos` y un año queda sin festivos. | La pantalla de festivos avisa cuando falta el año actual o el siguiente, y la migración ya deja cinco años. |
| Las pruebas transaccionales vacían las tablas con `flush`, y los ítems de la carga inicial desaparecen. | Las pruebas que necesitan ítems los crean con un fixture o no usan `transaction=True`. Las pruebas de carga inicial usan la base de pruebas normal, donde las migraciones de datos ya corrieron. |
| Un cambio de festivo después de desembolsar un crédito no mueve sus cuotas. | Es intencional: el plan de pagos es un snapshot inmutable (§9.5). Los festivos solo afectan a los cálculos nuevos. |
| Agregar acciones nuevas cambia las `choices` de `AuditEvent.action`. | La migración `auditoria/0004_catalog_actions.py` es una operación vacía en la base y no toca el trigger, como la `0003` de la SPEC 06. |

---

## Lo que **no** entra en esta spec

- Los modelos de cliente, tercero, crédito y pago que usarán los catálogos.
- Exigir texto libre al elegir "Otro" u "Otra".
- El tipo de documento de los usuarios internos en el catálogo.
- Aplicar los festivos al calendario de cuotas (SPEC 10).
- Calcular festivos al vuelo, importarlos de afuera o tenerlos por región.
- Restablecer los festivos oficiales de un año.
- Ítems de sistema en otros catálogos.

Cada uno de estos puntos, si llega, va en su propia spec.
