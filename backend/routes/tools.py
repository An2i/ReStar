import uuid

from fastapi import APIRouter, HTTPException

from backend.data_structures import build_tool_config_record
from backend.schemas import ToolConfigCreate, ToolConfigUpdate, ToolExecutionRequest
from backend.state import (
    save_tool_configs_state,
    tool_config_lock,
    tool_configs,
    tool_system,
)
from backend.utils import utc_now


router = APIRouter()


@router.get("/api/tool-system/tools")
def get_tool_system_tools() -> list[dict[str, object]]:
    return tool_system.list_tools()


@router.post("/api/tool-system/execute")
def execute_tool(payload: ToolExecutionRequest) -> dict[str, object]:
    return tool_system.execute(
        payload.tool,
        payload.arguments,
        session_id=payload.session_id,
        agent_id=payload.agent_id,
    )


@router.get("/api/tools")
def get_tools() -> list[dict[str, object]]:
    return sorted(
        tool_configs.values(),
        key=lambda item: (
            0 if item.get("is_builtin") else 1,
            str(item.get("created_at", "")),
        ),
    )


@router.post("/api/tools")
def create_tool(payload: ToolConfigCreate) -> dict[str, object]:
    tool_id = uuid.uuid4().hex
    now = utc_now()
    tool = build_tool_config_record(
        tool_id=tool_id,
        name=payload.name,
        command_line=payload.command_line,
        sandbox_command_line=payload.sandbox_command_line,
        description=payload.description,
        input_schema=payload.input_schema,
        is_builtin=False,
        created_at=now,
        updated_at=now,
    )
    with tool_config_lock:
        tool_configs[tool_id] = tool
        save_tool_configs_state()
    return tool


@router.put("/api/tools/{tool_id}")
def update_tool(tool_id: str, payload: ToolConfigUpdate) -> dict[str, object]:
    now = utc_now()
    with tool_config_lock:
        existing = tool_configs.get(tool_id)
        if not existing:
            raise HTTPException(status_code=404, detail="工具不存在")
        if existing.get("is_builtin"):
            raise HTTPException(status_code=400, detail="系统内置工具不可编辑")

        updated_tool = build_tool_config_record(
            tool_id=str(existing.get("id") or tool_id),
            name=payload.name,
            command_line=payload.command_line,
            sandbox_command_line=payload.sandbox_command_line,
            description=payload.description,
            input_schema=payload.input_schema,
            is_builtin=bool(existing.get("is_builtin")),
            created_at=str(existing.get("created_at") or now),
            updated_at=now,
        )
        tool_configs[tool_id] = updated_tool
        save_tool_configs_state()
    return updated_tool


@router.delete("/api/tools/{tool_id}")
def delete_tool(tool_id: str) -> dict[str, object]:
    with tool_config_lock:
        if tool_id not in tool_configs:
            raise HTTPException(status_code=404, detail="工具不存在")
        if tool_configs[tool_id].get("is_builtin"):
            raise HTTPException(status_code=400, detail="系统内置工具不可删除")
        tool_configs.pop(tool_id, None)
        save_tool_configs_state()
    return {"deleted": tool_id}
