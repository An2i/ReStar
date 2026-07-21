from fastapi import APIRouter


router = APIRouter()


@router.get("/api/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
