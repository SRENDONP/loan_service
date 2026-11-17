# SPEC 09 — Motor I: métodos de interés plano y redondeo

> **Estado:** Implementado
> **Depende de:** SPEC 01, SPEC 06, SPEC 08
> **Fecha:** 2026-11-17
> **Objetivo:** Crear la app `apps/amortizacion` como lógica pura que, a partir del monto, la tasa, el número de cuotas, la periodicidad y la regla de redondeo, devuelve la tabla de cuotas de los tres métodos de interés plano, con la suma del capital igual al monto y el saldo final en cero.

---

## 1. Por qué existe esta spec

La §9 de la constitución define el motor de amortización como el núcleo financiero del sistema, y la §5.2 y la §15.1 lo quieren como lógica pura con 100 % de cobertura. La 007 de la hoja tentativa es esta spec, que pasa a ser la SPEC 09. Las decisiones D3 y D12 fijan su contenido: el interés se cobra dentro de las cuotas, y cada producto elige un método de una lista.

El motor llega en tres specs:

- **SPEC 09 (esta):** el contrato de entrada y salida, el registro de métodos, el redondeo y los tres métodos planos del gota a gota.
- **SPEC 10:** el calendario de vencimientos, los días no hábiles y la gracia.
- **SPEC 11:** los métodos francés, alemán y sobre saldo, y la conversión a tasa efectiva anual.

Esta spec no tiene pantallas. El simulador (SPEC 12) es la primera que usa el motor.

En la fase de preguntas se cerraron cuatro reglas de cálculo:

- **El plano mensual usa meses de 30 días.** Cada periodo vale una fracción fija de mes, así que el motor I no necesita fechas.
- **Se redondea la cuota, no el interés.** El interés total queda a la precisión de la moneda. Las cuotas regulares se redondean al múltiplo, y la última cuota absorbe todas las diferencias.
- **La gracia no cambia el interés.** Solo atrasa el calendario (SPEC 10).
- **Un redondeo sin solución es un error.** El motor nunca entrega una tabla con una cuota en cero o con capital negativo.

---

## 2. Alcance

**Entra:**

- **La app `apps/amortizacion`**, registrada en `INSTALLED_APPS`, sin modelos, migraciones, vistas ni URL.
- **El contrato del motor:** las opciones (`InterestMethod`, `Periodicity` y `RoundingMode`), la regla de redondeo (`RoundingRule`), la entrada (`ScheduleInput`), la cuota (`Installment`) y la tabla (`Schedule`), como dataclasses inmutables con `Decimal`.
- **La validación de la entrada**, con errores que llevan un código y el campo que falla.
- **El registro de métodos:** cada método es una estrategia que se registra con su valor de `InterestMethod`. Un método nuevo se agrega sin tocar los existentes.
- **Los tres métodos planos** de la sección 1.1 de la hoja tentativa: plano fijo por crédito, plano mensual prorrateado y plano por cuota.
- **El redondeo de la cuota** al múltiplo y en el modo de la regla, y el ajuste de la última cuota.
- **Los totales:** capital, interés y total a pagar.
- **Las pruebas** con 100 % de cobertura del motor, incluidos los casos límite de la §15.1.
- **Un paso nuevo en el CI** que exige ese 100 %.
- **Una prueba de contrato** que compara las opciones del motor con las de `apps/parametros`.
- **La actualización de la documentación:** `CLAUDE.md` y `docs/specs-tentativas.md`.

**Fuera de alcance (para specs futuras):**

- Las fechas de vencimiento, los días no hábiles, el corrimiento y la gracia (SPEC 10).
- Los métodos francés, alemán y sobre saldo (SPEC 11). Su valor existe en el enum, pero pedirlo lanza `UnsupportedMethodError`.
- La tasa efectiva anual, el costo financiero total, la cuota mínima y la tolerancia de pago (SPEC 11).
- Leer el producto, su tasa o su redondeo desde `parametros`, y validar la tasa contra los topes (SPEC 12).
- Traducir los errores del motor a mensajes de la interfaz (SPEC 12).
- El gasto inicial (SPEC 17) y la mora (SPEC 20).
- Guardar la tabla. El snapshot inmutable lo guarda el desembolso (SPEC 17).
- Cualquier pantalla, vista o comando de gestión.

