# Hoja de ruta tentativa de specs

> **Documento de trabajo, no oficial.** Es la base para definir las specs definitivas, que se
> escriben con `/spec` en `specs/NN-slug.md`. La numeración de tres dígitos de esta hoja pasa a
> dos dígitos y empieza en `01`: la 000 pasa a ser la `01`, la 001 pasa a ser la `02`, y así
> hasta la 004 (`05`). **La 005 se dividió en dos** (SPEC 06, parámetros globales, y SPEC 07,
> catálogos y festivos), así que desde la 006 la spec definitiva lleva dos números más: la 006
> pasa a ser la `08`, la 007 la `09`, y así hasta la 026 (`28`). La numeración, el alcance y el
> orden pueden cambiar. La constitución prevalece sobre este documento.

Versión 3 · 2026-11-06 · Incorpora la segunda ronda de respuestas (ver sección 1).

---

## 1. Decisiones tomadas

| # | Tema | Decisión | Impacto |
|---|---|---|---|
| D1 | Negocios (§19.2) | Un solo negocio, con la posibilidad de ampliarse en el futuro | No se agrega `tenant` a los modelos en la v1. Los parámetros globales se guardan como registro único y no como constantes, para poder convertirlos después en "por negocio" sin rehacer la lógica. Se documenta en un ADR. |
| D2 | Stack | Últimas versiones de Python y Django (hoy Python 3.14 y Django 6.1) | Requiere **enmendar la §4** de la constitución según la §16.4. |
| D3 | Tasas e interés (§19.3) | Las tasas se parametrizan en el módulo de configuración y el interés se cobra dentro de las mismas cuotas | Ver D12: hay varios métodos de cálculo para elegir. |
| D4 | Periodicidad (§19.1) | La v1 incluye diaria, semanal, quincenal y mensual | La spec 008 cubre las cuatro. |
| D5 | Días no hábiles | La cuota que cae en un día no hábil se corre al siguiente día hábil | Ver D13: el corrimiento desplaza las cuotas siguientes. |
| D6 | Mora (§19.8) | La mora se cobra desde el día siguiente al vencimiento | La tolerancia por defecto es de 0 días y sigue siendo parametrizable por producto. Ver D14. |
| D7 | Recibo (§19.6) | Por ahora, solo un PDF imprimible | El recibo en PDF entra en la 016. La impresión térmica pasa a la fase 2. |
| D8 | Sin conexión y geolocalización (§19.4, §19.5) | Fase 2 | Se retira de la v1. Las coordenadas del cliente pueden quedar como campo opcional sin mapa. |
| D9 | Codeudor (§19.7) | Formulario genérico de **terceros**. Al crear el crédito se asocian el deudor (cliente) y el codeudor (tercero). | Nueva spec 012 de terceros. Se propone reutilizarla también para las referencias personales. |
| D10 | Cierre de caja | Lo hace el **supervisor**, por cobrador | Se define en la spec 020. |
| D11 | Auditoría | Retención de 1 año | Revisar contra las obligaciones legales de conservación (ver P5). |
| D12 | Método de cálculo del interés | Se elige entre varios métodos habituales, configurados en el módulo de parámetros | Cada producto define su método y el crédito lo conserva al aprobarse. Los métodos de la v1 están en la sección 1.1. La spec 009 vuelve a la v1. |
| D13 | Corrimiento por festivo | Cuando una cuota se corre un día, las siguientes también se corren un día | El calendario se va desplazando en cascada. Propuesta: dejarlo también como parámetro (en cascada o solo la cuota afectada) y usar la cascada por defecto. |
| D14 | Valor de la mora | Porcentaje diario parametrizable | Se configura por producto. Propuesta: se calcula sobre el valor vencido de la cuota, no sobre el saldo total, con un tope configurable que no supere la usura. |
| D15 | Castigo y bloqueo | Parametrizables | Por producto: días de atraso para poder castigar. Global: umbral para la lista de bloqueo y si el bloqueo es automático o manual. |
| D16 | Codeudor | Se indica al crear el crédito si es opcional u obligatorio | Es un campo del crédito, no del producto. Si es obligatorio, el crédito no se puede aprobar sin codeudor. |

