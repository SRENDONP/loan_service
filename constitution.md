# Constitución del Proyecto: Sistema de Gestión de Préstamos (Gota a Gota)

> Documento fundacional del proyecto. Todas las especificaciones, planes y tareas derivadas
> (metodología SDD) deben respetar lo aquí establecido. Ante cualquier conflicto, prevalece
> esta constitución sobre cualquier otro documento, salvo que se modifique formalmente.

---

## 1. Propósito

Construir un sistema de información web que permita gestionar de forma integral préstamos de
pequeña cuantía con cobro en cuotas frecuentes (diarias, semanales, quincenales o mensuales),
cubriendo:

- Autenticación y control de acceso de usuarios.
- Registro y administración de clientes.
- Creación y administración de créditos.
- Generación de tablas de amortización y planes de pago.
- Registro de pagos y seguimiento de mora.
- Reportes operativos y financieros.
- Parametrización completa de las reglas del negocio (tasas, cuotas, periodicidad, etc.).

---

## 2. Principios Rectores

1. **Parametrizar antes que codificar.** Ninguna regla de negocio que pueda variar (tasa,
   número de cuotas, periodicidad, método de amortización, días de cobro, multas, redondeo)
   puede estar fija en el código. Debe vivir en configuración administrable.
2. **Trazabilidad total.** Todo cambio sobre clientes, créditos, cuotas y pagos debe quedar
   registrado: quién, cuándo y qué cambió. Los registros financieros no se borran físicamente;
   se anulan con motivo.
3. **Integridad financiera.** Los cálculos monetarios usan `Decimal`, nunca `float`. Los
   importes se redondean según una regla configurable y explícita. Un crédito nunca puede
   quedar con saldos negativos ni con cuotas que no sumen el capital más intereses.
4. **Seguridad por defecto.** Acceso autenticado obligatorio, permisos por rol, y protección
   de datos personales.
5. **Interfaz fiel a la referencia.** La UI debe respetar el HTML/CSS suministrado como
   referencia visual; no se rediseña sin aprobación.
6. **Simplicidad operativa.** El sistema será usado por personas con poca formación técnica.
   Los flujos de cobro deben poder completarse en pocos pasos.
7. **Spec antes que código.** Ninguna funcionalidad se implementa sin una especificación
   aprobada (ver Sección 13).

---

## 3. Alcance

### 3.1 Incluido (versión 1)

- Gestión de usuarios, roles y autenticación.
- Gestión de clientes (datos personales, referencias, documento de identidad, historial).
- Gestión de créditos (solicitud, aprobación, desembolso, estados).
- Cálculo de tabla de amortización y generación del plan de pagos.
- Registro de pagos (totales y parciales/abonos).
- Gestión de mora, cálculo de saldos y cierre de créditos.
- Reportes (cartera, recaudo, mora, clientes, caja diaria).
- Panel de parametrización del sistema.
- Auditoría de cambios.

### 3.2 Excluido (versión 1)

- Integración con pasarelas de pago o bancos.
- Aplicación móvil nativa (la interfaz debe ser responsive, pero es web).
- Desembolsos automáticos a cuentas bancarias.
- Score crediticio automatizado o centrales de riesgo.
- Facturación electrónica DIAN.

Cualquier elemento excluido requiere una enmienda a esta constitución.

---

## 4. Stack Tecnológico

| Capa | Tecnología | Notas |
|---|---|---|
| Lenguaje | Python 3.14+ | Última versión estable (decisión D2) |
| Framework web | Django 6.1 | Vistas basadas en plantillas Django (SSR). Última versión estable (decisión D2) |
| Base de datos | PostgreSQL 16+ | Único motor soportado, también en las pruebas. PostgreSQL 18 en Docker y en CI |
| ORM | Django ORM | No se usa SQL crudo salvo para reportes complejos, documentado |
| Autenticación | Sistema de autenticación de Django, extendido | Ver Sección 6 |
| Frontend | HTML, CSS y JavaScript vanilla sobre la referencia suministrada | Sin frameworks SPA |
| Tareas asíncronas | Celery + Redis (opcional, fase 2) | Para recordatorios y cierres diarios |
| Pruebas | pytest + pytest-django | Cobertura mínima en Sección 12 |
| Calidad de código | Black, Ruff, mypy (opcional) | |
| Contenedores | Docker y docker-compose | Entorno de desarrollo reproducible |
| Variables de entorno | django-environ | Ningún secreto en el repositorio |

