import re
from dataclasses import dataclass, field

from backend.config import ROOT_DIR
from backend.data_structures import JsonDict
from backend.services.claude_tool_prompts import prompt_for, prompt_source_for

avoidCommands = '`cat`, `head`, `tail`, `sed`, `awk`, `find`, `grep`, or `echo`'


FILE_READ_TOOL_NAME = 'Read'
FILE_WRITE_TOOL_NAME = 'Write'
FILE_EDIT_TOOL_NAME = 'Edit'
GREP_TOOL_NAME = 'Grep'
GLOB_TOOL_NAME = 'Glob'
BASH_TOOL_NAME = 'Bash'
POWERSHELL_TOOL_NAME = 'Powershell'
currentMonthYear = " May 2026 "
MAX_LINES_TO_READ = 2000
MAX_READ_BYTES = 1024 * 1024

BUILTIN_COMMANDS = [
    "builtin:read_file",
    "builtin:write_file",
    "builtin:edit_file",
    "builtin:glob",
    "builtin:grep",
    "builtin:bash",
    "builtin:execute_command",
    "builtin:cmd",
    "builtin:powershell",
    "builtin:web_fetch",
    "builtin:web_search",
    "builtin:todo_write",
]
ALLOWED_BUILTIN_COMMANDS = set(BUILTIN_COMMANDS)
BUILTIN_TOOL_ORDER = {command: index for index, command in enumerate(BUILTIN_COMMANDS)}

DESCRIPTION_BY_TOOL_NAME = {
    "Read": (
        "Reads a file from the local filesystem. You can access any file directly by using this tool."\
        "Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned."\
    ),
    "Write": (
        "Writes a file to the local filesystem." 
    ),
    "Edit": (
        "Performs exact string replacements in files."
    ),
    "Glob": (
        "Fast file pattern matching tool that works with any codebase size. Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\"."\
        "Returns matching file paths sorted by modification time.Use this tool when you need to find files by name patterns."\
        "When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead."
    ),
    "Grep": (
        "A powerful search tool built on ripgrep."\
    ),
    "Bash": (
        "Executes a given Linux bash command and returns its output. The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile (bash or zsh). "
        "IMPORTANT: Avoid using this tool to run ${avoidCommands} commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:"
    ),
    "PowerShell": (
        "Executes a given PowerShell command with optional timeout. On macOS/Linux this requires PowerShell Core (`pwsh`) to be installed; otherwise use the Bash tool. Working directory persists between commands; shell state (variables, functions) does not." \
        "IMPORTANT: This tool is for terminal operations via PowerShell: git, npm, docker, and PS cmdlets. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead."\
    ),
    "WebFetch": (
        "Fetches content from a specified URL and processes it using an AI model."\
    ),
    "WebSearch": (
        "Allows Claude to search the web and use the results to inform responses."\
        "Provides up-to-date information for current events and recent data."\
        "Returns search result information formatted as search result blocks, including links as markdown hyperlinks."\
    ),
}

DESCRIPTION_BY_COMMAND = {
    "builtin:read_file": DESCRIPTION_BY_TOOL_NAME["Read"],
    "builtin:write_file": DESCRIPTION_BY_TOOL_NAME["Write"],
    "builtin:edit_file": DESCRIPTION_BY_TOOL_NAME["Edit"],
    "builtin:glob": DESCRIPTION_BY_TOOL_NAME["Glob"],
    "builtin:grep": DESCRIPTION_BY_TOOL_NAME["Grep"],
    "builtin:bash": DESCRIPTION_BY_TOOL_NAME["Bash"],
    "builtin:execute_command": DESCRIPTION_BY_TOOL_NAME["Bash"],
    "builtin:powershell": DESCRIPTION_BY_TOOL_NAME["PowerShell"],
    "builtin:web_fetch": DESCRIPTION_BY_TOOL_NAME["WebFetch"],
    "builtin:web_search": DESCRIPTION_BY_TOOL_NAME["WebSearch"],
}


def description_for(command_line: str, fallback: str = "", tool_name: str = "") -> str:
    return (
        DESCRIPTION_BY_TOOL_NAME.get(str(tool_name or ""))
        or DESCRIPTION_BY_COMMAND.get(command_line)
        or fallback
        or search_hint_for(command_line)
    )