### 1.1 Métodos de cálculo del interés propuestos para la v1

Cada producto elige uno. Todos comparten el redondeo, el ajuste de la última cuota y la regla de que la suma del capital es igual al monto.

| Método | Cómo se calcula | Ejemplo con $100.000, 10 % y 20 cuotas diarias |
|---|---|---|
| **Plano fijo por crédito** | Un porcentaje sobre el capital por todo el crédito, sin importar el plazo | Interés de $10.000 y cuotas de $5.500 |
| **Plano mensual prorrateado** | Tasa mensual × meses de plazo × capital | 20 días ≈ 0,67 meses, interés ≈ $6.667 y cuotas ≈ $5.333 |
| **Plano por cuota** | Tasa por periodo × número de cuotas × capital | Con 0,5 % diario: interés de $10.000 y cuotas de $5.500 |
| **Cuota fija (francés)** | Interés sobre el saldo, con cuota constante | |
| **Capital fijo (alemán)** | Abono constante a capital, con cuota decreciente | |
| **Interés sobre saldo** | Interés del periodo sobre el saldo pendiente | |

Los tres primeros son los habituales en el gota a gota y van en la spec 007. Los otros tres van en la 009. Hay que confirmar en la spec si la lista se queda así.

### Preguntas que siguen pendientes

- **P5. Retención de 1 año.** En Colombia, los libros y soportes contables se conservan 10 años (art. 60 del Código de Comercio y art. 28 de la Ley 962 de 2005). Propuesta: la auditoría de **accesos y sesiones** se retiene 1 año, y la auditoría de **operaciones financieras** se conserva mientras exista el registro financiero. Confirmar con un asesor.
- **P7. Quién decide si el codeudor es obligatorio.** ¿Lo marca el cobrador en la solicitud, o el supervisor al aprobar? Propuesta: el cobrador lo propone y el supervisor puede volverlo obligatorio al aprobar.

Las preguntas P1 a P4 y P6 quedaron resueltas con D12 a D16.

---

## 2. Criterios usados para ordenar

1. **Dependencias primero.** Cada spec solo usa cosas que ya existen en specs anteriores.
2. **Valor visible temprano.** Después de cada bloque debe haber algo que se pueda usar y probar en el navegador.
3. **Specs pequeñas.** Cada spec se puede implementar y verificar en pocos días.
4. **Se respeta el orden de la §16.3**, con los ajustes de la sección 5.

## 3. Vista general

| # | Spec | Bloque | Apps | Depende de |
|---|---|---|---|---|
| 000 | Fundación del proyecto | Base | `config/` | — |
| 001 | Layout base y menú modular | Base | `core` | 000 |
| 002 | Autenticación | Núcleo | `accounts` | 001 |
| 003 | Usuarios, roles y permisos | Núcleo | `accounts` | 002 |
| 004 | Auditoría base (registro) | Núcleo | `auditoria` | 003 |
| 005 | Parámetros globales (SPEC 06) | Configuración | `parametros` | 004 |
| 005b | Catálogos y festivos (SPEC 07) | Configuración | `parametros` | 005 |
| 006 | Productos de crédito y tasas | Configuración | `parametros` | 005 |
| 007 | Motor I: métodos de interés plano y redondeo | Motor | `amortizacion` | 000 |
| 008 | Motor II: calendario de vencimientos | Motor | `amortizacion` | 007 |
| 009 | Motor III: métodos sobre saldo y tasas equivalentes | Motor | `amortizacion` | 008 |
| 010 | Simulador de crédito | Motor | `creditos` | 006, 009 |
| 011 | Clientes | Operación | `clientes` | 005 |
| 012 | Terceros (codeudores y referencias) | Operación | `clientes` | 011 |
| 013 | Documentos y fotos | Operación | `clientes` | 012 |
| 014 | Solicitud, aprobación y rechazo de créditos | Operación | `creditos` | 006, 010, 012 |
| 015 | Desembolso y plan de pagos | Operación | `creditos` | 014 |
| 016 | Registro de pagos y recibos | Operación | `pagos` | 015 |
| 017 | Anulación de pagos | Operación | `pagos` | 016 |
| 018 | Mora | Operación | `mora` | 016 |
| 019 | Castigo de cartera y reestructuración | Operación | `creditos` | 018 |
| 020 | Cierre diario de caja | Operación | `pagos` | 017 |
| 021 | Dashboard por rol | Análisis | `reportes` | 018, 020 |
| 022 | Reportes operativos y exportación | Análisis | `reportes` | 020 |
| 023 | Reportes formales en PDF | Análisis | `reportes` | 022 |
| 024 | Consulta y retención de auditoría | Núcleo | `auditoria` | 004 |
| 025 | Endurecimiento de seguridad y producción | Cierre | transversal | todas |
| 026 | Datos de ejemplo, manuales y entrega | Cierre | transversal | todas |