---

## 5. Arquitectura

### 5.1 Estructura de aplicaciones Django

```
proyecto/
├── config/                 # Settings (base, dev, prod), urls raíz, wsgi/asgi
├── apps/
│   ├── accounts/           # Usuarios, roles, autenticación, permisos
│   ├── clientes/           # Gestión de clientes
│   ├── creditos/           # Solicitudes, créditos, estados
│   ├── amortizacion/       # Motor de cálculo (lógica pura, sin dependencias de vistas)
│   ├── pagos/              # Registro de pagos, abonos, aplicación a cuotas
│   ├── mora/               # Cálculo de mora y estados de atraso
│   ├── reportes/           # Consultas y exportación (PDF/Excel/CSV)
│   ├── parametros/         # Configuración parametrizable del sistema
│   └── auditoria/          # Registro de cambios
├── templates/              # Plantillas base y compartidas
├── static/                 # CSS y JS derivados de la referencia suministrada
├── specs/                  # Specs SDD (NN-slug.md), gestionadas con las skills /spec y /spec-impl
├── docs/                   # Decisiones (ADR) y documentación de apoyo
└── tests/
```

### 5.2 Reglas de arquitectura

- **El motor de amortización es lógica pura.** La app `amortizacion` no importa modelos de
  Django ni hace consultas a la base de datos. Recibe parámetros y devuelve resultados. Esto
  permite probarlo de forma aislada y con cobertura total.
- **Servicios sobre vistas.** La lógica de negocio vive en módulos `services.py` por app. Las
  vistas solo validan entrada, invocan servicios y renderizan respuestas.
- **Transacciones atómicas.** Operaciones que afecten varias tablas (desembolso, registro de
  pago, anulación) se ejecutan dentro de `transaction.atomic()`.
- **Sin lógica financiera en plantillas ni en JavaScript.** El cálculo siempre ocurre en el
  servidor. El frontend solo muestra resultados.

---

## 6. Autenticación y Control de Acceso

### 6.1 Requisitos

- Registro de usuarios solo por un administrador (no hay registro público abierto).
- Inicio y cierre de sesión con usuario o correo y contraseña.
- Recuperación de contraseña por correo electrónico.
- Cambio de contraseña obligatorio en el primer ingreso.
- Bloqueo temporal tras N intentos fallidos (N parametrizable, por defecto 5).
- Expiración de sesión por inactividad (tiempo parametrizable, por defecto 30 minutos).
- Contraseñas con hashing seguro (PBKDF2 o Argon2 vía Django) y validadores de complejidad.

### 6.2 Roles

| Rol | Descripción | Permisos principales |
|---|---|---|
| **Administrador** | Dueño o gerente del negocio | Todo, incluido parametrización y gestión de usuarios |
| **Supervisor** | Coordina cobradores | Aprobar créditos, anular pagos, ver todos los reportes |
| **Cajero/Cobrador** | Opera en campo o caja | Registrar clientes, crear solicitudes, registrar pagos |
| **Consulta** | Solo lectura | Ver clientes, créditos y reportes |

Los permisos se asignan mediante grupos de Django y se verifican en cada vista y servicio
sensible. Ningún rol puede modificar su propio nivel de acceso.

### 6.3 Reglas

- Toda acción sensible requiere permiso explícito, no basta con estar autenticado.
- Las sesiones se invalidan al cambiar la contraseña o desactivar al usuario.
- Los usuarios se desactivan, nunca se eliminan (preserva la trazabilidad).

---

## 7. Módulo de Clientes

### 7.1 Datos del cliente

- Tipo y número de documento (único por combinación).
- Nombres, apellidos, fecha de nacimiento (opcional).
- Teléfonos (principal y alterno), correo (opcional).
- Dirección de residencia y dirección de negocio, con referencia textual.
- Coordenadas geográficas opcionales (para ruta de cobro).
- Ocupación o actividad económica.
- Referencias personales (mínimo una, máximo parametrizable).
- Fotografía del cliente y del documento (opcional, almacenamiento seguro).
- Estado: activo, inactivo, en lista de bloqueo.

### 7.2 Reglas

- No se puede crear un crédito a un cliente en lista de bloqueo.
- El historial del cliente (créditos, pagos, mora) es consultable desde su ficha.
- Los datos personales se tratan conforme a la Sección 11.

