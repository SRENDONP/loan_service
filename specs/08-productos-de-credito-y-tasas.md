# SPEC 08 — Productos de crédito y tasas

> **Estado:** Implementado
> **Depende de:** SPEC 02, SPEC 04, SPEC 05, SPEC 06, SPEC 07
> **Fecha:** 2026-11-13
> **Objetivo:** Que el Administrador configure desde `/parametros/` los productos de crédito, con su método de interés, sus condiciones y un historial de tasas con vigencia, y los topes de tasa (la usura y otros) con su propio historial.

---

## 1. Por qué existe esta spec

La §10.2 de la constitución pide que cada producto de crédito tenga su propia configuración, y la §10.3 exige tasas con historial de vigencia y una validación contra la tasa de usura. La 006 de la hoja tentativa es esta spec, que pasa a ser la SPEC 08. Las decisiones D4, D6, D12, D14 y D15 fijan su contenido.

Los productos tienen que existir antes del simulador (SPEC 12) y de la solicitud de créditos (SPEC 16). El motor (SPEC 09 a 11) no depende de esta spec: recibe la tasa, el método y la periodicidad como parámetros.

En la fase de preguntas salieron tres temas de fondo:

- **La usura frente al gota a gota.** Un crédito plano típico (100.000 al 10 % en 20 cuotas diarias de 5.500) equivale a unos 2.900 % EA, muy por encima del tope legal. La persona decidió mantener la §10.3 tal cual: **la tasa que supera el tope se bloquea**.
- **Dónde se valida.** En los métodos planos, la EA depende del plazo y de la periodicidad, no solo de la tasa. El cálculo exacto (TIR) llega con el motor III (SPEC 11). Por eso **la validación se hace en cada crédito** (SPEC 12 y 16), con el plan real. Esta spec guarda los topes y su historial, pero no compara.
- **Topes distintos de la usura.** El sistema maneja un catálogo de tipos de tope, como un tope interno del negocio. La usura **siempre** aplica, y el producto puede sumar un tope adicional. Gana el más estricto. Así se respeta la §10.3 sin enmienda.

---

## 2. Alcance

**Entra:**

- **Productos de crédito** (`CreditProduct`), con los campos de la §10.2 que aplican aquí (§3.2).
- **Los seis métodos de interés** de la sección 1.1 de la hoja tentativa, como opciones cerradas (D12). El motor de cada uno llega en la SPEC 09 o en la 11.
- **La unidad de la tasa, fijada por el método:** por crédito, mensual o por periodo. Un método con tasa por periodo admite una sola periodicidad.
- **Las cuatro periodicidades** (D4): las permitidas y la de por defecto.
- **El historial de tasas del producto** (`ProductRateVersion`): mínima, por defecto y máxima, con fecha desde y fecha hasta. Una versión nueva rige desde hoy o desde una fecha futura.
- **Anular una versión programada** que todavía no rige.
- **Las condiciones del producto:** monto, cuotas, periodos de gracia sin cuota, mora (porcentaje diario, tope y tolerancia), días para castigar, gasto inicial, límite de créditos activos por cliente y un redondeo propio opcional.
- **El catálogo de tipos de tope** (`RateCapType`), con "Usura" como ítem de sistema, creado por migración y sin valor.
- **El historial de valores de cada tope** (`RateCapValue`), en % EA, con fecha desde, fecha hasta y la referencia de la resolución.
- **El servicio de lectura** que usarán el simulador y la solicitud: productos ofrecibles, la versión de tasa vigente en una fecha, los topes que aplican a un producto y su redondeo.
- **Las pantallas:** productos y topes de tasa, en la sección "Configuración". El Administrador edita, y el Supervisor y Consulta solo ven.
- **La auditoría** de cada acción, con categoría `FINANCIAL`.
- **La actualización de la documentación:** `CLAUDE.md` y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- Validar una tasa contra los topes. Lo hacen el simulador (SPEC 12) y la solicitud (SPEC 16), con la EA del plan que calcula la SPEC 11.
- Convertir una tasa a efectiva anual. Es de la SPEC 11.
- Calcular cuotas, el calendario o la gracia. Es del motor (SPEC 09 a 11).
- Congelar la tasa y las condiciones en el crédito. Lo hace la SPEC 16 al aprobar.
- Contar los créditos activos de un cliente. El producto guarda el límite y la SPEC 16 lo aplica.
- Aplicar el gasto inicial. Lo hace el desembolso (SPEC 17).
- Calcular la mora y comparar su valor con la usura. Lo hace la SPEC 20.
- Castigar un crédito. Lo hace la SPEC 21 con los días que guarda el producto.
- El codeudor. Es un campo del crédito, no del producto (D16, SPEC 16).
- Gracia con pago de solo interés, y días entre el desembolso y la primera cuota.
- Varios conceptos de gasto inicial por producto.
- Un tope por modalidad de crédito (consumo, microcrédito) atado a la Superfinanciera. El catálogo de topes lo permite a mano, pero sin integración.
- Importar el tope de usura de un servicio externo.
- Corregir una versión de tasa que ya rige. Se programa una nueva.

---

## 3. Modelo de datos

### 3.1 Opciones fijas (`apps/parametros/models.py`)

```python
class InterestMethod(models.TextChoices):
    FLAT_PER_CREDIT = "flat_per_credit", _("Plano fijo por crédito")
    FLAT_MONTHLY_PRORATED = "flat_monthly_prorated", _("Plano mensual prorrateado")
    FLAT_PER_INSTALLMENT = "flat_per_installment", _("Plano por cuota")
    FRENCH = "french", _("Cuota fija (francés)")
    GERMAN = "german", _("Capital fijo (alemán)")
    DECLINING_BALANCE = "declining_balance", _("Interés sobre saldo")


class RateUnit(models.TextChoices):
    PER_CREDIT = "per_credit", _("% por crédito")
    MONTHLY = "monthly", _("% mensual")
    PER_PERIOD = "per_period", _("% por periodo")


METHOD_RATE_UNIT: dict[InterestMethod, RateUnit] = {
    InterestMethod.FLAT_PER_CREDIT: RateUnit.PER_CREDIT,
    InterestMethod.FLAT_MONTHLY_PRORATED: RateUnit.MONTHLY,
    InterestMethod.FLAT_PER_INSTALLMENT: RateUnit.PER_PERIOD,
    InterestMethod.FRENCH: RateUnit.PER_PERIOD,
    InterestMethod.GERMAN: RateUnit.PER_PERIOD,
    InterestMethod.DECLINING_BALANCE: RateUnit.PER_PERIOD,
}


class Periodicity(models.TextChoices):
    DAILY = "daily", _("Diaria")
    WEEKLY = "weekly", _("Semanal")
    BIWEEKLY = "biweekly", _("Quincenal")
    MONTHLY = "monthly", _("Mensual")


class InitialChargeType(models.TextChoices):
    NONE = "none", _("Sin gasto inicial")
    FIXED = "fixed", _("Valor fijo")
    PERCENT = "percent", _("Porcentaje del monto")
```

