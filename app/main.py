from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.v1.endpoints.health import APP_VERSION
from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title=settings.app_name,
        description=(
            "API dla projektu 'eBobo - Zasiłkowy Przewodnik Przyszłego Rodzica' "
            "(HackNation 2026, ZUS)."
        ),
        version=APP_VERSION,
        docs_url="/docs",
        redoc_url="/redoc",
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_exception_handlers(app)

    app.include_router(api_router, prefix=settings.api_v1_prefix)

    static_admin_dir = Path(__file__).resolve().parent.parent / "static" / "admin"
    app.mount("/admin", StaticFiles(directory=static_admin_dir, html=True), name="admin-panel")

    return app


app = create_app()
