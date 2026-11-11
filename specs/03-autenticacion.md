# SPEC 03 — Autenticación

> **Estado:** Implementado
> **Depende de:** SPEC 01, SPEC 02
> **Fecha:** 2026-11-11
> **Objetivo:** Exigir sesión en todo el sistema con un inicio de sesión propio por usuario o correo, con bloqueo temporal tras intentos fallidos, cambio obligatorio de contraseña en el primer ingreso y recuperación de contraseña por correo simulado.

---

## 1. Por qué existe esta spec

Hasta la SPEC 02 todas las páginas son públicas, el único login es el del admin de Django y el modal de cierre de sesión apunta a `admin:logout`. La §6.1 exige acceso autenticado, bloqueo tras N intentos, cambio de contraseña en el primer ingreso, recuperación por correo y Argon2.

Esta spec también crea el **modelo de usuario propio** (`apps.accounts.User`). Cambiar `AUTH_USER_MODEL` después de que existan datos es muy costoso, y no hay producción todavía, así que es el momento de hacerlo.

Deja tres contratos que las specs siguientes reutilizan:

- **`apps.accounts.User`:** el modelo al que apuntan créditos, pagos, cierres y auditoría.
- **`apps/accounts/policy.py`:** el único punto que la SPEC 06 (parámetros globales) cambia para leer intentos, duración del bloqueo, longitud mínima de contraseña y vigencia del enlace de recuperación desde la base de datos. Es el mismo patrón del context processor `branding` (ADR-001).
- **`apps/accounts/services.py`:** el registro de intentos y el desbloqueo. La SPEC 04 (usuarios, roles y permisos) lo usa para que el administrador desbloquee una cuenta, y la SPEC 05 (auditoría base) para auditar los ingresos.

---

## 2. Alcance

**Entra:**

- **La app `apps/accounts`**, con el modelo `User` (subclase de `AbstractUser`), su manager, su migración inicial y `AUTH_USER_MODEL = "accounts.User"`.
- **Recrear la base de datos local** una vez, porque cambia `AUTH_USER_MODEL`. Se documenta en `README.md`.
- **Inicio de sesión con usuario o correo** y contraseña, con un backend propio:
  - Si el texto contiene `@`, se busca por correo sin distinguir mayúsculas. Si no, por nombre de usuario exacto.
  - El nombre de usuario ya no admite `@` ni `+` (validador propio).
- **Cierre de sesión** solo por `POST`, desde el modal existente.
- **Bloqueo temporal por cuenta:**
  - Tras 5 fallos seguidos (parametrizable), la cuenta queda bloqueada 15 minutos (parametrizable) y se desbloquea sola.
  - Un ingreso correcto pone el contador en 0.
  - Los intentos durante el bloqueo no lo alargan ni se cuentan.
  - El mensaje de error es siempre el mismo, exista o no el usuario, esté o no bloqueado, esté o no inactivo.
- **Cambio obligatorio de contraseña en el primer ingreso:**
  - El campo `must_change_password` vale `True` por defecto en todo usuario nuevo.
  - `createsuperuser` lo deja en `False`.
  - Mientras valga `True`, un middleware lleva al usuario a la pantalla de cambio de contraseña desde cualquier página.
  - Se apaga al cambiar la contraseña o al restablecerla con el enlace de recuperación.
- **Cambio voluntario de contraseña** desde el menú del usuario de la topbar, en la misma pantalla. Pide la contraseña actual. La sesión actual sigue abierta y las demás sesiones del usuario quedan invalidadas (§6.3).
- **Recuperación de contraseña por correo**, con las vistas de Django y plantillas propias:
  - Pedir el enlace con el correo. La respuesta es la misma exista o no el correo.
  - El enlace dura 1 hora (parametrizable) y deja de servir al usarse.
  - Restablecer la contraseña con el enlace desbloquea la cuenta y apaga `must_change_password`.
- **Correo simulado y parametrizable:** la variable de entorno `EMAIL_BACKEND` elige entre `console` (por defecto) y `file`. No hay SMTP en ningún entorno.
- **Argon2** como hasher principal (`django[argon2]`), conservando PBKDF2 para leer hashes existentes.
- **Política de contraseñas por defecto:** mínimo 8 caracteres, con al menos una letra y un número, más los validadores de Django de similitud con el usuario, contraseñas comunes y solo números.
- **El servicio provisional de políticas** `apps/accounts/policy.py`, que lee sus valores por defecto de los settings.
- **Sesión obligatoria en todo el sistema** con `LoginRequiredMiddleware` de Django. Solo son públicas el login, las pantallas de recuperación y `GET /health/`.
- **Duración provisional de la sesión:** se cierra al cerrar el navegador y dura como máximo 12 horas.
- **El admin de Django** se conserva:
  - Solo entran superusuarios activos.
  - `/admin/login/` redirige al login propio, así que aplican el bloqueo y el cambio obligatorio.
  - `User` queda registrado en el admin con sus campos nuevos, para crear usuarios hasta la SPEC 04.