---

## 8. Módulo de Créditos

### 8.1 Ciclo de vida del crédito

```
Solicitado ──► Aprobado ──► Desembolsado ──► Activo ──► Cancelado
     │             │                            │
     └──► Rechazado└──► Cancelado (antes         └──► En mora ──► Activo / Castigado
                         de desembolsar)
```

- **Solicitado:** registrado por el cobrador, pendiente de revisión.
- **Aprobado:** autorizado por un supervisor, con condiciones finales.
- **Rechazado:** no aprobado; se conserva con motivo.
- **Desembolsado:** se entrega el capital; genera el plan de pagos definitivo.
- **Activo:** en curso, con cuotas pendientes.
- **En mora:** con al menos una cuota vencida más allá del periodo de gracia.
- **Cancelado:** saldo en cero.
- **Castigado:** cartera incobrable (requiere permiso de administrador).

Las transiciones de estado están restringidas por reglas explícitas y quedan auditadas.

### 8.2 Datos del crédito

- Cliente, monto solicitado y monto aprobado.
- Tasa de interés (ver Sección 10), método de amortización, periodicidad y número de cuotas.
- Fecha de solicitud, aprobación y desembolso.
- Gastos o descuentos iniciales (opcional, parametrizable).
- Garantía o codeudor (opcional).
- Destino del crédito (opcional).
- Observaciones.

### 8.3 Reglas

- El monto está entre el mínimo y el máximo configurados para el tipo de crédito.
- Un cliente no puede tener más créditos activos que el límite parametrizado.
- Un crédito desembolsado no puede modificar su tasa, monto o cuotas. Si se requiere
  reestructuración, se crea un nuevo crédito vinculado al anterior.
- Los créditos anulados antes del desembolso no generan movimientos contables.

---

## 9. Motor de Amortización y Plan de Pagos

Este es el núcleo financiero del sistema. Debe ser exacto, probado y totalmente parametrizable.

### 9.1 Métodos de amortización soportados

| Método | Descripción | Uso típico |
|---|---|---|
| **Interés plano (flat)** | Interés calculado sobre el capital original, repartido en cuotas iguales | Gota a gota tradicional |
| **Cuota fija (francés)** | Cuota constante; el interés baja y el capital sube en el tiempo | Préstamos formales |
| **Capital fijo (alemán)** | Abono a capital constante; cuota decreciente | Casos especiales |
| **Interés sobre saldo** | Interés calculado sobre el saldo pendiente en cada periodo | Flexible |

El método se define por tipo de crédito y puede parametrizarse.

### 9.2 Parámetros del cálculo

- **Monto del capital.**
- **Tasa de interés** por periodo, con su equivalencia a tasa efectiva anual para mostrar.
- **Número de cuotas.**
- **Periodicidad:** diaria, semanal, quincenal o mensual.
- **Días no hábiles:** domingos, festivos y días personalizados, con opción de saltarlos o
  cobrarlos.
- **Fecha de inicio** y regla de vencimiento.
- **Redondeo:** a la unidad, a la decena, a la centena, o a centavos; y regla de ajuste de la
  última cuota para cuadrar la diferencia.
- **Gracia:** número de periodos sin cuota o solo interés (parametrizable).
- **Cuota mínima** y tolerancia de pago.

### 9.3 Salidas del motor

- Tabla de amortización completa: número de cuota, fecha de vencimiento, saldo inicial,
  capital, interés, cuota total, saldo final.
- Totales: capital, intereses, costo total del crédito.
- Tasa efectiva y costo financiero total.

### 9.4 Reglas del motor

- La suma de capitales de todas las cuotas debe ser igual al monto desembolsado (diferencia
  cero, verificada por prueba).
- El saldo final después de la última cuota debe ser exactamente cero.
- El motor es determinista: mismos parámetros, mismo resultado.
- Toda tabla generada se persiste como snapshot inmutable al desembolsar.

### 9.5 Plan de pagos

- Es la vista operativa de la tabla de amortización, con estado por cuota: pendiente, pagada,
  parcial, vencida.
- Cada cuota registra los pagos aplicados y la fecha de cancelación.
- Debe poder exportarse en PDF para entregar al cliente.

---

## 10. Parametrización

Todo lo que pueda variar debe administrarse desde el módulo `parametros`, sin tocar código.

