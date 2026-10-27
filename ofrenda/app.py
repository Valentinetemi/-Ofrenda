"""HTTP API and the single page. Nothing here talks to a cloud model."""

from __future__ import annotations

from fastapi import FastAPI
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from ofrenda.config import ROOT, Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="Ofrenda")
    app.state.settings = settings

    @app.get("/api/health")
    def health():
        return {"ok": True, "service": "ofrenda"}

    static_dir = ROOT / "static"
    if static_dir.is_dir():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    def index():
        page = static_dir / "index.html"
        if page.is_file():
            return FileResponse(page)
        return {"ok": True}

    return app


app = create_app()
