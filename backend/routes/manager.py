import uuid

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from backend.config import MEMORY_FILE, UPLOAD_DIR
from backend.schemas import ManagerRequest, MemoryRecordCreate
from backend.services.tasks import normalize_task_type
from backend.state import memory_manager, request_manager, session_storage, task_pool
from backend.utils import safe_filename


router = APIRouter()


def merged_task_snapshots() -> list[dict[str, object]]:
    active_tasks = task_pool.list_tasks()
    active_ids = {str(task.get("task_id") or task.get("id") or "") for task in active_tasks}
    history_tasks = [
        task
        for task in session_storage.list_task_snapshots()
        if str(task.get("task_id") or task.get("id") or "") not in active_ids
    ]
    return sorted(
        [*active_tasks, *history_tasks],
        key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
        reverse=True,
    )


def filter_task_snapshots(
    tasks: list[dict[str, object]],
    *,
    page: int,
    page_size: int,
    status: str,
    task_type: str,
    search: str,
) -> dict[str, object]:
    safe_page = max(1, int(page or 1))
    safe_page_size = min(max(1, int(page_size or 20)), 100)
    status_filter = str(status or "").strip().lower()
    type_filter = str(task_type or "").strip()
    search_filter = str(search or "").strip().lower()
    if status_filter:
        tasks = [
            task
            for task in tasks
            if str(task.get("status") or "").strip().lower() == status_filter
        ]
    if type_filter:
        tasks = [
            task
            for task in tasks
            if str(task.get("task_type") or "").strip() == type_filter
        ]
    if search_filter:
        filtered = []
        for task in tasks:
            result = task.get("result") if isinstance(task.get("result"), dict) else {}
            analysis_result = (
                result.get("analysis_result")
                if isinstance(result.get("analysis_result"), dict)
                else {}
            )
            search_text = " ".join(
                str(value or "")
                for value in (
                    task.get("task_id"),
                    task.get("id"),
                    task.get("task_type"),
                    task.get("task_name"),
                    analysis_result.get("summary"),
                    result.get("assistant_response"),
                )
            ).lower()
            if search_filter in search_text:
                filtered.append(task)
        tasks = filtered
    total = len(tasks)
    start = (safe_page - 1) * safe_page_size
    end = start + safe_page_size
    return {
        "items": tasks[start:end],
        "total": total,
        "page": safe_page,
        "page_size": safe_page_size,
        "total_pages": max(1, (total + safe_page_size - 1) // safe_page_size),
    }


@router.post("/api/manager/requests")
def route_manager_request(payload: ManagerRequest) -> dict[str, object]:
    return request_manager.route_request(payload)


@router.get("/api/manager/agents")
def get_manager_agents() -> list[dict[str, object]]:
    return request_manager.list_agents()


@router.get("/api/task-pool")
def get_task_pool() -> dict[str, object]:
    return task_pool.snapshot()


@router.get("/api/tasks")
def get_tasks(
    page: int = 1,
    page_size: int = 0,
    status: str = "",
    task_type: str = "",
    search: str = "",
) -> dict[str, object] | list[dict[str, object]]:
    tasks = merged_task_snapshots()
    if page_size and page_size > 0:
        return filter_task_snapshots(
            tasks,
            page=page,
            page_size=page_size,
            status=status,
            task_type=task_type,
            search=search,
        )
    return tasks


@router.get("/api/tasks/{task_id}")
def get_task(task_id: str) -> dict[str, object]:
    try:
        return task_pool.get_task(task_id)
    except HTTPException as exc:
        if exc.status_code != 404:
            raise
    snapshot = session_storage.get_task_snapshot(task_id)
    if not snapshot:
        raise HTTPException(status_code=404, detail="任务不存在")
    return snapshot


@router.post("/api/tasks")
def create_task(payload: dict[str, object]) -> dict[str, object]:
    task_type = str(payload.get("task_type") or payload.get("type") or "")
    task_payload = payload.get("payload")
    wait = bool(payload.get("wait", False))
    return request_manager.create_task(
        task_type,
        task_payload if isinstance(task_payload, dict) else payload,
        wait=wait,
    )


@router.get("/api/manager/sessions")
def get_manager_sessions() -> list[dict[str, object]]:
    return session_storage.list_sessions()


@router.get("/api/manager/sessions/{session_id}/events")
def get_manager_session_events(session_id: str, limit: int = 200) -> list[dict[str, object]]:
    return session_storage.read_events(session_id, limit=limit)


@router.post("/api/manager/program-analysis")
async def submit_program_analysis(
    analysis_type: str = Form(default="vulnerability"),
    execution_mode: str = Form(default="agent"),
    file: UploadFile = File(...),
) -> dict[str, object]:
    normalized_type = normalize_task_type(str(analysis_type or "vulnerability").strip())
    if normalized_type not in {"sample-analysis", "vulnerability-mining"}:
        raise HTTPException(status_code=400, detail="分析类型不支持")

    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    original_filename = safe_filename(file.filename)
    stored_filename = f"{uuid.uuid4().hex}_{original_filename}"
    stored_path = (UPLOAD_DIR / stored_filename).resolve()

    with stored_path.open("wb") as output:
        while True:
            chunk = await file.read(1024 * 1024)
            if not chunk:
                break
            output.write(chunk)

    if stored_path.stat().st_size == 0:
        stored_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail="上传文件不能为空")

    return request_manager.create_program_analysis_task(
        stored_path,
        original_filename,
        normalized_type,
        execution_mode=execution_mode,
    )


@router.get("/api/memory")
def get_memory_records() -> dict[str, object]:
    return {
        "memory_file": str(MEMORY_FILE),
        "records": memory_manager.list_records(),
    }


@router.post("/api/memory")
def create_memory_record(payload: MemoryRecordCreate) -> dict[str, object]:
    return memory_manager.add_record(
        payload.title,
        payload.content,
        tags=payload.tags,
        source="manual",
    )