Las specs 007 a 009 no dependen de Django, así que se pueden trabajar en paralelo con 002 a 006.

---

## 4. Detalle de cada spec

### Bloque A: Base

#### 000 · Fundación del proyecto
- **Incluye:**
  - Paquete `config/` con settings separados (`base`, `dev`, `prod`).
  - Carpetas `apps/`, `docs/specs/` y `docs/decisiones/`.
  - Secretos por variables de entorno y `.env.example`.
  - PostgreSQL con Docker y docker-compose.
  - Idioma `es-co`, zona horaria `America/Bogota` e i18n.
  - pytest y pytest-django, Ruff y Black.
  - CI y `README.md`.
  - Repositorio git.
- **Decisiones previas:**
  - **Enmienda de la §4** para usar Python 3.14 y Django 6.1 (D2).
  - **ADR-001:** un solo negocio preparado para crecer (D1).
  - **ADR-003:** librería de PDF (WeasyPrint, xhtml2pdf o ReportLab). Se usa desde la 015. Era el ADR-002, pero ese número lo tomó la sincronización de roles de la SPEC 04.
  - Proveedor de CI.
- **Criterio clave:** `docker-compose up` levanta la app y `uv run pytest` pasa en limpio.

#### 001 · Layout base y menú modular
- **Incluye:**
  - `base.html` derivado de SB Admin 2, con los recursos en `static/`.
  - Plantillas de error 403, 404 y 500.
  - Mensajes, tablas, formularios y modal de confirmación.
  - **Registro de módulos:** cada app declara su nombre, icono, ruta, orden y permisos, y con eso se construye el menú lateral.

### Bloque B: Núcleo de acceso

#### 002 · Autenticación
- **Incluye:**
  - Inicio de sesión con usuario o correo, y cierre de sesión.
  - Recuperación de contraseña por correo.
  - Cambio obligatorio de contraseña en el primer ingreso.
  - Bloqueo después de N intentos fallidos.
  - Validadores de complejidad y hashing con Argon2.
- **Nota:** el número de intentos y la política de contraseñas se leen de un servicio de parámetros con valores por defecto (5 intentos, 15 minutos de bloqueo). La spec 005 los vuelve editables.
- **Implementada como SPEC 03 (`specs/03-autenticacion.md`).** El correo de recuperación es simulado (consola o archivo), sin SMTP en ningún entorno.
- **Salió de esta spec y queda pendiente de ubicar:**
  - **Cierre de sesión por inactividad (§6.1).** Quedó ubicado e implementado en la SPEC 06 (parámetros globales), junto con la duración máxima de la sesión como parámetro.
  - **Trato uniforme en los textos (tú o usted).** Los textos propios usan "tú", pero varios textos de Django que se ven en las pantallas de contraseña usan "usted" (SPEC 03, §4.1). Resolverlo exige sobrescribir textos de Django.

#### 003 · Usuarios, roles y permisos
- **Incluye:**
  - Grupos Administrador, Supervisor, Cajero/Cobrador y Consulta, creados por migración de datos.
  - Creación, edición y desactivación de usuarios por el administrador.
  - Regla de que nadie puede cambiar su propio nivel de acceso.
  - Invalidación de sesiones al desactivar un usuario o cambiar su contraseña.
  - Utilidades de permisos para vistas y servicios.
  - Menú filtrado por rol.
