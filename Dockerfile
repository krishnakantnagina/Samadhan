# Samadhan API (S22). Build context = repo root: main.py resolves specs at <repo>/specs (D-S04-1).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev
COPY backend backend
COPY specs specs

WORKDIR /app/backend
ENTRYPOINT []
ENV PATH="/app/backend/.venv/bin:$PATH"
# Railway sets $PORT. Secrets come from the host's env settings, never from the image.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
