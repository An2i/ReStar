import base64
import copy
import hashlib
import json
import re
import shlex
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from backend.config import ROOT_DIR, UPLOAD_DIR
from backend.data_structures import JsonDict
PLACEHOLDER_PREFIX = "__sandbox_file__:"
SANDBOX_TASK_TYPES = {"sample-analysis", "vulnerability-mining"}
DEBUG_LOG_PREFIX = "[SANDBOX_DEBUG]"


class SandboxClientError(RuntimeError):
    pass


class SandboxClient:
    max_transfer_bytes = 50 * 1024 * 1024

    def __init__(self, platform: JsonDict, root_dir: Path = ROOT_DIR) -> None:
        self.platform = platform
        self.root_dir = root_dir.resolve()
        self.base_url = str(platform.get("url") or "").strip().rstrip("/")
        self.token = str(
            platform.get("api_key") or platform.get("token") or platform.get("cookie") or ""
        ).strip()
        if not self.base_url:
            raise SandboxClientError("沙箱URL未配置")

    def health(self) -> JsonDict:
        return self.request("GET", "/health", timeout=5)

    def environment_info(self) -> JsonDict:
        return self.health()

    def is_online(self) -> bool:
        try:
            return self.health().get("status") == "ok"
        except SandboxClientError:
            return False

    def ensure_tools_installed(self, tools: list[JsonDict]) -> JsonDict:
        check = self.request("POST", "/tools/check", {"tools": tools}, timeout=30)
        missing_tools = check.get("missing_tools")
        if not isinstance(missing_tools, list) or not missing_tools:
            return {"checked": True, "installed": False, "check": check}
        install_payload = {
            "tools": missing_tools,
            "files": self.collect_tool_install_files(missing_tools),
        }
        install = self.request("POST", "/tools/install", install_payload, timeout=60)
        return {
            "checked": True,
            "installed": True,
            "check": check,
            "install": install,
        }

    def execute_tool(
        self,
        tool: JsonDict,
        arguments: JsonDict,
        all_tools: list[JsonDict],
    ) -> JsonDict:
        install_result = self.ensure_tools_installed(all_tools)
        prepared_arguments, files, path_map = self.prepare_execution_payload(tool, arguments)
        # print(
        #     f"{DEBUG_LOG_PREFIX} tool={tool.get('name', '')} "
        #     f"prepared_arguments={str(prepared_arguments)[:800]} "
        #     f"file_count={len(files)} path_map={str(path_map)[:800]}"
        # )
        result = self.request(
            "POST",
            "/tools/execute",
            {
                "tool": tool,
                "arguments": prepared_arguments,
                "files": files,
            },
            timeout=180,
        )
        # result["sandbox"] = {
        #     "platform_id": self.platform.get("id", ""),
        #     "platform_name": self.platform.get("name", ""),
        #     "url": self.base_url,
        #     "path_map": path_map,
        #     "tool_install": install_result,
        # }
        return result

    def request(
        self,
        method: str,
        path: str,
        payload: JsonDict | None = None,
        timeout: float = 30,
    ) -> JsonDict:
        url = urljoin(f"{self.base_url}/", path.lstrip("/"))
        data = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Sandbox-Token"] = self.token
        request = Request(url, data=data, method=method.upper(), headers=headers)
        try:
            with urlopen(request, timeout=timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise SandboxClientError(f"沙箱请求失败: HTTP {exc.code} {detail}") from exc
        except URLError as exc:
            raise SandboxClientError(f"沙箱不可达: {exc.reason}") from exc
        except TimeoutError as exc:
            raise SandboxClientError("沙箱请求超时") from exc
        if not raw:
            return {}
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}

    def collect_tool_install_files(self, tools: list[JsonDict]) -> list[JsonDict]:
        files = []
        for tool in tools:
            if bool(tool.get("is_builtin")):
                continue
            if str(tool.get("sandbox_command_line") or "").strip():
                continue
            executable_path = self.find_local_executable_path(
                str(tool.get("local_command_line") or tool.get("command_line") or "")
            )
            if not executable_path:
                continue
            files.append(
                {
                    "tool_id": tool.get("id", ""),
                    "name": executable_path.name,
                    "source_path": str(executable_path),
                    "content_b64": self.encode_file(executable_path),
                }
            )
        return files

    def find_local_executable_path(self, command_line: str) -> Path | None:
        if not command_line or command_line.startswith("builtin:"):
            return None
        first_token = self.first_command_token(command_line)
        if not first_token:
            return None
        candidate = Path(first_token).expanduser()
        if not candidate.is_absolute():
            candidate = self.root_dir / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            return None
        if resolved.exists() and resolved.is_file():
            return resolved
        return None

    def first_command_token(self, command_line: str) -> str:
        stripped = command_line.strip()
        if not stripped:
            return ""
        if stripped[0] in {'"', "'"}:
            quote = stripped[0]
            end = stripped.find(quote, 1)
            if end > 1:
                return stripped[1:end]
        try:
            parts = shlex.split(stripped, posix=False)
        except ValueError:
            parts = stripped.split(maxsplit=1)
        if not parts:
            return ""
        return str(parts[0]).strip('"\'')

    def prepare_execution_payload(
        self,
        tool: JsonDict,
        arguments: JsonDict,
    ) -> tuple[JsonDict, list[JsonDict], JsonDict]:
        prepared_arguments = copy.deepcopy(arguments)
        if "command" in arguments:
            command_line = arguments["command"]
        elif "command_line" in arguments:
            command_line = arguments["command_line"]
        elif "command_line" in tool:
            command_line = tool["command_line"]
        else:
            command_line = ""

        files_by_path: dict[str, Path] = {}
        for path in self.collect_argument_file_paths(tool, prepared_arguments, command_line):
            files_by_path[str(path)] = path

        # print(
        #     f"{DEBUG_LOG_PREFIX} collect_payload tool={tool.get('name', '')} "
        #     f"command_line={str(command_line)[:500]} files={list(files_by_path.keys())[:10]}"
        # )

        files = []
        path_map: JsonDict = {}
        for source_path in files_by_path.values():
            file_id = hashlib.sha256(str(source_path).encode("utf-8")).hexdigest()[:16]
            placeholder = f"{PLACEHOLDER_PREFIX}{file_id}"
            files.append(
                {
                    "id": file_id,
                    "name": source_path.name,
                    "original_path": str(source_path),
                    "content_b64": self.encode_file(source_path),
                }
            )
            path_map[str(source_path)] = placeholder
            remote_alias = self.remote_materialized_path(source_path)
            if remote_alias:
                path_map[str(remote_alias)] = placeholder

        prepared_arguments = self.replace_paths_with_placeholders(prepared_arguments, path_map)
        prepared_arguments = self.normalize_remote_cwd(prepared_arguments)
        if str(tool.get("command_line") or "") == "builtin:write_file":
            prepared_arguments = self.prepare_remote_write_path(prepared_arguments)
        return prepared_arguments, files, path_map

    def collect_argument_file_paths(
        self,
        tool: JsonDict,
        arguments: JsonDict,
        command_line: str,
    ) -> list[Path]:
        if str(tool.get("command_line") or "") == "builtin:write_file":
            return []
        candidates: list[object] = []

        for key in ("path", "file_path", "sample_path", "target_path"):
            if key in arguments:
                candidates.append(arguments.get(key))
        candidates.extend(self.extract_quoted_paths(command_line))
        paths = []
        for candidate in candidates:
            path = self.resolve_existing_file(candidate)
            if path:
                paths.append(path)
        return paths

    def extract_quoted_paths(self, text: str) -> list[str]:
        if not text:
            return []
        matches = re.findall(r'"([^"]+)"|\'([^\']+)\'', text)
        return [left or right for left, right in matches if left or right]

    def resolve_existing_file(self, value: object) -> Path | None:
        raw_path = str(value or "").strip()
        if not raw_path or raw_path.startswith(PLACEHOLDER_PREFIX):
            return None
        if self.is_remote_sandbox_path(raw_path):
            return None
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = self.root_dir / candidate
        try:
            resolved = candidate.resolve()
        except OSError:
            resolved = None
        if resolved is None or not resolved.exists() or not resolved.is_file():
            resolved = self.resolve_remote_upload_file(raw_path)
            if resolved is None:
                return None
        try:
            file_size = resolved.stat().st_size
        except OSError:
            return None
        if file_size > self.max_transfer_bytes:
            raise SandboxClientError(f"文件过大，无法转发到沙箱: {resolved}")
        return resolved

    def is_remote_sandbox_path(self, raw_path: str) -> bool:
        health = self.environment_info()
        remote_paths = [
            str(health.get("root") or "").strip(),
            str(health.get("upload_dir") or "").strip(),
            str(health.get("output_dir") or "").strip(),
        ]
        try:
            candidate = Path(raw_path).resolve()
        except OSError:
            return False
        for remote_path in remote_paths:
            if not remote_path:
                continue
            try:
                remote_root = Path(remote_path).resolve()
            except OSError:
                continue
            if candidate == remote_root or remote_root in candidate.parents:
                return True
        return False

    def replace_paths_with_placeholders(self, value: Any, path_map: JsonDict) -> Any:
        if isinstance(value, dict):
            return {key: self.replace_paths_with_placeholders(item, path_map) for key, item in value.items()}
        if isinstance(value, list):
            return [self.replace_paths_with_placeholders(item, path_map) for item in value]
        if isinstance(value, str):
            replaced = value
            for source_path, placeholder in path_map.items():
                replaced = replaced.replace(source_path, str(placeholder))
                replaced = replaced.replace(str(Path(source_path)), str(placeholder))
            return replaced
        return value

    def resolve_remote_upload_file(self, raw_path: str) -> Path | None:
        health = self.environment_info()
        upload_dir = str(health.get("upload_dir") or "").strip()
        if not upload_dir:
            root_dir = str(health.get("root") or "").strip()
            upload_dir = str(Path(root_dir) / "uploads") if root_dir else ""
        if not upload_dir:
            return None
        try:
            remote_candidate = Path(raw_path).resolve()
            remote_upload_dir = Path(upload_dir).resolve()
        except OSError:
            return None
        if remote_candidate.parent != remote_upload_dir:
            return None
        local_candidate = (UPLOAD_DIR / remote_candidate.name).resolve()
        if not local_candidate.exists() or not local_candidate.is_file():
            local_candidate = self.resolve_prefixed_remote_upload_name(remote_candidate.name)
            if local_candidate is None:
                return None
        return local_candidate

    def resolve_prefixed_remote_upload_name(self, filename: str) -> Path | None:
        parts = str(filename or "").split("_", 1)
        if len(parts) != 2:
            return None
        local_candidate = (UPLOAD_DIR / parts[1]).resolve()
        if local_candidate.exists() and local_candidate.is_file():
            return local_candidate
        return None

    def prepare_remote_write_path(self, arguments: JsonDict) -> JsonDict:
        arguments = self.rewrite_write_content_paths(arguments)
        path = str(arguments.get("path") or "").strip()
        if not path:
            return arguments
        health = self.environment_info()
        remote_root = str(health.get("root") or "").strip()
        if remote_root:
            try:
                remote_path = Path(path).resolve()
                remote_root_path = Path(remote_root).resolve()
                if remote_path == remote_root_path or remote_root_path in remote_path.parents:
                    arguments["path"] = str(remote_path)
                    return arguments
            except OSError:
                pass
        arguments["path"] = safe_filename(Path(path).name)
        return arguments

    def rewrite_write_content_paths(self, arguments: JsonDict) -> JsonDict:
        content = arguments.get("content")
        if not isinstance(content, str) or not content:
            return arguments
        rewritten = content
        for candidate in self.extract_candidate_paths_from_text(content):
            local_path = self.resolve_existing_file(candidate)
            if not local_path:
                continue
            remote_runtime_path = self.remote_uploaded_runtime_path(local_path)
            if not remote_runtime_path:
                continue
            rewritten = rewritten.replace(candidate, remote_runtime_path)
        arguments["content"] = rewritten
        return arguments

    def extract_candidate_paths_from_text(self, text: str) -> list[str]:
        candidates: list[str] = []
        candidates.extend(self.extract_quoted_paths(text))
        candidates.extend(re.findall(r"[A-Za-z]:\\\\[^\r\n\"']+", text))
        unique: list[str] = []
        seen: set[str] = set()
        for item in candidates:
            normalized = str(item or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(normalized)
        return unique

    def remote_uploaded_runtime_path(self, value: object) -> str:
        local_path = self.resolve_existing_file(value)
        if not local_path:
            return ""
        health = self.environment_info()
        upload_dir = str(health.get("upload_dir") or "").strip()
        if not upload_dir:
            root_dir = str(health.get("root") or "").strip()
            upload_dir = str(Path(root_dir) / "uploads") if root_dir else ""
        if not upload_dir:
            return ""
        file_id = hashlib.sha256(str(local_path).encode("utf-8")).hexdigest()[:16]
        filename = safe_filename(local_path.name)
        return str(Path(upload_dir) / f"{file_id}_{filename}")

    def normalize_remote_cwd(self, arguments: JsonDict) -> JsonDict:
        cwd = str(arguments.get("cwd") or "").strip()
        if not cwd:
            return arguments
        health = self.environment_info()
        remote_root = str(health.get("root") or "").strip()
        if not remote_root:
            return arguments
        remote_upload_dir = str(health.get("upload_dir") or "").strip()
        if cwd == str(self.root_dir):
            arguments["cwd"] = remote_root
            return arguments
        try:
            cwd_path = Path(cwd).resolve()
            local_root = self.root_dir.resolve()
        except OSError:
            arguments["cwd"] = remote_root
            return arguments
        if cwd_path == local_root or local_root in cwd_path.parents:
            relative = cwd_path.relative_to(local_root)
            arguments["cwd"] = str((Path(remote_root) / relative).resolve())
            return arguments
        if remote_upload_dir:
            try:
                remote_upload_path = Path(remote_upload_dir).resolve()
                if cwd_path == remote_upload_path or remote_upload_path in cwd_path.parents:
                    arguments["cwd"] = str(cwd_path)
                    return arguments
            except OSError:
                pass
        arguments["cwd"] = remote_root
        return arguments

    def remote_materialized_path(self, value: object) -> str:
        local_path = self.resolve_existing_file(value)
        if not local_path:
            return str(value or "").strip()
        health = self.environment_info()
        upload_dir = str(health.get("upload_dir") or "").strip()
        if not upload_dir:
            root_dir = str(health.get("root") or "").strip()
            upload_dir = str(Path(root_dir) / "uploads") if root_dir else ""
        if not upload_dir:
            return str(local_path)
        file_id = hashlib.sha256(str(local_path).encode("utf-8")).hexdigest()[:16]
        filename = safe_filename(local_path.name)
        return str(Path(upload_dir) / f"{file_id}_{filename}")

    def encode_file(self, path: Path) -> str:
        if path.stat().st_size > self.max_transfer_bytes:
            raise SandboxClientError(f"文件过大，无法转发到沙箱: {path}")
        return base64.b64encode(path.read_bytes()).decode("ascii")


def safe_filename(filename: str) -> str:
    cleaned = Path(filename or "").name.replace("\\", "_").strip()
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", cleaned).strip("._ ")
    return cleaned or "output.txt"