- **Nota:** aquí se define qué es "un cobrador", porque créditos, pagos, cierre y dashboard filtran por él.
- **Implementada como SPEC 04 (`specs/04-usuarios-roles-permisos.md`).** Decisiones que afectan a las specs siguientes:
  - Cada usuario tiene exactamente un rol. Los permisos de cada rol están en `ROLE_PERMISSIONS` (`apps/accounts/roles.py`), y `sync_roles` los aplica después de cada `migrate` (ADR-002). **Cada spec que cree un módulo agrega ahí los permisos de sus modelos.**
  - "Cobrador" es un usuario activo, que no es superusuario, con el rol Cajero/Cobrador (`User.objects.collectors()`). No hay relación entre supervisor y cobradores: todo supervisor ve a todos.
  - El usuario tiene teléfono y documento. El tipo de documento usa opciones fijas (`CC`, `CE`, `PPT`, `PA` y `TI`); la 005 decide si pasa al catálogo de tipos de documento.
  - Las acciones sobre usuarios (crear, editar, desactivar con motivo, reactivar, desbloquear, restablecer la contraseña y cerrar sesiones) pasan por servicios que reciben al `actor`. La 004 (auditoría) los audita desde ahí.

#### 004 · Auditoría base
- **Incluye:**
  - Registro inmutable con usuario, fecha y hora, acción, entidad, valores anteriores y nuevos, e IP.
  - Servicio de registro y middleware.
  - Bloqueo de edición y borrado desde la aplicación.
  - Auditoría de inicios de sesión y de la gestión de usuarios.
  - Una categoría en cada registro (acceso, operación financiera o datos personales), para aplicar retenciones distintas en la 024.
- **Fuera de alcance:** la pantalla de consulta, que queda en la 024.
- **Implementada como SPEC 05 (`specs/05-auditoria-base.md`).** Decisiones que afectan a las specs siguientes:
  - **Cada spec que cree un módulo audita sus acciones:**
    - Agrega las acciones a `AuditAction` y a `ACTION_CATEGORIES` (`apps/auditoria/actions.py`).
    - Llama a `record(...)` dentro de la transacción del servicio, con `changes=diff(antes, después)` tomado con `snapshot`.
    - Incluye criterios de aceptación de su auditoría.
  - **Cuatro categorías, no tres:** acceso, seguridad (gestión de usuarios), datos personales y operación financiera. La categoría la fija el catálogo, no quien llama.
  - **Señales:** los ingresos, los fallos de ingreso y los cierres de sesión se auditan con las señales de autenticación de Django (ADR-004). Nada más usa señales.
  - **Inmutabilidad:** la aplicación rechaza la edición y el borrado, y un trigger de PostgreSQL rechaza `UPDATE` y `DELETE`. `TRUNCATE` sigue abierto (ver la 025).
  - **Consulta provisional:** mientras llega la 024, los registros solo se consultan en el admin de Django, de solo lectura y solo para superusuarios. Ningún rol tiene `auditoria.view_auditevent`.
  - **IP del cliente:** sale de `REMOTE_ADDR`. `X-Forwarded-For` solo se lee con `AUDIT_TRUSTED_PROXIES` mayor que 0; detrás de un nginx propio, `1`.
  - **Campos secretos:** nunca guardan su valor. Quedan como `"[oculto]"` según `SENSITIVE_FIELDS` (`apps/auditoria/services.py`), y cada spec la amplía si trae otro campo secreto.

### Bloque C: Configuración

#### 005 · Parámetros globales y catálogos
- **Parámetros globales:**
  - Nombre del negocio, logo, moneda y formato numérico y de fecha.
  - Días y horarios de cobro, y **qué días son no hábiles** (domingos y festivos) con su regla de corrimiento (D5).
  - Políticas de contraseña, número de intentos y tiempo de sesión.
  - Regla de redondeo por defecto.
- **Catálogos:**
  - Tipos de documento, ocupaciones y destinos de crédito.
  - Motivos de anulación y de rechazo.
  - **Festivos de Colombia**, con carga inicial y mantenimiento.
  - Tipos de relación de terceros: codeudor, referencia personal y otros.
- **Diseño:** un registro único de configuración, no constantes en el código (D1).
- **Se dividió en dos specs:**
  - **SPEC 06 (`specs/06-parametros-globales.md`), implementada:** los parámetros globales.
  - **SPEC 07, pendiente:** los catálogos (tipos de documento, ocupaciones, destinos de crédito, motivos de anulación y de rechazo, tipos de relación de terceros) y los festivos de Colombia con su carga inicial. Amplía `is_business_day` con los festivos sin cambiar su firma.