---

## 3. Modelo de datos

Esta spec no crea tablas en la base de datos. Las estructuras son dataclasses de Python.

### 3.1 Archivos de la app

| Archivo | Contenido |
|---|---|
| `apps/amortizacion/__init__.py` | Vacío. |
| `apps/amortizacion/apps.py` | `AmortizacionConfig`, con `name = "apps.amortizacion"` y `verbose_name = _("Amortización")`. Es el único archivo que importa `django`. |
| `apps/amortizacion/types.py` | Las opciones, `RoundingRule`, `ScheduleInput`, `Installment` y `Schedule`. |
| `apps/amortizacion/errors.py` | Las excepciones del motor. |
| `apps/amortizacion/rounding.py` | `round_to_rule` y `quantize_money`. |
| `apps/amortizacion/registry.py` | `register`, `get_strategy` y `registered_methods`. |
| `apps/amortizacion/methods/__init__.py` | Importa `flat` para que sus estrategias queden registradas. |
| `apps/amortizacion/methods/flat.py` | Los tres métodos planos y su reparto común. |
| `apps/amortizacion/engine.py` | `build_schedule`, la única función que usan las otras apps. |

**Pureza:** ningún archivo de la app, salvo `apps.py`, importa `django` ni otra app del proyecto. Solo usan la biblioteca estándar (`dataclasses`, `decimal`, `enum` y `typing`). Una prueba lo verifica leyendo el código con `ast`.

### 3.2 Opciones (`types.py`)

```python
class InterestMethod(StrEnum):
    FLAT_PER_CREDIT = "flat_per_credit"
    FLAT_MONTHLY_PRORATED = "flat_monthly_prorated"
    FLAT_PER_INSTALLMENT = "flat_per_installment"
    FRENCH = "french"
    GERMAN = "german"
    DECLINING_BALANCE = "declining_balance"


class Periodicity(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"
    BIWEEKLY = "biweekly"
    MONTHLY = "monthly"


class RoundingMode(StrEnum):
    HALF_UP = "half_up"
    UP = "up"
    DOWN = "down"


DAYS_PER_PERIOD: dict[Periodicity, int] = {
    Periodicity.DAILY: 1,
    Periodicity.WEEKLY: 7,
    Periodicity.BIWEEKLY: 15,
    Periodicity.MONTHLY: 30,
}
```

- **Los valores son los mismos de `apps/parametros`** (`InterestMethod` y `Periodicity` de la SPEC 08, `RoundingMode` de la SPEC 06). El motor no los importa: tiene los suyos. `tests/amortizacion/test_contract.py` compara las tres listas.
- **Son `StrEnum`**, así que el valor guardado en un producto (`"flat_per_credit"`) se convierte con `InterestMethod("flat_per_credit")`.
- **`DAYS_PER_PERIOD`** solo lo usa el plano mensual, con meses de 30 días (§3.6).
- **Las etiquetas en español** no van aquí, porque el motor no importa `gettext`. Las pantallas usan las de `parametros`.

### 3.3 Entrada (`types.py`)

```python
@dataclass(frozen=True, slots=True)
class RoundingRule:
    multiple: Decimal        # 1, 10, 50, 100, 500 o 1000
    mode: RoundingMode


@dataclass(frozen=True, slots=True)
class ScheduleInput:
    principal: Decimal       # monto del crédito
    rate: Decimal            # porcentaje en la unidad del método: 10 es 10 %
    installments: int        # número de cuotas
    method: InterestMethod
    periodicity: Periodicity
    rounding: RoundingRule
    money_precision: Decimal # Decimal("1") o Decimal("0.01")
```

