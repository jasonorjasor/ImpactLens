"""Serve the built frontend and API from one application."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from api import app as api_app


FRONTEND_DIST = Path(__file__).resolve().parent / "frontend" / "dist"


def create_app(frontend_directory=FRONTEND_DIST):
    frontend_directory = Path(frontend_directory)
    if not (frontend_directory / "index.html").is_file():
        raise RuntimeError("Frontend build is missing. Run 'npm run build' in frontend/ first.")

    app = FastAPI(title=api_app.title)
    app.include_router(api_app.router)
    app.mount("/", StaticFiles(directory=frontend_directory, html=True), name="frontend")
    return app