- **Decisiones de la SPEC 06 que afectan a las specs siguientes:**
  - Los parámetros globales solo se leen con `apps/parametros/services.py` (`get_settings`, `get_rounding_rule`, `is_business_day`). Un parámetro global nuevo es un campo tipado de `GlobalSettings`, nunca una constante ni un setting.
  - El redondeo por defecto es un múltiplo (1, 10, 50, 100, 500 o 1.000) y un modo (al más cercano, hacia arriba o hacia abajo), por defecto múltiplo de 50 al más cercano. El motor (007 y 008, que pasan a ser las SPEC 09 y 10) lo recibe como `RoundingRule`, sin importar `parametros`.
  - La regla de corrimiento (en cascada o solo la cuota afectada, D13) y los días de la semana no hábiles ya están en los parámetros, con la cascada por defecto. El calendario del motor los recibe como parámetros.
  - Los días y el horario de cobro se guardan, pero nada los aplica todavía. Lo decide la spec de pagos (016).
  - La zona horaria sigue fija en `America/Bogota`.
  - El cierre de sesión por inactividad (30 minutos) y la duración máxima (12 horas) son parámetros, y los aplica `SessionPolicyMiddleware`.
  - El tipo de documento de los usuarios internos sigue con la lista fija de la SPEC 04. El catálogo de la SPEC 07 es para clientes y terceros.

#### 006 · Productos de crédito y tasas
- **Incluye:**
  - CRUD de productos con los campos de la §10.2.
  - **Método de cálculo del interés**, elegido de la lista de la sección 1.1 (D12).
  - Tasa con su unidad según el método (por crédito, mensual o por periodo), rango permitido, valor por defecto e historial de vigencia.
  - Tope de usura configurable con su historial. Se compara convirtiendo la tasa del producto a efectiva anual.
  - Las cuatro periodicidades, con la permitida y la de por defecto (D4).
  - Mora: tolerancia por defecto de 0 días (D6), **porcentaje diario** y tope (D14).
  - **Días de atraso para poder castigar** (D15).
  - Activar y desactivar productos.

### Bloque D: Motor de amortización (lógica pura, 100 % de cobertura)

#### 007 · Motor I: métodos de interés plano y redondeo
- **Incluye:**
  - Contrato de entrada y salida con dataclasses tipadas y `Decimal`.
  - Diseño con un método intercambiable: cada método es una estrategia que se registra, para agregar métodos nuevos sin tocar los existentes (D12).
  - Los tres métodos planos de la sección 1.1: **plano fijo por crédito**, **plano mensual prorrateado** y **plano por cuota**, con el interés repartido en cada cuota.
  - Regla de prorrateo para el método mensual: días reales del plazo o meses de 30 días. Se decide en la spec.
  - Redondeo configurable y ajuste de la última cuota.
  - Totales de capital, interés y costo total.
- **Casos límite:** 1 cuota, tasa cero, montos muy pequeños, la suma del capital igual al monto y saldo final igual a 0.

#### 008 · Motor II: calendario de vencimientos
- **Incluye:**
  - Periodicidad diaria, semanal, quincenal y mensual (D4).
  - Fecha de inicio y regla para fin de mes (por ejemplo, el día 31).
  - Corrimiento al siguiente día hábil (D5), **en cascada**: las cuotas siguientes también se corren (D13). Los festivos entran como una lista de fechas.
  - Propuesta: la cascada como parámetro, con la opción de correr solo la cuota afectada.
  - Periodos de gracia.
- **Casos de prueba:**
  - Festivos seguidos (por ejemplo, Semana Santa).
  - Un festivo en lunes después de un domingo.
  - Créditos diarios que cruzan el fin de año.
  - Una cascada que empuja la última cuota a otro mes.

#### 009 · Motor III: métodos sobre saldo y tasas equivalentes
- **Incluye:**
  - Métodos francés, alemán e interés sobre saldo, como estrategias nuevas del motor.
  - Conversión de cualquier método a tasa efectiva anual (la necesita la validación de usura) y costo financiero total.
  - Cuota mínima y tolerancia de pago.