- **Pantallas** derivadas de `login.html` y `forgot-password.html`, sin la columna de imagen.
- **La topbar:** el menú del usuario agrega "Cambiar contraseña". El modal de cierre de sesión apunta a `accounts:logout`.
- **Pruebas** con pytest del modelo, el backend, el bloqueo, los validadores, el middleware, las vistas, la recuperación, el admin y las páginas que pasan a exigir sesión.
- **Verificación con Playwright** contra `login.html` y `forgot-password.html`, en escritorio y a 375 px, revisando la consola.

**Fuera de alcance (para specs futuras):**

- **El cierre de sesión por inactividad (§6.1).** Se retiró de esta spec por decisión de la persona. Va en una spec futura, que también hará parametrizable la duración de la sesión.
- **El envío real de correos (SMTP u otro proveedor).** Por ahora el correo es simulado en todos los entornos.
- **Crear, editar y desactivar usuarios desde la aplicación, los grupos y la regla de que nadie cambia su propio nivel de acceso.** Van en la SPEC 04.
- **Desbloquear una cuenta o volver a marcar `must_change_password` desde la aplicación.** Van en la SPEC 04, que reutiliza los servicios de esta spec.
- **Invalidar las sesiones al desactivar un usuario.** Va en la SPEC 04.
- **Auditar los inicios de sesión, los fallos y los bloqueos.** Van en la SPEC 05.
- **Editar los intentos, la duración del bloqueo y la política de contraseñas desde una pantalla.** Va en la SPEC 06.
- **Limitar intentos por IP, CAPTCHA o doble factor.**
- **El "Recuérdame" de `login.html`, el ingreso con Google o Facebook y el registro público.** No hay registro público (§6.1).
- **Foto de perfil del usuario.**

---

## 3. Modelo de datos

### 3.1 Usuario (`apps/accounts/models.py`)

```python
class User(AbstractUser):
    username_validator = UsernameValidator()   # letras, números, ".", "_" y "-"
    email = models.EmailField(_("correo electrónico"), blank=True)
    must_change_password = models.BooleanField(
        _("debe cambiar la contraseña"), default=True
    )
    failed_login_attempts = models.PositiveSmallIntegerField(
        _("intentos fallidos seguidos"), default=0
    )
    locked_until = models.DateTimeField(_("bloqueado hasta"), null=True, blank=True)

    objects = UserManager()   # create_superuser deja must_change_password=False

    class Meta:
        verbose_name = _("usuario")
        verbose_name_plural = _("usuarios")
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                condition=~Q(email=""),
                name="accounts_user_email_ci_unique",
                violation_error_message=_("Ya existe un usuario con este correo."),
            ),
        ]
```

Reglas:

- **Correo:** es opcional. Si existe, es único sin distinguir mayúsculas. Un usuario sin correo entra con su nombre de usuario, pero no puede recuperar la contraseña por sí mismo.
- **Bloqueo:** la cuenta está bloqueada si `locked_until` es mayor que la hora actual. Al bloquearla, `failed_login_attempts` vuelve a 0, así que al vencer el bloqueo el contador ya está limpio.
- **Sin borrado:** esta spec no borra usuarios. La desactivación con motivo llega en la SPEC 04 (§6.3).

### 3.2 Servicio provisional de políticas (`apps/accounts/policy.py`)

| Función | Setting que lee | Valor por defecto |
|---|---|---|
| `get_max_failed_attempts() -> int` | `ACCOUNTS_MAX_FAILED_ATTEMPTS` | `5` |
| `get_lockout_duration() -> timedelta` | `ACCOUNTS_LOCKOUT_MINUTES` | `15` minutos |
| `get_password_min_length() -> int` | `ACCOUNTS_PASSWORD_MIN_LENGTH` | `8` |
| `get_password_reset_timeout() -> int` | `PASSWORD_RESET_TIMEOUT` | `3600` segundos |

Nadie más lee esos settings. El validador de longitud y el generador de tokens de recuperación consultan estas funciones en cada uso, no al arrancar.

### 3.3 Servicios (`apps/accounts/services.py`)

Todos reciben `now: datetime | None = None` para poder probarlos sin librerías de tiempo. Si es `None`, usan `timezone.now()`.

- `find_user_by_identifier(identifier: str) -> User | None`: busca por correo si el texto contiene `@`, o por nombre de usuario si no.
- `is_locked(user: User, now=None) -> bool`.
- `authenticate_with_lockout(request: HttpRequest, identifier: str, password: str, now=None) -> User | None`:
  1. Si el usuario existe y está bloqueado, devuelve `None` sin contar el intento.
  2. Llama a `authenticate()`.
  3. Si falla y el usuario existe, llama a `register_failed_attempt`.
  4. Si funciona, llama a `clear_failed_attempts`.
