# Imagen de DESARROLLO (SPEC 01). La imagen de producción con gunicorn se define
# en la spec de endurecimiento de seguridad y producción.
FROM python:3.14-slim

COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

# El entorno virtual vive fuera de /app para que el volumen con el código
# montado desde el host no lo oculte.
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN useradd --create-home --uid 1000 app \
    && mkdir -p /opt/venv /app \
    && chown app:app /opt/venv /app

WORKDIR /app
USER app

# Primero solo las dependencias, para aprovechar la caché de capas.
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY --chown=app:app . .

EXPOSE 8000

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py runserver 0.0.0.0:8000"]
