import json

from backend.config import RUNTIME_DIR, TOOLS_CONFIG_FILE
from backend.data_structures import build_tool_config_record
from backend.utils import utc_now


ALLOWED_BUILTIN_COMMANDS = {
    "builtin:read_file",
    "builtin:write_file",
    "builtin:edit_file",
    "builtin:glob",
    "builtin:grep",
    "builtin:execute_command",
    "builtin:cmd",
    "builtin:powershell",
    "builtin:web_fetch",
    "builtin:web_search",
}

CLAUDE_STYLE_TOOL_RECORDS = [
    ("read", "Read", "builtin:read_file", "Reads a file from the local filesystem. You can access any file directly by using this tool."),
    ("write", "Write", "builtin:write_file", "Writes a file to the local filesystem."),
    ("edit", "Edit", "builtin:edit_file", "Performs exact string replacements in files."),
    ("glob", "Glob", "builtin:glob", "Fast file pattern matching tool that works with any codebase size."),
    ("grep", "Grep", "builtin:grep", "Search file contents by regular expression."),
    ("bash", "Bash", "builtin:execute_command", "Executes a given bash command and returns its output."),
    ("powershell", "PowerShell", "builtin:powershell", "Executes a PowerShell command. Requires pwsh/powershell on macOS/Linux."),
    ("web-fetch", "WebFetch", "builtin:web_fetch", "Fetches content from a specified URL and processes it using an AI model."),
    ("web-search", "WebSearch", "builtin:web_search", "Allows Agent to search the web and use the results to inform responses."),
]


def default_tool_records() -> dict[str, dict[str, object]]:
    now = utc_now()
    records = {}
    for tool_id, name, command_line, description in CLAUDE_STYLE_TOOL_RECORDS:
        records[tool_id] = build_tool_config_record(
            tool_id=tool_id,
            name=name,
            command_line=command_line,
            description=description,
            is_builtin=True,
            created_at=now,
            updated_at=now,
        )
    return records


def normalize_tool_config(tool_id: str, data: dict[str, object]) -> dict[str, object]:
    now = utc_now()
    return build_tool_config_record(
        tool_id=str(data.get("id") or tool_id),
        name=str(data.get("name") or tool_id).strip(),
        command_line=str(data.get("command_line") or "").strip(),
        sandbox_command_line=str(data.get("sandbox_command_line") or "").strip(),
        description=str(data.get("description") or "").strip(),
        input_schema=(
            data.get("input_schema")
            if isinstance(data.get("input_schema"), dict)
            else {}
        ),
        is_builtin=bool(data.get("is_builtin")),
        created_at=str(data.get("created_at") or now),
        updated_at=str(data.get("updated_at") or now),
    )


def load_tool_configs() -> dict[str, dict[str, object]]:
    if not TOOLS_CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(TOOLS_CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {
        str(tool_id): normalize_tool_config(str(tool_id), tool)
        for tool_id, tool in data.items()
        if isinstance(tool, dict)
    }


def save_tool_configs(tool_configs: dict[str, dict[str, object]]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = TOOLS_CONFIG_FILE.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(tool_configs, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temp_file.replace(TOOLS_CONFIG_FILE)


def ensure_default_tools(tool_configs: dict[str, dict[str, object]]) -> None:
    changed = False
    default_records = default_tool_records()
    for tool_id, tool in list(tool_configs.items()):
        command_line = str(tool.get("command_line") or "")
        if bool(tool.get("is_builtin")) and command_line.startswith("builtin:") and (
            command_line not in ALLOWED_BUILTIN_COMMANDS or tool_id not in default_records
        ):
            del tool_configs[tool_id]
            changed = True
    for tool_id, record in default_records.items():
        if tool_id not in tool_configs:
            tool_configs[tool_id] = record
            changed = True
        else:
            tool_configs[tool_id]["is_builtin"] = True
            tool_configs[tool_id]["command_line"] = record["command_line"]
    if changed:
        save_tool_configs(tool_configs)