- **`RoundingRule` del motor no es el de `parametros`.** Tienen los mismos campos y valores, y el simulador (SPEC 12) convierte uno en el otro.
- **`rate` está en la unidad que fija el método** (`METHOD_RATE_UNIT`, SPEC 08): plano fijo, % por crédito; plano mensual, % mensual; plano por cuota, % por periodo.
- **`money_precision`** sale de `currency_decimals` de los parámetros globales: `0` decimales es `Decimal("1")` y `2` es `Decimal("0.01")`. Lo convierte el simulador.
- **La gracia no es parte de la entrada.** No cambia el interés de los métodos planos (§6).

Reglas de la entrada, que `build_schedule` valida antes de calcular:

| Campo | Regla | Código del error |
|---|---|---|
| `principal` | Es un `Decimal`. | `invalid_type` |
| `principal` | Es mayor que 0. | `not_positive` |
| `principal` | Es múltiplo de `money_precision` (100.000,50 con precisión 1 falla). | `precision` |
| `rate` | Es un `Decimal`. | `invalid_type` |
| `rate` | Es mayor o igual que 0. El motor no pone un máximo: eso es del producto. | `negative` |
| `installments` | Es un `int` y no un `bool`. | `invalid_type` |
| `installments` | Está entre 1 y 999, como el producto (SPEC 08). | `out_of_range` |
| `method` | Es un valor de `InterestMethod`, como enum o como texto. | `invalid_choice` |
| `periodicity` | Es un valor de `Periodicity`, como enum o como texto. | `invalid_choice` |
| `money_precision` | Es `Decimal("1")` o `Decimal("0.01")`. | `invalid_choice` |
| `rounding.multiple` | Es un `Decimal` mayor que 0 y múltiplo de `money_precision`. | `invalid_rounding` |
| `rounding.mode` | Es un valor de `RoundingMode`, como enum o como texto. | `invalid_choice` |

- **Ningún `float` entra al motor.** Un `float` en el monto, la tasa o el múltiplo falla con `invalid_type`.
- **Los textos se normalizan** a su enum antes de calcular, así que la tabla siempre trae enums.

### 3.4 Salida (`types.py`)

```python
@dataclass(frozen=True, slots=True)
class Installment:
    number: int              # 1..n
    opening_balance: Decimal # saldo de capital antes de la cuota
    principal: Decimal       # abono a capital
    interest: Decimal
    payment: Decimal         # principal + interest
    closing_balance: Decimal # opening_balance - principal


@dataclass(frozen=True, slots=True)
class Schedule:
    installments: tuple[Installment, ...]
    regular_payment: Decimal # valor de las cuotas 1 a n-1 (con 1 cuota, el de esa cuota)
    total_principal: Decimal # igual a principal
    total_interest: Decimal
    total_payment: Decimal   # total_principal + total_interest
```

- **El saldo es saldo de capital**, como pide la §9.3. El interés no entra en el saldo.
- **Todo valor de la tabla está a la precisión de la moneda.** Ninguno tiene más decimales que `money_precision`.
- **Sin fechas.** La SPEC 10 decide cómo unir el calendario con la tabla, sin cambiar los valores que calcula esta spec.

### 3.5 Errores (`errors.py`)

```python
class AmortizationError(ValueError):
    code: str
    field: str | None

class AmortizationInputError(AmortizationError): ...  # una regla de la §3.3
class RoundingError(AmortizationError): ...           # el redondeo no tiene solución (§3.7)
class UnsupportedMethodError(AmortizationError): ...  # el método existe, pero no está registrado
```

- **Cada error lleva un `code`** estable (los de la §3.3 y la §3.7) y el `field` que falla, o `None`.
- **El mensaje está en español sin `gettext`**, para los registros y las pruebas. La interfaz no lo muestra tal cual: el simulador (SPEC 12) traduce el `code` a su texto.
- **`UnsupportedMethodError`** usa el código `unsupported_method` y el campo `method`.