### 10.1 Parámetros globales

- Nombre del negocio, logo, moneda y formato numérico.
- Zona horaria y formato de fecha.
- Días y horarios de cobro permitidos.
- Políticas de contraseña, intentos de bloqueo y tiempo de sesión.
- Regla de redondeo por defecto.

### 10.2 Parámetros por tipo de crédito (productos)

Cada producto de crédito define su propia configuración:

- Nombre del producto.
- Monto mínimo y máximo.
- Tasa de interés (rango permitido y valor por defecto).
- Método de amortización.
- Periodicidad permitida y por defecto.
- Número de cuotas mínimo, máximo y por defecto.
- Días de gracia y periodo de gracia.
- Porcentaje de mora y días de tolerancia antes de considerar mora.
- Gastos iniciales o descuentos (fijos o porcentuales).
- Límite de créditos activos por cliente.
- Activo o inactivo.

### 10.3 Control de tasas

- Las tasas se almacenan con historial de vigencia (fecha desde / fecha hasta).
- Un crédito conserva la tasa vigente al momento de su aprobación, aunque la tasa del producto
  cambie después.
- El sistema debe validar contra un **límite máximo legal de tasa de usura** configurable.
  Cualquier tasa que lo supere se bloquea y se advierte al usuario. El valor debe mantenerse
  actualizado con la certificación vigente de la Superintendencia Financiera de Colombia.

### 10.4 Catálogos administrables

- Tipos de documento, ocupaciones, destinos de crédito, motivos de anulación, motivos de
  rechazo, días festivos.

---

## 11. Pagos, Mora y Cierre

### 11.1 Registro de pagos

- Un pago puede ser total de la cuota, abono parcial o pago de varias cuotas.
- Orden de aplicación configurable: primero mora, luego intereses, luego capital (por defecto).
- Cada pago genera un recibo con número consecutivo único, sin huecos.
- Los pagos se anulan con motivo y autorización de supervisor; nunca se eliminan.
- Un pago no puede exceder el saldo pendiente sin generar un saldo a favor, que debe
  registrarse explícitamente.

### 11.2 Mora

- Una cuota pasa a vencida al superar la fecha de vencimiento más los días de tolerancia.
- La mora se calcula según la política del producto (fija o porcentual diaria), parametrizable.
- El cálculo de mora es un servicio separado, ejecutable diariamente.
- Los clientes con mora superior al umbral configurable pueden ser incluidos en lista de
  bloqueo automáticamente o por decisión manual.

### 11.3 Cierre

- Un crédito pasa a cancelado cuando su saldo llega a cero.
- El cierre diario de caja consolida los recaudos del día por cobrador y debe firmarse
  (registro de quién cerró y cuándo). Un cierre no se modifica; si hay error se registra un
  ajuste.

---

## 12. Reportes

### 12.1 Reportes obligatorios (versión 1)

1. **Cartera vigente:** créditos activos, saldos, próximos vencimientos.
2. **Cartera en mora:** clientes, días de atraso, valor en mora, antigüedad.
3. **Recaudo diario y por rango:** pagos por cobrador, por forma y por periodo.
4. **Cierre de caja:** resumen diario firmado.
5. **Créditos desembolsados:** colocación por periodo, por producto y por cobrador.
6. **Historial de cliente:** créditos, pagos y comportamiento.
7. **Plan de pagos individual:** exportable a PDF.
8. **Auditoría:** cambios por usuario y fecha.

### 12.2 Reglas de reportes

- Todos los reportes admiten filtros por fecha, cobrador, producto y estado.
- Exportación a Excel (XLSX) y CSV; los reportes formales a PDF.
- Los reportes se calculan sobre datos persistidos, nunca sobre el estado en memoria del
  navegador.
- Los reportes con datos personales solo son accesibles para roles autorizados y su
  exportación queda auditada.

---

## 13. Interfaz de Usuario

- La interfaz se construye **obligatoriamente** con la plantilla **SB Admin 2**, ubicada en
  `references/startbootstrap-sb-admin-2-gh-pages/`. Todo el HTML, CSS y JavaScript de la
  interfaz parte de ese material. No se usa otra plantilla, otro framework CSS ni otra librería
  de componentes. Cualquier desviación requiere aprobación explícita.
- Las plantillas Django se derivan de la referencia reemplazando el contenido estático por
  etiquetas de plantilla, sin alterar la estructura visual ni las clases CSS base.