- **Los valores no cambian nunca** después de usarse. El motor (SPEC 09 a 11) y el simulador (SPEC 12) se apoyan en ellos.
- **El método fija la unidad de la tasa** (`METHOD_RATE_UNIT`). La tasa siempre se guarda en esa unidad, como porcentaje: `10.0000` es 10 %.
- **Con unidad `per_period`**, el producto admite exactamente una periodicidad. Así "0,5 % por periodo" siempre significa lo mismo. Para ofrecer el mismo método en diario y en semanal, se crean dos productos.

### 3.2 El producto (`apps/parametros/models.py`)

```python
MONEY = {"max_digits": 14, "decimal_places": 2}
PERCENT = {"max_digits": 7, "decimal_places": 4}   # hasta 100.0000


class CreditProduct(models.Model):
    # Identificación
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)

    # Método y periodicidad
    interest_method = models.CharField(max_length=30, choices=InterestMethod.choices)
    allowed_periodicities = ArrayField(models.CharField(max_length=10, choices=Periodicity.choices))
    default_periodicity = models.CharField(max_length=10, choices=Periodicity.choices)

    # Monto y cuotas
    min_amount = models.DecimalField(**MONEY)
    max_amount = models.DecimalField(**MONEY)
    min_installments = models.PositiveSmallIntegerField()
    default_installments = models.PositiveSmallIntegerField()
    max_installments = models.PositiveSmallIntegerField()

    # Gracia: periodos sin cuota
    default_grace_periods = models.PositiveSmallIntegerField(default=0)
    max_grace_periods = models.PositiveSmallIntegerField(default=0)

    # Mora y castigo
    late_fee_daily_rate = models.DecimalField(**PERCENT)        # % diario sobre el valor vencido
    late_fee_cap_percent = models.DecimalField(**PERCENT)       # tope: % del valor vencido de la cuota
    late_tolerance_days = models.PositiveSmallIntegerField(default=0)
    write_off_min_days_past_due = models.PositiveSmallIntegerField()

    # Gasto inicial
    initial_charge_type = models.CharField(max_length=10, choices=InitialChargeType.choices,
                                           default=InitialChargeType.NONE)
    initial_charge_value = models.DecimalField(**MONEY, default=Decimal("0"))

    # Límite y redondeo
    max_active_credits_per_client = models.PositiveSmallIntegerField(default=1)
    rounding_multiple = models.PositiveIntegerField(null=True, blank=True,
                                                    choices=ROUNDING_MULTIPLE_CHOICES)
    rounding_mode = models.CharField(max_length=10, null=True, blank=True,
                                     choices=RoundingMode.choices)

    # Tope adicional (la usura aplica siempre)
    additional_rate_cap = models.ForeignKey("RateCapType", null=True, blank=True,
                                            on_delete=models.PROTECT, related_name="products")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.PROTECT, related_name="+")

    class Meta:
        ordering = ("name",)
        default_permissions = ("view", "add", "change")
        constraints = [...]   # ver las reglas

    @property
    def rate_unit(self) -> RateUnit: ...   # METHOD_RATE_UNIT[self.interest_method]
```

Todos los campos llevan `verbose_name` y `help_text` en español con `gettext_lazy`. El dinero se guarda con dos decimales, aunque la moneda se muestre sin ellos (SPEC 06).

Reglas del producto, validadas en `clean()` con el error en su campo. Las que caben en SQL también van como `CheckConstraint` (`parametros_creditproduct_<regla>`):

| Regla | Mensaje en el campo |
|---|---|
| El nombre es único sin distinguir mayúsculas, después de quitar los espacios de los extremos. | `name`: "Ya existe un producto con ese nombre." |
| `0 < min_amount <= max_amount`. | `max_amount`: "El monto máximo no puede ser menor que el mínimo." |
| `1 <= min_installments <= default_installments <= max_installments <= 999`. | En el campo que rompe el orden. |
| `allowed_periodicities` no está vacía, no repite valores y contiene a `default_periodicity`. | `default_periodicity`: "La periodicidad por defecto tiene que estar entre las permitidas." |
| Con unidad `per_period`, `allowed_periodicities` tiene exactamente un valor. | `allowed_periodicities`: "Con el método <método>, la tasa es por periodo y el producto admite una sola periodicidad." |
| `0 <= default_grace_periods <= max_grace_periods`, y `max_grace_periods < min_installments`. | En el campo que rompe la regla. |
| `0 <= late_fee_daily_rate <= 100` y `0 <= late_fee_cap_percent <= 100`. | En su campo. |
| `late_tolerance_days <= 90`. | `late_tolerance_days`. |
| `write_off_min_days_past_due >= 1`. | `write_off_min_days_past_due`. |
| Sin gasto inicial, `initial_charge_value = 0`. Con `fixed`, `0 < valor < min_amount`. Con `percent`, `0 < valor < 100`. | `initial_charge_value`. |
| `max_active_credits_per_client >= 1`. | `max_active_credits_per_client`. |
| `rounding_multiple` y `rounding_mode` van los dos o ninguno. | `rounding_mode`: "Elige el múltiplo y el modo, o deja los dos vacíos para usar el redondeo global." |
| `additional_rate_cap` no es la usura y, al asignarse, está activo. | `additional_rate_cap`: "La usura ya aplica a todos los productos." o "Ese tope está inactivo." |

Reglas de edición:

- **El método no cambia después de crear el producto**, porque las versiones de tasa están en su unidad. Para cambiar de método se crea otro producto.
- **Con unidad `per_period`, la periodicidad tampoco cambia**, por la misma razón.
- **El resto de los campos se edita sin historial**, con auditoría. Un cambio no afecta a los créditos que ya existen: la SPEC 16 copia en el crédito las condiciones que le aplican al aprobarlo.
- **No existe el permiso `delete`**, y `delete()` lanza `PermissionDenied`. Un producto se desactiva y deja de ofrecerse en solicitudes nuevas. Los créditos que ya lo usan no cambian.

### 3.3 El historial de vigencia (`apps/parametros/models.py`)

Las versiones de tasa y los valores de tope comparten un modelo abstracto:

```python
class ValidityVersion(models.Model):
    valid_from = models.DateField()
    valid_to = models.DateField(null=True, blank=True, editable=False)  # la fija el servicio
    voided_at = models.DateTimeField(null=True, blank=True, editable=False)
    voided_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                  on_delete=models.PROTECT, related_name="+", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                   related_name="+", editable=False)

    class Meta:
        abstract = True
        default_permissions = ("view", "add", "change")


class ProductRateVersion(ValidityVersion):
    product = models.ForeignKey(CreditProduct, on_delete=models.PROTECT, related_name="rate_versions")
    min_rate = models.DecimalField(**PERCENT)
    default_rate = models.DecimalField(**PERCENT)
    max_rate = models.DecimalField(**PERCENT)
    # Meta: ordering ("product", "valid_from"); única por (product, valid_from) entre las no anuladas


class RateCapValue(ValidityVersion):
    cap_type = models.ForeignKey("RateCapType", on_delete=models.PROTECT, related_name="values")
    annual_effective_rate = models.DecimalField(max_digits=9, decimal_places=4)  # % EA
    reference = models.CharField(max_length=150, blank=True, default="")         # "Resolución 1234 de 2026"
    # Meta: ordering ("cap_type", "valid_from"); única por (cap_type, valid_from) entre las no anuladas
```