### 3.6 Interés total de cada método (`methods/flat.py`)

Cada estrategia calcula el interés total sin redondeos intermedios y lo redondea una sola vez a `money_precision`, al más cercano (`ROUND_HALF_UP`). Con `P` el monto, `r` la tasa como porcentaje y `n` las cuotas:

| Método | Interés total |
|---|---|
| Plano fijo por crédito | `P × r / 100` |
| Plano mensual prorrateado | `P × r / 100 × n × DAYS_PER_PERIOD[periodicidad] / 30` |
| Plano por cuota | `P × r / 100 × n` |

- **Las multiplicaciones van antes de la división**, en un `decimal.localcontext()` con 28 dígitos de precisión, para que 20 cuotas diarias den exactamente 20/30 de mes.
- **El plano fijo y el plano por cuota no usan la periodicidad.** La reciben igual, porque es parte de la entrada.
- Ejemplos con 100.000, 20 cuotas y precisión 1:

| Método | Tasa | Interés total |
|---|---|---|
| Plano fijo | 10 % por crédito | 10.000 |
| Plano mensual, diaria | 10 % mensual | 6.667 (6.666,67 redondeado) |
| Plano por cuota, diaria | 0,5 % por periodo | 10.000 |

### 3.7 Reparto en cuotas y redondeo (`methods/flat.py` y `rounding.py`)

Los tres métodos planos comparten el reparto. Con `I` el interés total:

1. **Cuota regular:** `R = round_to_rule((P + I) / n, rounding)`.
2. **Interés de cada cuota regular:** `i = (I / n)` truncado hacia abajo a `money_precision`.
3. **Capital de cada cuota regular:** `c = R − i`.
4. **Cuotas 1 a n−1:** `i` de interés, `c` de capital y `R` de cuota.
5. **Última cuota:** interés `I − (n − 1) × i`, capital `P − (n − 1) × c` y cuota la suma de los dos.
6. **Con una sola cuota**, solo existe la última: interés `I`, capital `P` y cuota `P + I`. El múltiplo no se aplica.

`round_to_rule(valor, regla)` divide entre el múltiplo, redondea a un entero y multiplica de nuevo:

| Modo | Redondeo de `Decimal` |
|---|---|
| `half_up` | `ROUND_HALF_UP` |
| `up` | `ROUND_CEILING` |
| `down` | `ROUND_FLOOR` |

`quantize_money(valor, precisión, modo)` deja un valor a la precisión de la moneda.

**Por qué el interés regular se trunca:** así `(n − 1) × i` nunca supera a `I`, y el interés de la última cuota nunca es negativo.

**Cuándo el redondeo no tiene solución.** Con más de una cuota, el motor lanza `RoundingError` si:

| Caso | Código |
|---|---|
| La cuota regular `R` queda en 0. | `zero_payment` |
| El capital regular `c` es negativo: la cuota no alcanza ni para su interés. | `negative_principal` |
| El capital de la última cuota es negativo: las cuotas regulares ya pagaron más que el monto. | `overpaid` |
| La última cuota queda en 0. | `zero_last_payment` |

Un capital regular en 0 sí se permite: todo el capital queda en la última cuota.

**Invariantes**, que cumple toda tabla que el motor entrega:

- La suma del capital de las cuotas es exactamente `P`, y el saldo final de la última es exactamente 0.
- La suma del interés es exactamente `I`, y la suma de las cuotas es `P + I`.
- Cada cuota tiene capital e interés mayores o iguales que 0, y valor mayor que 0.
- Las cuotas 1 a n−1 valen lo mismo, y ese valor es múltiplo de `rounding.multiple`.
- El saldo inicial de cada cuota es el saldo final de la anterior, y el de la primera es `P`.
- Los mismos parámetros dan siempre la misma tabla (§9.4).

**Ejemplo** (plano mensual, 100.000, 10 % mensual, 20 cuotas diarias, múltiplo de 50 al más cercano, precisión 1):