### 13.1 Uso de la plantilla SB Admin 2

- **La carpeta de referencia es de solo lectura.** Los recursos se copian a `static/`
  (`css/sb-admin-2.min.css`, `js/sb-admin-2.min.js`, `img/` y `vendor/`) y desde ahí se
  sirven. Las plantillas nunca enlazan archivos dentro de `references/`.
- **Librerías:** Bootstrap 4, jQuery, jQuery Easing, Font Awesome Free 5, Chart.js 2 y
  DataTables (bs4), en las versiones que trae la plantilla. Para cambiar de versión dentro de
  la misma versión mayor (por ejemplo, por un parche de seguridad) hace falta un ADR que
  verifique que la apariencia no cambia. No se agregan librerías nuevas sin aprobación.
- **Las páginas de la plantilla son el modelo de cada tipo de pantalla:**

  | Página de referencia | Se usa para |
  |---|---|
  | `index.html` | Layout principal (sidebar, topbar, footer) y dashboard |
  | `blank.html` | Punto de partida de cualquier página interna nueva |
  | `login.html` y `forgot-password.html` | Inicio de sesión y recuperación de contraseña |
  | `register.html` | Solo como modelo visual de formularios. No hay registro público (§6.1). |
  | `tables.html` | Listados con DataTables |
  | `charts.html` | Gráficas con Chart.js |
  | `cards.html` y `buttons.html` | Tarjetas de indicadores, botones y acciones |
  | `utilities-*.html` | Clases utilitarias de color, borde, animación y otras |
  | `404.html` | Páginas de error (403, 404 y 500) |

- **Las personalizaciones** (colores del negocio, logo, componentes que no trae la plantilla)
  van en un archivo CSS propio que se carga después de `sb-admin-2.min.css`. Nunca se edita el
  CSS de la plantilla. Si se recompila desde `scss/`, el cambio requiere un ADR.
- **Los scripts de demostración** (`js/demo/`) solo sirven de ejemplo. Los datos de las
  gráficas y tablas los entrega siempre el servidor (§5.2).
- **Componentes nuevos:** si se necesita un componente que la plantilla no trae, se construye
  con clases de Bootstrap 4 y de SB Admin 2, siguiendo el estilo de la plantilla.
- Diseño responsive: funcional en celular para uso en campo.
- Accesibilidad mínima: contraste adecuado, etiquetas en formularios, navegación por teclado.
- Idioma de la interfaz: español (Colombia). El sistema debe preparar la internacionalización
  (`gettext`) para futuros idiomas.
- Mensajes de error y validación claros, en lenguaje no técnico.
- Confirmación explícita antes de acciones irreversibles (anular pago, castigar crédito,
  cerrar caja).

---

## 14. Seguridad y Protección de Datos

- Cumplimiento de la **Ley 1581 de 2012 (Habeas Data)** y sus decretos reglamentarios en
  Colombia: autorización del titular para el tratamiento de datos, finalidad explícita y
  derechos de consulta, actualización y supresión.
- Cifrado en tránsito (HTTPS obligatorio en producción) y cifrado de datos sensibles en
  reposo cuando sea posible.
- Protección CSRF, XSS y SQL injection mediante las medidas nativas de Django. Prohibido
  desactivarlas.
- Cabeceras de seguridad configuradas (HSTS, X-Frame-Options, Content-Security-Policy).
- Subida de archivos validada por tipo y tamaño, almacenada fuera del directorio público.
- Secretos únicamente por variables de entorno. Nunca en el repositorio.
- Respaldos automáticos diarios de PostgreSQL con prueba de restauración periódica.
- Registro de auditoría inmutable para acciones sobre datos financieros y personales.
- Principio de mínimo privilegio para usuarios de base de datos y de aplicación.

---

## 15. Calidad, Pruebas y Estándares de Código

### 15.1 Pruebas

- **Motor de amortización:** cobertura del 100%. Incluye casos límite (1 cuota, tasa cero,
  montos pequeños, redondeos, fechas con festivos).
- **Servicios financieros:** cobertura mínima del 90%.
- **Vistas y flujos críticos:** pruebas de integración para login, creación de crédito,
  registro de pago y generación de reportes.