Reglas de las versiones:

- **Se agregan, no se editan.** Los únicos cambios después de crear una versión son `valid_to`, que mantiene el servicio, y la anulación de una versión programada.
- **Una versión nueva rige desde hoy o desde una fecha futura** (`timezone.localdate()`, `America/Bogota`). Una fecha pasada se rechaza: "La vigencia no puede empezar en una fecha pasada."
- **Una versión nueva empieza después de la última no anulada.** Si ya hay una versión programada para el 1 de diciembre, la nueva tiene que empezar después de esa fecha. Para corregir la programada, primero se anula.
- **`valid_to` se calcula.** Al crear una versión, la anterior no anulada queda con `valid_to = valid_from de la nueva - 1 día`. La última no anulada tiene `valid_to = None`. Al anular la última, la anterior vuelve a `None`.
- **Solo se anula una versión que todavía no rige** (`valid_from > hoy`), y siempre es la última. Una versión que ya rigió, o que rige hoy, no se anula: un crédito pudo haberla congelado. La anulada se conserva con `voided_at` y `voided_by`.
- **La versión vigente en una fecha** es la no anulada con el mayor `valid_from <= fecha`. Si no hay ninguna, no hay versión vigente.
- **Tasas del producto:** `0 <= min_rate <= default_rate <= max_rate <= 100`. Una tasa en cero se permite (el motor la soporta).
- **Valor de un tope:** `0 < annual_effective_rate <= 9999.9999`.
- **No existe el permiso `delete`**, y `delete()` lanza `PermissionDenied`. `change` es el permiso para anular.

### 3.4 Los tipos de tope (`apps/parametros/models.py` y `catalogs.py`)

```python
class RateCapType(CatalogItem): ...   # "tipo de tope de tasa"

# catalogs.py
RATE_CAP_USURY = "USURA"
RATE_CAP_CATALOG = Catalog("topes-tasa", RateCapType, _("Topes de tasa"), 10)
```

- **Es un catálogo de texto más** (SPEC 07): código, nombre, orden, activo y de sistema. Se crea, edita, desactiva y reactiva con los servicios de catálogos de la SPEC 07, pasando `RATE_CAP_CATALOG`.
- **No está en `CATALOGS`**, así que no aparece en el submenú "Catálogos". Tiene su propia pantalla, porque cada tipo muestra su historial de valores (§3.9).
- **"Usura" (`USURA`) es un ítem de sistema**, creado por la migración `0007_initial_rate_cap_types.py`, **sin ningún valor**. El Administrador carga el valor certificado vigente desde la pantalla. La migración no inventa una cifra legal.
- **Desactivar un tipo usado como tope adicional por un producto activo** lanza `CatalogRuleError`: "Lo usa el producto <nombre>. Quítalo del producto antes de desactivarlo." Esa regla se agrega a `deactivate_catalog_item` solo para `RateCapType`.

### 3.5 Servicio (`apps/parametros/services.py`)

Las funciones de las SPEC 06 y 07 se conservan. Se agregan:

```python
@dataclass(frozen=True)
class ApplicableCap:
    cap_type: RateCapType
    value: RateCapValue | None   # None: no hay valor vigente en esa fecha


# Lectura (sin permisos)
def get_offerable_products(on: date | None = None) -> QuerySet[CreditProduct]: ...
def get_product(pk: int) -> CreditProduct: ...
def get_rate_version(product: CreditProduct, on: date | None = None) -> ProductRateVersion | None: ...
def get_rate_cap_value(cap_type: RateCapType, on: date | None = None) -> RateCapValue | None: ...
def get_applicable_caps(product: CreditProduct, on: date | None = None) -> list[ApplicableCap]: ...
def get_product_rounding_rule(product: CreditProduct) -> RoundingRule: ...

# Productos
def create_product(actor: User, data: Mapping[str, Any], rate: Mapping[str, Any]) -> CreditProduct: ...
def update_product(actor: User, product: CreditProduct, data: Mapping[str, Any]) -> CreditProduct: ...
def deactivate_product(actor: User, product: CreditProduct) -> CreditProduct: ...
def reactivate_product(actor: User, product: CreditProduct) -> CreditProduct: ...
def schedule_rate_version(actor: User, product: CreditProduct, data: Mapping[str, Any]) -> ProductRateVersion: ...
def void_rate_version(actor: User, version: ProductRateVersion) -> ProductRateVersion: ...

# Valores de los topes
def schedule_rate_cap_value(actor: User, cap_type: RateCapType, data: Mapping[str, Any]) -> RateCapValue: ...
def void_rate_cap_value(actor: User, value: RateCapValue) -> RateCapValue: ...
```

| Función | Qué hace |
|---|---|
| `get_offerable_products` | Los productos activos que tienen una versión de tasa vigente en `on` (hoy si es `None`), por nombre. Es la lista que ofrecerán el simulador y la solicitud. |
| `get_product` | El producto con ese `pk`, activo o no. Lanza `CreditProduct.DoesNotExist`. |
| `get_rate_version` | La versión vigente del producto en `on` (§3.3), o `None`. |
| `get_rate_cap_value` | El valor vigente del tope en `on`, o `None`. |
| `get_applicable_caps` | Siempre la usura primero y, si el producto tiene `additional_rate_cap`, ese después, cada uno con su valor vigente en `on`. La SPEC 16 bloquea la aprobación si alguno tiene `value=None` o si la EA del plan supera el menor valor. |
| `get_product_rounding_rule` | El redondeo del producto si lo tiene, o `get_rounding_rule()` (global). |
| `create_product` | Verifica `parametros.add_creditproduct`. Crea el producto y su primera versión de tasa en la misma transacción. Valida los dos con `full_clean()` y audita las dos acciones. |
| `update_product` | Verifica `parametros.change_creditproduct`. Ignora `interest_method` y, con unidad `per_period`, `allowed_periodicities`. Sin cambios no guarda ni registra. |
| `deactivate_product` y `reactivate_product` | Verifican `change`. Lanzan `ProductRuleError` si el producto ya está en ese estado. |
| `schedule_rate_version` | Verifica `parametros.add_productrateversion`. Aplica las reglas de la §3.3, cierra la versión anterior y audita. |
| `void_rate_version` | Verifica `parametros.change_productrateversion`. Lanza `ProductRuleError` si la versión ya rige, si ya está anulada o si no es la última. Reabre la anterior y audita. |
| `schedule_rate_cap_value` y `void_rate_cap_value` | Lo mismo, con `add_ratecapvalue` y `change_ratecapvalue`. |

Reglas:

