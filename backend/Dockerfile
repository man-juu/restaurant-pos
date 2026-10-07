# Production image for the API, the admin API, migrations and jobs (one image, several commands).
# Multi-stage: build wheels with tools, ship only the runtime. Runs as a non-root user.

FROM python:3.12-slim AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /src
COPY pyproject.toml ./
COPY app ./app
RUN pip wheel --wheel-dir /wheels .

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 ENVIRONMENT=production
RUN groupadd --system --gid 10001 app && useradd --system --uid 10001 --gid app --no-create-home app
WORKDIR /app
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links=/wheels /wheels/*.whl && rm -rf /wheels
COPY alembic.ini ./
COPY migrations ./migrations
COPY app ./app
# Named volumes copy this owner on first mount, so the app user can write uploads.
RUN mkdir -p /var/lib/pos/uploads && chown app:app /var/lib/pos/uploads
USER app
EXPOSE 8000
# Two workers fit the 4 GB VPS budget (docs/07 section 3). Proxy headers are trusted only
# from the web (Caddy) container's fixed address on the internal network (compose.prod.yaml).
ENV FORWARDED_ALLOW_IPS=172.28.0.10
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "2", "--proxy-headers", "--no-server-header"]