- Todo cambio en fórmulas o reglas financieras requiere prueba nueva o actualizada.
- **Verificación en navegador:** toda spec con interfaz se verifica con el MCP de Playwright
  contra sus criterios de aceptación y contra la referencia visual (ver §16.5). Esta
  verificación complementa a pytest, no lo reemplaza.

### 15.2 Estándares

- Código en inglés (nombres de variables, funciones, clases). Textos de interfaz en español.
- PEP 8 aplicado con Black y Ruff; sin advertencias en CI.
- Tipos explícitos en servicios y motor de cálculo.
- Migraciones versionadas; nunca editar migraciones aplicadas.
- Commits pequeños con mensajes en formato convencional (`feat:`, `fix:`, `docs:`, `test:`).
- Ningún `print()` ni `breakpoint()` en código integrado.

### 15.3 Integración continua

Cada cambio ejecuta: linter, formateo, pruebas y verificación de migraciones. Un cambio que
falle cualquiera de estas verificaciones no puede integrarse.

---

## 16. Metodología SDD (Spec-Driven Development)

### 16.1 Flujo de trabajo obligatorio

Cada funcionalidad sigue este orden, sin excepciones:

1. **Constitución** (este documento): principios y restricciones.
2. **Especificación**, con la skill `/spec`. Contiene el objetivo, el alcance (lo que entra y
   lo que no), el modelo de datos, el plan de implementación en pasos numerados, los
   criterios de aceptación verificables, las decisiones tomadas y descartadas, y los riesgos.
   El plan técnico y las tareas atómicas viven dentro de la spec, en su plan de implementación.
3. **Aprobación:** la spec nace en `Borrador`. Solo una persona la cambia a `Aprobado`,
   después de revisarla. El agente nunca la aprueba.
4. **Implementación**, con la skill `/spec-impl`. Crea la rama `spec-NN-slug` y avanza paso a
   paso, con pruebas escritas junto al código y una pausa para revisar el diff después de cada
   paso.
5. **Verificación:** contraste contra los criterios de aceptación de la spec, con pytest y,
   cuando hay interfaz, con el MCP de Playwright. Si todo pasa, la spec cambia a `Implementado`.

### 16.2 Organización de documentos

```
specs/
├── .spec-config.yml        # Configuración del flujo (AutoCreateBranch)
├── 01-fundacion-proyecto.md
├── 02-layout-base.md
└── ...                     # NN-slug.md, numeración de dos dígitos
docs/
├── specs-tentativas.md     # Hoja de ruta tentativa (no oficial)
└── decisiones/             # ADRs (Architecture Decision Records)
```

- **Estados válidos de una spec:** `Borrador`, `En revisión`, `Aprobado`, `Implementado` y
  `Obsoleto`. Se usan siempre en español.
- Si una funcionalidad no cabe en un objetivo de una sola frase, se divide en varias specs.

### 16.3 Orden de implementación sugerido

1. Base del proyecto, Docker, configuración por entorno.
2. Autenticación, roles y permisos.
3. Parametrización (productos y tasas).
4. Motor de amortización (lógica pura, con pruebas).
5. Clientes.
6. Créditos y su ciclo de estados.
7. Pagos y aplicación a cuotas.
8. Mora y cierre de caja.
9. Reportes y exportación.
10. Auditoría transversal y endurecimiento de seguridad.

### 16.4 Reglas de cambio

- Un cambio a esta constitución requiere registro con fecha, motivo y aprobación del
  responsable del proyecto.
- Ninguna tarea puede contradecir la constitución. Si lo hace, se corrige la tarea, no la
  constitución, salvo que el cambio sea deliberado y documentado.

### 16.5 Herramientas obligatorias de desarrollo asistido

El proyecto se construye **obligatoriamente** con las skills y los servidores MCP instalados
en el repositorio. Ninguna spec se escribe, implementa ni verifica sin ellas.

| Herramienta | Tipo | Uso obligatorio |
|---|---|---|
| `/spec` | Skill | Escribir toda spec nueva, con su fase de preguntas antes de redactarla |
| `/spec-impl` | Skill | Implementar toda spec en estado `Aprobado` |
| `django-patterns` | Skill | Diseñar e implementar modelos, servicios, vistas, formularios, ORM, middleware y pruebas de Django |
| `frontend-design` | Skill | Construir las plantillas y componentes de interfaz |
| `playwright` | MCP | Verificar en el navegador los flujos y la fidelidad visual de cada spec con interfaz |

