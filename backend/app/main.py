"""REVEnova FastAPI application entrypoint."""
import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.database import init_db

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("revenova")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        description="Autonomous Revenue Recovery Intelligence Platform",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.on_event("startup")
    def _startup() -> None:
        init_db()
        logger.info("%s ready (LLM backend: %s)", settings.app_name,
                    "mock" if settings.use_mock_llm else settings.openai_model)

    app.include_router(router)

    @app.get("/health")
    def health() -> dict:
        from app.core.database import is_postgres

        return {
            "status": "ok",
            "app": settings.app_name,
            "db": "postgres+pgvector" if is_postgres() else "sqlite-fallback",
            "llm": "mock-detailed" if settings.use_mock_llm else settings.openai_model,
            "jobs": "celery" if settings.use_celery else "sync-fallback",
        }

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)