- **`ProductRuleError`** es una subclase de `ValidationError`, como `CatalogRuleError`. La vista muestra su mensaje con `messages.error`.
- **Todos los servicios de edición** toman la fila con `select_for_update()` (el producto o el tipo de tope, para serializar las versiones), toman un `snapshot` antes y después, y llaman a `record` dentro de la misma `transaction.atomic()`.
- **`require_perms` se importa dentro de cada función de edición**, por el ciclo de importación de la SPEC 06 (§6.1).
- **Fuera de `apps/parametros`, nadie consulta estos modelos con `objects` para leer**: pasan por el servicio. Las specs futuras sí declaran `ForeignKey` a `CreditProduct` y a `ProductRateVersion`, con `on_delete=PROTECT`.
- **La fecha de hoy** sale siempre de `timezone.localdate()`. Las pruebas la fijan pasando `on` o con un fixture que congele la fecha.

### 3.6 Auditoría

| Acción | Valor | Etiqueta | Categoría |
|---|---|---|---|
| `PRODUCT_CREATED` | `productos.created` | "Producto de crédito creado" | `FINANCIAL` |
| `PRODUCT_UPDATED` | `productos.updated` | "Producto de crédito editado" | `FINANCIAL` |
| `PRODUCT_DEACTIVATED` | `productos.deactivated` | "Producto de crédito desactivado" | `FINANCIAL` |
| `PRODUCT_REACTIVATED` | `productos.reactivated` | "Producto de crédito reactivado" | `FINANCIAL` |
| `PRODUCT_RATE_SCHEDULED` | `productos.rate_scheduled` | "Tasa de producto programada" | `FINANCIAL` |
| `PRODUCT_RATE_VOIDED` | `productos.rate_voided` | "Tasa de producto anulada" | `FINANCIAL` |
| `RATE_CAP_VALUE_SCHEDULED` | `topes.value_scheduled` | "Valor de tope programado" | `FINANCIAL` |
| `RATE_CAP_VALUE_VOIDED` | `topes.value_voided` | "Valor de tope anulado" | `FINANCIAL` |

- **La entidad** es el producto, la versión de tasa o el valor de tope.
- **`changes` de creación** guarda todos los campos auditables con `None` como valor anterior. En el producto son todos los campos de la §3.2 menos las fechas técnicas. En las versiones, las tasas o el valor, `valid_from` y `reference`. Los `Decimal` van como texto y las fechas en ISO 8601.
- **Programar una versión** también deja en `extra` el `pk` y el `valid_to` nuevo de la versión que cerró, si hubo una. **Anular** deja en `extra` el `pk` de la versión que reabrió.
- **Los tipos de tope** auditan con las acciones `catalogos.*` de la SPEC 07 y su categoría `SECURITY`, porque usan sus servicios.
- Ningún campo es secreto, así que `SENSITIVE_FIELDS` no cambia.
- La migración `apps/auditoria/migrations/0005_product_actions.py` actualiza las `choices` de `AuditEvent.action`, como la `0004` de la SPEC 07.

### 3.7 Permisos

En `roles.py`, dos conjuntos nuevos:

```python
PRODUCT_MODELS = ("creditproduct", "productrateversion", "ratecaptype", "ratecapvalue")

PRODUCT_PERMISSIONS = frozenset(          # el Administrador
    f"parametros.{action}_{model}" for model in PRODUCT_MODELS for action in ("view", "add", "change")
)
PRODUCT_VIEW_PERMISSIONS = frozenset(     # el Supervisor y Consulta
    f"parametros.view_{model}" for model in PRODUCT_MODELS
)
```

| Rol | Productos y topes |
|---|---|
| Administrador | Ve, crea, edita, programa y anula (`PRODUCT_PERMISSIONS`). |
| Supervisor | Solo ve (`PRODUCT_VIEW_PERMISSIONS`). |
| Cajero/Cobrador | Sin pantalla. El simulador le ofrecerá los productos por el servicio, sin permisos. |
| Consulta | Solo ve (`PRODUCT_VIEW_PERMISSIONS`). |

### 3.8 Menú

`apps/parametros/menu.py` agrega dos entradas a la sección `configuracion`, después de "Catálogos" (orden 20):

| Clave | Etiqueta | Icono | Orden | Ruta | Permiso |
|---|---|---|---|---|---|
| `parametros.productos` | "Productos de crédito" | `fas fa-fw fa-file-invoice-dollar` | 30 | `parametros:product_list` | `parametros.view_creditproduct` |
| `parametros.topes` | "Topes de tasa" | `fas fa-fw fa-balance-scale` | 40 | `parametros:ratecap_list` | `parametros.view_ratecaptype` |

El Supervisor y Consulta ven la sección "Configuración" solo con estas dos entradas, porque no tienen permisos de parámetros ni de catálogos.

### 3.9 Pantallas

| Ruta | Método | Vista | Permiso |
|---|---|---|---|
| `/parametros/productos/` | GET | `ProductListView` | `view_creditproduct` |
| `/parametros/productos/nuevo/` | GET, POST | `ProductCreateView` | `add_creditproduct` |
| `/parametros/productos/<pk>/` | GET | `ProductDetailView` | `view_creditproduct` |
| `/parametros/productos/<pk>/editar/` | GET, POST | `ProductUpdateView` | `change_creditproduct` |
| `/parametros/productos/<pk>/desactivar/` | POST | `ProductDeactivateView` | `change_creditproduct` |
| `/parametros/productos/<pk>/reactivar/` | POST | `ProductReactivateView` | `change_creditproduct` |
| `/parametros/productos/<pk>/tasas/nueva/` | GET, POST | `RateVersionCreateView` | `add_productrateversion` |
| `/parametros/productos/<pk>/tasas/<version_pk>/anular/` | POST | `RateVersionVoidView` | `change_productrateversion` |
| `/parametros/topes/` | GET | `RateCapListView` | `view_ratecaptype` |
| `/parametros/topes/nuevo/` | GET, POST | `RateCapCreateView` | `add_ratecaptype` |
| `/parametros/topes/<pk>/` | GET | `RateCapDetailView` | `view_ratecaptype` |
| `/parametros/topes/<pk>/editar/` | GET, POST | `RateCapUpdateView` | `change_ratecaptype` |
| `/parametros/topes/<pk>/desactivar/` | POST | `RateCapDeactivateView` | `change_ratecaptype` |
| `/parametros/topes/<pk>/reactivar/` | POST | `RateCapReactivateView` | `change_ratecaptype` |
| `/parametros/topes/<pk>/valores/nuevo/` | GET, POST | `RateCapValueCreateView` | `add_ratecapvalue` |
| `/parametros/topes/<pk>/valores/<value_pk>/anular/` | POST | `RateCapValueVoidView` | `change_ratecapvalue` |

- **Un `version_pk` o un `value_pk` que no pertenece** al producto o al tope de la ruta responde 404.
- **Un usuario que solo ve** no encuentra botones de crear, editar, programar, desactivar ni anular. Las rutas de edición le responden 403.

**Listado de productos** (`templates/parametros/product_list.html`, desde `tables.html`):

- Título y botón "Nuevo producto" (solo con `add_creditproduct`).
- Tabla con `includes/datatable.html`: nombre (enlace al detalle), método, periodicidades, monto (mínimo y máximo con `moneda`), cuotas (mínimo y máximo), tasa por defecto vigente con su unidad ("10 % por crédito"), estado y acciones.
- Sin versión vigente hoy, la columna de la tasa muestra la insignia "Sin tasa vigente" (`badge-warning`).
- El estado es una insignia "Activo" (`badge-success`) o "Inactivo" (`badge-secondary`).

