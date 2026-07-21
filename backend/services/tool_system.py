import uuid
import json
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from backend.config import ROOT_DIR, TOOL_AUDIT_FILE
from backend.data_structures import JsonDict
from backend.services.sandbox_client import (
    SANDBOX_TASK_TYPES,
    SandboxClient,
    SandboxClientError,
)
from backend.services.session_memory import SessionStorage
from backend.services.tool_definition import (
    ToolDefinition,
    ToolDefinitionRegistry,
    input_schema_for,
    permission_for,
)
from backend.services.tool_renderer import ToolRenderer
from backend.services.tool_runtime import ToolRuntime
from backend.utils import append_jsonl, utc_now

DEBUG_LOG_PREFIX = "[TOOL_DEBUG]"


class ToolSystem:
    """Thin facade that coordinates tool definition, runtime, and rendering layers."""

    def __init__(
        self,
        tool_configs: dict[str, JsonDict],
        session_storage: SessionStorage | None = None,
        root_dir: Path = ROOT_DIR,
        sandbox_resolver: Any | None = None,
    ) -> None:
        self.tool_configs = tool_configs
        self.session_storage = session_storage
        self.registry = ToolDefinitionRegistry(tool_configs)
        self.runtime = ToolRuntime(root_dir, tool_configs)
        self.renderer = ToolRenderer()
        self.sandbox_resolver = sandbox_resolver

    def list_tools(self) -> list[JsonDict]:
        return [definition.to_dict() for definition in self.registry.list_definitions()]

    def getTools(self, provider: str) -> list[JsonDict]:
        tool_specs = []
        if provider == "openai":
            tool_specs = [
                {
                    "type": "function",
                    "function":{
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": {
                            **dict(tool.get("input_schema") or {}),
                        },
                    }
                }
                for tool in self.list_tools()
            ]
        elif provider == "deepseek":
            tool_specs = [
                {
                    "type": "function",
                    "function":{
                        "name": tool.get("name", ""),
                        "description": tool.get("description", ""),
                        "parameters": {
                            **dict(tool.get("input_schema") or {}),
                        },
                    }
                }
                for tool in self.list_tools()
            ]
        return tool_specs

    def sandbox_tool_inventory(self) -> list[JsonDict]:
        inventory = []
        for tool in self.list_tools():
            compact_tool = dict(tool)
            compact_tool.pop("prompt", None)
            compact_tool.pop("prompt_source", None)
            if str(compact_tool.get("sandbox_command_line") or "").strip():
                compact_tool["local_command_line"] = compact_tool.get("command_line", "")
                compact_tool["command_line"] = str(compact_tool["sandbox_command_line"]).strip()
            inventory.append(compact_tool)
        return inventory

    def describe_tool(self, tool: JsonDict) -> JsonDict:
        return self.registry.describe_tool(tool)

    def input_schema_for(self, command_line: str) -> JsonDict:
        return input_schema_for(command_line)

    def permission_for(self, command_line: str) -> JsonDict:
        return permission_for(command_line)

    def get_definition(self, tool_key: str) -> ToolDefinition | None:
        return self.registry.get_definition(tool_key)

    def get_tool(self, tool_key: str) -> JsonDict | None:
        definition = self.get_definition(tool_key)
        return definition.to_dict() if definition else None

    def execute(
        self,
        tool_name: str,
        arguments: JsonDict | None = None,
        session_id: str = "",
        agent_id: str = "",
        task_type: str = "",
        use_sandbox: bool = True,
    ) -> JsonDict:
        definition = self.get_definition(tool_name)
        if not definition:
            raise HTTPException(status_code=404, detail="工具不存在")

        use_render = self.renderer.render_tool_use(
            definition,
            self.redact_arguments(arguments),
        )
        # print(
        #     f"{DEBUG_LOG_PREFIX} tool={tool_name} "
        #     f"task_type={task_type} "
        #     f"args={str(self.redact_arguments(arguments))[:800]}"
        # )

        self.audit_event(
            "tool_use",
            definition,
            {
                "arguments": arguments,
                "rendered": use_render,
            },
            session_id=session_id,
            agent_id=agent_id,
        )

        try:
            sandbox_client = self.get_sandbox_client(task_type) if use_sandbox else None
            # print(f"{DEBUG_LOG_PREFIX} sandbox_enabled={sandbox_client is not None}")
            sandbox_fallback: JsonDict | None = None
            if sandbox_client:
                sandbox_tool = self.response_tool(definition)
                if str(sandbox_tool.get("sandbox_command_line") or "").strip():
                    sandbox_tool["command_line"] = str(sandbox_tool["sandbox_command_line"]).strip()
                try:
                    result = sandbox_client.execute_tool(
                        sandbox_tool,
                        arguments,
                        self.sandbox_tool_inventory(),
                    )
                except SandboxClientError as exc:
                    sandbox_fallback = {
                        "mode": "local_fallback",
                        "reason": str(exc),
                    }
                    result = self.runtime.execute(definition, arguments)
            else:
                result = self.runtime.execute(definition, arguments)
        except HTTPException as exc:
            self.audit_event(
                "tool_result",
                definition,
                {
                    "status": "failed",
                    "error": exc.detail,
                    "rendered": self.renderer.render_error(definition, exc.detail),
                },
                session_id=session_id,
                agent_id=agent_id,
            )
            raise
        except SandboxClientError as exc:
            self.audit_event(
                "tool_result",
                definition,
                {
                    "status": "failed",
                    "error": str(exc),
                    "rendered": self.renderer.render_error(definition, str(exc)),
                },
                session_id=session_id,
                agent_id=agent_id,
            )
            raise HTTPException(status_code=502, detail=str(exc)) from exc

        status = self.status_for_result(result)
        # print(f"{DEBUG_LOG_PREFIX} status={status} result={str(result)[:1200]}")
        result_render = self.renderer.render_tool_result(definition, result, status)
        response = {
            "tool": self.response_tool(definition)["name"],
            "arguments": self.redact_arguments(arguments),
            "result": result,
            "status": status,
            # "rendered": {
            #     "use": use_render,
            #     "result": result_render,
            # },
            # "search_text": " ".join(
            #     part
            #     for part in [
            #         use_render.get("search_text", ""),
            #         result_render.get("search_text", ""),
            #     ]
            #     if part
            # ),
            "executed_at": utc_now(),
        }
        if sandbox_fallback:
            response["sandbox"] = sandbox_fallback
        self.audit_event(
            "tool_result",
            definition,
            {
                "status": status,
                "result": result,
                "rendered": result_render,
            },
            session_id=session_id,
            agent_id=agent_id,
        )
        return response

    def status_for_result(self, result: JsonDict) -> str:
        if not isinstance(result, dict):
            return "fail"
        if str(result.get("status") or "").lower() in {"failed", "fail", "error"}:
            return "fail"
        if result.get("error") or result.get("detail"):
            return "fail"
        stderr = str(result.get("stderr") or "")
        stdout = str(result.get("stdout") or "")
        if bool(result.get("timed_out")):
            return "fail"
        if "exit_code" in result:
            if result.get("exit_code") not in (None, 0):
                return "fail"
            return "success"
        if stderr != "":
            return "fail"
        elif "Error:" in stdout:
            return "fail"
        else:
            return "success"

    def get_sandbox_client(self, task_type: str) -> SandboxClient | None:
        if task_type not in SANDBOX_TASK_TYPES or not self.sandbox_resolver:
            return None
        platform = self.sandbox_resolver()
        if not platform:
            return None
        try:
            client = SandboxClient(platform, self.runtime.root_dir)
        except SandboxClientError:
            return None
        return client if client.is_online() else None

    def response_tool(self, definition: ToolDefinition) -> JsonDict:
        return {
            "id": definition.id,
            "name": definition.name,
            "command_line": definition.command_line,
            "sandbox_command_line": definition.sandbox_command_line,
            "is_builtin": definition.is_builtin,
            "permission": definition.permission,
            "runtime": {
                "is_enabled": definition.is_enabled,
                **definition.runtime_traits,
            },
            "renderer": definition.renderer,
        }

    def validate_required_arguments(self, tool: JsonDict, arguments: JsonDict) -> None:
        definition = ToolDefinition.from_config(tool)
        self.runtime.validate_required_arguments(definition, arguments)

    def check_permission(self, tool: JsonDict, arguments: JsonDict) -> None:
        definition = ToolDefinition.from_config(tool)
        self.runtime.check_permission(definition, arguments)

    def audit_event(
        self,
        event_type: str,
        definition: ToolDefinition,
        payload: JsonDict,
        session_id: str = "",
        agent_id: str = "",
    ) -> None:
        event = {
            "id": uuid.uuid4().hex,
            "type": event_type,
            "tool_id": definition.id,
            "tool_name": definition.name,
            "session_id": session_id,
            "agent_id": agent_id,
            "payload": self.redact_arguments(payload),
            "created_at": utc_now(),
        }
        append_jsonl(TOOL_AUDIT_FILE, event)
        if self.session_storage and session_id:
            self.session_storage.append_event(
                session_id, event_type, event, agent_id=agent_id
            )

    def redact_arguments(self, arguments: JsonDict | object) -> JsonDict | list[object] | object:
        if isinstance(arguments, dict):
            redacted: JsonDict = {}
            for key, value in arguments.items():
                key_text = str(key)
                if key_text.lower() in {"api_key", "token", "cookie", "password", "secret"}:
                    redacted[key_text] = "***"
                else:
                    redacted[key_text] = self.redact_arguments(value)
            return redacted
        if isinstance(arguments, list):
            return [self.redact_arguments(item) for item in arguments]
        if isinstance(arguments, str):
            stripped = arguments.strip()
            if stripped.startswith("{") or stripped.startswith("["):
                try:
                    parsed = json.loads(arguments)
                except json.JSONDecodeError:
                    return arguments
                return self.redact_arguments(parsed)
            return arguments
        return arguments

    def resolve_workspace_path(
        self, value: object, *, must_exist: bool = False
    ) -> Path:
        return self.runtime.resolve_workspace_path(value, must_exist=must_exist)

    def read_file(self, arguments: JsonDict) -> JsonDict:
        return self.runtime.read_file(arguments)

    def write_file(self, arguments: JsonDict) -> JsonDict:
        return self.runtime.write_file(arguments)

    # def execute_command(self, arguments: JsonDict) -> JsonDict:
    #     return self.runtime.execute_bash(arguments)

    def execute_configured_command(
        self, tool: JsonDict, arguments: JsonDict
    ) -> JsonDict:
        return self.runtime.execute_configured_command(
            ToolDefinition.from_config(tool), arguments
        )