Las herramientas se subordinan a esta constitución. Cuando una de ellas sugiera algo que la
contradiga, prevalece la constitución:

- **`frontend-design`** no autoriza a rediseñar. La referencia SB Admin 2 sigue siendo la fuente
  visual oficial (§2.5, §13). La skill se usa para aplicar esa referencia con calidad
  (jerarquía, legibilidad, responsive y accesibilidad), no para cambiar su estética.
- **`django-patterns`** incluye patrones de Django REST Framework, caché y señales. DRF no
  forma parte del stack (§4), y la interfaz es SSR. Esos patrones solo se usan con una enmienda
  o un ADR aprobado.
- **`/spec-impl`** nunca hace commits automáticos. Los commits los hace la persona, con
  mensajes convencionales (§15.2).

Las skills se registran en `skills-lock.json`. Agregar, quitar o actualizar una skill o un
servidor MCP requiere un ADR.

---

## 17. Entregables Mínimos

- Repositorio con la estructura de la Sección 5.
- Entorno reproducible con `docker-compose up`.
- Documentación de instalación y configuración en `README.md`.
- Manual de usuario básico por rol.
- Suite de pruebas automatizadas ejecutable con un solo comando.
- Script de semillas con datos de ejemplo (productos, usuarios de prueba, clientes ficticios).

---

## 18. Criterios de Aceptación Globales

El sistema se considera listo para producción cuando:

1. Todas las specs de la versión 1 están implementadas y sus criterios de aceptación cumplidos.
2. El motor de amortización pasa todas las pruebas, incluidos los casos límite.
3. Una tabla de amortización puede generarse para cualquier combinación válida de
   parámetros sin errores ni saldos inconsistentes.
4. Ningún parámetro de negocio requiere cambios de código para ajustarse.
5. Los roles restringen efectivamente el acceso a las funciones correspondientes.
6. Los reportes cuadran con los movimientos registrados.
7. La interfaz respeta la referencia visual suministrada.
8. Se completó una revisión de seguridad básica y la política de datos personales está
   documentada.

---

## 19. Preguntas Abiertas

Estas decisiones deben resolverse antes de escribir la spec correspondiente:

1. ¿Los cobros serán diarios por defecto o el sistema debe soportar todas las periodicidades
   desde la versión 1?
2. ¿Se manejará un solo negocio (monousuario de empresa) o múltiples negocios en la misma
   instancia (multi-tenant)?
3. ¿El método de amortización por defecto será interés plano, cuota fija o ambos?
4. ¿Se requiere geolocalización de cobros en la versión 1?
5. ¿Los cobradores pueden registrar pagos sin conexión (offline) para sincronizar después?
6. ¿Qué formato de recibo se requiere: impreso térmico, PDF o ambos?
7. ¿Se necesitan garantías o codeudores como parte obligatoria del flujo?
8. ¿Cuál es la política de mora y de castigo de cartera del negocio?

---

## 20. Glosario

- **Gota a gota:** modalidad de préstamo informal de pequeña cuantía con cobro frecuente,
  generalmente diario, en campo.
- **Amortización:** proceso de pago progresivo de una deuda mediante cuotas.
- **Cuota:** pago periódico que incluye capital e intereses.
- **Mora:** incumplimiento del pago en la fecha pactada más el periodo de tolerancia.
- **Castigo de cartera:** baja contable de un crédito considerado incobrable.
- **Tasa de usura:** tasa máxima legal de interés, certificada periódicamente.
- **SDD:** Spec-Driven Development, metodología donde la especificación precede al código.

---

*Versión 1.3 · Documento vivo: se actualiza mediante el procedimiento de la Sección 16.4.*

## Registro de enmiendas