**Formulario del producto** (`templates/parametros/product_form.html`, desde `blank.html` y `register.html`, con las tarjetas de `cards.html`):

- Una tarjeta por grupo: "Identificación", "Método y periodicidad", "Monto y cuotas", "Gracia", "Mora y castigo", "Gasto inicial", "Límite y redondeo" y "Tope adicional".
- **Al crear**, una tarjeta más, "Tasa inicial", con mínima, por defecto, máxima y "Rige desde" (por defecto, hoy). La ayuda del método explica la unidad de cada uno: "Plano fijo: % por crédito. Plano mensual: % mensual. Los demás: % por periodo, con una sola periodicidad."
- **Al editar**, el método se muestra como texto de solo lectura. Con unidad `per_period`, la periodicidad también. No hay tarjeta de tasa: se programa una versión desde el detalle.
- Las periodicidades permitidas son casillas (`CheckboxSelectMultiple`), y el redondeo ofrece una opción vacía "Usar el redondeo global (<múltiplo> <modo>)".
- El tope adicional ofrece "Ninguno" y los tipos activos que no son la usura.
- Al guardar bien, se va al detalle con "Se guardó <nombre>." Sin cambios, "No hubo cambios en <nombre>." Con errores, la misma página responde 200 con los errores en sus campos.

**Detalle del producto** (`templates/parametros/product_detail.html`, desde `blank.html` y `cards.html`):

- Encabezado con el nombre, la insignia de estado y los botones "Editar", "Desactivar" o "Reactivar".
- Una tarjeta con las condiciones de la §3.2 por grupo, con el dinero con `moneda` y los porcentajes con su unidad.
- **Tarjeta "Tasas"**: la versión vigente hoy resaltada y una tabla con todas las versiones (desde, hasta, mínima, por defecto, máxima, estado y quién la creó). El estado es "Vigente" (`badge-success`), "Programada" (`badge-info`), "Anterior" (`badge-secondary`) o "Anulada" (`badge-dark`). La programada lleva el botón "Anular" con `data-confirm`. Botón "Programar nueva tasa".
- **Tarjeta "Topes que aplican"**: la usura y el tope adicional, cada uno con su valor vigente hoy, o con la alerta `alert-warning` "<tope> no tiene un valor vigente. Los créditos de este producto no se podrán aprobar hasta que se cargue." Una nota explica: "La tasa se valida contra estos topes en cada crédito, con su tasa efectiva anual."

**Formulario de versión de tasa** (`templates/parametros/rate_version_form.html`): mínima, por defecto y máxima, con la unidad del producto como sufijo (`input-group-append`), y "Rige desde". Muestra la versión vigente como referencia.

**Listado de topes** (`templates/parametros/ratecap_list.html`, desde `tables.html`):

- Tabla: nombre (enlace al detalle), código, valor vigente hoy en % EA (o "Sin valor vigente" con `badge-warning`), desde, estado y acciones. La usura lleva la insignia "Sistema" (`badge-info`) y no tiene botón de desactivar.
- **Aviso:** si la usura no tiene valor vigente hoy, una alerta `alert-warning` arriba de la tabla dice "La usura no tiene un valor vigente. Carga el valor certificado por la Superintendencia Financiera para poder aprobar créditos."
- Botón "Nuevo tope" (solo con `add_ratecaptype`).

**Detalle de un tope** (`templates/parametros/ratecap_detail.html`): nombre, código, estado, los productos que lo usan como tope adicional (la usura dice "Aplica a todos los productos") y la tabla de valores con los mismos estados y el botón "Anular" de las tasas. Botón "Programar nuevo valor".

**Formulario de un tipo de tope** (`templates/parametros/ratecap_form.html`): el mismo de un ítem de catálogo de la SPEC 07 (código opcional, nombre y orden), reutilizando `CatalogItemForm`.

**Formulario de valor de tope** (`templates/parametros/ratecap_value_form.html`): valor en % EA (sufijo "% EA"), "Rige desde" y referencia (ayuda: "Por ejemplo, Resolución 1234 de 2026 de la Superintendencia Financiera.").

**Comunes:**

- Los formularios son `ModelForm` o `Form` en `apps/parametros/forms.py`, con `{{ form }}` y el renderizador de la SPEC 02. La vista llama al servicio, nunca a `form.save()`.
- Las fechas de vigencia usan `<input type="date">`, y se muestran con `fecha`.
- Un GET a desactivar, reactivar o anular responde 405.
- Las acciones de cada fila usan plantillas pequeñas en `templates/parametros/includes/`, como en la SPEC 07.
- En celular (unos 375 px), las tablas usan el desplazamiento propio de DataTables, las tarjetas se apilan y la página no se desplaza a lo ancho.
- La plantilla no calcula nada: la versión vigente, el estado de cada versión y la unidad llegan calculados desde la vista.

### 3.10 Archivos nuevos y modificados

**Nuevos:**

- `apps/parametros/migrations/0006_credit_products.py` y `0007_initial_rate_cap_types.py`.
- `apps/auditoria/migrations/0005_product_actions.py`.
- `templates/parametros/product_list.html`, `product_form.html`, `product_detail.html`, `rate_version_form.html`, `ratecap_list.html`, `ratecap_detail.html`, `ratecap_form.html` y `ratecap_value_form.html`.
- `templates/parametros/includes/product_actions.html`, `ratecap_actions.html` y `version_actions.html`.
- `tests/parametros/test_product_models.py`, `test_product_services.py`, `test_rate_versions.py`, `test_rate_caps.py`, `test_product_views.py`, `test_ratecap_views.py` y `test_product_audit.py`.

**Modificados:**

- `apps/parametros/models.py`, `catalogs.py`, `services.py`, `forms.py`, `views.py`, `urls.py` y `menu.py`.
- `apps/auditoria/actions.py`.
- `apps/accounts/roles.py` y `tests/accounts/test_roles.py`.
- `tests/parametros/conftest.py`: fixtures `product_editor`, `product_viewer` y `make_product`.
- `CLAUDE.md` y `docs/specs-tentativas.md`.

---

## 4. Plan de implementación

