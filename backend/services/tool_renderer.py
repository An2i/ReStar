from backend.data_structures import JsonDict
from backend.services.tool_definition import ToolDefinition


class ToolRenderer:
    """Presentation, transcript, and search text helpers for tool activity."""

    preview_chars = 1600

    def render_tool_use(self, definition: ToolDefinition, arguments: JsonDict) -> JsonDict:
        summary = self._argument_summary(definition, arguments)
        
        return {
            "title": definition.name,
            "subtitle": definition.description,
            "summary": summary,
            "risk": definition.permission.get("risk", ""),
            "search_text": " ".join(
                part
                for part in [
                    definition.name,
                    definition.command_line,
                    definition.description,
                    definition.search_hint,
                    summary,
                ]
                if part
            ),
        }

    def render_tool_result(
        self,
        definition: ToolDefinition,
        result: JsonDict,
        status: str = "success",
    ) -> JsonDict:
        summary = self._result_summary(definition, result, status)
        return {
            "title": definition.name,
            "status": status,
            "summary": summary,
            "transcript": self._transcript(definition, result, status),
            "search_text": self.extract_search_text(definition, result),
        }

    def render_error(self, definition: ToolDefinition, error: object) -> JsonDict:
        message = str(error)
        return {
            "title": definition.name,
            "status": "failed",
            "summary": message,
            "transcript": f"{definition.name} failed: {message}",
            "search_text": f"{definition.name} {message}",
        }
    
    # 从工具执行结果中提取“可搜索文本”
    # 根据不同工具类型，提取不同的重要字段。返回：一个拼接后的字符串
    def extract_search_text(self, definition: ToolDefinition, result: JsonDict) -> str:
        if definition.command_line == "builtin:read_file":
            return " ".join(
                str(result.get(key) or "")
                for key in ("path", "sha256")
                if result.get(key)
            )
        if definition.command_line == "builtin:write_file":
            return str(result.get("path") or "")
        if "stdout" in result or "stderr" in result:
            return " ".join(
                str(result.get(key) or "")[: self.preview_chars]
                for key in ("command_line", "stdout", "stderr")
                if result.get(key)
            )
        return " ".join(str(value) for value in result.values() if value not in (None, ""))

    def _argument_summary(self, definition: ToolDefinition, arguments: JsonDict) -> str:
        if definition.command_line == "builtin:read_file":
            return f"读取 {arguments.get('path', '')}"
        if definition.command_line == "builtin:write_file":
            return f"写入 {arguments.get('path', '')}"
        if definition.command_line == "builtin:execute_bash":
            return str(arguments.get("command_line") or arguments.get("command") or "")
        if arguments:
            visible = {
                key: value
                for key, value in arguments.items()
                if str(key).lower() not in {"api_key", "token", "cookie", "password", "secret"}
            }
            return str(visible)
        return definition.command_line

    def _result_summary(self, definition: ToolDefinition, result: JsonDict, status: str) -> str:
        if status != "success":
            if "exit_code" in result:
                timeout_text = " timeout" if result.get("timed_out") else ""
                return f"exit_code={result.get('exit_code')}{timeout_text}"
            return str(result.get("error") or "工具执行失败")
        if definition.command_line == "builtin:read_file":
            return (
                f"{result.get('path', '')} "
                f"size={result.get('size', 0)} "
                f"preview={result.get('preview_bytes', 0)} bytes"
            )
        if definition.command_line == "builtin:write_file":
            return f"{result.get('path', '')} 写入 {result.get('bytes_written', 0)} bytes"
        if "exit_code" in result:
            timeout_text = " timeout" if result.get("timed_out") else ""
            return f"exit_code={result.get('exit_code')}{timeout_text}"
        return "工具执行完成"

    def _transcript(self, definition: ToolDefinition, result: JsonDict, status: str) -> str:
        summary = self._result_summary(definition, result, status)
        if "stdout" in result or "stderr" in result:
            stdout = str(result.get("stdout") or "")[-self.preview_chars :]
            stderr = str(result.get("stderr") or "")[-self.preview_chars :]
            return (
                f"{definition.name}: {summary}\n"
                f"stdout:\n{stdout}\n"
                f"stderr:\n{stderr}"
            ).strip()
        return f"{definition.name}: {summary}"
