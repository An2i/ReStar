#!/usr/bin/env python
"""Minimal CodeX sandbox server.

Run this script inside a sandbox host. It exposes JSON HTTP endpoints used by
the CodeX backend sandbox client to install tool metadata, receive files, run
tools, and return complete execution results.
"""

from __future__ import annotations

import argparse
import base64
import fnmatch
import hashlib
import html
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List
from urllib.error import HTTPError, URLError
from urllib.parse import quote_plus, urlparse
from urllib.request import Request, urlopen


JsonDict = Dict[str, Any]
PLACEHOLDER_PREFIX = "__sandbox_file__:"


class SandboxRuntime:
    glob_default_limit = 100
    vcs_directories_to_exclude = {".git", ".svn", ".hg", ".bzr", ".jj", ".sl"}
    grep_default_head_limit = 250
    grep_type_extensions = {
        "c": {".c", ".h"},
        "cc": {".cc", ".hh"},
        "cpp": {".cpp", ".cxx", ".hpp", ".hxx", ".cc", ".hh"},
        "cs": {".cs"},
        "css": {".css"},
        "go": {".go"},
        "html": {".html", ".htm"},
        "java": {".java"},
        "js": {".js", ".cjs", ".mjs", ".jsx"},
        "json": {".json"},
        "md": {".md", ".markdown"},
        "php": {".php"},
        "py": {".py"},
        "rs": {".rs"},
        "sh": {".sh", ".bash", ".zsh"},
        "sql": {".sql"},
        "toml": {".toml"},
        "ts": {".ts", ".tsx", ".mts", ".cts"},
        "tsx": {".tsx"},
        "txt": {".txt"},
        "xml": {".xml"},
        "yaml": {".yaml", ".yml"},
    }
    blocked_command_patterns = (
        " format ",
        " shutdown",
        " reboot",
        " diskpart",
        " bcdedit",
        " reg delete",
        " del /s",
        " rd /s",
        " rmdir /s",
        " remove-item -recurse",
        " remove-item -r",
    )
    text_extensions = {
        ".bat",
        ".c",
        ".cfg",
        ".cmd",
        ".conf",
        ".cpp",
        ".cs",
        ".css",
        ".go",
        ".h",
        ".hpp",
        ".html",
        ".ini",
        ".java",
        ".js",
        ".json",
        ".jsx",
        ".log",
        ".md",
        ".php",
        ".ps1",
        ".py",
        ".rs",
        ".sh",
        ".sql",
        ".toml",
        ".ts",
        ".tsx",
        ".txt",
        ".xml",
        ".yaml",
        ".yml",
    }

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir.resolve()
        self.upload_dir = self.root_dir / "uploads"
        self.output_dir = self.root_dir / "outputs"
        self.tool_dir = self.root_dir / "tools"
        self.installed_tools_file = self.root_dir / "installed_tools.json"
        self.root_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.tool_dir.mkdir(parents=True, exist_ok=True)

    def load_installed_tools(self) -> Dict[str, JsonDict]:
        if not self.installed_tools_file.exists():
            return {}
        try:
            data = json.loads(self.installed_tools_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def save_installed_tools(self, tools: Dict[str, JsonDict]) -> None:
        self.installed_tools_file.write_text(
            json.dumps(tools, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def tool_fingerprint(self, tool: JsonDict) -> str:
        payload = {
            "id": tool.get("id", ""),
            "name": tool.get("name", ""),
            "command_line": tool.get("command_line", ""),
            "sandbox_command_line": tool.get("sandbox_command_line", ""),
            "local_command_line": tool.get("local_command_line", ""),
            "description": tool.get("description", ""),
            "is_builtin": bool(tool.get("is_builtin")),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")
        ).hexdigest()

    def check_tools(self, tools: List[JsonDict]) -> JsonDict:
        installed = self.load_installed_tools()
        missing = []
        present = []
        for tool in tools:
            tool_id = str(tool.get("id") or "")
            if not tool_id:
                continue
            if bool(tool.get("is_builtin")):
                present.append(tool_id)
                continue
            record = installed.get(tool_id)
            if record and record.get("fingerprint") == self.tool_fingerprint(tool):
                present.append(tool_id)
            else:
                missing.append(tool)
        return {"present_tool_ids": present, "missing_tools": missing}

    def install_tools(self, tools: List[JsonDict], files: List[JsonDict]) -> JsonDict:
        installed = self.load_installed_tools()
        file_records = self.install_tool_files(files)
        installed_ids = []
        registered_ids = []
        for tool in tools:
            tool_id = str(tool.get("id") or "")
            if not tool_id:
                continue
            record = dict(tool)
            command_line = str(record.get("command_line") or "")
            for file_record in file_records:
                if file_record.get("tool_id") != tool_id:
                    continue
                source_path = str(file_record.get("source_path") or "")
                remote_path = str(file_record.get("remote_path") or "")
                if source_path and remote_path:
                    source_name = Path(source_path).name
                    if source_path in command_line:
                        command_line = command_line.replace(source_path, remote_path, 1)
                    elif source_name and source_name in command_line:
                        command_line = command_line.replace(source_name, remote_path, 1)
            record["command_line"] = command_line
            record["fingerprint"] = self.tool_fingerprint(tool)
            record["installed_at"] = utc_now()
            installed[tool_id] = record
            if bool(tool.get("is_builtin")):
                registered_ids.append(tool_id)
            else:
                installed_ids.append(tool_id)
        self.save_installed_tools(installed)
        return {
            "installed_tool_ids": installed_ids,
            "registered_tool_ids": registered_ids,
            "installed_files": file_records,
        }

    def install_tool_files(self, files: List[JsonDict]) -> List[JsonDict]:
        records = []
        for file_item in files:
            tool_id = safe_name(str(file_item.get("tool_id") or "tool"))
            filename = safe_name(str(file_item.get("name") or "tool.bin"))
            content_b64 = str(file_item.get("content_b64") or "")
            if not content_b64:
                continue
            target_dir = self.tool_dir / tool_id
            target_dir.mkdir(parents=True, exist_ok=True)
            target_path = (target_dir / filename).resolve()
            data = base64.b64decode(content_b64.encode("ascii"))
            target_path.write_bytes(data)
            try:
                target_path.chmod(target_path.stat().st_mode | 0o111)
            except OSError:
                pass
            records.append(
                {
                    "tool_id": tool_id,
                    "name": filename,
                    "source_path": str(file_item.get("source_path") or ""),
                    "remote_path": str(target_path),
                    "size": len(data),
                    "sha256": hashlib.sha256(data).hexdigest(),
                }
            )
        return records

    def materialize_files(self, files: List[JsonDict]) -> Dict[str, str]:
        placeholder_map = {}
        for file_item in files:
            file_id = safe_name(str(file_item.get("id") or uuid.uuid4().hex))
            filename = safe_name(str(file_item.get("name") or "input.bin"))
            content_b64 = str(file_item.get("content_b64") or "")
            if not content_b64:
                continue
            target_path = (self.upload_dir / f"{file_id}_{filename}").resolve()
            data = base64.b64decode(content_b64.encode("ascii"))
            target_path.write_bytes(data)
            placeholder_map[f"{PLACEHOLDER_PREFIX}{file_id}"] = str(target_path)
        return placeholder_map

    def execute_tool(self, tool: JsonDict, arguments: JsonDict, files: List[JsonDict]) -> JsonDict:
        placeholder_map = self.materialize_files(files)
        arguments = replace_placeholders(arguments, placeholder_map)
        # print("payload: ", arguments)
        installed = self.load_installed_tools()
        tool_id = str(tool.get("id") or "")
        definition = installed.get(tool_id, tool)
        command_line = str(definition.get("command_line") or tool.get("command_line") or "")
        command_line = replace_placeholders(command_line, placeholder_map)

        if command_line == "builtin:read_file":
            result = self.read_file(arguments)
        elif command_line == "builtin:write_file":
            result = self.write_file(arguments)
        elif command_line == "builtin:bash":
            result = self.execute_bash(arguments)
        elif command_line == "builtin:cmd":
            result = self.execute_cmd(arguments)
        elif command_line == "builtin:powershell":
            result = self.execute_powershell(arguments)
        elif command_line == "builtin:edit_file":
            result = self.edit_file(arguments)
        elif command_line == "builtin:notebook_edit":
            result = self.notebook_edit(arguments)
        elif command_line == "builtin:glob":
            result = self.glob_files(arguments)
        elif command_line == "builtin:grep":
            result = self.grep_files(arguments)
        elif command_line == "builtin:web_fetch":
            result = self.web_fetch(arguments)
        elif command_line == "builtin:web_search":
            result = self.web_search(arguments)
        elif command_line in {
            "builtin:todo_write",
            "builtin:task_create",
            "builtin:task_get",
            "builtin:task_list",
            "builtin:task_update",
            "builtin:task_stop",
            "builtin:task_output",
            # "builtin:config",
            # "builtin:sleep",
            # "builtin:ask_user_question",
            # "builtin:send_user_message",
            # "builtin:send_message",
            # "builtin:tool_search",
            # "builtin:agent",
            # "builtin:team_create",
            # "builtin:team_delete",
            # "builtin:enter_plan_mode",
            # "builtin:exit_plan_mode",
            # "builtin:enter_worktree",
            # "builtin:exit_worktree",
            # "builtin:cron_create",
            # "builtin:cron_delete",
            # "builtin:cron_list",
            # "builtin:remote_trigger",
            # "builtin:skill",
            # "builtin:mcp",
            # "builtin:mcp_auth",
            # "builtin:list_mcp_resources",
            # "builtin:read_mcp_resource",
            # "builtin:lsp",
            # "builtin:repl",
            # "builtin:structured_output",
            # "builtin:testing_permission",
        }:
            result = self.platform_state_tool(command_line, arguments)
        else:
            result = self.execute_configured_command(command_line, arguments)
        # result["sandbox_server"] = {
        #     "root": str(self.root_dir),
        #     "executed_at": utc_now(),
        #     "materialized_files": list(placeholder_map.values()),
        # }
        return result

    def resolve_path(self, value: object, *, must_exist: bool = False, output: bool = False) -> Path:
        raw_path = str(value or "").strip()
        if not raw_path:
            raise ValueError("路径不能为空")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = (self.output_dir if output else self.root_dir) / candidate
        resolved = candidate.resolve()
        if resolved != self.root_dir and self.root_dir not in resolved.parents:
            raise ValueError("路径必须位于沙箱工作目录内")
        if must_exist and not resolved.exists():
            raise FileNotFoundError(str(resolved))
        return resolved

    def argument_path(self, arguments: JsonDict, *keys: str) -> object:
        for key in keys:
            value = arguments.get(key)
            if value not in (None, ""):
                return value
        return ""

    def read_file(self, arguments: JsonDict) -> JsonDict:
        file_path = self.resolve_path(
            self.argument_path(arguments, "path", "file_path"),
            must_exist=True,
        )
        encoding = str(arguments.get("encoding") or "utf-8")
        encoding_mode = encoding.strip().lower().replace("_", "-")

        result: JsonDict = {
            "path": str(file_path),
            # "filePath": str(file_path),
            "size": 0,
            # "sha256": hash_file(file_path, "sha256"),
            # "preview_bytes": len(data),
            # "text_preview": text_preview,
            # "hex_preview": data[:256].hex(" "),
            "stdout": "",
        }

        if not file_path.is_file():
            # raise HTTPException(status_code=400, detail="路径不是文件")
            result["stdout"] = "Read Error: 路径不是文件"
            return result

        result["size"] = file_path.stat().st_size

        if encoding_mode == "base64":
            offset = max(int(arguments.get("offset") or 0), 0)
            max_bytes = int(arguments.get("max_bytes") or arguments.get("limit") or 8192)
            max_bytes = min(max(max_bytes, 1), 1024 * 1024)
            data = file_path.read_bytes()[offset : offset + max_bytes]
            text_preview = base64.b64encode(data).decode("ascii")
            result.update(
                {
                    "stdout": "Read Result {encoding: base64, offset: "
                    + str(offset)
                    + ", bytes_read: "
                    + str(len(data))
                    + ", Read Data:"
                    + text_preview
                    + "}\n",
                }
            )
        elif "offset" in arguments or "limit" in arguments:
            text = file_path.read_text(encoding=encoding, errors="replace")
            offset = int(arguments.get("offset") or 1)
            limit = int(arguments.get("limit") or 2000)
            offset = max(offset, 1)
            limit = min(max(limit, 1), 2000)
            lines = text.splitlines()
            selected = lines[offset - 1 : offset - 1 + limit]
            formatted = "\n".join(
                f"{line_number:6}\t{line}"
                for line_number, line in enumerate(selected, start=offset)
            )
            result.update(
                {
                    # "content": formatted,
                    # "start_line": offset,
                    # "total_lines": len(lines),
                    # "lines_read": len(selected),
                    "stdout": "Read Result {start_line: "
                    + str(offset)
                    + ", lines_read: "
                    + str(len(selected))
                    + ", Read Data:"
                    + formatted
                    + "}\n",
                }
            )
        else:
            max_bytes = int(arguments.get("max_bytes") or 8192)
            max_bytes = min(max(max_bytes, 128), 1024 * 1024)
            data = file_path.read_bytes()[:max_bytes]
            text_preview = data.decode(encoding, errors="replace")
            result.update(
                {
                    # "content": formatted,
                    # "start_line": offset,
                    # "total_lines": len(lines),
                    # "lines_read": len(selected),
                    "stdout": "Read Result {Read Data:"
                    + text_preview
                    + "}\n",
                }
            )
        return result

    def write_file(self, arguments: JsonDict) -> JsonDict:
        file_path = self.resolve_path(
            self.argument_path(arguments, "path", "file_path"),
            must_exist=False,
        )
        content = str(arguments.get("content") or "")
        overwrite = bool(arguments.get("overwrite", True))
        if file_path.exists() and not overwrite:
            # raise HTTPException(status_code=409, detail="目标文件已存在")
            return {
                "path": str(file_path),
                # "bytes_written": file_path.stat().st_size,
                # "content": content,
                "stdout": "Write Error: "
                + str(file_path)
                + " 目标文件已存在，无法写入.\n",
            }

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(
            content, encoding=str(arguments.get("encoding") or "utf-8")
        )
        return {
            "path": str(file_path),
            # "bytes_written": file_path.stat().st_size,
            # "content": content,
            "stdout": "Write Result: Success to write "
            + str(file_path.stat().st_size)
            + " into "
            + str(file_path)
            + ".\n",
        }

    def edit_file(self, arguments: JsonDict) -> JsonDict:
        file_path = self.resolve_path(
            self.argument_path(arguments, "file_path", "path"),
            must_exist=True,
        )
        if not file_path.is_file():
            # raise HTTPException(status_code=400, detail="路径不是文件")
            return {
                "path": str(file_path),
                # "bytes_written": file_path.stat().st_size,
                # "content": content,
                "Edit stdout": "Error: 路径不是文件.\n",
            }
        old_string = str(arguments.get("old_string") or "")
        new_string = str(arguments.get("new_string") or "")
        if not old_string:
            # raise HTTPException(status_code=400, detail="old_string不能为空")
            return {
                "path": str(file_path),
                # "bytes_written": file_path.stat().st_size,
                # "content": content,
                "stdout": "Edit Error: old_string 字段不能为空.\n",
            }
        encoding = str(arguments.get("encoding") or "utf-8")
        original = file_path.read_text(encoding=encoding, errors="replace")
        occurrences = original.count(old_string)
        if occurrences == 0:
            # raise HTTPException(status_code=404, detail="未找到要替换的文本")
            return {
                "path": str(file_path),
                # "bytes_written": file_path.stat().st_size,
                # "content": content,
                "stdout": "Edit Error: 未找到要替换的文本.\n",
            }

        replace_all = bool(arguments.get("replace_all", False))
        if occurrences > 1 and not replace_all:
            # raise HTTPException(
            #     status_code=409,
            #     detail="匹配到多处文本，请启用replace_all或提供更精确的old_string",
            # )
            return {
                "path": str(file_path),
                # "bytes_written": file_path.stat().st_size,
                # "content": content,
                "stdout": "Edit Error: 匹配到多处文本，请启用replace_all或提供更精确的old_string.\n",
            }
        updated = original.replace(old_string, new_string, -1 if replace_all else 1)
        file_path.write_text(updated, encoding=encoding)
        return {
            "path": str(file_path),
            # "filePath": str(file_path),
            # "oldString": old_string,
            # "newString": new_string,
            # "replaceAll": replace_all,
            # "replacements": occurrences if replace_all else 1,
            # "bytes_written": file_path.stat().st_size,
            "stdout": "Edit Result: Success to edit " + str(file_path) + ".\n",
        }

    def notebook_edit(self, arguments: JsonDict) -> JsonDict:
        notebook_path = self.resolve_path(arguments.get("notebook_path"), must_exist=True)
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
        cells = notebook.setdefault("cells", [])
        if not isinstance(cells, list):
            raise ValueError("notebook cells格式不正确")
        cell_id = str(arguments.get("cell_id") or "")
        edit_mode = str(arguments.get("edit_mode") or "replace")
        cell_type = str(arguments.get("cell_type") or "code")
        new_source = str(arguments.get("new_source") or "")

        def source_lines(text: str) -> List[str]:
            return [line if line.endswith("\n") else f"{line}\n" for line in text.splitlines()] or [""]

        def get_cell_id(cell: JsonDict) -> str:
            metadata = cell.get("metadata") if isinstance(cell.get("metadata"), dict) else {}
            return str(cell.get("id") or metadata.get("id") or "")

        index = next((idx for idx, cell in enumerate(cells) if isinstance(cell, dict) and get_cell_id(cell) == cell_id), -1)
        if edit_mode == "replace":
            if index < 0:
                raise ValueError("cell_id不存在")
            existing = cells[index]
            cell_type = str(arguments.get("cell_type") or existing.get("cell_type") or "code")
            existing["cell_type"] = cell_type
            existing["source"] = source_lines(new_source)
            target_id = get_cell_id(existing) or cell_id
        elif edit_mode == "insert":
            target_id = uuid.uuid4().hex[:12]
            new_cell: JsonDict = {"cell_type": cell_type, "id": target_id, "metadata": {}, "source": source_lines(new_source)}
            if cell_type == "code":
                new_cell.update({"execution_count": None, "outputs": []})
            cells.insert(index + 1 if index >= 0 else 0, new_cell)
        elif edit_mode == "delete":
            if index < 0:
                raise ValueError("cell_id不存在")
            removed = cells.pop(index)
            target_id = get_cell_id(removed) or cell_id
            cell_type = str(removed.get("cell_type") or cell_type)
        else:
            raise ValueError("edit_mode不支持")
        notebook_path.write_text(json.dumps(notebook, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"notebook_path": str(notebook_path), "cell_id": target_id, "cell_type": cell_type, "edit_mode": edit_mode, "cell_count": len(cells)}

    def glob_files(self, arguments: JsonDict) -> JsonDict:
        started_at = time.time()
        pattern = str(arguments.get("pattern") or "").strip()
        if not pattern:
            raise ValueError("pattern不能为空")
        search_root = self.resolve_path(
            arguments.get("path") or str(self.root_dir), must_exist=True
        )
        if not search_root.is_dir():
            search_root = search_root.parent
        limit = min(
            max(int(arguments.get("limit") or self.glob_default_limit), 1), 5000
        )
        matches = self.collect_glob_matches(search_root, pattern)
        matches = sorted(matches, key=lambda item: item.stat().st_mtime, reverse=True)
        filenames = [str(path) for path in matches[:limit]]
        return {
            # "pattern": pattern,
            "path": str(search_root),
            # "files": filenames,
            # "filenames": filenames,
            # "numFiles": len(filenames),
            # "totalMatches": len(matches),
            # "durationMs": int((time.time() - started_at) * 1000),
            # "truncated": len(matches) > limit,
            "stdout": "Glob Result: " + ", ".join(filenames) + ".\n",
        }

    def collect_glob_matches(self, search_root: Path, pattern: str) -> list[Path]:
        seen: set[str] = set()
        matches: list[Path] = []

        def append_match(path: Path) -> None:
            if not path.exists() or not path.is_file():
                return
            if any(part in self.vcs_directories_to_exclude for part in path.parts):
                return
            path_text = str(path)
            if path_text in seen:
                return
            seen.add(path_text)
            matches.append(path)

        for path in search_root.glob(pattern):
            append_match(path)
        if "**" not in pattern:
            for path in search_root.rglob(pattern):
                append_match(path)
        return matches

    def grep_files(self, arguments: JsonDict) -> JsonDict:
        pattern = str(arguments.get("pattern") or "")
        if not pattern:
            # raise HTTPException(status_code=400, detail="pattern不能为空")
            return {
                "stdout": "Grep Error: pattern不能为空.\n",
            }
        flags = re.IGNORECASE if bool(arguments.get("-i")) else 0
        multiline = bool(arguments.get("multiline"))
        regex_flags = flags | re.MULTILINE | (re.DOTALL if multiline else 0)
        try:
            regex = re.compile(pattern, regex_flags)
        except re.error as e:
            # return {"stdout": f"Grep Error: 无效的正则表达式: {e}."}
            return {"stdout": "Grep Error: 无效的正则表达式."}
        output_mode = str(
            arguments.get("output_mode")
            or arguments.get("mode")
            or "files_with_matches"
        )
        search_path = self.resolve_path(
            arguments.get("path") or str(self.root_dir), must_exist=True
        )
        raw_head_limit = arguments.get("head_limit")
        if raw_head_limit in (None, ""):
            head_limit: int | None = self.grep_default_head_limit
        else:
            parsed_limit = int(raw_head_limit)
            head_limit = None if parsed_limit == 0 else min(max(parsed_limit, 1), 5000)
        offset = max(int(arguments.get("offset") or 0), 0)
        context_all = arguments.get("context")
        if context_all in (None, ""):
            context_all = arguments.get("-C")
        if context_all not in (None, ""):
            context_before = context_after = min(max(int(context_all), 0), 20)
        else:
            context_before = min(max(int(arguments.get("-B") or 0), 0), 20)
            context_after = min(max(int(arguments.get("-A") or 0), 0), 20)
        show_line_numbers = bool(arguments.get("-n", True))
        glob_patterns = self.parse_grep_glob_patterns(arguments.get("glob"))
        include_glob = str(arguments.get("glob") or "*")
        type_filter = str(arguments.get("type") or "").strip().lower()

        candidates = self.collect_grep_candidates(
            search_path, glob_patterns, type_filter
        )
        matches: list[JsonDict] = []
        file_counts: dict[str, int] = {}
        for path in candidates:
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            lines = text.splitlines()
            file_match_count = 0
            if multiline:
                file_matches = self.collect_multiline_grep_matches(
                    path,
                    text,
                    lines,
                    regex,
                    context_before,
                    context_after,
                    show_line_numbers,
                )
            else:
                file_matches = self.collect_line_grep_matches(
                    path,
                    lines,
                    regex,
                    context_before,
                    context_after,
                    show_line_numbers,
                )
            file_match_count = len(file_matches)
            for match in file_matches:
                if head_limit is not None and len(matches) >= offset + head_limit:
                    break
                matches.append(match)
            if file_match_count:
                file_counts[str(path)] = file_match_count
        visible_matches = matches[
            offset : (offset + head_limit) if head_limit is not None else None
        ]
        if output_mode == "files_with_matches":
            sorted_files = sorted(
                file_counts.keys(),
                key=lambda item: (
                    Path(item).stat().st_mtime if Path(item).exists() else 0
                ),
                reverse=True,
            )
            visible_files = sorted_files[
                offset : (offset + head_limit) if head_limit is not None else None
            ]
            result: JsonDict = {
                # "files": visible_files,
                # "filenames": visible_files,
                # "numFiles": len(visible_files),
                "stdout": "Grep{ "
                + "files: "
                + str(visible_files)
                + ", numFiles: "
                + str(len(visible_files))
                + "}",
            }
        elif output_mode == "count":
            sorted_counts = sorted(
                file_counts.items(),
                key=lambda item: item[0],
            )
            visible_counts = sorted_counts[
                offset : (offset + head_limit) if head_limit is not None else None
            ]
            result = {
                # "counts": dict(visible_counts),
                # "numMatches": sum(count for _, count in visible_counts),
                # "numFiles": len(visible_counts),
                "stdout": "Grep{ "
                + "counts: "
                + str(dict(visible_counts))
                + ", numFiles: "
                + str(len(visible_counts))
                + "}",
            }
        else:
            result = {
                # "matches": visible_matches,
                # "content": self.render_grep_content(visible_matches),
                # "numLines": len(visible_matches),
                # "numFiles": len(
                #     {str(item.get("path") or "") for item in visible_matches}
                # ),
                # "filenames": list(
                #     dict.fromkeys(
                #         str(item.get("path") or "")
                #         for item in visible_matches
                #         if item.get("path")
                #     )
                # ),
                "stdout": "Grep{ "
                + "content: "
                + self.render_grep_content(visible_matches)
                + ", numLines: "
                + str(len(visible_matches))
                + ", numFiles: "
                + str(len({str(item.get("path") or "") for item in visible_matches}))
                + ", filenames: "
                + str(
                    list(
                        dict.fromkeys(
                            str(item.get("path") or "")
                            for item in visible_matches
                            if item.get("path")
                        )
                    )
                )
                + "}",
            }
        # result.update(
        #     {
        #         "pattern": pattern,
        #         "path": str(search_path),
        #         "type": type_filter,
        #         "glob": include_glob,
        #         "mode": output_mode,
        #         "match_count": sum(file_counts.values()),
        #         "file_count": len(file_counts),
        #         "appliedOffset": offset,
        #         "appliedLimit": head_limit,
        #         "truncated": head_limit is not None
        #         and len(matches) > offset + head_limit,
        #     }
        # )
        return result

    def parse_grep_glob_patterns(self, value: object) -> list[str]:
        raw = str(value or "").strip()
        if not raw:
            return []
        patterns: list[str] = []
        for token in raw.split():
            if "{" in token and "}" in token:
                patterns.append(token)
            else:
                patterns.extend(part for part in token.split(",") if part)
        return patterns

    def collect_grep_candidates(
        self, search_path: Path, glob_patterns: list[str], type_filter: str
    ) -> list[Path]:
        if search_path.is_file():
            return (
                [search_path]
                if self.is_grep_candidate(search_path, glob_patterns, type_filter)
                else []
            )
        candidates: list[Path] = []
        for path in search_path.rglob("*"):
            if not path.is_file():
                continue
            if self.is_grep_candidate(
                path, glob_patterns, type_filter, base_dir=search_path
            ):
                candidates.append(path)
        return candidates

    def is_grep_candidate(
        self,
        path: Path,
        glob_patterns: list[str],
        type_filter: str,
        base_dir: Path | None = None,
    ) -> bool:
        if any(part in self.vcs_directories_to_exclude for part in path.parts):
            return False
        suffix = path.suffix.lower()
        if suffix and suffix not in self.text_extensions:
            return False
        if type_filter:
            allowed_suffixes = self.grep_type_extensions.get(type_filter, set())
            if allowed_suffixes and suffix not in allowed_suffixes:
                return False
            if not allowed_suffixes and type_filter not in suffix.lstrip("."):
                return False
        if not glob_patterns:
            return True
        relative_path = str(path.relative_to(base_dir or self.root_dir)).replace(
            "\\", "/"
        )
        filename = path.name
        return any(
            fnmatch.fnmatch(relative_path, pattern)
            or fnmatch.fnmatch(filename, pattern)
            for pattern in glob_patterns
        )

    def collect_line_grep_matches(
        self,
        path: Path,
        lines: list[str],
        regex: re.Pattern[str],
        context_before: int,
        context_after: int,
        show_line_numbers: bool,
    ) -> list[JsonDict]:
        matches: list[JsonDict] = []
        for line_number, line in enumerate(lines, start=1):
            if not regex.search(line):
                continue
            start = max(1, line_number - context_before)
            end = min(len(lines), line_number + context_after)
            matches.append(
                {
                    "path": str(path),
                    "line_number": line_number if show_line_numbers else 0,
                    "line": line,
                    "context": (
                        [
                            {"line_number": idx, "line": lines[idx - 1]}
                            for idx in range(start, end + 1)
                        ]
                        if context_before or context_after
                        else []
                    ),
                }
            )
        return matches

    def collect_multiline_grep_matches(
        self,
        path: Path,
        text: str,
        lines: list[str],
        regex: re.Pattern[str],
        context_before: int,
        context_after: int,
        show_line_numbers: bool,
    ) -> list[JsonDict]:
        matches: list[JsonDict] = []
        for match in regex.finditer(text):
            start_line = text.count("\n", 0, match.start()) + 1
            end_line = text.count("\n", 0, match.end()) + 1
            context_start = max(1, start_line - context_before)
            context_end = min(len(lines), end_line + context_after)
            matches.append(
                {
                    "path": str(path),
                    "line_number": start_line if show_line_numbers else 0,
                    "end_line": end_line if show_line_numbers else 0,
                    "line": text[match.start() : match.end()][:2000],
                    "context": (
                        [
                            {"line_number": idx, "line": lines[idx - 1]}
                            for idx in range(context_start, context_end + 1)
                        ]
                        if context_before or context_after
                        else []
                    ),
                }
            )
        return matches

    def render_grep_content(self, matches: list[JsonDict]) -> str:
        rendered_lines: list[str] = []
        for item in matches:
            path = str(item.get("path") or "")
            line_number = item.get("line_number", 0)
            line = str(item.get("line") or "")
            if line_number:
                rendered_lines.append(f"{path}:{line_number}:{line}")
            else:
                rendered_lines.append(f"{path}:{line}")
        return "\n".join(rendered_lines)

    def execute_powershell(self, arguments: JsonDict) -> JsonDict:
        command = str(
            arguments.get("command") or arguments.get("command_line") or ""
        ).strip()
        if not command:
            return {
                "stdout": "",
                "stderr": "PowerShell Error: command cannot be empty.",
            }
        command = (
            "$ProgressPreference='SilentlyContinue'; $InformationPreference='SilentlyContinue'; "
            + command
        )
        powershell_executable = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell_executable:
            return {
                "stdout": "",
                "stderr": (
                    "PowerShell Error: PowerShell executable was not found. "
                    "Install PowerShell Core (pwsh) or use the Bash tool on macOS/Linux."
                ),
                "exit_code": None,
                "timed_out": False,
            }
        encoded_command = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        timeout = int(arguments.get("timeout") or 30)
        timeout = min(max(timeout, 1), 120)
        cwd = self.resolve_path(
            arguments.get("cwd") or str(self.root_dir),
            must_exist=True,
        )
        if not cwd.is_dir():
            return {
                "stdout": "",
                "stderr": "PowerShell Error: working directory is not a directory.",
                "exit_code": None,
                "timed_out": False,
            }
        try:
            completed = subprocess.run(
                [
                    powershell_executable,
                    "-NoProfile",
                    "-NonInteractive",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-EncodedCommand",
                    encoded_command,
                ],
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "timed_out": True,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": None,
            }
        return {
            "timed_out": False,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }

    def execute_cmd(self, arguments: JsonDict) -> JsonDict:
        command = str(
            arguments.get("command") or arguments.get("command_line") or ""
        ).strip()
        if not command:
            return {
                "stdout": "",
                "stderr": "Cmd Error: command cannot be empty.",
            }
        if not platform.system().lower().startswith("win"):
            return self.execute_bash(
                {
                    "command_line": command,
                    "cwd": arguments.get("cwd", str(self.root_dir)),
                    "timeout": arguments.get("timeout", 30),
                }
            )

        timeout = int(arguments.get("timeout") or 30)
        timeout = min(max(timeout, 1), 120)
        cwd = self.resolve_path(
            arguments.get("cwd") or str(self.root_dir),
            must_exist=True,
        )
        if not cwd.is_dir():
            return {
                "stdout": "",
                "stderr": "Cmd Error: working directory is not a directory.",
            }
        try:
            print(command)
            completed = subprocess.run(
                ["cmd.exe", "/d", "/s", "/c", command],
                cwd=str(cwd),
                shell=False,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            return {
                "timed_out": True,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": None,
            }
        return {
            "timed_out": False,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }

    def execute_for_platform(self, arguments: JsonDict) -> JsonDict:
        if platform.system().lower().startswith("win"):
            return self.execute_cmd(arguments)
        return self.execute_bash(arguments)

    def web_fetch(self, arguments: JsonDict) -> JsonDict:
        started_at = time.time()
        url = str(arguments.get("url") or "").strip()
        if not url:
            # raise HTTPException(status_code=400, detail="url不能为空")
            return {
                "stdout": "",
                "stderr": "WebFetch Error: url不能为空.",
            }
        if url.startswith("http://"):
            url = "https://" + url[len("http://") :]
        prompt = str(arguments.get("prompt") or "").strip()
        if not prompt:
            # raise HTTPException(status_code=400, detail="prompt不能为空")
            return {
                "stdout": "",
                "stderr": "WebFetch Error: prompt不能为空.",
            }

        timeout = min(max(int(arguments.get("timeout") or 20), 1), 60)
        max_bytes = min(max(int(arguments.get("max_bytes") or 100000), 1024), 1000000)
        request = Request(url, headers={"User-Agent": "CodeX-ToolRuntime/1.0"})
        try:
            with urlopen(request, timeout=timeout) as response:
                body = response.read(max_bytes)
                code = getattr(response, "status", 200)
                reason = getattr(response, "reason", "")
                content_type = response.headers.get("content-type", "")
                final_url = str(response.geturl() or url)
        except HTTPError as exc:
            body = exc.read(max_bytes)
            code = exc.code
            reason = str(exc.reason)
            content_type = exc.headers.get("content-type", "")
            final_url = str(getattr(exc, "url", url) or url)
        except URLError as exc:
            return {
                # "url": url,
                # "status": "failed",
                # "error": str(exc.reason),
                # "durationMs": int((time.time() - started_at) * 1000),
                # "stdout": "",
                "stderr": f"WebFetch Error: the url is {url}, {str(exc.reason)}.",
            }

        text = body.decode("utf-8", errors="replace")
        if "html" in content_type.lower():
            text = self.html_to_text(text)
        redirect_message = self.build_web_fetch_redirect_message(
            url, final_url, prompt, code, reason
        )
        result_text = redirect_message or self.build_web_fetch_result(
            prompt, text[:100000]
        )
        return {
            # "url": url,
            # "final_url": final_url,
            # "status": "success",
            # "code": code,
            # "codeText": reason,
            # "content_type": content_type,
            # "bytes": len(body),
            # "durationMs": int((time.time() - started_at) * 1000),
            # "prompt": prompt,
            # "content": text[:100000],
            # "result": result_text,
            "stdout": "WebFetch Result: "
            + str(
                {
                    "url": url,
                    "final_url": final_url,
                    "status": "success",
                    "code": code,
                    "codeText": reason,
                    "content_type": content_type,
                    "bytes": len(body),
                    "durationMs": int((time.time() - started_at) * 1000),
                    "prompt": prompt,
                    "content": text[:100000],
                    "result": result_text,
                }
            ),
        }

    def web_search(self, arguments: JsonDict) -> JsonDict:
        started_at = time.time()
        query = str(arguments.get("query") or "").strip()
        if len(query) < 2:
            # raise HTTPException(status_code=400, detail="query至少需要2个字符")
            return {
                "stdout": "",
                "stderr": "WebSearch Error: query至少需要2个字符.",
            }

        allowed_domains = self.normalize_domain_list(arguments.get("allowed_domains"))
        blocked_domains = self.normalize_domain_list(arguments.get("blocked_domains"))
        if allowed_domains and blocked_domains:
            # raise HTTPException(
            #     status_code=400,
            #     detail="不能同时设置 allowed_domains 和 blocked_domains",
            # )
            return {
                "stdout": "",
                "stderr": "WebSearch Error: 不能同时设置 allowed_domains 和 blocked_domains.",
            }
        max_results = min(max(int(arguments.get("max_results") or 5), 1), 10)
        search_url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        request = Request(search_url, headers={"User-Agent": "CodeX-ToolRuntime/1.0"})
        try:
            with urlopen(request, timeout=20) as response:
                content = response.read(300000).decode("utf-8", errors="replace")
            fetch_status = "success"
        except (HTTPError, URLError) as exc:
            content = ""
            fetch_status = "failed"
            fetch_error = str(exc)
        results = []
        for match in re.finditer(
            r'<a[^>]+class="result__a"[^>]+href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            content,
            re.IGNORECASE | re.DOTALL,
        ):
            title = self.html_to_text(match.group("title")).strip()
            url = html.unescape(match.group("url"))
            hostname = urlparse(url).hostname or ""
            if allowed_domains and not self.domain_allowed(hostname, allowed_domains):
                continue
            if blocked_domains and self.domain_allowed(hostname, blocked_domains):
                continue
            results.append({"title": title, "url": url})
            if len(results) >= max_results:
                break
        return {
            "stdout": "WebSearch Result: "
            + str(
                {
                    "query": query,
                    "status": "success" if results else fetch_status,
                    "error": fetch_error if fetch_status == "failed" else "",
                    "result_count": len(results),
                    "results": results,
                    "allowed_domains": allowed_domains,
                    "blocked_domains": blocked_domains,
                    "durationSeconds": round(time.time() - started_at, 3),
                    "source": search_url,
                }
            )
        }

    def build_web_fetch_redirect_message(
        self,
        original_url: str,
        final_url: str,
        prompt: str,
        code: int,
        reason: str,
    ) -> str:
        original_host = urlparse(original_url).hostname or ""
        final_host = urlparse(final_url).hostname or ""
        if not final_host or final_host == original_host or final_url == original_url:
            return ""
        return (
            "REDIRECT DETECTED: The URL redirects to a different host.\n\n"
            f"Original URL: {original_url}\n"
            f"Redirect URL: {final_url}\n"
            f"Status: {code} {reason}\n\n"
            "To complete your request, call WebFetch again with:\n"
            f'- url: "{final_url}"\n'
            f'- prompt: "{prompt}"'
        )

    def build_web_fetch_result(self, prompt: str, content: str) -> str:
        return f"Prompt:\n{prompt}\n\n" "Fetched content:\n" f"{content}"

    def normalize_domain_list(self, value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        domains: list[str] = []
        for item in value:
            text = str(item or "").strip().lower()
            if text:
                domains.append(text)
        return domains

    def domain_allowed(self, hostname: str, domains: list[str]) -> bool:
        host = hostname.lower().strip(".")
        for domain in domains:
            clean = domain.lower().strip(".")
            if host == clean or host.endswith("." + clean):
                return True
        return False

    def html_to_text(self, value: str) -> str:
        value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
        value = re.sub(r"(?s)<br\s*/?>", "\n", value)
        value = re.sub(r"(?s)</p\s*>", "\n", value)
        value = re.sub(r"(?s)<.*?>", " ", value)
        value = html.unescape(value)
        return re.sub(r"[ \t\r\f\v]+", " ", value).strip()

    def platform_state_tool(self, command_line: str, arguments: JsonDict) -> JsonDict:
        if command_line == "builtin:sleep":
            seconds = min(max(float(arguments.get("seconds") or 0), 0.0), 30.0)
            time.sleep(seconds)
            return {"status": "success", "slept_seconds": seconds}
        if command_line == "builtin:structured_output":
            return {"status": "success", "structured_output": arguments}
        event = {"id": uuid.uuid4().hex, "tool": command_line.replace("builtin:", ""), "arguments": arguments, "created_at": utc_now()}
        events_file = self.root_dir / "platform_tool_events.json"
        try:
            events = json.loads(events_file.read_text(encoding="utf-8")) if events_file.exists() else []
        except json.JSONDecodeError:
            events = []
        if not isinstance(events, list):
            events = []
        events.append(event)
        events_file.write_text(json.dumps(events[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        return {"status": "success", "message": "沙箱状态型工具调用已记录。", "event": event}

    def execute_bash(self, arguments: JsonDict) -> JsonDict:
        command_line = str(
            arguments.get("command_line") or arguments.get("command") or ""
        ).strip()
        if not command_line:
            # raise HTTPException(status_code=400, detail="命令行不能为空")
            return {
                "stdout": "",
                "stderr": "Bash Error: 命令行不能为空.",
            }

        timeout = int(arguments.get("timeout") or 30)
        timeout = min(max(timeout, 1), 120)
        cwd = self.resolve_path(
            arguments.get("cwd") or str(self.root_dir), must_exist=True
        )
        if not cwd.is_dir():
            # raise HTTPException(status_code=400, detail="工作目录不是文件夹")
            return {
                "stdout": "",
                "stderr": "Bash Error: 工作目录不是文件夹.",
            }

        try:
            completed = subprocess.run(
                command_line,
                cwd=str(cwd),
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                encoding="utf-8",
                errors="replace",
            )
        except subprocess.TimeoutExpired as exc:
            return {
                # "command_line": command_line,
                # "cwd": str(cwd),
                "timed_out": True,
                # "timeout": timeout,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "exit_code": None,
            }

        return {
            # "command_line": command_line,
            # "cwd": str(cwd),
            "timed_out": False,
            "exit_code": completed.returncode,
            "stdout": completed.stdout[-12000:],
            "stderr": completed.stderr[-12000:],
        }

    def execute_configured_command(self, command_template: str, arguments: JsonDict) -> JsonDict:
        if not command_template:
            raise ValueError("工具命令行为空")
        arguments = self.apply_configured_command_defaults(command_template, arguments)
        template_arguments = self.flatten_template_arguments(arguments)
        try:
            command_line = command_template.format(
                **template_arguments
            )
        except KeyError as exc:
            raise ValueError(f"工具命令行缺少参数: {exc.args[0]}") from exc
        except ValueError as exc:
            raise ValueError(f"工具命令行模板无效: {exc}") from exc
        return self.execute_for_platform(
            {
                "command_line": command_line,
                "timeout": arguments.get("timeout", 30),
                "cwd": arguments.get("cwd", str(self.root_dir)),
            }
        )

    def apply_configured_command_defaults(self, command_template: str, arguments: JsonDict) -> JsonDict:
        prepared = dict(arguments)
        if "{log_path}" in command_template and not prepared.get("log_path"):
            prepared["log_path"] = str(
                (self.root_dir / f"tool-log-{uuid.uuid4().hex}.log").resolve()
            )
        return prepared

    def flatten_template_arguments(self, arguments: JsonDict) -> Dict[str, str]:
        flattened: Dict[str, str] = {}
        powershell = platform.system().lower().startswith("win")
        for key, value in arguments.items():
            key_text = str(key)
            if key_text in {"cwd", "timeout"}:
                continue
            if key_text == "args" and isinstance(value, dict):
                for arg_key, arg_value in value.items():
                    flattened[str(arg_key)] = self.template_escape(
                        arg_value, powershell=powershell
                    )
                continue
            flattened[key_text] = self.template_escape(value, powershell=powershell)
        return flattened

    @staticmethod
    def template_escape(value: object, *, powershell: bool = False) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        text = str(value)
        if powershell:
            return (
                text.replace("`", "``")
                .replace("$", "`$")
                .replace('"', '`"')
            )
        return text.replace('"', '\\"')

    @staticmethod
    def normalize_configured_command_line(command_line: str) -> str:
        if platform.system().lower().startswith("win") and command_line.lstrip().startswith('"'):
            return "& " + command_line
        return command_line

    def check_command_allowed(self, command_line: str) -> None:
        padded = f" {command_line.lower()} "
        if any(pattern in padded for pattern in self.blocked_command_patterns):
            raise PermissionError("命令行被沙箱权限策略拦截")


class SandboxRequestHandler(BaseHTTPRequestHandler):
    runtime: SandboxRuntime
    auth_token = ""

    def do_GET(self) -> None:
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, status=401)
            return
        path = urlparse(self.path).path
        if path == "/health":
            self.send_json(
                {
                    "status": "ok",
                    "server": "codex-sandbox",
                    "root": str(self.runtime.root_dir),
                    "upload_dir": str(self.runtime.upload_dir),
                    "output_dir": str(self.runtime.output_dir),
                    "cwd": str(Path.cwd().resolve()),
                    "os_name": platform.system(),
                    "os_release": platform.release(),
                    "os_version": platform.version(),
                    "machine": platform.machine(),
                    "python_version": platform.python_version(),
                    "time": utc_now(),
                }
            )
            return
        self.send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        if not self.authorized():
            self.send_json({"error": "unauthorized"}, status=401)
            return
        path = urlparse(self.path).path
        try:
            payload = self.read_json()
            if path == "/tools/check":
                self.send_json(self.runtime.check_tools(payload.get("tools", [])))
            elif path == "/tools/install":
                self.send_json(
                    self.runtime.install_tools(
                        payload.get("tools", []),
                        payload.get("files", []),
                    )
                )
            elif path == "/tools/execute":
                self.send_json(
                    self.runtime.execute_tool(
                        payload.get("tool", {}),
                        payload.get("arguments", {}),
                        payload.get("files", []),
                    )
                )
            else:
                self.send_json({"error": "not_found"}, status=404)
        except Exception as exc:
            self.send_json(
                {"error": exc.__class__.__name__, "detail": str(exc)},
                status=500,
            )

    def read_json(self) -> JsonDict:
        length = int(self.headers.get("Content-Length") or "0")
        if length <= 0:
            return {}
        data = self.rfile.read(length)
        parsed = json.loads(data.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def send_json(self, payload: JsonDict, status: int = 200) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def authorized(self) -> bool:
        if not self.auth_token:
            return True
        auth = self.headers.get("Authorization", "")
        token = self.headers.get("X-Sandbox-Token", "")
        return auth == f"Bearer {self.auth_token}" or token == self.auth_token

    def log_message(self, format_text: str, *args: object) -> None:
        sys.stderr.write(
            f"{self.address_string()} - [{self.log_date_time_string()}] "
            f"{format_text % args}\n"
        )


def replace_placeholders(value: Any, placeholder_map: Dict[str, str]) -> Any:
    if isinstance(value, dict):
        return {key: replace_placeholders(item, placeholder_map) for key, item in value.items()}
    if isinstance(value, list):
        return [replace_placeholders(item, placeholder_map) for item in value]
    if isinstance(value, str):
        replaced = value
        for placeholder, remote_path in placeholder_map.items():
            replaced = replaced.replace(placeholder, remote_path)
        return replaced
    return value


def safe_name(value: str) -> str:
    cleaned = Path(value or "").name.replace("\\", "_").strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", cleaned).strip("._ ")
    return cleaned or "file.bin"


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_obj:
        for chunk in iter(lambda: file_obj.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="CodeX sandbox server")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--root", default=str(Path.cwd() / "codex_sandbox_runtime"))
    parser.add_argument("--token", default=os.environ.get("CODEX_SANDBOX_TOKEN", ""))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    handler = SandboxRequestHandler
    handler.runtime = SandboxRuntime(Path(args.root))
    handler.auth_token = str(args.token or "")
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"CodeX sandbox server listening on {args.host}:{args.port}")
    print(f"Sandbox root: {handler.runtime.root_dir}")
    server.serve_forever()


if __name__ == "__main__":
    main()