1. **Opciones y modelos.** Escribir `InterestMethod`, `RateUnit`, `METHOD_RATE_UNIT`, `Periodicity`, `InitialChargeType`, `RateCapType`, `ValidityVersion`, `CreditProduct`, `ProductRateVersion` y `RateCapValue` con sus `clean()` y restricciones, y generar `0006_credit_products.py`. Pruebas en `test_product_models.py`: cada regla de la tabla de la §3.2 (el error en su campo y la restricción de la base), las tasas de una versión, el valor de un tope, `delete()` rechazado y permisos sin `delete`.
2. **Carga inicial y catálogo.** Escribir `0007_initial_rate_cap_types.py` (la usura de sistema, sin valores), `RATE_CAP_USURY`, `RATE_CAP_CATALOG` y la regla de desactivación de un tipo en uso. Pruebas en `test_rate_caps.py`.
3. **Lectura.** Escribir `get_product`, `get_rate_version`, `get_rate_cap_value`, `get_applicable_caps`, `get_offerable_products` y `get_product_rounding_rule`. Pruebas en `test_rate_versions.py` y `test_product_services.py`, con fechas fijas.
4. **Auditoría y servicios de edición.** Agregar las ocho acciones a `AuditAction` y `ACTION_CATEGORIES`, generar `auditoria/0005_product_actions.py` y escribir los servicios de productos, versiones y valores. Pruebas en `test_product_services.py`, `test_rate_versions.py`, `test_rate_caps.py` y `test_product_audit.py`: permisos, campos ignorados, vigencias, cierre y reapertura de `valid_to`, anulación, sin cambios sin registro y reversión si `record` falla.
5. **Permisos.** Agregar `PRODUCT_PERMISSIONS` y `PRODUCT_VIEW_PERMISSIONS` a `ROLE_PERMISSIONS` con su prueba de la matriz.
6. **Pantallas de topes.** Escribir los formularios, las vistas, las URL, las plantillas y la entrada del menú de topes. Pruebas en `test_ratecap_views.py`.
7. **Pantallas de productos.** Escribir el listado, el formulario de creación con la tasa inicial, la edición, el detalle, la versión de tasa y la entrada del menú. Pruebas en `test_product_views.py`.
8. **Verificación en el navegador.** Recorrer con el MCP de Playwright como Administrador la creación de un tope y su valor, la creación de un producto, una versión programada y su anulación. Recorrer como Supervisor el listado y el detalle de solo lectura. Hacerlo en escritorio y a unos 375 px, y comparar con `tables.html`, `blank.html`, `register.html` y `cards.html`.
9. **Documentación.** Actualizar `CLAUDE.md` (estado del proyecto y una sección "Productos de crédito y tasas (SPEC 08)" con cómo leer un producto, su versión vigente, sus topes y su redondeo, y qué le toca a cada spec futura) y `docs/specs-tentativas.md` (la SPEC 08 implementada y sus decisiones para las specs siguientes).

---

## 5. Criterios de aceptación

**Modelo**

- [ ] Crear un producto con `min_amount` mayor que `max_amount`, con `default_installments` fuera del rango o con `default_periodicity` fuera de `allowed_periodicities` falla con el error en su campo, y la restricción de la base falla igual por SQL.
- [ ] Un producto "Plano por cuota" con dos periodicidades permitidas falla con el mensaje de la §3.2. Uno "Plano fijo por crédito" con las cuatro se guarda.
- [ ] Un producto con `max_grace_periods` igual o mayor que `min_installments` falla.
- [ ] Un gasto inicial fijo igual o mayor que `min_amount`, uno porcentual de 100, o un valor distinto de cero sin gasto inicial fallan.
- [ ] Un redondeo con múltiplo y sin modo falla.
- [ ] Elegir la usura como tope adicional falla con "La usura ya aplica a todos los productos."
- [ ] Dos productos con nombres que solo difieren en mayúsculas fallan.
- [ ] Una versión con `min_rate` mayor que `default_rate`, o con `max_rate` de 100,0001, falla. Una con las tres tasas en 0 se guarda.
- [ ] Un valor de tope de 0 falla.
- [ ] `delete()` sobre un producto, una versión, un tipo de tope o un valor lanza `PermissionDenied`, y las cuatro tablas solo tienen los permisos `view`, `add` y `change`.
- [ ] `CreditProduct.rate_unit` devuelve `per_credit`, `monthly` y `per_period` para los métodos plano fijo, plano mensual y francés.

**Carga inicial y tipos de tope**

- [ ] Después de `migrate` sobre una base vacía existe el tipo `USURA`, activo, de sistema y sin ningún valor.
- [ ] Desactivar la usura lanza `CatalogRuleError`.
- [ ] Desactivar un tipo que es el tope adicional de un producto activo lanza `CatalogRuleError` con el nombre del producto. Si el producto está inactivo, se desactiva.

**Vigencias** (con hoy fijado en el 13 de noviembre de 2026)

- [ ] Programar una versión desde el 12 de noviembre de 2026 falla con "La vigencia no puede empezar en una fecha pasada."
- [ ] Con una versión desde el 13 de noviembre y otra programada desde el 1 de diciembre, la primera queda con `valid_to` del 30 de noviembre y la segunda sin `valid_to`.
- [ ] Con esas dos versiones, `get_rate_version(product, on=date(2026, 11, 30))` devuelve la primera, y con el 1 de diciembre devuelve la segunda.
- [ ] Programar una versión desde el 20 de noviembre, con la del 1 de diciembre ya programada, falla.
- [ ] Anular la versión del 1 de diciembre la deja con `voided_at` y `voided_by`, y la del 13 de noviembre vuelve a `valid_to = None`. `get_rate_version` con el 1 de diciembre devuelve la del 13 de noviembre.
- [ ] Anular la versión que rige desde hoy, una que ya rigió o una ya anulada lanza `ProductRuleError` y no crea registros de auditoría.
- [ ] Las mismas cuatro reglas se cumplen con los valores de un tope.
- [ ] Un producto creado con su tasa inicial desde el 1 de diciembre no aparece en `get_offerable_products()` hoy, y sí con `on=date(2026, 12, 1)`. Un producto inactivo nunca aparece.

**Lectura**

- [ ] `get_applicable_caps` de un producto sin tope adicional devuelve solo la usura. Con un tope adicional, devuelve la usura primero y el adicional después, cada uno con su valor vigente o con `value=None`.
- [ ] `get_product_rounding_rule` de un producto sin redondeo propio devuelve el global, y uno con múltiplo 100 hacia arriba devuelve `RoundingRule(Decimal("100"), RoundingMode.UP)`.

**Servicios de edición**

- [ ] `create_product` crea el producto y su primera versión en una sola transacción. Si la versión es inválida, tampoco se crea el producto.
- [ ] `update_product` con `interest_method` en `data` no cambia el método. Con un método por periodo, tampoco cambia la periodicidad.
- [ ] Editar un producto sin cambios no guarda ni registra.
- [ ] Desactivar un producto ya inactivo, o reactivar uno activo, lanza `ProductRuleError`.
- [ ] Un servicio de edición llamado por un Supervisor o por un usuario sin permisos lanza `PermissionDenied` y no crea registros.

**Pantallas y permisos**

