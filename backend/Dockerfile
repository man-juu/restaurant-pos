# Development image. Production image (non-root, multi-stage) comes in slice 0.8.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
RUN mkdir app && pip install -e ".[dev]"
COPY . .
CMD ["uvicorn", "app.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--reload"]
