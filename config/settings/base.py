"""
Configuración común a todos los entornos.

Los valores que cambian por entorno o que son secretos se leen de variables de
entorno con django-environ. En local se cargan desde `.env` si el archivo existe;
en Docker y en CI llegan por el entorno del proceso.
"""

from pathlib import Path

import environ
from django.contrib.messages import constants as messages
from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    # No sobrescribe variables que ya existan en el entorno del proceso.
    environ.Env.read_env(_env_file)


# Aplicaciones

INSTALLED_APPS = [
    # Admin de Django solo para superusuarios (SPEC 03).
    "apps.accounts.apps.SuperuserAdminConfig",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    # ArrayField de los parámetros globales (SPEC 06).
    "django.contrib.postgres",
    # Apps del proyecto
    "apps.core",
    "apps.accounts",
    # Registro de auditoría inmutable (SPEC 05).
    "apps.auditoria",
    # Parámetros globales del negocio (SPEC 06).
    "apps.parametros",
]

# Modelo de usuario propio (SPEC 03). Cambiarlo con datos reales es muy costoso.
AUTH_USER_MODEL = "accounts.User"

# Ingreso con nombre de usuario o correo, con bloqueo temporal (SPEC 03).
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.UsernameOrEmailBackend"]

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"
LOGOUT_REDIRECT_URL = "accounts:login"

# La sesión se cierra al cerrar el navegador. La inactividad y la duración
# máxima son parámetros globales y las aplica SessionPolicyMiddleware (SPEC 06,
# §3.5). SESSION_COOKIE_AGE es el máximo del rango (24 horas), como tope duro
# aunque el middleware fallara.
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 60 * 24

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # IP, navegador, ruta e id de cada petición para la auditoría (SPEC 05).
    "apps.auditoria.middleware.AuditContextMiddleware",
    # Cierre de sesión por inactividad y por duración máxima (SPEC 06).
    "apps.accounts.middleware.SessionPolicyMiddleware",
    # Toda vista exige sesión salvo las marcadas con @login_not_required (SPEC 03).
    "django.contrib.auth.middleware.LoginRequiredMiddleware",
    # Quien debe cambiar la contraseña no pasa de esa pantalla (SPEC 03).
    "apps.accounts.middleware.ForcePasswordChangeMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.context_processors.branding",
            ],
        },
    },
]

# Formularios: `{{ form }}` usa las plantillas de templates/forms/ con las clases
# de Bootstrap 4 (SPEC 02, paso 8).
FORM_RENDERER = "apps.core.forms.BootstrapFormRenderer"

# Mensajes: el nivel `error` usa la clase de alerta `alert-danger` de Bootstrap.
MESSAGE_TAGS = {messages.ERROR: "danger"}

WSGI_APPLICATION = "config.wsgi.application"


# Base de datos: PostgreSQL es el único motor soportado (constitución §4).

DATABASES = {
    "default": env.db("DATABASE_URL"),
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"


# Hashers de contraseñas: Argon2 es el principal (constitución §6.1). Los demás
# se conservan para leer hashes existentes, que se actualizan al iniciar sesión.

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.ScryptPasswordHasher",
]


# Validación de contraseñas

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "apps.accounts.validators.PolicyMinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
    {
        "NAME": "apps.accounts.validators.LettersAndDigitsValidator",
    },
]


# Las políticas de cuentas (intentos, bloqueo, longitud mínima y vigencia del
# enlace de recuperación) viven en los parámetros globales desde la SPEC 06 y
# solo se leen con apps/accounts/policy.py.


# Auditoría (SPEC 05, §3.5). Número de proxies de confianza delante de la
# aplicación. Con 0 la IP es REMOTE_ADDR y se ignora X-Forwarded-For, que el
# cliente puede falsificar. Detrás de un nginx propio, 1.

AUDIT_TRUSTED_PROXIES = env.int("AUDIT_TRUSTED_PROXIES", default=0)
if AUDIT_TRUSTED_PROXIES < 0:
    raise ImproperlyConfigured("AUDIT_TRUSTED_PROXIES no puede ser negativo.")


# Internacionalización: español de Colombia, preparado para más idiomas.

LANGUAGE_CODE = "es-co"

LANGUAGES = [
    ("es-co", _("Español (Colombia)")),
]

LOCALE_PATHS = [BASE_DIR / "locale"]

TIME_ZONE = "America/Bogota"

USE_I18N = True

USE_TZ = True


# Archivos estáticos

STATIC_URL = "static/"

# Recursos de SB Admin 2 copiados de references/ y los estilos y scripts propios.
STATICFILES_DIRS = [BASE_DIR / "static"]


# Correo simulado (SPEC 03). No hay SMTP en ningún entorno: la variable de
# entorno EMAIL_BACKEND elige entre "console" (por defecto), que imprime el
# correo en la consola, y "file", que lo guarda en EMAIL_FILE_PATH. Los nombres
# van en minúscula para que no sean settings: con MAILERS, Django no admite los
# settings antiguos EMAIL_BACKEND ni EMAIL_FILE_PATH.

email_backends = {
    "console": "django.core.mail.backends.console.EmailBackend",
    "file": "django.core.mail.backends.filebased.EmailBackend",
}


def build_mailers(backend: str, file_path: Path) -> dict[str, dict]:
    """Arma MAILERS para el correo simulado, o falla si el backend no existe."""
    if backend not in email_backends:
        raise ImproperlyConfigured(
            f"EMAIL_BACKEND={backend!r} no es válido. Usa uno de: "
            f"{', '.join(email_backends)}."
        )
    mailer: dict[str, object] = {"BACKEND": email_backends[backend]}
    if backend == "file":
        mailer["OPTIONS"] = {"file_path": str(file_path)}
    return {"default": mailer}


email_file_path = Path(env.str("EMAIL_FILE_PATH", default="tmp/emails"))
if not email_file_path.is_absolute():
    email_file_path = BASE_DIR / email_file_path

MAILERS = build_mailers(env.str("EMAIL_BACKEND", default="console"), email_file_path)

DEFAULT_FROM_EMAIL = env.str("DEFAULT_FROM_EMAIL", default="no-responder@localhost")