- [ ] El Administrador ve "Productos de crédito" y "Topes de tasa" en "Configuración", y todas las rutas de la §3.9 le responden 200 o redirigen como corresponde.
- [ ] El Supervisor y Consulta ven las dos entradas, el listado y los detalles responden 200 sin botones de edición, y las rutas de edición les responden 403.
- [ ] El Cajero/Cobrador no ve las entradas, y todas las rutas de la §3.9 le responden 403.
- [ ] Crear un producto desde la pantalla con su tasa inicial redirige al detalle con "Se guardó <nombre>." y muestra la versión como "Vigente".
- [ ] Al editar un producto, el método no es un campo del formulario; enviar `interest_method` en el POST no lo cambia.
- [ ] Guardar un producto con errores responde 200 y muestra el error en su campo.
- [ ] El detalle muestra la versión programada con "Programada" y el botón "Anular"; anularla desde la pantalla la muestra como "Anulada".
- [ ] Sin valor vigente de la usura, el listado de topes y el detalle de cada producto muestran su alerta. Con un valor vigente, no la muestran.
- [ ] Un `version_pk` de otro producto en la ruta de anular responde 404, y un GET a desactivar, reactivar o anular responde 405.
- [ ] Con Playwright, los listados se ven con la estructura de `tables.html` y los formularios y detalles con la de `blank.html`, `register.html` y `cards.html`; a unos 375 px la página no se desplaza a lo ancho; y la consola no muestra errores.

**Auditoría**

- [ ] Cada servicio de edición crea su acción de la §3.6 con categoría `FINANCIAL`, el `actor` como actor y la entidad correcta.
- [ ] `create_product` deja dos registros: `productos.created` y `productos.rate_scheduled`.
- [ ] Programar una versión que cierra otra deja en `extra` el `pk` y el `valid_to` de la versión cerrada.
- [ ] Crear, editar y desactivar un tipo de tope crea los registros `catalogos.*` de la SPEC 07.
- [ ] Si `record` lanza una excepción dentro de un servicio de edición, el producto, la versión o el valor no cambian, y `valid_to` de la versión anterior tampoco.

**Calidad y documentación**

- [ ] `uv run pytest --cov` pasa, y `apps/parametros` tiene al menos 90 % de cobertura.
- [ ] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] Todos los textos visibles nuevos están envueltos en `gettext`, `gettext_lazy` o `{% translate %}`.
- [ ] Ningún módulo fuera de `apps/parametros` importa `CreditProduct`, `ProductRateVersion`, `RateCapType` ni `RateCapValue` para leerlos con `objects`.
- [ ] `CLAUDE.md` explica cómo leer un producto ofrecible, su versión de tasa vigente, sus topes y su redondeo.
- [ ] `docs/specs-tentativas.md` marca la SPEC 08 como implementada y deja sus decisiones para las SPEC 09, 11, 12, 16, 17, 20 y 21.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** la tasa que supera el tope se bloquea, como dice la §10.3. Decisión de la persona en la fase de preguntas, sabiendo que una tasa plana típica del gota a gota supera la usura.
- **No:** un parámetro para solo advertir, ni una advertencia sin bloqueo. Las dos exigirían enmendar la §10.3.
- **Sí:** la validación contra los topes se hace en cada crédito (SPEC 12 y 16), con la EA del plan real. En los métodos planos, la EA depende del plazo y de la periodicidad, así que una tasa sola no se puede comparar.
- **No:** validar el producto con su combinación más cara. Obligaría a traer el cálculo de la EA antes del motor y bloquearía productos que, con otros plazos, sí pasan.
- **Sí:** un catálogo de tipos de tope, con la usura como ítem de sistema. Es lo que pidió la persona: el sistema maneja distintos topes, no solo la usura.
- **Sí:** la usura aplica siempre, y el producto suma un tope adicional opcional. Gana el más estricto. Respeta la §10.3 sin enmienda.
- **No:** validar solo contra el tope elegido. Un producto con un tope interno dejaría de validarse contra la usura.
- **No:** un tope por modalidad con su propio catálogo. El catálogo de tipos ya permite crear "Usura microcrédito" a mano, si hace falta.
- **Sí:** la usura se crea sin valor, y el Administrador lo carga. La migración no inventa una cifra legal. Sin valor vigente, la SPEC 16 no aprueba créditos, y las pantallas lo avisan.
- **Sí:** los topes se guardan en % EA, la unidad de la certificación de la Superintendencia Financiera.
- **Sí:** los seis métodos se pueden elegir desde ya (D12). La lista queda cerrada en esta spec, y el simulador llega cuando el motor ya tiene los seis.
- **No:** solo los tres planos ahora. La lista cambiaría en dos specs.
- **Sí:** el método fija la unidad de la tasa, y un método por periodo admite una sola periodicidad. La tasa nunca es ambigua.
- **No:** una tasa mensual que el motor convierte. El plano por cuota quedaría casi igual al plano mensual.
- **No:** una tasa por cada periodicidad permitida. El formulario y el historial serían pesados.
- **Sí:** el método no cambia después de crear el producto, y con unidad por periodo la periodicidad tampoco. Las versiones de tasa están en la unidad del método.
- **Sí:** el historial guarda la tasa mínima, la de por defecto y la máxima. Así se sabe qué rango estaba vigente cuando se aprobó un crédito.
- **Sí:** una versión nueva rige desde hoy o desde una fecha futura. El tope del trimestre siguiente se deja cargado con anticipación.
- **No:** fechas pasadas. Reescribirían lo que ya rigió y lo que un crédito pudo haber congelado.
- **Sí:** las versiones se agregan y nunca se editan. Solo se anula la última, y solo si todavía no rige. Corrige un error de programación sin tocar nada que ya se usó, y nada se borra.
- **Sí:** `valid_to` se guarda, y lo mantiene el servicio. La §10.3 habla de "fecha desde / fecha hasta", y el listado no tiene que calcularla.
- **Sí:** un modelo abstracto `ValidityVersion` para las versiones de tasa y los valores de tope. Las dos siguen las mismas reglas de vigencia.
- **Sí:** el resto de las condiciones se edita sin historial, con auditoría. La SPEC 16 las copia en el crédito al aprobarlo, así que un cambio no afecta a los créditos que ya existen.
- **No:** todas las condiciones dentro de la versión. Cada cambio de mora o de gasto crearía una versión de tasa.
- **No:** que la mora y el castigo se lean siempre del producto. Un cambio afectaría a créditos ya pactados.
- **Sí:** la gracia son periodos sin cuota, con un máximo y un valor por defecto. Los "días de gracia" de la §10.2 son la tolerancia de mora (`late_tolerance_days`), que ya está en el producto.
- **No:** gracia de solo interés ni días hasta la primera cuota. Agregarían variantes a cada método del motor.
- **Sí:** un solo gasto inicial, fijo o porcentual, que el desembolso (SPEC 17) descuenta.
- **No:** varios conceptos de gasto por producto. Agrega una tabla que hoy no hace falta.
- **Sí:** el tope de la mora es un porcentaje del valor vencido de la cuota (D14). La SPEC 20 lo aplica cuota por cuota y compara el resultado con la usura.
- **Sí:** el producto puede tener su propio redondeo, y si no lo tiene usa el global. Así el redondeo global es "por defecto", como dice la §10.1.
- **Sí:** el límite de créditos activos cuenta solo los del mismo producto, desde la solicitud (Solicitado, Aprobado, Desembolsado, Activo y En mora). Evita dos solicitudes en paralelo. Lo aplica la SPEC 16.
- **Sí:** el Administrador edita, y el Supervisor y Consulta solo ven. El Supervisor aprueba créditos y necesita conocer las condiciones.
- **Sí:** las acciones de productos, tasas y topes auditan con `FINANCIAL`, porque cambian lo que se cobra. Los tipos de tope usan las acciones `catalogos.*` (`SECURITY`), como los demás catálogos.
- **Sí:** los productos y los topes viven en `apps/parametros`. La §10.2 los ubica en la parametrización, y ADR-001 pide un solo servicio de lectura.
- **No:** una app `productos` nueva. No está en las apps de la §5.1.
- **Sí:** los valores de `InterestMethod` y `Periodicity` se definen aquí y son el contrato con el motor. El motor no importa `parametros`: recibe el valor como texto o como su propio enum con los mismos valores.