- **Nota:** entra en la v1, porque se quiere tener variedad de métodos (D12).

#### 010 · Simulador de crédito
- **Incluye:** selección de producto, monto, cuotas y periodicidad, con la tabla calculada en el servidor y sin persistir nada.
- **Uso:** es la base del formulario de solicitud.

### Bloque E: Operación

#### 011 · Clientes
- **Incluye:**
  - Datos de la §7.1.
  - Documento único por tipo.
  - Estados activo, inactivo y en lista de bloqueo.
  - Búsqueda con DataTables y ficha con historial.
  - **Autorización de tratamiento de datos** según la Ley 1581.
  - Coordenadas opcionales, sin mapa (D8).

#### 012 · Terceros (codeudores y referencias)
- **Objetivo:** un formulario genérico de personas relacionadas que no son el deudor (D9).
- **Incluye:**
  - Datos básicos (documento, nombres, teléfonos, dirección y ocupación).
  - Autorización de tratamiento de datos.
  - Búsqueda por documento para reutilizar un tercero que ya existe.
- **Relaciones:**
  - Un tercero puede ser **referencia personal** de un cliente. Así se cumple el mínimo y máximo de referencias de la §7.1.
  - Un tercero puede ser **codeudor** de un crédito. La asociación se hace en la 014.
- **Decisiones previas:**
  - ¿Un cliente puede ser codeudor de otro? Propuesta: sí. Si el documento ya existe como cliente, se reutiliza la persona.
  - ¿Clientes y terceros comparten un modelo base de "persona"? Se decide en el plan técnico.

#### 013 · Documentos y fotos
- **Incluye:**
  - Foto y documento del cliente y del tercero.
  - Validación de tipo y tamaño.
  - Almacenamiento fuera del directorio público y descarga con verificación de permisos.
- **Nota:** se puede posponer sin bloquear nada.

#### 014 · Solicitud, aprobación y rechazo de créditos
- **Incluye:**
  - Solicitud a partir del simulador.
  - **Asociación del deudor (cliente) y del codeudor (tercero)** (D9).
  - **Indicador de codeudor opcional u obligatorio en cada crédito** (D16). Si es obligatorio, no se puede aprobar sin codeudor (ver P7).
  - Validaciones de monto, límite de créditos activos y cliente bloqueado.
  - Aprobación por el supervisor con la **tasa congelada al aprobar**.
  - Rechazo con motivo y cancelación antes del desembolso.
  - Máquina de estados auditada.

#### 015 · Desembolso y plan de pagos
- **Incluye:**
  - Desembolso atómico con gastos o descuentos iniciales.
  - **Snapshot inmutable** de la tabla de amortización.
  - Detalle del crédito: resumen, cuotas, pagos e historial.
  - **Plan de pagos en PDF.**
- **Decisión previa:** si "Desembolsado" y "Activo" son estados distintos. Propuesta: el crédito pasa a Activo en la misma operación y queda registrada la transición.

#### 016 · Registro de pagos y recibos
- **Incluye:**
  - Pago de la cuota completa, abono parcial y pago de varias cuotas.
  - Orden de aplicación configurable: mora, luego interés, luego capital.
  - Saldo a favor explícito.
  - **Recibo en PDF con número consecutivo sin huecos** (D7).
  - Paso a Cancelado cuando el saldo llega a 0.
  - Flujo corto y responsive.
- **Nota:** se trabaja siempre en línea (D8).
- **Decisión previa:** formas de pago (efectivo, transferencia, otras).

#### 017 · Anulación de pagos
- **Incluye:**
  - Anulación por un supervisor con motivo.
  - Reversión de la aplicación a las cuotas.
  - El recibo anulado se conserva y su número no se reutiliza.

#### 018 · Mora
- **Incluye:**
  - Proceso diario idempotente: la cuota queda vencida **desde el día siguiente al vencimiento** (D6, tolerancia 0 parametrizable).
  - Cálculo de la mora con el **porcentaje diario del producto** sobre el valor vencido, con su tope (D14).
  - Transición Activo ↔ En mora.
  - Lista de bloqueo según el umbral global, automática o manual según el parámetro (D15).
