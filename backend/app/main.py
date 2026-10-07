"""Real FastAPI core (T07). Spec: docs/specs/S04-message-endpoint.md section 1.

No /message logic here yet (T18) - only app setup: config, CORS, /health, and startup loading
of the service specs. `backend/mock/app.py` (T08) is untouched and stays available for the
website and for the contract suite until CONTRACT_TARGET=real is exercised (T18/T19).
"""

import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import config, schemas, service_spec
from app.auth_routes import router as auth_router
from app.routes import router
from mock.errors import register_error_handlers

SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"
logger = logging.getLogger(__name__)


def is_production() -> bool:
    """True on a real host (Render sets RENDER=true, Railway sets RAILWAY_ENVIRONMENT=production) or when ENV=production."""
    env = os.environ
    return (
        env.get("ENV", "").strip().lower() == "production"
        or env.get("RAILWAY_ENVIRONMENT", "").strip().lower() == "production"
        or env.get("RENDER", "").strip().lower() in ("1", "true", "yes")
    )


def docs_enabled() -> bool:
    """The interactive API docs (/docs, /redoc, /openapi.json) map the whole API for anyone who finds the address: off in production unless ENABLE_API_DOCS=1."""
    return not is_production() or os.environ.get("ENABLE_API_DOCS", "").strip().lower() in ("1", "true", "yes", "on")


def create_app(specs_dir: Path = SPECS_DIR) -> FastAPI:
    origins = config.get_allowed_origins()  # raises before the app object exists

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.specs = service_spec.load_specs(specs_dir)  # SpecError -> startup fails
        yield

    docs = docs_enabled()
    app = FastAPI(
        title="Samadhan API",
        version=schemas.CONTRACT_VERSION,
        lifespan=lifespan,
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")
    app.include_router(auth_router, prefix="/api/v1")  # S31 phone registration / saved login

    @app.get("/health", response_model=schemas.HealthResponse)
    def health() -> schemas.HealthResponse:
        return schemas.HealthResponse()

    @app.get("/health/ready")
    def ready() -> JSONResponse:
        """Unlike /health (the process is up), this checks the database too: 503 while it cannot be reached. Use it for the host's health check."""
        try:
            from app.db import get_client

            get_client().table("offices").select("id").limit(1).execute()
        except Exception as exc:  # noqa: BLE001 -- any failure means "not ready"; the reason stays in the log, never in the answer
            logger.warning("readiness check failed: %s", type(exc).__name__)
            return JSONResponse(status_code=503, content={"status": "unavailable", "database": "down"})
        return JSONResponse(content={"status": "ok", "database": "ok"})

    return app


app = create_app()