def string_property(description: str = "") -> JsonDict:
    result: JsonDict = {"type": "string"}
    if description:
        result["description"] = description
    return result


def integer_property(default: int = 0, minimum: int = 0, maximum: int = 9007199254740991, description: str = '') -> JsonDict:
    return {
        "type": "integer",
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "description": description,
    }


def number_property(default: float = 0.0, minimum: float = 0.0, maximum: float = 1000.0, description: str = '') -> JsonDict:
    return {
        "type": "number",
        "default": default,
        "minimum": minimum,
        "maximum": maximum,
        "description": description,
    }


def object_schema(required: list[str] | None = None, properties: JsonDict | None = None) -> JsonDict:
    return {
        "type": "object",
        "required": required or [],
        "properties": properties or {},
    }


def passthrough_object_schema(properties: JsonDict | None = None) -> JsonDict:
    schema = object_schema(properties=properties)
    schema["additionalProperties"] = True
    return schema


def input_schema_for(command_line: str) -> JsonDict:
    if command_line == "builtin:read_file":
        return object_schema(
            properties={
                "path": string_property("The absolute path to the file to read (must be absolute, not relative)."),
                "offset": integer_property(1, 1, MAX_LINES_TO_READ, "The line number to start reading from. Only provide if the file is too large to read at once"),
                "limit": integer_property(9007199254740991, 1, 9007199254740991, "The number of lines to read. Only provide if the file is too large to read at once."),
                "encoding": {"type": "string", "default": "utf-8", "description": "The encoding way"},
            }
        )
    if command_line == "builtin:write_file":
        return object_schema(
            ["content"],
            {
                "path": string_property("The absolute path to the file to write (must be absolute, not relative)."),
                "content": string_property("The content to write to the file"),
                "encoding": {"type": "string", "default": "utf-8", "description": "The encoding way"},
            },
        )
    if command_line == "builtin:edit_file":
        return object_schema(
            ["old_string", "new_string"],
            {
                "file_path": string_property("The absolute path to the file to modify."),
                "path": string_property("Alias for file_path."),
                "old_string": string_property("The text to replace"),
                "new_string": string_property("The text to replace it with (must be different from old_string)"),
                "replace_all": {"type": "boolean", "default": False, "description": "Replace all occurrences of old_string (default false)"},
            },
        )
    if command_line == "builtin:glob":
        return object_schema(
            ["pattern"],
            {
                "pattern": string_property("The glob pattern to match files against."),
                "path": {"type": "string", "default": str(ROOT_DIR), "description":"The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter \"undefined\" or \"null\" - simply omit it for the default behavior. Must be a valid directory path if provided."},
            },
        )
    if command_line == "builtin:grep":
        return object_schema(
            ["pattern"],
            {
                "pattern": {"type": "string", "description":"The regular expression pattern to search for in file contents"},
                "path": {"type": "string", "default": str(ROOT_DIR), "description":"File or directory to search in (rg PATH). Defaults to current working directory."},
                "glob": {"type": "string", "description":"Glob pattern to filter files (e.g. \"*.js\", \"*.{ts,tsx}\") - maps to rg --glob"},
                "type": {"type": "string", "description":"File type to search (rg --type). Common types: js, py, rust, go, java, etc. More efficient than include for standard file types."},
                "output_mode": {"type": "string", "enum": ["content", "files_with_matches", "count"], "description":"Output mode: \"content\" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), \"files_with_matches\" shows file paths (supports head_limit), \"count\" shows match counts (supports head_limit). Defaults to \"files_with_matches\"."},
                "-n": {"type": "boolean", "default": True, "description":"Show line numbers in output (rg -n). Requires output_mode: \"content\", ignored otherwise. Defaults to true."},
                "-B": {"type": "integer", "description":"Number of lines to show before each match (rg -B). Requires output_mode: \"content\", ignored otherwise."},
                "-A": {"type": "integer", "description":"Number of lines to show after each match (rg -A). Requires output_mode: \"content\", ignored otherwise."},
                "-C": {"type": "integer", "description":"Alias for context."},
                "head_limit": {"type": "integer", "description":"Limit output to first N lines/entries, equivalent to \"| head -N\". Works across all output modes: content (limits output lines), files_with_matches (limits file paths), count (limits count entries). Defaults to 250 when unspecified. Pass 0 for unlimited (use sparingly — large result sets waste context)."},
                "offset": integer_property(0, 0, 100000, "Skip first N lines/entries before applying head_limit, equivalent to \"| tail -n +N | head -N\". Works across all output modes. Defaults to 0."),
                "context": integer_property(0, 0, 20, "Number of lines to show before and after each match (rg -C). Requires output_mode: \"content\", ignored otherwise."),
                "multiline": {"type": "boolean", "default": False, "description":"Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false."},
            },
        )
    if command_line in {"builtin:bash", "builtin:execute_command"}:
        return object_schema(
            [],
            {
                "command": string_property("The command to execute"),
                "timeout": integer_property(30, 1, 120, "Optional timeout in milliseconds (max 600000)"),
            },
        )
    if command_line == "builtin:cmd":
        return object_schema(
            [],
            {
                "command": string_property("Command to execute. Uses cmd.exe on Windows and the default POSIX shell on macOS/Linux."),
                "command_line": string_property("Alias for command."),
                "cwd": {"type": "string", "default": str(ROOT_DIR), "description": "The current working directory"},
                "timeout": integer_property(30, 1, 120, "The command execution timeout"),
            },
        )
    if command_line == "builtin:powershell":
        return object_schema(
            [],
            {
                "command": string_property("PowerShell command to execute. Requires PowerShell Core (`pwsh`) on macOS/Linux."),
                "command_line": string_property("Alias for command."),
                "cwd": {"type": "string", "default": str(ROOT_DIR), "description": "The current working directory"},
                "timeout": integer_property(30, 1, 120, "The command execution timeout"),
            },
        )
    if command_line == "builtin:web_fetch":
        return object_schema(
            ["url", "prompt"],
            {
                "url": string_property("The URL to fetch content from"),
                "prompt": string_property("The prompt to run on the fetched content"),
                "timeout": integer_property(20, 1, 60, "timeout"),
                "max_bytes": integer_property(100000, 1024, 1000000, "max_bytes"),
            },
        )
    if command_line == "builtin:web_search":
        return object_schema(
            ["query"],
            {
                "query": string_property("The search query to use"),
                "allowed_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Only include search results from these domains",
                },
                "blocked_domains": {
                    "type": "array",
                    "items": {"type": "string"},
                    "default": [],
                    "description": "Never include search results from these domains",
                },
                "max_results": integer_property(5, 1, 10, "Maximum number of search results"),
            },
        )
    template_fields = sorted(
        {
            match.group(1)
            for match in re.finditer(r"{([A-Za-z_][A-Za-z0-9_]*)}", command_line)
            if match.group(1) not in {"cwd", "timeout"}
        }
    )
    properties: JsonDict = {
        "cwd": {"type": "string", "default": str(ROOT_DIR)},
        "timeout": integer_property(30, 1, 120, "Command execution timeout."),
        "args": {
            "type": "object",
            "additionalProperties": True,
            "description": "Named arguments for command templates. Values are shell-quoted by the runtime.",
        },
    }
    for field_name in template_fields:
        properties[field_name] = string_property(f"Template parameter {{{field_name}}}.")
    return object_schema(
        required=[field_name for field_name in template_fields if field_name != "log_path"],
        properties=properties,
    )


