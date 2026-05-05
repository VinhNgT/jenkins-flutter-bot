"""Page routes — serves the SPA shell."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

STATIC_DIR = Path(__file__).resolve().parent.parent / "static"

router = APIRouter()


@router.get("/")
async def index() -> FileResponse:
    """Serve the main dashboard page."""
    return FileResponse(STATIC_DIR / "index.html")
