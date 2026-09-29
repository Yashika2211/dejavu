# The DejaVu API. Build from the repo root, since the API reads data/fixtures:
#   docker build -f backend/Dockerfile -t dejavu-api .
FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1
WORKDIR /app

COPY backend/pyproject.toml backend/uv.lock backend/
RUN cd backend && uv sync --locked --no-dev --no-install-project

COPY backend/ backend/
COPY data/fixtures/ data/fixtures/
RUN cd backend && uv sync --locked --no-dev

WORKDIR /app/backend
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-sync uvicorn dejavu.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