| Versión | Fecha | Secciones | Motivo | Aprobó |
|---|---|---|---|---|
| 1.1 | 2026-11-06 | §5.1, §15.1, §16.1, §16.2 y §16.5 (nueva) | Hacer obligatorio el uso de las skills (`/spec`, `/spec-impl`, `django-patterns`, `frontend-design`) y del MCP `playwright`. Adoptar el formato de spec de la skill (`specs/NN-slug.md`, con el plan dentro de la spec) en lugar de `docs/specs/NNN-nombre/` con tres archivos. | Sebastián Rendón |
| 1.2 | 2026-11-06 | §13 y §13.1 (nueva) | Hacer obligatorio el uso de la plantilla SB Admin 2 (`references/startbootstrap-sb-admin-2-gh-pages/`) como base de todo el HTML, CSS y JavaScript, con reglas para copiar recursos, personalizar estilos y saber qué página de referencia usar en cada pantalla. | Sebastián Rendón |
| 1.3 | 2026-11-10 | §4 | Adoptar las últimas versiones estables de Python (3.14+) y Django (6.1) según la decisión D2 de `docs/specs-tentativas.md`, fijar PostgreSQL 18 en Docker y CI (manteniendo el mínimo 16+) y elegir django-environ para las variables de entorno. Se aplica con la SPEC 01 (fundación del proyecto). |  |


## Informacion adicional

# Organización del sistema de préstamos (gota a gota)

2026-11-06 · Sebastian Rendón

## 1. Mapa general de módulos

El sistema se divide en un núcleo obligatorio y en módulos que pueden agregarse después sin tocar lo demás.

| Grupo | Módulo | Contenido principal |
| --- | --- | --- |
| Núcleo | Autenticación | Login, logout, recuperación de contraseña, bloqueo por intentos fallidos |
| Núcleo | Gestión de usuarios | Crear, activar o desactivar usuarios y asignar roles |
| Núcleo | Configuraciones | Parámetros generales, productos de crédito, tasas, cuotas y catálogos |
| Núcleo | Auditoría | Registro de quién hizo qué, cuándo y sobre qué dato |
| Operación | Clientes | Listado, búsqueda, creación, edición y ficha con historial |
| Operación | Créditos | Solicitud, aprobación, desembolso y listado con filtros por estado |
| Operación | Detalle de crédito | Resumen, cuotas, pagos, historial y documentos |
| Operación | Tabla de amortización | Generación, visualización y exportación a PDF |
| Análisis | Dashboard | Indicadores clave según el rol del usuario |
| Análisis | Reportes | Puede dejarse para una fase posterior |

El registro de pagos se considera parte de la versión 1, porque sin él el plan de pagos no muestra lo cobrado.

## 2. Panel lateral y extensibilidad

Cada módulo se registra con su nombre, icono, ruta, orden y permisos. El menú lateral se construye leyendo ese registro.

1. Crear la app del módulo con su propia carpeta en Django.
2. Declarar su entrada de menú y los permisos necesarios en su archivo de registro.
3. Usar las plantillas comunes que heredan del layout principal.
4. El menú muestra u oculta cada opción según el rol del usuario.

Así, un módulo nuevo como Cobranza o Inventario aparece en el menú sin cambiar el resto del sistema.

## 3. Dashboard

El dashboard muestra indicadores en tres niveles, y cada cifra respeta el rol del usuario: un cobrador ve sus datos y el administrador ve todo.

| Nivel | Contenido | Ejemplo |
| --- | --- | --- |
| Tarjetas superiores | Cifras del día o del mes | Cartera vigente, recaudo de hoy, cuotas que vencen hoy, valor en mora, créditos nuevos |
| Gráficas | Tendencias y comparaciones | Recaudo diario de los últimos 30 días, cartera por estado, recaudo por cobrador, evolución de la mora |
| Listas de acción | Tareas inmediatas | Clientes con cuotas vencidas, próximos vencimientos, últimos pagos registrados |

Las gráficas se definirán en detalle cuando se escriba la especificación del dashboard.

## 4. Seguridad contra inyección SQL

El sistema usa el ORM de Django y no concatena texto en consultas. Así, cada dato del usuario llega a la base de datos como parámetro.

- Solo se usa SQL crudo en casos excepcionales, con parámetros enlazados y revisión de código.
- Toda entrada se valida en formularios y en la capa de servicios, no solo en la interfaz.
- La aplicación usa un usuario de PostgreSQL con mínimos privilegios, sin permiso para borrar tablas.
- El escape automático de plantillas permanece activo.
- Las pruebas incluyen intentos de inyección en campos de búsqueda y filtros.

## 5. Auditoría

Cada cambio importante queda registrado y los registros no pueden editarse ni borrarse desde la aplicación.

- Qué se guarda: usuario, fecha y hora, acción, entidad afectada, valores anteriores y nuevos, y dirección IP.
- Quién la consulta: solo los administradores, con filtros por usuario, fecha y entidad.
- Retención: pendiente de definir (indefinida o de 2 años).

