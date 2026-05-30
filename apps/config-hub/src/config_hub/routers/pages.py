"""Page routes — serves the SPA shell."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse

WEBAPP_DIR = Path(__file__).resolve().parent.parent / "webapp"

router = APIRouter()


@router.get("/webapp-admin")
async def index() -> FileResponse:
    """Serve the admin dashboard SPA shell."""
    return FileResponse(WEBAPP_DIR / "index.html")
