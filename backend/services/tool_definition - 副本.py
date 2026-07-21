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
        "Usage:"\
        " - The file_path parameter must be an absolute path, not a relative path"
        " - By default, it reads up to ${MAX_LINES_TO_READ} lines starting from the beginning of the file."
        " - You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters"
        " - When you already know which part of the file you need, only read that part. This can be important for larger files."
        " - Results are returned using cat -n format, with line numbers starting at 1."
        " - You can optionally specify a line offset and limit (especially handy for long files), but it's recommended to read the whole file by not providing these parameters."
        " - This tool allows Agent to read images (eg PNG, JPG, etc). When reading an image file the contents are presented visually as Claude Code is a multimodal LLM."
    ),
    "Write": (
        "Writes a file to the local filesystem." 
        "Usage:" 
        " - This tool will overwrite the existing file if there is one at the provided path." 
        " - If this is an existing file, you MUST use the ${FILE_READ_TOOL_NAME} tool first to read the file's contents. This tool will fail if you did not read the file first." \
        " - Prefer the Edit tool for modifying existing files \u2014 it only sends the diff. Only use this tool to create new files or for complete rewrites." \
        " - NEVER create documentation files (*.md) or README files unless explicitly requested by the User." \
        " - Only use emojis if the user explicitly requests it. Avoid writing emojis to files unless asked."
    ),
    "Edit": (
        "Performs exact string replacements in files."
        "Usage:" \
        " - When editing text from Read tool output, ensure you preserve the exact indentation (tabs/spaces) as it appears AFTER the line number prefix. Everything after that is the actual file content to match. Never include any part of the line number prefix in the old_string or new_string." \
        " - ALWAYS prefer editing existing files in the codebase. NEVER write new files unless explicitly required." \
        " - Only use emojis if the user explicitly requests it. Avoid adding emojis to files unless asked." \
        " - The edit will FAIL if `old_string` is not unique in the file. Either provide a larger string with more surrounding context to make it unique or use `replace_all` to change every instance of `old_string`." \
        " - Use `replace_all` for replacing and renaming strings across the file. This parameter is useful if you want to rename a variable for instance."\
        " - You must use your `${FILE_READ_TOOL_NAME}` tool at least once in the conversation before editing. This tool will error if you attempt an edit without reading the file."
    ),
    "Glob": (
        "Fast file pattern matching tool that works with any codebase size. Supports glob patterns like \"**/*.js\" or \"src/**/*.ts\"."\
        "Returns matching file paths sorted by modification time.Use this tool when you need to find files by name patterns."\
        "When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead."
    ),
    "Grep": (
        "A powerful search tool built on ripgrep."\
        "Usage:"\
        " - ALWAYS use ${GREP_TOOL_NAME} for search tasks. NEVER invoke `grep` or `rg` as a ${BASH_TOOL_NAME} command. The ${GREP_TOOL_NAME} tool has been optimized for correct permissions and access."\
        " - Supports full regex syntax (e.g., \"log.*Error\", \"function\\s+\\w+\")"\
        " - Filter files with glob parameter (e.g., \"*.js\", \"**/*.tsx\") or type parameter (e.g., \"js\", \"py\", \"rust\")"\
        " - Output modes: \"content\" shows matching lines, \"files_with_matches\" shows only file paths (default), \"count\" shows match counts"\
        " - Pattern syntax: Uses ripgrep (not grep) - literal braces need escaping (use `interface\\{\\}` to find `interface{}` in Go code)"\
        " - Multiline matching: By default patterns match within single lines only. For cross-line patterns like `struct \\{[\\s\\S]*?field`, use `multiline: true`"
    ),
    "Bash": (
        "Executes a given bash command and returns its output. The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile (bash or zsh). "
        "IMPORTANT: Avoid using this tool to run ${avoidCommands} commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:"
         "Usage notes:"\
        "   - File search: Use ${GLOB_TOOL_NAME} (NOT find or ls)"\
        "   - Content search: Use ${GREP_TOOL_NAME} (NOT grep or rg)"\
        "   - Communication: Output text directly (NOT echo/printf)"\
        "   - Read files: Use ${FILE_READ_TOOL_NAME} (NOT cat/head/tail)"\
        "   - Edit files: Use ${FILE_EDIT_TOOL_NAME} (NOT sed/awk)"\
        "   - Write files: Use ${FILE_WRITE_TOOL_NAME} (NOT echo >/cat <<EOF)"\
        "While the ${BASH_TOOL_NAME} tool can do similar things, it’s better to use the built-in tools as they provide a better user experience and make it easier to review tool calls and give permission."\
        "If your command will create new directories or files, first use this tool to run `ls` to verify the parent directory exists and is the correct location."\
        "Always quote file paths that contain spaces with double quotes in your command (e.g., cd \"path with spaces/file.txt\")"\
        "Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it."\
        "You may specify an optional timeout in milliseconds (up to 600000ms / 10 minutes). By default, your command will timeout after 120000ms (2 minutes)."\
        "Try to maintain your current working directory throughout the session by using absolute paths and avoiding usage of `cd`. You may use `cd` if the User explicitly requests it."\
        "Do not sleep between commands that can run immediately — just run them."\
        "If the commands are independent and can run in parallel, make multiple ${BASH_TOOL_NAME} tool calls in a single message. "\
        "If the commands depend on each other and must run sequentially, use a single ${BASH_TOOL_NAME} call with '&&' to chain them together."\
        "Use ';' only when you need to run commands sequentially but don't care if earlier commands fail."\
        "DO NOT use newlines to separate commands (newlines are ok in quoted strings)."
    ),
    "PowerShell": (
        "Executes a given PowerShell command with optional timeout. Working directory persists between commands; shell state (variables, functions) does not." \
        "IMPORTANT: This tool is for terminal operations via PowerShell: git, npm, docker, and PS cmdlets. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead."\
        "Before executing the command, please follow these steps:"\
        "1. Directory Verification:"\
        "   - If the command will create new directories or files, first use `Get-ChildItem` (or `ls`) to verify the parent directory exists and is the correct location."\
        "2. Command Execution:"\
        "   - Always quote file paths that contain spaces with double quotes"\
        "   - Capture the output of the command."\
        "PowerShell Syntax Notes:"\
        "   - Variables use $ prefix: $myVar = 'value'"\
        "   - Escape character is backtick (`), not backslash"\
        "   - Use Verb-Noun cmdlet naming: Get-ChildItem, Set-Location, New-Item, Remove-Item"\
        "   - Common aliases: ls (Get-ChildItem), cd (Set-Location), cat (Get-Content), rm (Remove-Item)"\
        "   - Pipe operator | works similarly to bash but passes objects, not text"\
        "   - Use Select-Object, Where-Object, ForEach-Object for filtering and transformation"\
        "   - String interpolation: 'Hello $name' or 'Hello $($obj.Property)'"\
        "   - Registry access uses PSDrive prefixes: `HKLM:\\SOFTWARE\\...`, `HKCU:\\...` — NOT raw `HKEY_LOCAL_MACHINE\\...`"\
        "   - Environment variables: read with `$env:NAME`, set with `$env:NAME = 'value'` (NOT `Set-Variable` or bash `export`)"\
        "   - Call native exe with spaces in path via call operator: `& 'C:\\Program Files\\App\\app.exe' arg1 arg2`"\
        "Interactive and blocking commands (will hang — this tool runs with -NonInteractive):"\
        "   - NEVER use `Read-Host`, `Get-Credential`, `Out-GridView`, `$Host.UI.PromptForChoice`, or `pause`"\
        "   - Destructive cmdlets (`Remove-Item`, `Stop-Process`, `Clear-Content`, etc.) may prompt for confirmation. Add `-Confirm:$false` when you intend the action to proceed. Use `-Force` for read-only/hidden items."\
        "   - Never use `git rebase -i`, `git add -i`, or other commands that open an interactive editor"
        "Usage notes:"\
        "   - The command argument is required."\
        "   - You can specify an optional timeout in milliseconds (up to ${getMaxTimeoutMs()}ms / ${getMaxTimeoutMs() / 60000} minutes). If not specified, commands will timeout after ${getDefaultTimeoutMs()}ms (${getDefaultTimeoutMs() / 60000} minutes)."\
        "   - It is very helpful if you write a clear, concise description of what this command does."\
        "   - If the output exceeds ${getMaxOutputLength()} characters, output will be truncated before being returned to you."\
        "   - Avoid using PowerShell to run commands that have dedicated tools, unless explicitly instructed:"\
        "   - File search: Use ${GLOB_TOOL_NAME} (NOT Get-ChildItem -Recurse)"\
        "   - Content search: Use ${GREP_TOOL_NAME} (NOT Select-String)"\
        "   - Read files: Use ${FILE_READ_TOOL_NAME} (NOT Get-Content)"\
        "   - Edit files: Use ${FILE_EDIT_TOOL_NAME}"\
        "   - Write files: Use ${FILE_WRITE_TOOL_NAME} (NOT Set-Content/Out-File)"\
        "   - Communication: Output text directly (NOT Write-Output/Write-Host)"\
        "   - When issuing multiple commands:"\
        "   - If the commands are independent and can run in parallel, make multiple ${POWERSHELL_TOOL_NAME} tool calls in a single message."\
        "   - If the commands depend on each other and must run sequentially, chain them in a single ${POWERSHELL_TOOL_NAME} call (see edition-specific chaining syntax above)."\
        "   - Use `;` only when you need to run commands sequentially but don't care if earlier commands fail."\
        "   - DO NOT use newlines to separate commands (newlines are ok in quoted strings and here-strings)"\
        "   - Avoid unnecessary `Start-Sleep` commands:"\
        "   - Do not sleep between commands that can run immediately — just run them."\
        "   - If your command is long running and you would like to be notified when it finishes — simply run your command using `run_in_background`. There is no need to sleep in this case."\
        "   - Do not retry failing commands in a sleep loop — diagnose the root cause or consider an alternative approach."\
        "   - If waiting for a background task you started with `run_in_background`, you will be notified when it completes — do not poll."\
        "   - If you must poll an external process, use a check command rather than sleeping first."\
        "   - If you must sleep, keep the duration short (1-5 seconds) to avoid blocking the user."\
        "   - You can use the `run_in_background` parameter to run the command in the background. Only use this if you don't need the result immediately and are OK being notified when the command completes later. You do not need to check the output right away - you'll be notified when it finishes."
    ),
    "WebFetch": (
        "Fetches content from a specified URL and processes it using an AI model."\
        "Takes a URL and a prompt as input."\
        "Fetches the URL content, converts HTML to markdown."\
        "Processes the content with the prompt using a small, fast model."\
        "Returns the model's response about the content."\
        "Use this tool when you need to retrieve and analyze web content."
    ),
    "WebSearch": (
        "Allows Claude to search the web and use the results to inform responses."\
        "Provides up-to-date information for current events and recent data."\
        "Returns search result information formatted as search result blocks, including links as markdown hyperlinks."\
        "Use this tool for accessing information beyond Claude's knowledge cutoff."\
        "Searches are performed automatically within a single API call."\
        "CRITICAL REQUIREMENT - You MUST follow this:."\
        "  - After answering the user's question, you MUST include a \"Sources:\" section at the end of your response."\
        "  - In the Sources section, list all relevant URLs from the search results as markdown hyperlinks: [Title](URL)."\
        "  - This is MANDATORY - never skip including sources in your response."\
        "  - Example format:."\
        "    [Your answer here]"\
        "    Sources:."\
        "    - [Source Title 1](https://example.com/1)"\
        "    - [Source Title 2](https://example.com/2)"\
        "Usage notes:"\
        "  - Domain filtering is supported to include or block specific websites."\
        "  - Web search is only available in the US."\
        "IMPORTANT - Use the correct year in search queries:"\
        "  - The current month is ${currentMonthYear}. You MUST use this year when searching for recent information, documentation, or current events."\
        "  - Example: If the user asks for \"latest React docs\", search for \"React documentation\" with the current year, NOT last year."
    ),
}

