"""Real FastAPI core (T07). Spec: docs/specs/S04-message-endpoint.md section 1.

No /message logic here yet (T18) - only app setup: config, CORS, /health, and startup loading
of the service specs. `backend/mock/app.py` (T08) is untouched and stays available for the
website and for the contract suite until CONTRACT_TARGET=real is exercised (T18/T19).
"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import config, schemas, service_spec
from app.routes import router
from mock.errors import register_error_handlers

SPECS_DIR = Path(__file__).resolve().parents[2] / "specs"


def create_app(specs_dir: Path = SPECS_DIR) -> FastAPI:
    origins = config.get_allowed_origins()  # raises before the app object exists

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.specs = service_spec.load_specs(specs_dir)  # SpecError -> startup fails
        yield

    app = FastAPI(title="Samadhan API", version=schemas.CONTRACT_VERSION, lifespan=lifespan)
    register_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )
    app.include_router(router, prefix="/api/v1")

    @app.get("/health", response_model=schemas.HealthResponse)
    def health() -> schemas.HealthResponse:
        return schemas.HealthResponse()

    return app


app = create_app()