| Cuotas | Interés | Capital | Cuota |
|---|---|---|---|
| 1 a 19 | 333 | 5.017 | 5.350 |
| 20 | 340 | 4.677 | 5.017 |
| **Total** | **6.667** | **100.000** | **106.667** |

### 3.8 Registro de métodos (`registry.py`)

```python
class ScheduleStrategy(Protocol):
    def build(self, data: ScheduleInput) -> Schedule: ...

def register(method: InterestMethod) -> Callable[[type[ScheduleStrategy]], type[ScheduleStrategy]]: ...
def get_strategy(method: InterestMethod) -> ScheduleStrategy: ...
def registered_methods() -> frozenset[InterestMethod]: ...
```

- **`register`** es un decorador de clase. Registrar dos veces el mismo método lanza `ValueError`, para que un método nuevo nunca pise a otro por error.
- **`get_strategy`** lanza `UnsupportedMethodError` si el método no está registrado.
- **La estrategia arma la tabla completa**, no solo el interés total. Así la SPEC 11 agrega el francés, el alemán y el sobre saldo con su propio reparto, sin tocar el de los planos.
- **Después de esta spec**, `registered_methods()` devuelve exactamente los tres métodos planos.

### 3.9 Punto de entrada (`engine.py`)

```python
def build_schedule(data: ScheduleInput) -> Schedule: ...
```

- Valida la entrada (§3.3), normaliza los textos a enums, busca la estrategia y devuelve su tabla.
- Es la única función que importan las otras apps, junto con los tipos y los errores.
- No lee parámetros, no consulta la base de datos y no tiene estado.

### 3.10 Archivos nuevos y modificados

**Nuevos:**

- Los archivos de `apps/amortizacion/` de la §3.1.
- `tests/amortizacion/__init__.py`.
- `tests/amortizacion/test_inputs.py`: cada regla de la §3.3 con su código y su campo.
- `tests/amortizacion/test_rounding.py`: `round_to_rule` y `quantize_money` en los tres modos, con valores exactos, a mitad de camino y negativos de cero.
- `tests/amortizacion/test_flat_methods.py`: el interés total de cada método y las tablas exactas de la §5.
- `tests/amortizacion/test_invariants.py`: una malla de combinaciones que comprueba los invariantes de la §3.7 o un `RoundingError`.
- `tests/amortizacion/test_registry.py`: el registro, el doble registro y los métodos no registrados.
- `tests/amortizacion/test_purity.py`: ningún archivo de la app, salvo `apps.py`, importa `django` ni `apps.*`.
- `tests/amortizacion/test_contract.py`: los valores de las tres opciones son iguales a los de `apps/parametros`.

**Modificados:**

- `config/settings/base.py`: `"apps.amortizacion"` en `INSTALLED_APPS`, después de `"apps.parametros"`.
- `.github/workflows/ci.yml`: el paso "Cobertura del motor" después de "Pruebas".
- `CLAUDE.md` y `docs/specs-tentativas.md`.

---

## 4. Plan de implementación