- `register_failed_attempt(user: User, now=None) -> None`: dentro de `transaction.atomic()` y con `select_for_update()`, suma 1. Si llega al máximo, fija `locked_until = now + get_lockout_duration()` y pone el contador en 0.
- `clear_failed_attempts(user: User) -> None`: pone el contador en 0 y `locked_until` en `None`. La SPEC 04 lo usa para desbloquear.
- `mark_password_changed(user: User) -> None`: apaga `must_change_password`.

### 3.4 Rutas (`apps/accounts/urls.py`, `app_name = "accounts"`)

| Ruta | Nombre | Vista | Pública |
|---|---|---|---|
| `ingresar/` | `accounts:login` | `LoginView` propia | Sí |
| `salir/` | `accounts:logout` | `LogoutView` (solo `POST`) | No |
| `contrasena/cambiar/` | `accounts:password_change` | `PasswordChangeView` propia | No |
| `contrasena/recuperar/` | `accounts:password_reset` | `PasswordResetView` | Sí |
| `contrasena/recuperar/enviado/` | `accounts:password_reset_done` | `PasswordResetDoneView` | Sí |
| `contrasena/restablecer/<uidb64>/<token>/` | `accounts:password_reset_confirm` | `PasswordResetConfirmView` propia | Sí |
| `contrasena/restablecer/listo/` | `accounts:password_reset_complete` | `PasswordResetCompleteView` | Sí |

`config/urls.py` incluye estas rutas en la raíz y agrega `admin/login/` (vista `accounts.views.admin_login_redirect`) antes de `admin.site.urls`.

### 3.5 Archivos nuevos y modificados

```
apps/accounts/
├── __init__.py  apps.py  admin.py  models.py  managers.py
├── backends.py        # UsernameOrEmailBackend
├── forms.py           # LoginForm, PasswordChangeForm, SetPasswordForm, PasswordResetForm
├── middleware.py      # ForcePasswordChangeMiddleware
├── policy.py  services.py  tokens.py  validators.py
├── views.py  urls.py
└── migrations/0001_initial.py
templates/accounts/
├── auth_base.html                 # página sin barra lateral (bg-gradient-primary)
├── login.html  password_change.html
├── password_reset.html  password_reset_done.html
├── password_reset_confirm.html  password_reset_complete.html
└── email/password_reset_subject.txt  email/password_reset_email.txt
tests/accounts/
├── __init__.py  test_models.py  test_backends.py  test_services.py  test_validators.py
├── test_login.py  test_password_change.py  test_password_reset.py
├── test_middleware.py  test_admin.py  test_policy.py  test_settings.py
modificados:
  config/settings/base.py  config/settings/dev.py  config/urls.py
  apps/core/views.py (health con @login_not_required)
  templates/includes/topbar.html  templates/includes/logout_modal.html
  tests/conftest.py  tests/core/*.py (las páginas ahora exigen sesión)
  pyproject.toml  uv.lock  .env.example  .gitignore  README.md  CLAUDE.md
  docs/specs-tentativas.md
```

### 3.6 Cambios en la configuración (`config/settings/base.py`)

- `"apps.accounts"` en `INSTALLED_APPS` y `AUTH_USER_MODEL = "accounts.User"`.
- `AUTHENTICATION_BACKENDS = ["apps.accounts.backends.UsernameOrEmailBackend"]`.
- `MIDDLEWARE`: `django.contrib.auth.middleware.LoginRequiredMiddleware` y después `apps.accounts.middleware.ForcePasswordChangeMiddleware`, ambos justo después de `AuthenticationMiddleware`.
- `LOGIN_URL = "accounts:login"`, `LOGIN_REDIRECT_URL = "core:home"` y `LOGOUT_REDIRECT_URL = "accounts:login"`.
- `PASSWORD_HASHERS`: Argon2 primero, después PBKDF2, PBKDF2-SHA1 y Scrypt.
- `AUTH_PASSWORD_VALIDATORS`: similitud con el usuario, `apps.accounts.validators.PolicyMinimumLengthValidator`, contraseñas comunes, solo números y `apps.accounts.validators.LettersAndDigitsValidator`.
- Los cuatro settings de la §3.2.
- `SESSION_EXPIRE_AT_BROWSER_CLOSE = True` y `SESSION_COOKIE_AGE = 60 * 60 * 12`.
- **Correo:** `MAILERS["default"]` se arma en `base.py` según `EMAIL_BACKEND` (`console` o `file`; cualquier otro valor lanza `ImproperlyConfigured`). Con `file`, los correos se guardan en `EMAIL_FILE_PATH` (por defecto `tmp/emails/`, ignorada en git). `DEFAULT_FROM_EMAIL` sale del entorno, con un valor por defecto. Se quita la definición de `MAILERS` de `dev.py`.

---

## 4. Plan de implementación

Cada paso deja el sistema funcionando. Antes de los pasos con código de Django se carga la skill `django-patterns`, y antes de los pasos con plantillas, la skill `frontend-design` (§16.5).

