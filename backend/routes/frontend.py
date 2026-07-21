from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from backend.config import ASSETS_DIR, FRONTEND_DIST, REPORT_DIR, ROOT_DIR


router = APIRouter()


def mount_frontend_assets(app: object) -> None:
    if ASSETS_DIR.exists():
        app.mount("/assets", StaticFiles(directory=ASSETS_DIR), name="assets")
    if REPORT_DIR.exists():
        app.mount("/reports", StaticFiles(directory=REPORT_DIR), name="reports")


@router.get("/{full_path:path}")
def serve_frontend(full_path: str) -> FileResponse:
    if full_path.startswith("api/"):
        raise HTTPException(status_code=404, detail="API接口不存在")

    index_file = FRONTEND_DIST / "index.html"
    if not index_file.exists():
        return FileResponse(ROOT_DIR / "frontend" / "index.html")
    return FileResponse(index_file)
