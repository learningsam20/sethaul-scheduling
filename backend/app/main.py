from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.db import ensure_database
from app.routers import admin_router, analytics_router, auth_router, chat_router, location_router, ops_router, penalty_router, operational_messages_router
from app.tracing import configure_langsmith

settings = get_settings()
configure_langsmith()
ensure_database()

app = FastAPI(title=settings.app_name, version="1.0.0")
origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins or ["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = settings.api_prefix
app.include_router(auth_router.router, prefix=api)
app.include_router(chat_router.router, prefix=api)
app.include_router(ops_router.router, prefix=api)
app.include_router(admin_router.router, prefix=api)
app.include_router(analytics_router.router, prefix=api)
app.include_router(location_router.router, prefix=api)
app.include_router(penalty_router.router, prefix=api)
app.include_router(operational_messages_router.router, prefix=api)


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "classroom_now": settings.classroom_now,
        "langsmith": configure_langsmith(),
    }


@app.get("/api/health")
def api_health():
    return health()


static_dir = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if static_dir.exists():
    app.mount("/assets", StaticFiles(directory=static_dir / "assets"), name="assets")

    @app.get("/")
    def index():
        return FileResponse(static_dir / "index.html")

    @app.get("/{full_path:path}")
    def spa(full_path: str):
        candidate = static_dir / full_path
        if candidate.exists() and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(static_dir / "index.html")
