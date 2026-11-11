"""
Configuración de producción: mínimo seguro.

No hay valores por defecto para los secretos ni para los hosts: si falta
SECRET_KEY, ALLOWED_HOSTS o DATABASE_URL, Django no arranca
(ImproperlyConfigured). HSTS, CSP y el resto del endurecimiento quedan para la
spec de seguridad y producción.
"""

from .base import *  # noqa: F403
from .base import env

DEBUG = False

SECRET_KEY = env.str("SECRET_KEY")

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS")

# HTTPS detrás de un proxy inverso que termina TLS y envía X-Forwarded-Proto.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

SECURE_CONTENT_TYPE_NOSNIFF = True
