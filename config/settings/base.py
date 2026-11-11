"""
Configuración común a todos los entornos.

Los valores que cambian por entorno o que son secretos se leen de variables de
entorno con django-environ. En local se cargan desde `.env` si el archivo existe;
en Docker y en CI llegan por el entorno del proceso.
"""

from pathlib import Path

import environ
from django.contrib.messages import constants as messages
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()

_env_file = BASE_DIR / ".env"
if _env_file.exists():
    # No sobrescribe variables que ya existan en el entorno del proceso.
    environ.Env.read_env(_env_file)


# Aplicaciones

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.forms",
    # Apps del proyecto
    "apps.core",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
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


# Validación de contraseñas

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",  # noqa: E501
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


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