- **Nota:** el valor de la mora también debe respetar el tope de usura.

#### 019 · Castigo de cartera y reestructuración
- **Incluye:**
  - Castigo con permiso de administrador y confirmación explícita, posible solo cuando el atraso supera los días configurados en el producto (D15).
  - Reestructuración que crea un crédito nuevo vinculado.

#### 020 · Cierre diario de caja
- **Incluye:**
  - El **supervisor** cierra la caja de cada cobrador (D10).
  - Resumen del día, firma con usuario y fecha, y cierre inmutable con ajustes.
- **Decisión previa:** qué pasa con un pago registrado en una caja ya cerrada (se rechaza o va a la caja del día siguiente).

### Bloque F: Análisis

#### 021 · Dashboard por rol
- **Incluye:**
  - Tarjetas y gráficas con Chart.js con datos calculados en el servidor.
  - Listas de acción.
  - El cobrador ve solo sus datos.

#### 022 · Reportes operativos y exportación
- **Incluye:**
  - Cartera vigente, cartera en mora, recaudo y créditos desembolsados.
  - Filtros por fecha, cobrador, producto y estado.
  - Exportación a XLSX y CSV, auditada.

#### 023 · Reportes formales en PDF
- **Incluye:** cierre de caja firmado, historial del cliente y plan de pagos, con la plantilla de PDF común de la 015.

### Bloque G: Cierre

#### 024 · Consulta y retención de auditoría (será la SPEC 26)
- **Incluye:**
  - Pantalla solo para administradores, con filtros por usuario, fecha y entidad.
  - **Depuración automática a 1 año** (D11), según la categoría del registro (P5).
- **Nota (SPEC 05):**
  - La depuración tiene que pasar el trigger `auditoria_auditevent_immutable` por una vía controlada (ADR-004).
  - Esta spec asigna `auditoria.view_auditevent` en `ROLE_PERMISSIONS`.
  - La categoría `security` (gestión de usuarios) necesita su propia retención.

#### 025 · Endurecimiento de seguridad y producción
- **Incluye:**
  - HTTPS y HSTS, CSP y X-Frame-Options.
  - Usuario de base de datos con mínimos privilegios. Entre otros, sin permiso de `TRUNCATE` sobre `auditoria_auditevent` (SPEC 05, ADR-004).
  - Respaldos diarios con prueba de restauración.
  - Pruebas de inyección.
  - Revisión de seguridad y política de datos personales.

#### 026 · Datos de ejemplo, manuales y entrega
- **Incluye:**
  - Datos de ejemplo, ampliados en cada spec.
  - Manual por rol.
  - Verificación de los criterios de la §18.

### Fase 2
- Ruta de cobro con mapa y geolocalización (D8).
- Pagos sin conexión con sincronización (D8).
- Impresión de recibos en impresora térmica (D7).
- Recordatorios y procesos automáticos con Celery y Redis.
- Multi-tenant (D1).

---

## 5. Diferencias con la constitución que conviene resolver

1. **§4, stack.** Se pasa a las últimas versiones de Python y Django (D2). Requiere una enmienda formal.
2. **§16.2 frente a §16.3.** La numeración de ejemplo no coincide con el orden de implementación. Esta hoja sigue el orden de la §16.3.
3. **Auditoría.** Se divide en el registro (004, temprano) y la consulta con retención (024).
4. **Dashboard.** No figura en la §16. Aquí queda como 021.
5. **Reportes.** La información adicional dice que pueden ir en una fase posterior, pero la §12.1 los declara obligatorios en la v1. Hay que definirlo.
6. **§19.** Las preguntas 1 a 8 quedan resueltas con D1 a D16. Conviene actualizar la sección con estas decisiones.
9. **§9.1, métodos de amortización.** Agregar los tres métodos planos de la sección 1.1, porque la constitución solo menciona uno.
10. **§10.2, productos.** Ya no incluye el codeudor, que ahora se define en cada crédito (D16).
7. **§3.2 y §19.4 a §19.6.** Agregar a la lista de exclusiones de la v1 el trabajo sin conexión, la geolocalización y la impresión térmica.
8. **§7.1, referencias personales.** Pasan a ser terceros relacionados (D9). Es un cambio de modelo, no de regla.