def permission_for(command_line: str) -> JsonDict:
    permissions = {
        "builtin:read_file": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:write_file": {"mode": "allow", "risk": "write_workspace", "workspace_scoped": True},
        "builtin:edit_file": {"mode": "allow", "risk": "write_workspace", "workspace_scoped": True},
        "builtin:glob": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:grep": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:bash": {"mode": "guarded", "risk": "command_execution", "workspace_scoped": True},
        "builtin:execute_command": {"mode": "guarded", "risk": "command_execution", "workspace_scoped": True},
        "builtin:cmd": {"mode": "guarded", "risk": "command_execution", "workspace_scoped": True},
        "builtin:powershell": {"mode": "guarded", "risk": "command_execution", "workspace_scoped": True},
        "builtin:web_fetch": {"mode": "allow", "risk": "network_read", "workspace_scoped": False},
        "builtin:web_search": {"mode": "allow", "risk": "network_read", "workspace_scoped": False},
    }
    if command_line in permissions:
        return permissions[command_line]
    return {"mode": "guarded", "risk": "configured_command", "workspace_scoped": True}


def runtime_traits_for(command_line: str) -> JsonDict:
    traits = {
        "builtin:read_file": {"is_concurrency_safe": True, "is_read_only": True, "is_destructive": False, "writes_files": False},
        "builtin:write_file": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": True},
        "builtin:edit_file": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": True},
        "builtin:glob": {"is_concurrency_safe": True, "is_read_only": True, "is_destructive": False, "writes_files": False},
        "builtin:grep": {"is_concurrency_safe": True, "is_read_only": True, "is_destructive": False, "writes_files": False},
        "builtin:bash": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": False},
        "builtin:execute_command": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": False},
        "builtin:cmd": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": False},
        "builtin:powershell": {"is_concurrency_safe": False, "is_read_only": False, "is_destructive": False, "writes_files": False},
        "builtin:web_fetch": {"is_concurrency_safe": True, "is_read_only": True, "is_destructive": False, "writes_files": False},
        "builtin:web_search": {"is_concurrency_safe": True, "is_read_only": True, "is_destructive": False, "writes_files": False},
    }
    return traits.get(
        command_line,
        {
            "is_concurrency_safe": False,
            "is_read_only": False,
            "is_destructive": False,
            "writes_files": False,
        },
    )