1. **Argon2.** `uv add "django[argon2]"`. Configurar `PASSWORD_HASHERS` con Argon2 primero. En `tests/conftest.py`, una fixture `autouse` usa el hasher MD5 para que las pruebas sean rápidas. Crear `tests/accounts/test_settings.py`, que comprueba que el primer hasher configurado en los settings del proyecto es Argon2 y que una contraseña hasheada con él empieza por `argon2`. Verificación: `uv run pytest tests/accounts/test_settings.py`.
2. **App y modelo `User`.** Crear `apps/accounts` (`name = "apps.accounts"`), el modelo de la §3.1, `UsernameValidator`, el `UserManager` y la migración `0001_initial`. Configurar `AUTH_USER_MODEL`. Recrear la base local (`docker compose down -v`, `docker compose up -d db` y `migrate`). Crear `tests/accounts/test_models.py`:
   - `create_user` deja `must_change_password=True` y `create_superuser` lo deja en `False`.
   - Dos usuarios con el mismo correo en distinta capitalización violan la restricción.
   - Dos usuarios sin correo sí se permiten.
   - Un nombre de usuario con `@` o `+` no pasa `full_clean`.
3. **Servicio de políticas y validadores.** Crear `policy.py` y los settings de la §3.2. Crear `validators.py`, con `PolicyMinimumLengthValidator` y `LettersAndDigitsValidator`, con mensajes y `get_help_text` en español. Configurar `AUTH_PASSWORD_VALIDATORS`. Crear `test_policy.py` (cada función devuelve el valor por defecto y respeta un `override_settings`) y `test_validators.py` (`"cobro2026"` pasa; `"abcdefgh"`, `"12345678"`, `"abc1234"` y `"abc12345"` no pasan; cambiar la longitud con `override_settings` cambia el resultado).
4. **Backend y servicios de bloqueo.** Crear `backends.py`, con `UsernameOrEmailBackend` (subclase de `ModelBackend`): busca con `find_user_by_identifier`, y su `user_can_authenticate` rechaza a los inactivos y a los bloqueados. Crear `services.py` (§3.3). Configurar `AUTHENTICATION_BACKENDS`. Crear `test_backends.py` y `test_services.py`, que cubran:
   - El ingreso por usuario, por correo y por correo con otra capitalización.
   - El usuario inactivo y el inexistente.
   - El quinto fallo bloquea la cuenta y el cuarto no.
   - Con la cuenta bloqueada, la contraseña correcta no entra y el intento no se cuenta.
   - A los 15 minutos la cuenta entra de nuevo.
   - Un ingreso correcto pone el contador en 0.
   - `clear_failed_attempts` desbloquea.
   - Un fallo con un usuario inexistente no escribe nada en la base de datos.
5. **Página base de autenticación y login.** Crear `templates/accounts/auth_base.html` a partir de `login.html`: `body.bg-gradient-primary`, la tarjeta `card o-hidden border-0 shadow-lg my-5` en `col-xl-6 col-lg-7 col-md-9`, sin la columna de imagen, con `business_name` y `brand_icon`, los mensajes de Django y los mismos scripts. Crear `LoginForm` (usa `authenticate_with_lockout`, con el campo "Usuario o correo", y agrega `form-control-user` y el placeholder a los widgets en un solo lugar) y `templates/accounts/login.html`, sin "Recuérdame", sin los botones de Google y Facebook y sin "Crear una cuenta", con el enlace "¿Olvidaste tu contraseña?". Crear las rutas `accounts:login` y `accounts:logout`. Configurar `LOGIN_URL`, `LOGIN_REDIRECT_URL` y `LOGOUT_REDIRECT_URL`. Cambiar el modal de cierre de sesión a `accounts:logout`. Verificación: el login con un superusuario redirige a `/`, y "Cerrar sesión" vuelve al login con un mensaje.
6. **Sesión obligatoria.** Agregar `LoginRequiredMiddleware`. Marcar con `@login_not_required` el login, `health` y las vistas de recuperación. Configurar la duración de la sesión. Ajustar `tests/core/` para que las páginas se pidan con un usuario autenticado (`force_login`) y agregar pruebas de que un anónimo que pide `/` o `/componentes/` es redirigido a `/ingresar/?next=...`. Verificación: `uv run pytest tests/core`.
7. **Cambio de contraseña y middleware.** Crear `PasswordChangeView` y `PasswordChangeForm` propios (al guardar llaman a `mark_password_changed`) y `templates/accounts/password_change.html`, dentro de `base.html` y a partir de `blank.html`, con una tarjeta y una alerta cuando el cambio es obligatorio. Crear `ForcePasswordChangeMiddleware`: si `must_change_password` es verdadero, redirige a `accounts:password_change` desde cualquier ruta salvo esa misma, `accounts:logout`, `STATIC_URL` y `/health/`. Agregar "Cambiar contraseña" y un `dropdown-divider` al menú del usuario de la topbar, como en `index.html`. Crear `test_password_change.py` y `test_middleware.py`:
   - Un usuario con la marca es redirigido desde `/` y desde `/admin/`, y puede cerrar sesión.
   - Después del cambio, la marca se apaga y `/` responde 200.
   - Una contraseña actual incorrecta o una nueva que no cumple la política devuelve el formulario con errores.
   - Después del cambio, la sesión actual sigue abierta y otra sesión del mismo usuario queda cerrada.