1. **App y contrato.** Crear `apps/amortizacion` con `apps.py`, registrarla en `INSTALLED_APPS` y escribir `types.py` y `errors.py`. Pruebas en `test_contract.py` (las tres listas de valores) y `test_purity.py`.
2. **Redondeo.** Escribir `rounding.py`. Pruebas en `test_rounding.py`.
3. **Registro y entrada.** Escribir `registry.py` y `engine.py` con la validación de la §3.3, sin métodos registrados todavía. Pruebas en `test_registry.py` y `test_inputs.py`: cada regla de la entrada y `UnsupportedMethodError` para cualquier método.
4. **Plano fijo por crédito.** Escribir el reparto común de la §3.7 y la primera estrategia en `methods/flat.py`. Pruebas en `test_flat_methods.py`: las tablas del plano fijo de la §5, una cuota, tasa cero y los cuatro códigos de `RoundingError`.
5. **Plano mensual y plano por cuota.** Agregar las otras dos estrategias. Pruebas en `test_flat_methods.py`: las tablas de la §5 en las cuatro periodicidades.
6. **Malla de invariantes.** Escribir `test_invariants.py` con la combinación de los tres métodos, las cuatro periodicidades, montos (50, 1.000, 100.000 y 12.345.678), cuotas (1, 2, 3, 7, 20, 30 y 999), tasas (0, 0,5, 10 y 100), los seis múltiplos, los tres modos y las dos precisiones. Cada caso cumple los invariantes o lanza `RoundingError`.
7. **Cobertura en el CI.** Agregar el paso `uv run pytest tests/amortizacion --cov=apps/amortizacion --cov-report=term-missing --cov-fail-under=100` y comprobarlo en local.
8. **Documentación.** Actualizar `CLAUDE.md` (estado del proyecto, el comando de cobertura del motor y una sección "Motor de amortización (SPEC 09)" con cómo llamar a `build_schedule`, cómo registrar un método y qué le toca a las SPEC 10 a 12) y `docs/specs-tentativas.md` (la SPEC 09 implementada y sus decisiones para las specs siguientes).

---

## 5. Criterios de aceptación

**Estructura y contrato**

- [ ] `apps.amortizacion` está en `INSTALLED_APPS` y la app no tiene `models.py`, migraciones, vistas ni URL.
- [ ] Ningún archivo de `apps/amortizacion`, salvo `apps.py`, importa `django` ni un módulo `apps.*`, y `test_purity.py` falla si alguno lo hace.
- [ ] Los valores de `InterestMethod`, `Periodicity` y `RoundingMode` del motor son exactamente los de `apps/parametros`.
- [ ] `ScheduleInput`, `Installment`, `Schedule` y `RoundingRule` son inmutables: asignar un campo lanza `FrozenInstanceError`.
- [ ] `registered_methods()` devuelve exactamente los tres métodos planos.
- [ ] Pedir `french`, `german` o `declining_balance` lanza `UnsupportedMethodError` con el código `unsupported_method`.
- [ ] Registrar dos veces el mismo método lanza `ValueError`.

**Entrada**

- [ ] Cada regla de la tabla de la §3.3 lanza `AmortizationInputError` con su código y su campo.
- [ ] Un `float` en el monto, la tasa o el múltiplo lanza `invalid_type`.
- [ ] `method="flat_per_credit"` como texto da la misma tabla que `InterestMethod.FLAT_PER_CREDIT`.

**Tablas exactas** (100.000, 20 cuotas, múltiplo de 50 al más cercano y precisión 1, salvo que se diga otra cosa)

- [ ] Plano fijo al 10 %: interés total 10.000 y 20 cuotas de 5.500, cada una con 500 de interés y 5.000 de capital.
- [ ] Plano por cuota al 0,5 % diario: la misma tabla que el plano fijo al 10 %.
- [ ] Plano mensual al 10 % con 20 cuotas diarias: la tabla del ejemplo de la §3.7 (19 cuotas de 5.350 con 333 y 5.017, y la última de 5.017 con 340 y 4.677).
- [ ] La misma tabla con precisión 0,01: interés total 6.666,67, 19 cuotas de 5.350 con 333,33 y 5.016,67, y la última de 5.016,67 con 333,40 y 4.683,27.
- [ ] Plano mensual al 10 % con 8 cuotas semanales: interés total 18.667, 7 cuotas de 14.850 con 2.333 y 12.517, y la última de 14.717 con 2.336 y 12.381.
- [ ] Plano mensual al 10 % da 30.000 de interés con 6 cuotas quincenales y con 3 mensuales.
- [ ] Plano fijo al 10 % con múltiplo de 1.000 hacia abajo: 19 cuotas de 5.000 y la última de 15.000.

**Casos límite**

