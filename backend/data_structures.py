from pathlib import Path
from typing import Any, TypedDict, TypeAlias

from backend.utils import hash_file, iso_from_timestamp, utc_now

JsonDict: TypeAlias = dict[str, Any]


class FileInfoRecord(TypedDict):
    filename: str
    path: str
    size: int
    created_at: str
    modified_at: str
    md5: str
    sha256: str


class LLMSnapshotRecord(TypedDict, total=False):
    allocated: bool
    message: str
    platform_id: str
    platform_name: str
    provider: str
    occupied_count: int
    token_record: JsonDict


class ToolExecutionRecord(TypedDict):
    tool: str
    purpose: str
    status: str
    execution: JsonDict
    created_at: str


class AnalysisResultRecord(TypedDict, total=False):
    summary: str
    assistant_response: str
    risk_level: str
    plan_source: str
    failed_tool_count: int
    next_steps: list[str]
    file_name: str


class TaskSnapshotRecord(TypedDict, total=False):
    id: str
    task_id: str
    task_type: str
    task_name: str
    session_id: str
    status: str
    created_at: str
    updated_at: str
    started_at: str
    completed_at: str
    iteration_count: int
    llm: LLMSnapshotRecord
    tool_result_count: int
    last_decision: JsonDict
    result: JsonDict
    error: str
    report_path: str


class AgentStatusRecord(TypedDict, total=False):
    id: str
    session_id: str
    created_at: str
    updated_at: str
    type: str
    file_name: str
    status: str
    llm: LLMSnapshotRecord


class StatusModuleRecord(TypedDict):
    id: str
    capability_type: str
    name: str
    url: str
    model: str
    api_key: str
    token: str
    cookie: str
    capabilities: JsonDict
    status: str
    created_at: str
    updated_at: str


class CapabilityTypeRecord(TypedDict, total=False):
    name: str
    is_default: bool
    created_at: str
    updated_at: str
    platform_count: int
    pool_class: str


class ToolConfigRecord(TypedDict):
    id: str
    name: str
    command_line: str
    sandbox_command_line: str
    description: str
    input_schema: JsonDict
    is_builtin: bool
    created_at: str
    updated_at: str


def build_file_info_record(file_path: Path, original_filename: str) -> FileInfoRecord:
    stat = file_path.stat()
    return {
        "filename": original_filename,
        "path": str(file_path),
        "size": stat.st_size,
        "created_at": iso_from_timestamp(stat.st_ctime),
        "modified_at": iso_from_timestamp(stat.st_mtime),
        "md5": hash_file(file_path, "md5"),
        "sha256": hash_file(file_path, "sha256"),
    }


def build_llm_snapshot_record(
    llm_platform: JsonDict | None,
    llm_pool: Any | None,
    llm_selection: JsonDict | None,
    allocation_error: str = "",
) -> LLMSnapshotRecord:
    if not llm_platform or not llm_pool:
        return {
            "allocated": False,
            "message": allocation_error or "未分配LLM平台",
        }
    return {
        "allocated": True,
        "platform_id": str(llm_platform.get("id", "")),
        "platform_name": str(llm_platform.get("name", "")),
        "provider": str(llm_pool.detect_provider(llm_platform)),
        "occupied_count": (
            int(llm_selection.get("occupied_count", 0))
            if isinstance(llm_selection, dict)
            else 0
        ),
        "token_record": (
            dict(llm_selection.get("token_record", {}))
            if isinstance(llm_selection, dict)
            and isinstance(llm_selection.get("token_record"), dict)
            else {}
        ),
    }


def build_tool_execution_record(
    id: str,
    tool: str,
    purpose: str,
    status: str,
    execution: JsonDict,
) -> ToolExecutionRecord:
    return {
        "id": id,
        "tool": tool,
        "purpose": purpose,
        "status": status,
        "execution": execution,
        "created_at": utc_now(),
    }


def build_task_snapshot_record(
    *,
    task_id: str,
    task_type: str,
    task_name: str,
    session_id: str,
    status: str,
    created_at: str,
    updated_at: str,
    started_at: str,
    completed_at: str,
    iteration_count: int,
    llm: LLMSnapshotRecord,
    tool_result_count: int,
    last_decision: JsonDict | None,
    result: JsonDict | None,
    error: str,
    report_path: str,
) -> TaskSnapshotRecord:
    return {
        "id": task_id,
        "task_id": task_id,
        "task_type": task_type,
        "task_name": task_name,
        "session_id": session_id,
        "status": status,
        "created_at": created_at,
        "updated_at": updated_at,
        "started_at": started_at,
        "completed_at": completed_at,
        "iteration_count": iteration_count,
        "llm": llm,
        "tool_result_count": tool_result_count,
        "last_decision": last_decision or {},
        "result": result or {},
        "error": error,
        "report_path": report_path,
    }


def build_agent_status_record(
    *,
    agent_id: str,
    session_id: str,
    created_at: str,
    agent_type: str,
    file_name: str,
    status: str,
    llm: LLMSnapshotRecord,
    updated_at: str = "",
) -> AgentStatusRecord:
    record: AgentStatusRecord = {
        "id": agent_id,
        "session_id": session_id,
        "created_at": created_at,
        "type": agent_type,
        "file_name": file_name,
        "status": status,
        "llm": llm,
    }
    if updated_at:
        record["updated_at"] = updated_at
    return record


def build_status_module_record(
    *,
    module_id: str,
    capability_type: str,
    name: str,
    url: str,
    model: str = "",
    api_key: str = "",
    token: str = "",
    cookie: str = "",
    capabilities: JsonDict | None = None,
    status: str = "online",
    created_at: str = "",
    updated_at: str = "",
) -> StatusModuleRecord:
    now = utc_now()
    return {
        "id": module_id,
        "capability_type": capability_type,
        "name": name,
        "url": url,
        "model": model,
        "api_key": api_key,
        "token": token,
        "cookie": cookie,
        "capabilities": dict(capabilities or {}),
        "status": status,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }


def build_capability_type_record(
    *,
    name: str,
    is_default: bool,
    created_at: str = "",
    updated_at: str = "",
    platform_count: int | None = None,
    pool_class: str | None = None,
) -> CapabilityTypeRecord:
    now = utc_now()
    record: CapabilityTypeRecord = {
        "name": name,
        "is_default": is_default,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }
    if platform_count is not None:
        record["platform_count"] = platform_count
    if pool_class is not None:
        record["pool_class"] = pool_class
    return record


def build_tool_config_record(
    *,
    tool_id: str,
    name: str,
    command_line: str,
    description: str,
    is_builtin: bool,
    sandbox_command_line: str = "",
    input_schema: JsonDict | None = None,
    created_at: str = "",
    updated_at: str = "",
) -> ToolConfigRecord:
    now = utc_now()
    return {
        "id": tool_id,
        "name": name,
        "command_line": command_line,
        "sandbox_command_line": sandbox_command_line,
        "description": description,
        "input_schema": normalize_tool_input_schema(
            input_schema,
            command_line=command_line,
            sandbox_command_line=sandbox_command_line,
        ),
        "is_builtin": is_builtin,
        "created_at": created_at or now,
        "updated_at": updated_at or now,
    }


def normalize_tool_input_schema(
    input_schema: JsonDict | None,
    *,
    command_line: str = "",
    sandbox_command_line: str = "",
) -> JsonDict:
    schema = dict(input_schema or {})
    required = schema.get("required")
    if (
        isinstance(required, list)
        and "{log_path}" in f"{command_line}\n{sandbox_command_line}"
    ):
        schema["required"] = [item for item in required if item != "log_path"]
    return schema
