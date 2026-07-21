from fastapi import APIRouter, HTTPException

from backend.schemas import SkillCreate, SkillUpdate
from backend.state import skill_system


router = APIRouter()


@router.get("/api/skills")
def get_skills() -> list[dict[str, object]]:
    return skill_system.list_skills()


@router.get("/api/skills/{skill_id}")
def get_skill(skill_id: str) -> dict[str, object]:
    skill = skill_system.get_skill(skill_id)
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return skill


@router.post("/api/skills")
def create_skill(payload: SkillCreate) -> dict[str, object]:
    try:
        return skill_system.create_skill(
            name=payload.name,
            description=payload.description,
            keywords=payload.keywords,
            content=payload.content,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/skills/import")
def import_skill(payload: SkillCreate) -> dict[str, object]:
    try:
        return skill_system.create_skill(
            name=payload.name,
            description=payload.description,
            keywords=payload.keywords,
            content=payload.content,
            source="markdown-import",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put("/api/skills/{skill_id}")
def update_skill(skill_id: str, payload: SkillUpdate) -> dict[str, object]:
    try:
        skill = skill_system.update_skill(
            skill_id=skill_id,
            name=payload.name,
            description=payload.description,
            keywords=payload.keywords,
            content=payload.content,
            source=payload.source,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not skill:
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return skill


@router.delete("/api/skills/{skill_id}")
def delete_skill(skill_id: str) -> dict[str, object]:
    if not skill_system.delete_skill(skill_id):
        raise HTTPException(status_code=404, detail="Skill 不存在")
    return {"deleted": skill_id}