8. **Correo simulado.** Armar `MAILERS` en `base.py` según `EMAIL_BACKEND` y quitarlo de `dev.py`. Agregar `EMAIL_BACKEND`, `EMAIL_FILE_PATH` y `DEFAULT_FROM_EMAIL` a `.env.example` y `tmp/` a `.gitignore`. Agregar a `test_settings.py`: `console` y `file` producen el backend esperado, y un valor desconocido lanza `ImproperlyConfigured`.
9. **Recuperación de contraseña.** Crear `tokens.py` (generador que usa `get_password_reset_timeout()`), `PasswordResetForm` y `SetPasswordForm` propios (al guardar, llaman a `clear_failed_attempts` y `mark_password_changed`), las cuatro rutas, sus plantillas sobre `auth_base.html` a partir de `forgot-password.html`, y las plantillas del correo en texto plano. Crear `test_password_reset.py`, con el correo de pruebas (`mailoutbox`):
   - Un correo registrado recibe un mensaje con un enlace que funciona.
   - Un correo no registrado no recibe nada y ve la misma pantalla.
   - El enlace usado una vez ya no sirve, y un enlace de más de una hora tampoco.
   - Restablecer desbloquea una cuenta bloqueada y apaga `must_change_password`.
   - Un usuario sin correo no recibe nada.
10. **Admin de Django.** Registrar `User` en `apps/accounts/admin.py` con un `UserAdmin` que muestra `must_change_password`, `failed_login_attempts` y `locked_until`. Hacer que `admin.site` exija `is_superuser`. Crear `admin_login_redirect`: con un usuario autenticado que no es superusuario responde 403, y si no, redirige a `accounts:login` conservando `next`. Crear `test_admin.py`:
    - Un anónimo en `/admin/` termina en `/ingresar/`.
    - Un superusuario entra a `/admin/`.
    - Un usuario `is_staff` que no es superusuario recibe 403 sin bucles de redirección.
    - Un usuario creado desde el admin queda con `must_change_password=True`.
11. **Verificación en el navegador.** Con el stack de Docker levantado, recorrer con el MCP de Playwright el login, un error de login, el bloqueo, el cambio obligatorio, el cambio voluntario, la recuperación completa (leyendo el enlace del log de la consola de `web`) y el cierre de sesión:
    - Comparar el login con `login.html` y la recuperación con `forgot-password.html`, en escritorio (1280 px) y en celular (375 px).
    - Comprobar que no hay desplazamiento horizontal a 375 px.
    - Leer la consola en busca de errores y comprobar que no se pide nada a `source.unsplash.com`.

    Dejar las capturas en el scratchpad y anotar en la spec cualquier diferencia.
12. **Documentación.** Actualizar `README.md`: recrear la base local, crear el primer superusuario y ver los correos simulados. Actualizar `CLAUDE.md`: el estado del proyecto, la fila de recuperación de contraseña de la tabla de pendientes (correo simulado, sin SMTP) y una fila nueva para el cierre por inactividad. En `docs/specs-tentativas.md`, anotar que el cierre por inactividad salió de la spec de autenticación y queda pendiente de ubicar.

### 4.1 Resultado de la verificación en el navegador (paso 11)

Se recorrió con Playwright, con el stack de Docker, el 2026-11-11: el login, un error de login, el bloqueo al quinto fallo (con la contraseña correcta rechazada), el cambio obligatorio (con errores de política y después válido), el cambio voluntario, el cierre de sesión, la recuperación completa (con el enlace leído del log de `web`), el enlace usado una segunda vez y el admin como anónimo y como superusuario.

- **Estructura:** el login y la recuperación tienen `body.bg-gradient-primary` y la cadena `container > row.justify-content-center > col-xl-6.col-lg-7.col-md-9 > card.o-hidden.border-0.shadow-lg.my-5 > card-body.p-0 > p-5`, con `form.user`, `form-control-user` y `btn-user btn-block`, como `login.html` y `forgot-password.html` sin la columna de imagen.
- **375 px:** ni el login, ni la recuperación, ni el restablecimiento, ni el cambio de contraseña tienen desplazamiento horizontal.
- **Consola y red:** no hay errores en las pantallas propias, y ninguna petición va a `source.unsplash.com`.

Diferencias y observaciones, ninguna bloqueante:

- **Trato mezclado (tú y usted).** Los textos propios usan "tú", pero los de Django usan "usted": la ayuda de los validadores de similitud, de contraseñas comunes y de solo números ("Su contraseña…") y la del campo de confirmación ("ingrese la misma contraseña"). Corregirlo exige sobrescribir textos de Django. La persona decidió dejarlo para otra spec, y quedó anotado en `docs/specs-tentativas.md`.
- **El correo por consola sale en *quoted-printable*.** Como el cuerpo tiene "ñ", las líneas largas se cortan con un `=` al final, también la del enlace. Para usar el enlace desde el log hay que unir las líneas. `EMAIL_BACKEND=file` produce el mismo formato.
- **`favicon.ico` da 404 solo en el admin de Django.** Su plantilla no define favicon; las pantallas propias sí.
- **Chrome muestra un aviso `VERBOSE`** en los formularios de cambio y restablecimiento: sugiere un campo de usuario, aunque sea oculto, para los gestores de contraseñas. No es un error.
- **El fondo degradado se repite** debajo de la tarjeta cuando el contenido es más alto que la pantalla, como en el restablecimiento a 375 px. Es el comportamiento de `bg-gradient-primary` de la plantilla.

---

## 5. Criterios de aceptación

- [x] `AUTH_USER_MODEL` es `"accounts.User"` y `uv run python manage.py migrate` funciona sobre una base vacía.
- [x] `create_user` deja `must_change_password=True` y `createsuperuser` lo deja en `False`.
- [x] No se pueden guardar dos usuarios con el mismo correo en distinta capitalización, pero sí dos usuarios sin correo.
- [x] Un nombre de usuario con `@` o `+` no pasa la validación del modelo.
- [x] El primer hasher de `PASSWORD_HASHERS` es Argon2, y una contraseña guardada con la configuración del proyecto empieza por `argon2`.
- [x] La contraseña `"cobro2026"` pasa los validadores; `"abcdefgh"`, `"12345678"`, `"abc1234"` y `"abc12345"` (está en la lista de contraseñas comunes de Django) no pasan, con mensajes en español.
- [x] Un usuario entra con su nombre de usuario y también con su correo escrito en otra capitalización.
- [x] Un anónimo que pide `/` o `/componentes/` es redirigido a `/ingresar/?next=...`, y después de entrar llega a la página pedida.
- [x] `GET /health/` responde 200 sin sesión.
- [x] Una URL insegura en `next` (otro dominio) no se sigue: el login redirige a `/`.
- [x] Una contraseña incorrecta, un usuario inexistente, un usuario inactivo y una cuenta bloqueada muestran exactamente el mismo mensaje de error.
- [x] El quinto fallo seguido bloquea la cuenta. Durante el bloqueo, la contraseña correcta no permite entrar y el contador no cambia.
- [x] A los 15 minutos del bloqueo (simulados con `now`), la contraseña correcta permite entrar.
- [x] Un ingreso correcto deja `failed_login_attempts` en 0.
- [x] Cambiar `ACCOUNTS_MAX_FAILED_ATTEMPTS` y `ACCOUNTS_LOCKOUT_MINUTES` con `override_settings` cambia el comportamiento del bloqueo sin tocar otro código.
- [x] `GET /salir/` no cierra la sesión (405), y `POST /salir/` la cierra y redirige al login con un mensaje.
- [x] Un usuario con `must_change_password=True` es redirigido a `/contrasena/cambiar/` desde `/`, `/componentes/` y `/admin/`, y puede cerrar sesión.
- [x] Después de cambiar la contraseña, `must_change_password` es `False`, la sesión actual sigue abierta y otra sesión abierta del mismo usuario queda cerrada.
- [x] El menú del usuario de la topbar muestra "Cambiar contraseña" y "Cerrar sesión", separados por un `dropdown-divider`.
- [x] Pedir la recuperación con un correo registrado envía un solo correo con un enlace a `/contrasena/restablecer/`. Con un correo no registrado no se envía nada y la pantalla es la misma.
- [x] El enlace de recuperación deja de servir después de usarse y después de una hora.
- [x] Restablecer la contraseña con el enlace desbloquea la cuenta, pone el contador en 0 y deja `must_change_password` en `False`.
- [x] `EMAIL_BACKEND=file` guarda el correo en `EMAIL_FILE_PATH`, y un valor desconocido impide arrancar con `ImproperlyConfigured`.
- [x] La sesión expira al cerrar el navegador (`SESSION_EXPIRE_AT_BROWSER_CLOSE`) y `SESSION_COOKIE_AGE` es de 12 horas.
- [x] Un anónimo que pide `/admin/` termina en `/ingresar/`. Un superusuario entra al admin. Un usuario `is_staff` que no es superusuario recibe 403 sin bucles de redirección.
- [x] El login y las pantallas de recuperación no contienen la clase `bg-login-image` ni `bg-password-image`, ni "Recuérdame", ni los botones de Google y Facebook, ni un enlace de registro.
- [x] Todos los textos visibles de las plantillas nuevas y de los correos están envueltos en `{% translate %}`, `{% blocktranslate %}` o `gettext`.
- [x] `uv run pytest --cov` pasa, y `apps/accounts/services.py` tiene al menos 90 % de cobertura.
- [x] `uv run ruff check .`, `uv run black --check .`, `uv run python manage.py check` y `uv run python manage.py makemigrations --check --dry-run` pasan.
- [x] En Playwright, a 1280 px, el login y la recuperación tienen el fondo `bg-gradient-primary` y la tarjeta con la misma estructura que `login.html` y `forgot-password.html`, sin la columna de imagen.
- [x] En Playwright, a 375 px, el login, la recuperación y el cambio de contraseña no tienen desplazamiento horizontal.
- [x] En Playwright, la consola no muestra errores en el login, la recuperación ni el cambio de contraseña, y ninguna petición va a `source.unsplash.com`.
- [x] `README.md` explica cómo recrear la base local, crear el primer superusuario y ver los correos simulados.

