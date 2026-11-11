"""Configuración de desarrollo local."""

from .base import *  # noqa: F403
from .base import env

SECRET_KEY = env.str(
    "SECRET_KEY",
    default="dev-insegura-solo-para-desarrollo-local",
)

DEBUG = env.bool("DEBUG", default=True)

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