DESCRIPTION_BY_COMMAND = {
    "builtin:read_file": DESCRIPTION_BY_TOOL_NAME["Read"],
    "builtin:write_file": DESCRIPTION_BY_TOOL_NAME["Write"],
    "builtin:edit_file": DESCRIPTION_BY_TOOL_NAME["Edit"],
    "builtin:glob": DESCRIPTION_BY_TOOL_NAME["Glob"],
    "builtin:grep": DESCRIPTION_BY_TOOL_NAME["Grep"],
    "builtin:bash": DESCRIPTION_BY_TOOL_NAME["Bash"],
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
    if command_line == "builtin:bash":
        return object_schema(
            [],
            {
                "command": string_property("The command to execute"),
                "timeout": integer_property(30, 1, 120, "Optional timeout in milliseconds (max 600000)"),
            },
        )
    if command_line == "builtin:powershell":
        return object_schema(
            [],
            {
                "command": string_property("PowerShell command to execute."),
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
    return object_schema(
        properties={
            "cwd": {"type": "string", "default": str(ROOT_DIR)},
            "timeout": integer_property(30, 1, 120, "Null"),
        }
    )


def permission_for(command_line: str) -> JsonDict:
    permissions = {
        "builtin:read_file": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:write_file": {"mode": "allow", "risk": "write_workspace", "workspace_scoped": True},
        "builtin:edit_file": {"mode": "allow", "risk": "write_workspace", "workspace_scoped": True},
        "builtin:glob": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:grep": {"mode": "allow", "risk": "read_only", "workspace_scoped": True},
        "builtin:bash": {"mode": "guarded", "risk": "command_execution", "workspace_scoped": True},
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
        "builtin:powershell": "Executes a given PowerShell command with optional timeout. ",
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
        name = str(tool.get("name") or "").strip()
        raw_description = str(tool.get("description") or "").strip()
        raw_prompt = str(tool.get("prompt") or "").strip()
        traits = runtime_traits_for(command_line)
        return cls(
            id=str(tool.get("id") or "").strip(),
            name=name,
            command_line=command_line,
            description=description_for(command_line, raw_description, name),
            prompt=prompt_for(command_line, raw_prompt, name),
            prompt_source=prompt_source_for(command_line, name),
            is_builtin=bool(tool.get("is_builtin")),
            created_at=str(tool.get("created_at") or ""),
            updated_at=str(tool.get("updated_at") or ""),
            input_schema=input_schema_for(command_line),
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
            "description": self.description,
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
        return False

    def get_definition(self, tool_key: str) -> ToolDefinition | None:
        for definition in self.list_definitions():
            if definition.matches(tool_key):
                return definition
        return None

    def describe_tool(self, tool: JsonDict) -> JsonDict:
        return ToolDefinition.from_config(tool).to_dict() 