---

## 6. Decisiones tomadas y descartadas

- **Sí:** un modelo de usuario propio (`accounts.User`) desde ahora. Cambiar `AUTH_USER_MODEL` con datos reales es muy costoso, y hoy solo obliga a recrear la base local.
- **No:** `auth.User` con un perfil 1:1. El correo no quedaría único en la base de datos y cada consulta necesitaría un join.
- **Sí:** el correo es opcional pero único sin distinguir mayúsculas. Un cobrador sin correo puede trabajar, aunque no pueda recuperar su contraseña por sí mismo.
- **No:** correo obligatorio. Es una barrera para cobradores en campo.
- **Sí:** el texto del login se busca por correo si contiene `@`, y el nombre de usuario ya no admite `@` ni `+`. Así nunca hay dos usuarios que coincidan con el mismo texto.
- **Sí:** bloqueo temporal por cuenta, de 15 minutos tras 5 fallos seguidos, que se desbloquea solo.
- **No:** bloqueo por cuenta e IP. Los cobradores en campo pueden compartir la IP de la red móvil. **No:** bloqueo hasta que el administrador desbloquee, porque la §6.1 pide un bloqueo temporal y dejaría al cobrador sin trabajar.
- **No:** contar los fallos dentro de una ventana de tiempo. Obligaría a guardar cada intento. El contador de fallos seguidos es suficiente.
- **Sí:** el contador y el bloqueo viven en el modelo `User`. Es un dato por cuenta y no hace falta otra tabla.
- **No:** django-axes. Agrega una dependencia y sus propias tablas para algo que cabe en dos campos y un servicio.
- **Sí:** el bloqueo se aplica en `services.py`, y el backend también rechaza a las cuentas bloqueadas como segunda barrera.
- **Sí:** el bloqueo impide iniciar sesión, pero no cierra las sesiones ya abiertas. El backend sobrescribe `get_user` para rechazar solo a los inactivos. Así, quien bloquea a propósito la cuenta de un cobrador no lo saca mientras trabaja. Lo decidió la persona al implementar el paso 4.
- **No:** que el bloqueo también cierre las sesiones abiertas (lo que pasaría con el `get_user` de `ModelBackend`, que usa `user_can_authenticate`).
- **No:** usar la señal `user_login_failed`. La lógica de negocio no va en señales (`CLAUDE.md`).
- **Sí:** el mismo mensaje de error para todo fallo, incluido el bloqueo. No revela qué usuarios existen. El mensaje avisa que tras varios fallos la cuenta se bloquea unos minutos.
- **Sí:** el contador se modifica con `select_for_update()` dentro de `transaction.atomic()`, para que dos intentos simultáneos no se pisen.
- **Sí:** la política de contraseñas por defecto es de 8 caracteres con letras y números, más los validadores de Django. Es más fácil para usuarios con poca formación técnica (§2.6).
- **No:** 10 caracteres con mayúsculas, minúsculas y números. Se descartó por la misma razón. La SPEC 06 permite endurecerla.
- **Sí:** el ejemplo de contraseña válida es `"cobro2026"` y no `"abc12345"`, que está en la lista de contraseñas comunes de Django y la rechaza `CommonPasswordValidator`. Se detectó al implementar el paso 3, y la persona eligió conservar el validador.
- **Sí:** un servicio provisional `policy.py` que lee los settings. La SPEC 06 solo cambia ese módulo para leer la base de datos.
- **No:** crear ya un modelo mínimo de parámetros. Adelantaría la SPEC 06.
- **Sí:** Argon2 como hasher principal, conservando PBKDF2 para leer hashes existentes. Las pruebas usan MD5 por velocidad, y una prueba comprueba que el proyecto usa Argon2.
- **No:** el cierre de sesión por inactividad. La persona decidió dejarlo para una spec futura.
- **Sí:** mientras tanto, la sesión se cierra al cerrar el navegador y dura como máximo 12 horas, una jornada. Es un valor fijo en settings y provisional.
- **No:** la duración por defecto de Django (2 semanas). Un celular perdido quedaría con la sesión abierta demasiado tiempo.
- **Sí:** se quita "Recuérdame" del login. Contradice la duración corta de la sesión.
- **Sí:** `must_change_password` vale `True` por defecto, salvo con `createsuperuser`. El primer administrador ya eligió su contraseña al crearlo.
- **No:** obligar también al superusuario creado por consola.
- **Sí:** el cambio voluntario de contraseña usa la misma pantalla que el obligatorio, dentro del layout.
- **Sí:** la recuperación entra completa, con un correo simulado que se elige por `EMAIL_BACKEND` (`console` o `file`). No hay SMTP en ningún entorno. La persona pidió no implementar el envío real todavía.
- **Sí:** el enlace de recuperación dura 1 hora y desbloquea la cuenta al usarse. Usarlo demuestra que la persona es dueña del correo.
- **Sí:** se conserva el admin de Django solo para superusuarios, con el login propio. Sirve para crear usuarios hasta la SPEC 04, y no deja un camino que salte el bloqueo o el cambio obligatorio.
- **No:** quitar el admin, porque no habría cómo crear usuarios sin consola. **No:** dejarlo con su login propio.
- **Sí:** se usa `LoginRequiredMiddleware` de Django, y las vistas públicas se marcan con `@login_not_required`. Una vista nueva queda protegida por defecto.
- **No:** poner `@login_required` en cada vista. Es fácil olvidarlo.
- **Sí:** se quita la columna de imagen de `login.html` y `forgot-password.html`, con aprobación explícita de la persona. El CSS de la plantilla la carga desde `source.unsplash.com`, que ya no funciona. La tarjeta queda más angosta y centrada.
- **No:** conservar la columna con una imagen local. **No:** dejar la clase original, porque saldría vacía y pediría un recurso externo.
- **Sí:** los campos del login y de la recuperación llevan `form-control-user`, como en la plantilla. Se agrega en un solo lugar de `forms.py`, porque es una variante de estilo propia de las pantallas de autenticación.
- **Sí:** los servicios reciben `now` como parámetro para probar el bloqueo sin agregar librerías de tiempo.