def search_hint_for(command_line: str) -> str:
    hints = {
        "builtin:read_file": "Reads a file from the local filesystem.",
        "builtin:write_file": "Writes a file to the local filesystem.",
        "builtin:edit_file": "Performs exact string replacements in files.",
        "builtin:glob": "Fast file pattern matching tool that works with any codebase size. ",
        "builtin:grep": "A powerful search tool built on ripgrep.",
        "builtin:bash": "Executes a given bash command and returns its output.",
        "builtin:execute_command": "Executes a guarded shell command and returns its output.",
        "builtin:cmd": "Executes a command and returns its output. Uses cmd.exe on Windows and the default POSIX shell on macOS/Linux.",
        "builtin:powershell": "Executes a PowerShell command. Requires pwsh/powershell on macOS/Linux.",
        "builtin:web_fetch": "Fetches content from a specified URL and processes it using an AI model.",
        "builtin:web_search": "Allows Agent to search the web and use the results to inform responses.",
    }
    if command_line in hints:
        return hints[command_line]
    if command_line in BUILTIN_TOOL_ORDER:
        return "Claude-style platform tool implemented in CodeX."
    return "configured command external tool"


def summary_fields_for(command_line: str) -> list[str]:
    fields = {
        "builtin:read_file": ["path", "size", "sha256", "preview_bytes", "start_line", "lines_read"],
        "builtin:write_file": ["path", "bytes_written"],
        "builtin:edit_file": ["path", "replacements", "bytes_written"],
        "builtin:glob": ["pattern", "path", "numFiles", "truncated"],
        "builtin:grep": ["pattern", "path", "mode", "match_count", "file_count"],
        "builtin:bash": ["command_line", "cwd", "exit_code", "timed_out"],
        "builtin:execute_command": ["command_line", "cwd", "exit_code", "timed_out"],
        "builtin:cmd": ["command_line", "cwd", "exit_code", "timed_out"],
        "builtin:powershell": ["command_line", "cwd", "exit_code", "timed_out"],
        "builtin:web_fetch": ["url", "status", "code", "bytes", "content_type"],
        "builtin:web_search": ["query", "status", "result_count", "source"],
    }
    return fields.get(command_line, ["command_line", "cwd", "exit_code"])


