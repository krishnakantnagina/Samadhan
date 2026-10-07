# Samadhan API (S22). Build context = repo root: main.py resolves specs at <repo>/specs (D-S04-1).
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
COPY backend/pyproject.toml backend/uv.lock backend/.python-version backend/
RUN cd backend && uv sync --frozen --no-dev
COPY backend backend
COPY specs specs

WORKDIR /app/backend
# Run as an unprivileged user: a bug in the app or a dependency then cannot touch the rest of the container.
RUN useradd --system --no-create-home --uid 10001 samadhan && chown -R samadhan /app
USER samadhan
ENTRYPOINT []
ENV PATH="/app/backend/.venv/bin:$PATH"
# The host (or `docker run`) asks this every 30 s; /health answers while the process is up.
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD python -c "import os,urllib.request; urllib.request.urlopen('http://127.0.0.1:%s/health' % os.environ.get('PORT','8000'), timeout=4)" || exit 1
# Railway sets $PORT. Secrets come from the host's env settings, never from the image.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