- [ ] Una cuota: plano fijo al 10 % sobre 100.000 da una cuota de 110.000 con cualquier regla de redondeo, incluido el múltiplo de 1.000 hacia arriba.
- [ ] Una cuota diaria con plano mensual al 10 %: interés 333 y cuota 100.333, sin redondeo al múltiplo.
- [ ] Tasa cero con 3 cuotas: interés 0, dos cuotas de 33.350 y la última de 33.300.
- [ ] Monto 100 con 20 cuotas, tasa 0 y múltiplo de 50 al más cercano lanza `RoundingError` con `zero_payment`. Con múltiplo de 1, da 20 cuotas de 5.
- [ ] Plano fijo al 10 % con múltiplo de 1.000 hacia arriba o al más cercano lanza `RoundingError` con `overpaid`.
- [ ] Monto 1.000 en 3 cuotas, tasa 0 y múltiplo de 500 hacia arriba lanza `RoundingError` con `zero_last_payment`.
- [ ] Monto 10, plano fijo al 1.100 %, 2 cuotas y múltiplo de 50 hacia abajo lanza `RoundingError` con `negative_principal`.
- [ ] 999 cuotas diarias se calculan y cumplen los invariantes.

**Invariantes**

- [ ] En toda la malla del paso 6, cada caso lanza `RoundingError` o cumple todos los invariantes de la §3.7.
- [ ] Ningún valor de una tabla tiene más decimales que `money_precision`.
- [ ] Llamar dos veces a `build_schedule` con la misma entrada da tablas iguales (`==`).

**Calidad y documentación**

