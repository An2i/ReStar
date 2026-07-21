"""FastAPI route modules."""

[
    {
        "type": "function",
        "function": {
            "name": "Read",
            "description": "Reads a file from the local filesystem. You can access any file directly by using this tool.Assume this tool is able to read all files on the machine. If the User provides a path to a file assume that path is valid. It is okay to read a file that does not exist; an error will be returned.",
            "parameters": {
                "type": "object",
                "required": [],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to read (must be absolute, not relative).",
                    },
                    "offset": {
                        "type": "integer",
                        "default": 1,
                        "minimum": 1,
                        "maximum": 2000,
                        "description": "The line number to start reading from. Only provide if the file is too large to read at once",
                    },
                    "limit": {
                        "type": "integer",
                        "default": 9007199254740991,
                        "minimum": 1,
                        "maximum": 9007199254740991,
                        "description": "The number of lines to read. Only provide if the file is too large to read at once.",
                    },
                    "encoding": {
                        "type": "string",
                        "default": "utf-8",
                        "description": "The encoding way",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Write",
            "description": "Writes a file to the local filesystem.",
            "parameters": {
                "type": "object",
                "required": ["content"],
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "The absolute path to the file to write (must be absolute, not relative).",
                    },
                    "content": {
                        "type": "string",
                        "description": "The content to write to the file",
                    },
                    "encoding": {
                        "type": "string",
                        "default": "utf-8",
                        "description": "The encoding way",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Edit",
            "description": "Performs exact string replacements in files.",
            "parameters": {
                "type": "object",
                "required": ["old_string", "new_string"],
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "The absolute path to the file to modify.",
                    },
                    "path": {"type": "string", "description": "Alias for file_path."},
                    "old_string": {
                        "type": "string",
                        "description": "The text to replace",
                    },
                    "new_string": {
                        "type": "string",
                        "description": "The text to replace it with (must be different from old_string)",
                    },
                    "replace_all": {
                        "type": "boolean",
                        "default": False,
                        "description": "Replace all occurrences of old_string (default false)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Glob",
            "description": 'Fast file pattern matching tool that works with any codebase size. Supports glob patterns like "**/*.js" or "src/**/*.ts".Returns matching file paths sorted by modification time.Use this tool when you need to find files by name patterns.When you are doing an open ended search that may require multiple rounds of globbing and grepping, use the Agent tool instead.',
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The glob pattern to match files against.",
                    },
                    "path": {
                        "type": "string",
                        "default": ".",
                        "description": 'The directory to search in. If not specified, the current working directory will be used. IMPORTANT: Omit this field to use the default directory. DO NOT enter "undefined" or "null" - simply omit it for the default behavior. Must be a valid directory path if provided.',
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Grep",
            "description": "A powerful search tool built on ripgrep.",
            "parameters": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "The regular expression pattern to search for in file contents",
                    },
                    "path": {
                        "type": "string",
                        "default": ".",
                        "description": "File or directory to search in (rg PATH). Defaults to current working directory.",
                    },
                    "glob": {
                        "type": "string",
                        "description": 'Glob pattern to filter files (e.g. "*.js", "*.{ts,tsx}") - maps to rg --glob',
                    },
                    "type": {
                        "type": "string",
                        "description": "File type to search (rg --type). Common types: js, py, rust, go, java, etc. More efficient than include for standard file types.",
                    },
                    "output_mode": {
                        "type": "string",
                        "enum": ["content", "files_with_matches", "count"],
                        "description": 'Output mode: "content" shows matching lines (supports -A/-B/-C context, -n line numbers, head_limit), "files_with_matches" shows file paths (supports head_limit), "count" shows match counts (supports head_limit). Defaults to "files_with_matches".',
                    },
                    "-n": {
                        "type": "boolean",
                        "default": True,
                        "description": 'Show line numbers in output (rg -n). Requires output_mode: "content", ignored otherwise. Defaults to true.',
                    },
                    "-B": {
                        "type": "integer",
                        "description": 'Number of lines to show before each match (rg -B). Requires output_mode: "content", ignored otherwise.',
                    },
                    "-A": {
                        "type": "integer",
                        "description": 'Number of lines to show after each match (rg -A). Requires output_mode: "content", ignored otherwise.',
                    },
                    "-C": {"type": "integer", "description": "Alias for context."},
                    "head_limit": {
                        "type": "integer",
                        "description": 'Limit output to first N lines/entries, equivalent to "| head -N". Works across all output modes: content (limits output lines), files_with_matches (limits file paths), count (limits count entries). Defaults to 250 when unspecified. Pass 0 for unlimited (use sparingly — large result sets waste context).',
                    },
                    "offset": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 100000,
                        "description": 'Skip first N lines/entries before applying head_limit, equivalent to "| tail -n +N | head -N". Works across all output modes. Defaults to 0.',
                    },
                    "context": {
                        "type": "integer",
                        "default": 0,
                        "minimum": 0,
                        "maximum": 20,
                        "description": 'Number of lines to show before and after each match (rg -C). Requires output_mode: "content", ignored otherwise.',
                    },
                    "multiline": {
                        "type": "boolean",
                        "default": False,
                        "description": "Enable multiline mode where . matches newlines and patterns can span lines (rg -U --multiline-dotall). Default: false.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "Bash",
            "description": "Executes a given Linux bash command and returns its output. The working directory persists between commands, but shell state does not. The shell environment is initialized from the user's profile (bash or zsh). IMPORTANT: Avoid using this tool to run ${avoidCommands} commands, unless explicitly instructed or after you have verified that a dedicated tool cannot accomplish your task. Instead, use the appropriate dedicated tool as this will provide a much better experience for the user:",
            "parameters": {
                "type": "object",
                "required": [],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "The command to execute",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 120,
                        "description": "Optional timeout in milliseconds (max 600000)",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "PowerShell",
            "description": "Executes a given PowerShell command with optional timeout in the Windows OS. Working directory persists between commands; shell state (variables, functions) does not.IMPORTANT: This tool is for terminal operations via PowerShell: git, npm, docker, and PS cmdlets. DO NOT use it for file operations (reading, writing, editing, searching, finding files) - use the specialized tools for this instead.",
            "parameters": {
                "type": "object",
                "required": [],
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "PowerShell command to execute.",
                    },
                    "command_line": {
                        "type": "string",
                        "description": "Alias for command.",
                    },
                    "cwd": {
                        "type": "string",
                        "default": ".",
                        "description": "The current working directory",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 120,
                        "description": "The command execution timeout",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebFetch",
            "description": "Fetches content from a specified URL and processes it using an AI model.",
            "parameters": {
                "type": "object",
                "required": ["url", "prompt"],
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "The URL to fetch content from",
                    },
                    "prompt": {
                        "type": "string",
                        "description": "The prompt to run on the fetched content",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 20,
                        "minimum": 1,
                        "maximum": 60,
                        "description": "timeout",
                    },
                    "max_bytes": {
                        "type": "integer",
                        "default": 100000,
                        "minimum": 1024,
                        "maximum": 1000000,
                        "description": "max_bytes",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "WebSearch",
            "description": "Allows Claude to search the web and use the results to inform responses.Provides up-to-date information for current events and recent data.Returns search result information formatted as search result blocks, including links as markdown hyperlinks.",
            "parameters": {
                "type": "object",
                "required": ["query"],
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The search query to use",
                    },
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
                    "max_results": {
                        "type": "integer",
                        "default": 5,
                        "minimum": 1,
                        "maximum": 10,
                        "description": "Maximum number of search results",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "cdb",
            "description": "使用 Windows Debugging Tools 的 cdb 调试 Windows 可执行程序。适用于加载 EXE、设置断点、运行、查看寄存器/调用栈/模块/异常信息。参数 target_path 为待调试程序路径，commands 为 cdb 命令序列，log_path 为日志输出路径。",
            "parameters": {
                "type": "object",
                "required": ["commands", "target_path"],
                "properties": {
                    "cwd": {
                        "type": "string",
                        "default": ".",
                    },
                    "timeout": {
                        "type": "integer",
                        "default": 30,
                        "minimum": 1,
                        "maximum": 120,
                        "description": "Command execution timeout.",
                    },
                    "args": {
                        "type": "object",
                        "additionalProperties": True,
                        "description": "Named arguments for command templates. Values are shell-quoted by the runtime.",
                    },
                    "commands": {
                        "type": "string",
                        "description": "Template parameter {commands}.",
                    },
                    "log_path": {
                        "type": "string",
                        "description": "Template parameter {log_path}.",
                    },
                    "target_path": {
                        "type": "string",
                        "description": "Template parameter {target_path}.",
                    },
                },
            },
        },
    },
]