@dataclass(frozen=True)
class ToolDefinition:
    """Declarative, model-facing description of a tool."""

    id: str
    name: str
    command_line: str
    sandbox_command_line: str = ""
    description: str = ""
    prompt: str = ""
    prompt_source: str = ""
    is_builtin: bool = False
    created_at: str = ""
    updated_at: str = ""
    input_schema: JsonDict = field(default_factory=dict)
    permission: JsonDict = field(default_factory=dict)
    runtime_traits: JsonDict = field(default_factory=dict)
    renderer: JsonDict = field(default_factory=dict)
    search_hint: str = ""
    is_enabled: bool = True

    @classmethod
    def from_config(cls, tool: JsonDict) -> "ToolDefinition":
        command_line = str(tool.get("command_line") or "").strip()
        sandbox_command_line = str(tool.get("sandbox_command_line") or "").strip()
        name = str(tool.get("name") or "").strip()
        raw_description = str(tool.get("description") or "").strip()
        raw_prompt = str(tool.get("prompt") or "").strip()
        traits = runtime_traits_for(command_line)
        return cls(
            id=str(tool.get("id") or "").strip(),
            name=name,
            command_line=command_line,
            sandbox_command_line=sandbox_command_line,
            description=description_for(command_line, raw_description, name),
            prompt=prompt_for(command_line, raw_prompt, name),
            prompt_source=prompt_source_for(command_line, name),
            is_builtin=bool(tool.get("is_builtin")),
            created_at=str(tool.get("created_at") or ""),
            updated_at=str(tool.get("updated_at") or ""),
            input_schema=normalize_definition_input_schema(
                dict(tool.get("input_schema"))
                if isinstance(tool.get("input_schema"), dict)
                and tool.get("input_schema")
                else input_schema_for(command_line),
                command_line=command_line,
                sandbox_command_line=sandbox_command_line,
            ),
            permission=permission_for(command_line),
            runtime_traits=traits,
            renderer={
                "kind": "builtin" if command_line.startswith("builtin:") else "configured",
                "summary_fields": summary_fields_for(command_line),
            },
            search_hint=search_hint_for(command_line),
            is_enabled=bool(tool.get("is_enabled", True)),
        )

    def to_dict(self) -> JsonDict:
        return {
            "id": self.id,
            "name": self.name,
            "command_line": self.command_line,
            "sandbox_command_line": self.sandbox_command_line,
            "description": self.description,
            "input_schema": self.input_schema,
            "prompt": self.prompt,
            "prompt_source": self.prompt_source,
            "is_builtin": self.is_builtin,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "input_schema": self.input_schema,
            "permission": self.permission,
            "runtime": {
                "is_enabled": self.is_enabled,
                **self.runtime_traits,
            },
            "renderer": self.renderer,
            "search_hint": self.search_hint,
        }

    def matches(self, tool_key: str) -> bool:
        normalized = str(tool_key or "").strip().lower()
        if not normalized:
            return False
        return normalized in {
            self.id.lower(),
            self.name.lower(),
            self.command_line.lower(),
        }


class ToolDefinitionRegistry:
    def __init__(self, tool_configs: dict[str, JsonDict]) -> None:
        self.tool_configs = tool_configs

    def list_definitions(self) -> list[ToolDefinition]:
        return sorted(
            (
                ToolDefinition.from_config(tool)
                for tool in self.tool_configs.values()
                if self.is_allowed_tool(tool)
            ),
            key=lambda item: (
                0 if item.is_builtin else 1,
                BUILTIN_TOOL_ORDER.get(item.command_line, 99),
                item.created_at,
                item.name,
            ),
        )

    def is_allowed_tool(self, tool: JsonDict) -> bool:
        command_line = str(tool.get("command_line") or "").strip()
        if command_line.startswith("builtin:"):
            return command_line in ALLOWED_BUILTIN_COMMANDS
        return bool(command_line)

    def get_definition(self, tool_key: str) -> ToolDefinition | None:
        for definition in self.list_definitions():
            if definition.matches(tool_key):
                return definition
        return None

    def describe_tool(self, tool: JsonDict) -> JsonDict:
        return ToolDefinition.from_config(tool).to_dict() 


def normalize_definition_input_schema(
    input_schema: JsonDict,
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