- [ ] `uv run pytest tests/amortizacion --cov=apps/amortizacion --cov-fail-under=100` pasa, y el CI lo ejecuta como un paso propio.
- [ ] `uv run pytest --cov`, `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [ ] Las funciones públicas del motor tienen anotaciones de tipo completas.
- [ ] `CLAUDE.md` explica cómo llamar a `build_schedule`, cómo registrar un método nuevo y el comando de cobertura del motor.
- [ ] `docs/specs-tentativas.md` marca la SPEC 09 como implementada y deja sus decisiones para las SPEC 10, 11 y 12.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** el plano mensual usa meses de 30 días: diaria 1/30, semanal 7/30, quincenal 1/2 y mensual 1. Es la convención comercial, coincide con el ejemplo de la hoja (20 cuotas diarias ≈ 0,67 meses) y no depende del calendario.
- **No:** los días reales del plazo. Harían depender el interés de la fecha de inicio, de los domingos y de los festivos, y el motor I necesitaría el calendario de la SPEC 10.
- **Sí:** el interés total se redondea una sola vez, a la precisión de la moneda. El costo del crédito es el que da la fórmula, sin el efecto del múltiplo.
- **No:** redondear el interés total al múltiplo. Cambiaría el costo del crédito por una decisión de presentación.
- **Sí:** las cuotas regulares se redondean al múltiplo y la última absorbe las diferencias de capital y de interés. Es lo que se cobra en la calle: cuotas redondas y un ajuste al final.
- **No:** redondear por separado el capital y el interés de cada cuota. Da cuotas que no son múltiplo y diferencias en cada fila.
- **Sí:** el interés de cada cuota regular se trunca hacia abajo. Así el interés de la última nunca es negativo.
- **Sí:** con una cuota no se aplica el múltiplo. La única cuota es la última, y la última siempre absorbe el ajuste.
- **Sí:** un redondeo sin solución lanza `RoundingError` con su código. El simulador lo muestra, y el producto se corrige con otro múltiplo u otro monto.
- **No:** bajar en silencio a la precisión de la moneda. El crédito tendría cuotas que nadie configuró.
- **Sí:** un capital regular en 0 se permite. La tabla sigue cumpliendo los invariantes, aunque todo el capital quede al final.
- **Sí:** la gracia no cambia el interés de los métodos planos y no es parte de la entrada del motor I. Solo atrasa el calendario (SPEC 10), así que no encarece el crédito.
- **No:** contar la gracia en el plazo del plano mensual o en las cuotas del plano por cuota.
- **Sí:** `apps/amortizacion` es una app de Django registrada en `INSTALLED_APPS`, pero sin modelos, y solo `apps.py` importa `django`. Respeta la §5.1 y la §5.2 al mismo tiempo.
- **No:** un paquete de Python fuera de `INSTALLED_APPS`. Se apartaría de cómo están las demás apps.
- **Sí:** el motor tiene sus propios enums y su propio `RoundingRule`, con los mismos valores de `parametros`. Una prueba compara las listas desde esta spec, no desde la SPEC 12.
- **Sí:** el enum de métodos trae los seis valores, y el registro solo los tres planos. El contrato queda completo desde ya y la SPEC 11 solo registra estrategias.
- **No:** solo los tres planos en el enum. El contrato cambiaría en la SPEC 11.
- **Sí:** cada estrategia arma la tabla completa. Los métodos sobre saldo tienen otro reparto, y así no tocan el de los planos.
- **No:** estrategias que solo devuelven el interés total. Obligaría a cambiar el motor en la SPEC 11.
- **Sí:** dataclasses inmutables con `slots`. La tabla es un valor: no se modifica después de calcularla, como el snapshot de la §9.4.
- **Sí:** el saldo de cada cuota es saldo de capital, como la §9.3.
- **Sí:** los errores llevan un `code` y un `field`, con el mensaje en español sin `gettext`. El motor no importa Django, así que la traducción la hace el simulador a partir del código.
- **Sí:** la precisión de la moneda es parte de la entrada (`1` o `0.01`). El motor no lee `currency_decimals`: lo recibe, como el redondeo.
- **Sí:** el motor no pone un máximo a la tasa. El rango lo valida el producto (SPEC 08) y los topes el simulador (SPEC 12).
- **Sí:** el 100 % de cobertura se exige con un paso propio del CI. Si alguien baja la cobertura del motor, el CI falla.
- **No:** dejar el 100 % solo como criterio de aceptación. Nada impediría que bajara después.
- **Sí:** la malla de invariantes se escribe con `pytest.mark.parametrize` y ciclos, sin librerías nuevas. Agregar una librería de pruebas por propiedades (como Hypothesis) necesitaría su propia decisión.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| La última cuota queda muy distinta de las demás con un múltiplo grande (por ejemplo, 15.000 frente a 5.000). | Es el resultado correcto de la regla. El simulador (SPEC 12) muestra la tabla completa antes de solicitar, y el producto puede tener su propio redondeo (SPEC 08). |
| Muchos créditos pequeños lanzan `RoundingError` con el redondeo global de 50. | El error trae su código, y el monto mínimo del producto evita la mayoría de los casos. El simulador explica la causa. |
| Los enums del motor y los de `parametros` se desalinean. | `test_contract.py` compara las tres listas desde esta spec. |
| Un error de redondeo pasa en un caso que nadie probó. | La malla de invariantes recorre miles de combinaciones, y el CI exige 100 % de cobertura del motor. |
| La malla hace lentas las pruebas. | Las combinaciones se eligen para que el archivo corra en pocos segundos. Si crece, se reduce la malla sin quitar los casos límite. |
| La SPEC 11 necesita algo que el contrato no trae. | Las estrategias arman la tabla completa y la entrada es un dataclass: la SPEC 11 puede agregar campos con valor por defecto sin romper a los planos. |

---

## Lo que **no** entra en esta spec

- Fechas de vencimiento, días no hábiles, corrimiento y gracia (SPEC 10).
- Métodos francés, alemán y sobre saldo, tasa efectiva anual y costo financiero total (SPEC 11).
- Cuota mínima y tolerancia de pago (SPEC 11).
- Leer productos o parámetros, validar contra los topes y traducir los errores (SPEC 12).
- Gasto inicial (SPEC 17), mora (SPEC 20) y snapshot de la tabla (SPEC 17).
- Pantallas, vistas y comandos de gestión.

Cada uno de estos puntos, si llega, va en su propia spec.