---

## 7. Riesgos identificados

| Riesgo | Mitigación |
|---|---|
| Cambiar `AUTH_USER_MODEL` choca con las migraciones ya aplicadas en la base local (`InconsistentMigrationHistory`). | El paso 2 recrea la base local, y `README.md` lo explica. En CI la base se crea vacía. |
| Las pruebas existentes de `tests/core` fallan porque las páginas pasan a exigir sesión. | El paso 6 las ajusta con `force_login` y agrega pruebas para el anónimo. |
| Un atacante bloquea a propósito la cuenta de un cobrador escribiendo contraseñas falsas. | El bloqueo dura solo 15 minutos, el cobrador puede desbloquearse con la recuperación si tiene correo, y la SPEC 04 permite desbloquear desde la aplicación. |
| `/admin/login/` y el login propio se redirigen entre sí en un bucle con un usuario `is_staff` que no es superusuario. | `admin_login_redirect` responde 403 a un usuario autenticado que no es superusuario. Una prueba lo cubre. |
| El middleware de cambio obligatorio bloquea los estáticos, el healthcheck o el propio cierre de sesión. | La lista de rutas permitidas incluye `STATIC_URL`, `/health/`, `accounts:logout` y `accounts:password_change`, y cada una tiene prueba. |
| El texto de `next` lleva a un dominio externo (redirección abierta). | Se usa la validación de `LoginView` de Django (`url_has_allowed_host_and_scheme`). Un criterio lo comprueba. |
| Argon2 hace lentas las pruebas. | Las pruebas usan MD5, y una sola prueba comprueba la configuración real. |
| El correo simulado da la impresión de que la recuperación ya funciona en producción. | `README.md` y `CLAUDE.md` dicen que el correo es simulado, y la tabla de pendientes registra el envío real. |
| Dos intentos fallidos simultáneos cuentan solo uno. | `register_failed_attempt` usa `select_for_update()` dentro de `transaction.atomic()`. |

---

## Lo que **no** entra en esta spec

- El cierre de sesión por inactividad y la duración parametrizable de la sesión.
- El envío real de correos (SMTP u otro proveedor).
- Crear, editar, desactivar y desbloquear usuarios desde la aplicación, y los grupos y permisos.
- Invalidar las sesiones al desactivar un usuario.
- La auditoría de ingresos, fallos y bloqueos.
- La pantalla para editar la política de contraseñas, los intentos y la duración del bloqueo.
- El límite por IP, el CAPTCHA y el doble factor.
- "Recuérdame", el ingreso con redes sociales y el registro público.
- La foto de perfil del usuario.

Cada uno de estos puntos, si llega, va en su propia spec.
