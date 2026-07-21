import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException

from backend.schemas import KnowledgeBaseCreate, KnowledgeBaseDelete, KnowledgeBaseQuery
from backend.state import (
    knowledge_base_lock,
    knowledge_bases,
    save_knowledge_bases_state,
)
from backend.stores.knowledge_store import (
    build_knowledge_base_index,
    query_json_vector_store,
    remove_knowledge_vector_dir,
)


router = APIRouter()


@router.get("/api/knowledge-bases")
def get_knowledge_bases() -> list[dict[str, object]]:
    return sorted(
        knowledge_bases.values(),
        key=lambda item: str(item.get("created_at", "")),
        reverse=True,
    )


@router.post("/api/knowledge-bases")
def create_knowledge_base(payload: KnowledgeBaseCreate) -> dict[str, object]:
    folder_path = Path(payload.folder_path).expanduser()
    if not folder_path.exists() or not folder_path.is_dir():
        raise HTTPException(status_code=400, detail="知识库文件夹路径不存在或不是文件夹")

    kb_id = uuid.uuid4().hex
    created_at = datetime.now(timezone.utc).isoformat()
    try:
        index_info = build_knowledge_base_index(kb_id, folder_path)
    except OSError as exc:
        raise HTTPException(status_code=400, detail=f"知识库索引创建失败: {exc}") from exc

    knowledge_base = {
        "id": kb_id,
        "name": payload.name,
        "folder_path": str(folder_path.resolve()),
        "created_at": created_at,
        "updated_at": created_at,
        **index_info,
    }
    with knowledge_base_lock:
        knowledge_bases[kb_id] = knowledge_base
        save_knowledge_bases_state()
    return knowledge_base


@router.delete("/api/knowledge-bases")
def delete_knowledge_bases(payload: KnowledgeBaseDelete) -> dict[str, object]:
    deleted_ids = []
    with knowledge_base_lock:
        for kb_id in payload.ids:
            if kb_id in knowledge_bases:
                remove_knowledge_vector_dir(kb_id)
                knowledge_bases.pop(kb_id, None)
                deleted_ids.append(kb_id)
        save_knowledge_bases_state()
    return {"deleted": deleted_ids}


@router.post("/api/knowledge-bases/query")
def query_knowledge_bases(payload: KnowledgeBaseQuery) -> dict[str, object]:
    selected_ids = payload.knowledge_base_ids or list(knowledge_bases.keys())
    results = []
    for kb_id in selected_ids:
        if kb_id not in knowledge_bases:
            continue
        results.extend(
            query_json_vector_store(
                kb_id,
                payload.query,
                payload.top_k,
                knowledge_bases,
            )
        )
    results = sorted(results, key=lambda item: float(item["score"]), reverse=True)[
        : payload.top_k
    ]
    return {"query": payload.query, "results": results}