### 6.1 Decisiones tomadas durante la implementación

- **Sí:** las reglas que caben en SQL son `CheckConstraint` con el nombre `parametros_creditproduct_<regla>`. La periodicidad por defecto se comprueba con `allowed_periodicities @> ARRAY[default_periodicity]`, y la lista de periodicidades, con que no esté vacía y solo tenga valores de `Periodicity`. Que no se repitan valores no cabe en un `CHECK`: solo lo valida `clean()`.
- **Sí:** `rounding_mode` es un `CharField` con `null=True`, como pide la §3.2, con `# noqa: DJ001`: sin redondeo propio, el múltiplo y el modo son `NULL` y `rounding_pair` lo comprueba en SQL.
- **Sí:** si un campo falla en `clean_fields()`, Django lo deja con el valor original. Los `clean()` solo comparan valores que ya son números (`_number`), para que el error quede en su campo en vez de lanzar `TypeError`.
- **Sí:** el tope adicional inactivo se rechaza solo al asignarlo. Un producto cuyo tope se desactivó después sigue siendo válido y su formulario lo sigue ofreciendo.
- **Sí:** `RATE_CAP_USURY` se agregó en el paso 1, porque `clean()` lo necesita para rechazar la usura como tope adicional. La prueba de la SPEC 07 que exigía todo `CatalogItem` en `CATALOGS` ahora compara con `CATALOGS` más `RATE_CAP_CATALOG`.
- **Sí:** los servicios igualan cada `Decimal` a los decimales de su campo antes de auditar (`_normalize_decimals`). Sin eso, `"10"` frente a `10.0000` parecía un cambio y la auditoría guardaba textos distintos para el mismo valor.
- **Sí:** el mensaje cuando una versión no empieza después de la última es "La vigencia tiene que empezar después del <fecha>, cuando empieza la última versión. Para corregir una versión programada, anúlala primero." Al anular, se revisa en orden: ya anulada, ya rige o rigió, no es la última.
- **Sí:** en `extra`, programar deja `closed_pk` y `closed_valid_to`, y anular deja `reopened_pk`. Anular registra en `changes` el cambio de `voided_at` y `voided_by`.
- **Sí:** el fixture `today` congela `timezone.localdate()` con `monkeypatch`, sin agregar dependencias. `make_product` crea con el ORM, sin servicios ni auditoría.
- **Sí:** Consulta dejó de ser un rol sin permisos. La prueba de la SPEC 04 que lo usaba para un 403 genérico, con un urlconf reducido, ahora usa el Cajero/Cobrador.
- **Sí:** `format_percent` y el filtro `porcentaje` se agregaron a `apps/parametros/formatting.py`, que no estaba en la lista de la §3.10. Muestran el número sin los ceros que sobran (`25,02`), con los separadores de `es-co`.
- **Sí:** la unidad al lado de un campo se dibuja con `templates/forms/field_suffix.html` (`input-group-append`), que se pide con `add_suffix(campo, unidad)`. El error va dentro del grupo para que Bootstrap lo muestre.
- **Sí:** el estado de cada versión y el botón "Anular" (solo en la última programada) los arma `version_rows` en la vista, y lo comparten las tasas y los topes con `includes/version_actions.html`.
- **Sí:** al guardar un tipo de tope se vuelve a su detalle, y al desactivar o reactivar un producto, al detalle del producto, también desde el listado. Desactivar o reactivar un tipo de tope vuelve al listado.
- **Sí:** en la tarjeta "Tasa inicial" el sufijo es "%", porque al crear todavía no se conoce el método; la tarjeta explica la unidad de cada uno. En "Programar nueva tasa" el sufijo es la unidad real del producto.
- **Sí:** el formulario del producto se dibuja por tarjetas con `field.as_field_group`, en el orden de `PRODUCT_FORM_GROUPS`. Los errores del servicio se ponen en el formulario que tiene ese campo (el del producto o el de la tasa inicial).
- **Sí:** Django 6.1 trae "- Select an option -" sin traducir como opción vacía. Los formularios de esta spec ponen "Elige una opción"; los de otras pantallas siguen igual hasta que una spec lo arregle en el renderizador. La descripción usa tres renglones.
- **Sí:** en celular, la tarjeta "Tasa vigente hoy" deja que cada valor baje de renglón, porque la etiqueta quedaba pegada al valor.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| Con el bloqueo por usura, la mayoría de los créditos típicos del gota a gota no se podrán aprobar. | Es una decisión explícita de la persona (§6). Esta spec no compara tasas, así que el efecto aparece en la SPEC 12 (simulador). Ahí el resultado será visible antes de la solicitud, y cambiar a "advertir" exigiría enmendar la §10.3. |
| El Administrador no carga el valor de la usura y ningún crédito se aprueba. | El listado de topes y el detalle de cada producto avisan, y la SPEC 16 dirá por qué no se aprueba. |
| Una versión que rige desde hoy tiene un error y no se puede anular. | La pantalla pide confirmar antes de programar. La corrección es programar una versión desde mañana; los créditos de hoy ya la habrán congelado con su valor real. |
| Los valores de `InterestMethod` y `Periodicity` se desalinean con el motor. | Son la fuente única. La SPEC 09 los usa como contrato, y una prueba de la SPEC 12 compara las dos listas. |
| `services.py` de `parametros` crece demasiado. | Las funciones de productos van agrupadas y documentadas. Si pasa de un tamaño razonable, una spec futura lo divide en un paquete sin cambiar las importaciones. |
| Agregar acciones cambia las `choices` de `AuditEvent.action`. | La migración `auditoria/0005_product_actions.py` es una operación vacía en la base y no toca el trigger. |
| Las pruebas de vigencia dependen de la fecha de hoy. | Los servicios reciben `on` y las pruebas fijan la fecha. Ninguna prueba depende de la fecha real. |

---

## Lo que **no** entra en esta spec

- Validar tasas contra los topes y convertirlas a EA (SPEC 11, 12 y 16).
- Calcular cuotas, el calendario o la gracia (SPEC 09 a 11).
- Congelar la tasa y las condiciones en el crédito, y contar sus créditos activos (SPEC 16).
- Aplicar el gasto inicial (SPEC 17), calcular la mora (SPEC 20) y castigar (SPEC 21).
- El codeudor (SPEC 16).
- Gracia de solo interés, días hasta la primera cuota y varios gastos iniciales.
- Topes por modalidad atados a la Superfinanciera e importar la usura de afuera.
- Corregir una versión que ya rige.

Cada uno de estos puntos, si llega, va en su propia spec.
