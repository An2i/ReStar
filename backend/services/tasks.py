import json
import ast
import html
import os
import platform
import queue
import re
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Callable
import copy

from fastapi import HTTPException

from backend.config import REPORT_DIR, ROOT_DIR, TASK_RUNTIME_DIR
from backend.data_structures import (
    JsonDict,
    build_llm_snapshot_record,
    build_task_snapshot_record,
    build_tool_execution_record,
)
from backend.services.sandbox_client import SANDBOX_TASK_TYPES, SandboxClientError
from backend.services.session_memory import (
    MemoryManager,
    SessionStorage,
    compact_task_snapshot,
)
from backend.services.threat_intelligence import fetch_file_report
from backend.services.tool_system import ToolSystem
from backend.utils import utc_now, is_valid_json

from backend.services.contextManager import ContextManager
from backend.services.llm_models import ModelManager
from backend.services.llm_models import call_model
from backend.services.report_renderer import (
    is_structured_report_task,
    normalize_structured_report,
    render_structured_report_html,
    structured_report_instruction,
    structured_report_schema,
    structured_report_summary,
)

DEBUG_LOG_PREFIX = "[TASK_DEBUG]"

def debug_preview(value: object, limit: int = 600) -> str:
    text = str(value).replace("\r", "\\r").replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<{len(text)} chars>"


def normalize_debug_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def summarize_tool_pattern_from_values(tool_name: str, arguments: object) -> str:
    if not isinstance(arguments, dict):
        return tool_name
    command = normalize_debug_text(
        arguments.get("command") or arguments.get("command_line") or ""
    )
    path = normalize_debug_text(
        arguments.get("path") or arguments.get("file_path") or ""
    )
    if command:
        lowered_command = command.lower()
        if "get-filehash" in lowered_command:
            return f"{tool_name}:op=file_hash"
        if any(
            marker in lowered_command
            for marker in (
                "get-itemproperty",
                "get-item ",
                "get-childitem",
                "get-content",
            )
        ):
            if "get-content" in lowered_command and "encoding byte" in lowered_command:
                return f"{tool_name}:op=binary_read"
            if "get-childitem" in lowered_command:
                return f"{tool_name}:op=directory_list"
            if "get-itemproperty" in lowered_command or "get-item " in lowered_command:
                return f"{tool_name}:op=file_metadata"
            return f"{tool_name}:op=file_inspect"
        if "format-hex" in lowered_command:
            return f"{tool_name}:op=hex_dump"
        if (
            "select-string" in lowered_command
            or "findstr" in lowered_command
            or "strings" in lowered_command
        ):
            return f"{tool_name}:op=string_search"
        if "resolve-path" in lowered_command:
            return f"{tool_name}:op=path_resolve"
        if "python" in lowered_command:
            return f"{tool_name}:op=python_probe"
        if lowered_command.startswith("& "):
            return f"{tool_name}:op=direct_exec"
        return f"{tool_name}:op={lowered_command[:40]}"
    if path:
        return f"{tool_name}:op=path_read"
    return tool_name



def diff_llm_debug_summary(
    previous: dict[str, object] | None, current: dict[str, object]
) -> dict[str, object]:
    if not previous:
        return {
            "assistant_changed": bool(current.get("assistant")),
            "reasoning_changed": bool(current.get("reasoning")),
            "tool_names_changed": bool(current.get("tool_names")),
            "new_tools": current.get("tool_names", []),
            "removed_tools": [],
            "repeated_signatures": [],
            "repeated_patterns": [],
        }
    prev_assistant = str(previous.get("assistant") or "")
    prev_reasoning = str(previous.get("reasoning") or "")
    prev_tools = list(previous.get("tool_names") or [])
    prev_signatures = list(previous.get("tool_signatures") or [])
    prev_patterns = list(previous.get("tool_patterns") or [])
    curr_tools = list(current.get("tool_names") or [])
    curr_signatures = list(current.get("tool_signatures") or [])
    curr_patterns = list(current.get("tool_patterns") or [])
    return {
        "assistant_changed": prev_assistant != str(current.get("assistant") or ""),
        "reasoning_changed": prev_reasoning != str(current.get("reasoning") or ""),
        "tool_names_changed": prev_tools != curr_tools,
        "new_tools": [tool for tool in curr_tools if tool and tool not in prev_tools],
        "removed_tools": [
            tool for tool in prev_tools if tool and tool not in curr_tools
        ],
        "repeated_signatures": [
            sig for sig in curr_signatures if sig and sig in prev_signatures
        ],
        "repeated_patterns": [
            pattern for pattern in curr_patterns if pattern and pattern in prev_patterns
        ],
    }


def looks_like_binary_preview(text: object) -> bool:
    value = str(text or "")
    if not value:
        return False
    if "This program cannot be run in DOS mode." in value:
        return True
    non_printable = sum(
        1
        for ch in value[:400]
        if ch not in "\r\n\t" and (ord(ch) < 32 or ord(ch) == 127 or ord(ch) == 65533)
    )
    sample_len = max(1, min(len(value), 400))
    return (non_printable / sample_len) > 0.08


def summarize_tool_pattern(tool_result: object) -> str:
    if not isinstance(tool_result, dict):
        return ""
    tool_name = str(tool_result.get("tool") or "").strip()
    execution = (
        tool_result.get("execution")
        if isinstance(tool_result.get("execution"), dict)
        else {}
    )
    arguments = (
        execution.get("arguments")
        if isinstance(execution.get("arguments"), dict)
        else {}
    )
    return summarize_tool_pattern_from_values(tool_name, arguments)


def compress_tooluse_for_context(tool_name: str, arguments: object) -> str:
    if not isinstance(arguments, dict):
        return tool_name
    command = normalize_debug_text(
        arguments.get("command") or arguments.get("command_line") or ""
    )
    path = normalize_debug_text(
        arguments.get("path") or arguments.get("file_path") or ""
    )
    if command:
        if len(command) > 220:
            command = command[:220] + " ... [script/command truncated]"
        return f"{tool_name} command: {command}"
    if path:
        return f"{tool_name} path: {path}"
    compact_args = normalize_debug_text(arguments)
    if len(compact_args) > 220:
        compact_args = compact_args[:220] + " ... [args truncated]"
    return f"{tool_name} args: {compact_args}"


def summarize_context_tail(messages: object, limit: int = 4) -> list[str]:
    if not isinstance(messages, list):
        return []
    summary: list[str] = []
    for message in messages[-limit:]:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        content = normalize_debug_text(message.get("content") or "")
        if len(content) > 160:
            content = content[:160] + " ..."
        summary.append(f"{role}: {content}")
    return summary


def summarize_execution_error(tool_result: object) -> str:
    if not isinstance(tool_result, dict):
        return normalize_debug_text(tool_result)[:300]
    execution = (
        tool_result.get("execution")
        if isinstance(tool_result.get("execution"), dict)
        else {}
    )
    if isinstance(execution, dict):
        error = execution.get("error")
        if error:
            return normalize_debug_text(error)[:300]
        nested = (
            execution.get("result") if isinstance(execution.get("result"), dict) else {}
        )
        stderr = nested.get("stderr") if isinstance(nested, dict) else ""
        stdout = nested.get("stdout") if isinstance(nested, dict) else ""
        if stderr:
            return normalize_debug_text(stderr)[:300]
        if stdout:
            return normalize_debug_text(stdout)[:300]
    return normalize_debug_text(tool_result)[:300]


def render_inline_html(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    return escaped


def markdown_like_to_html(text: str) -> str:
    lines = str(text or "").splitlines()
    html_parts: list[str] = []
    in_code = False
    code_lines: list[str] = []
    table_rows: list[list[str]] = []
    paragraph_lines: list[str] = []

    def flush_paragraph() -> None:
        nonlocal paragraph_lines
        if paragraph_lines:
            html_parts.append(f"<p>{render_inline_html(' '.join(paragraph_lines))}</p>")
            paragraph_lines = []

    def flush_table() -> None:
        nonlocal table_rows
        if not table_rows:
            return
        rows = [row for row in table_rows if row]
        if len(rows) < 1:
            table_rows = []
            return
        header = rows[0]
        body = rows[1:]
        parts = [
            '<div class="report-table-wrap"><table class="report-table">',
            "<thead><tr>",
        ]
        parts.extend(f"<th>{render_inline_html(cell)}</th>" for cell in header)
        parts.append("</tr></thead>")
        if body:
            parts.append("<tbody>")
            for row in body:
                parts.append("<tr>")
                parts.extend(f"<td>{render_inline_html(cell)}</td>" for cell in row)
                parts.append("</tr>")
            parts.append("</tbody>")
        parts.append("</table></div>")
        html_parts.append("".join(parts))
        table_rows = []

    for raw_line in lines:
        line = raw_line.rstrip("\n")
        stripped = line.strip()
        if stripped.startswith("```"):
            flush_paragraph()
            flush_table()
            if in_code:
                html_parts.append(
                    f'<pre class="report-code"><code>{html.escape(chr(10).join(code_lines))}</code></pre>'
                )
                code_lines = []
                in_code = False
            else:
                in_code = True
            continue
        if in_code:
            code_lines.append(line)
            continue
        if stripped.startswith("|") and stripped.endswith("|"):
            flush_paragraph()
            cells = [cell.strip() for cell in stripped.strip("|").split("|")]
            if cells and not all(
                re.fullmatch(r"[:\-\s]+", cell or "") for cell in cells
            ):
                table_rows.append(cells)
            continue
        flush_table()
        if not stripped:
            flush_paragraph()
            continue
        heading_match = re.fullmatch(r"(#{1,6})\s+(.*)", stripped)
        if heading_match:
            flush_paragraph()
            level = len(heading_match.group(1))
            html_parts.append(
                f"<h{level}>{render_inline_html(heading_match.group(2).strip())}</h{level}>"
            )
            continue
        bullet_match = re.fullmatch(r"[-*]\s+(.*)", stripped)
        if bullet_match:
            flush_paragraph()
            html_parts.append(
                f'<p class="report-bullet">• {render_inline_html(bullet_match.group(1))}</p>'
            )
            continue
        paragraph_lines.append(stripped)

    if in_code:
        html_parts.append(
            f'<pre class="report-code"><code>{html.escape(chr(10).join(code_lines))}</code></pre>'
        )
    flush_table()
    flush_paragraph()
    return (
        "\n".join(html_parts)
        if html_parts
        else f"<pre>{html.escape(str(text or ''))}</pre>"
    )


TASK_TYPE_DEFINITIONS: dict[str, dict[str, str]] = {
    "evasion-generation": {
        "name": "免杀生成",
        "system_prompt": (
            "你是CodeX平台中的免杀生成任务agent。你需要在合法授权的安全测试场景下，"
            "围绕输入样本或需求制定分析、变形、验证计划。禁止输出可直接用于未授权攻击的操作，"
            "必须优先使用平台工具获取事实，再给出下一步决策。"
        ),
        "user_prompt": (
            "任务类型：免杀生成。\n"
            "请根据用户输入、上传文件和已有工具，完成任务环境初始化、样本信息收集、"
            "生成策略规划和结果总结。\n\n"
            "任务输入：\n{payload_json}"
        ),
    },
    "vulnerability-mining": {
        "name": "漏洞挖掘",
        "system_prompt": (
            """请你充当一名资深软件漏洞挖掘专家，帮助我分析目标程序或代码中的潜在安全漏洞。你的任务是对目标程序进行逆向工程分析，最终将所有内容整理输出一份分析报告。"""
        ),
        "user_prompt": (
            "请帮我对该程序进行漏洞挖掘，待分析程序路径：{target_path}。\n"
            "请分析目标中的攻击面、危险函数、输入处理、边界条件和可验证线索，必要时调用工具读取文件或执行受控命令。\n"
            "如果没有完成所有分析过程，必须要在回复中给出下一步指示和tool调用。\n"
            "不要假设提示词中已经包含完整文件内容；如需文件头、元数据、字符串、目录信息或命令执行结果，请通过工具按需获取。\n\n"
        ),
    },
    "sample-analysis": {
        "name": "样本分析",
        "system_prompt": (
            """请你充当一名资深软件安全研究员和恶意样本逆向分析专家，帮助我分析一个可疑样本。
我提供了样本文件，你的任务是：
1. 判断该样本是否为恶意样本，并给出恶意性结论和置信度。
2. 分析样本的基础信息，包括文件类型、哈希、架构、编译时间、数字签名、节区信息等。
3. 进行静态分析，识别可疑字符串、导入函数、加壳、混淆、反调试、反虚拟机等特征。
4. 进行动态行为分析，梳理样本运行后的进程行为、文件行为、注册表行为、网络行为、权限行为和内存行为。
5. 分析样本使用的关键技术，例如：
   - 加壳 / 混淆
   - 反调试 / 反沙箱 / 反虚拟机
   - 进程注入
   - 持久化
   - 权限提升
   - C2 通信
   - 信息窃取
   - 下载执行
   - 横向移动
   - 防御规避
6. 汇总样本的所有恶意行为，并为每项行为提供证据、影响和置信度。
7. 提取 IOC，包括哈希、IP、域名、URL、文件路径、注册表项、互斥体、User-Agent 等。
8. 将样本行为映射到 MITRE ATT&CK，并说明映射理由。
9. 给出检测、防护、清理和应急处置建议。
10. 明确区分“已确认结论”“合理推测”“待验证内容”，不得编造不存在的行为。
最终将所有内容整理输出一份分析报告。
"""
        ),
        "user_prompt": (
            "请帮我对样本进行分析，待分析样本的路径：{target_path}。\n"
            "请围绕样本元数据、逆向工程分析结果等证据形成分析结论，并指出后续可接入的深度分析工具。\n"
            "不要假设提示词中已经包含完整样本内容；如需文件头、哈希、字符串、静态特征或动态行为证据，请通过工具按需获取。\n"
            "如果没有完成所有分析过程，必须要在回复中给出下一步指示和tool调用。\n"
        ),
    },
    "code-audit": {
        "name": "代码审计",
        "system_prompt": (
            """请你充当一名资深代码安全审计专家，帮助我对代码进行安全审计。
我会提供以下一种或多种材料：
- 源代码片段
- 项目目录结构
- 配置文件
- 路由 / 接口定义
- 依赖清单
- 关键业务逻辑说明
- 报错信息或运行日志

你的任务是：

1. 判断代码中是否存在安全漏洞或高风险实现。
2. 分析漏洞类型、代码位置、触发条件、影响范围和风险等级。
3. 对用户输入、权限校验、认证逻辑、敏感操作、文件读写、数据库操作、命令执行、网络请求、模板渲染等关键点进行审计。
4. 判断漏洞是否真实可达，避免仅凭危险函数误报。
5. 明确区分：
   - 确认漏洞
   - 疑似风险
   - 安全加固建议
6. 针对每个问题提供具体修复建议，必要时给出安全代码示例。
7. 给出复测方法，说明如何验证漏洞是否修复。
8. 不编造代码中不存在的问题；如信息不足，请说明需要补充哪些上下文。

请按照以下格式输出：
# 代码安全审计报告
## 1. 审计结论
- 整体风险等级：
- 是否发现确认漏洞：
- 主要风险概述：
- 需要优先修复的问题：
## 2. 审计范围
- 编程语言：
- 框架 / 技术栈：
- 审计文件 / 函数：
- 已知上下文：
- 缺失上下文：
## 3. 漏洞与风险列表
| 编号 | 类型 | 位置 | 风险等级 | 状态 | 简要说明 |
|---|---|---|---|---|---|
| V-001 | 示例：SQL 注入 | 文件/函数/行号 | 高 | 确认漏洞 | 示例说明 |
## 4. 详细漏洞分析
### V-001：漏洞名称
#### 4.1 漏洞位置
- 文件：
- 函数：
- 行号：
- 相关代码：
#### 4.2 漏洞成因
说明该问题为什么存在。
#### 4.3 触发条件
说明需要什么输入、权限、配置或环境条件才能触发。
#### 4.4 影响范围
说明可能造成的数据泄露、权限提升、代码执行、业务绕过等影响。
#### 4.5 风险等级
- 等级：
- 判断依据：
#### 4.6 修复建议
给出具体修复方案，必要时提供安全代码示例。
#### 4.7 复测方法
说明如何验证该问题已修复。
## 5. 疑似风险
列出因上下文不足暂时无法确认的问题，并说明需要补充的信息。
## 6. 安全加固建议
- 输入校验：
- 权限控制：
- 错误处理：
- 日志审计：
- 密钥管理：
- 依赖安全：
- 配置安全：

## 7. 总结
给出最终安全结论和修复优先级。"""
        ),
        "user_prompt": (
            "任务类型：代码审计。\n"
            "请梳理代码结构、关键入口、数据流和可疑实现，"
            "并通过工具结果迭代形成审计结论。\n\n"
            "任务输入：\n{payload_json}"
        ),
    },
}


TASK_TYPE_ALIASES = {
    "evasion": "evasion-generation",
    "免杀生成": "evasion-generation",
    "vulnerability": "vulnerability-mining",
    "vulnerability-analysis": "vulnerability-mining",
    "漏洞挖掘": "vulnerability-mining",
    "漏洞分析": "vulnerability-mining",
    "sample": "sample-analysis",
    "sample-analysis": "sample-analysis",
    "样本分析": "sample-analysis",
    "program-analysis": "sample-analysis",
    "code": "code-audit",
    "code-audit": "code-audit",
    "代码审计": "code-audit",
}


def normalize_task_type(task_type: str) -> str:
    normalized = str(task_type or "").strip()
    return TASK_TYPE_ALIASES.get(
        normalized, TASK_TYPE_ALIASES.get(normalized.lower(), normalized)
    )


def extract_target_path_from_payload(payload: dict[str, object]) -> str:
    file_info = payload.get("file_info")
    if isinstance(file_info, dict):
        for key in ("path", "file_path", "target_path", "sample_path"):
            value = file_info.get(key)
            if value:
                return str(value)
    for key in ("file_path", "target_path", "sample_path", "path"):
        value = payload.get(key)
        if value:
            return str(value)
    return ""


def parese_LLMDecsion(
    provider: str, purpose: str, tooluse: dict[str, object]
) -> JsonDict:
    """{'source': 'local', 'name': '', 'purpose': '', 'arguments': {}, }"""
    decsion = {
        "id": "",
        "name": "",
        "purpose": purpose,
        "arguments": "",
    }
    if provider == "openai":
        decsion["name"] = tooluse["function"]["name"]
        decsion["id"] = tooluse["id"]
        decsion["arguments"] = parse_tool_arguments(tooluse["function"].get("arguments"))
    if provider == "deepseek":
        decsion["name"] = tooluse["function"]["name"]
        decsion["id"] = tooluse["id"]
        decsion["arguments"] = parse_tool_arguments(tooluse["function"].get("arguments"))
    # if provider == "claude":
    #     return "claude-3-5-haiku-latest"
    # if provider == "gemini":
    #     return "gemini-1.5-flash"
    return decsion


def parse_tool_arguments(value: object) -> JsonDict:
    if isinstance(value, dict):
        return value
    if value in (None, ""):
        return {}
    text = str(value).strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        try:
            parsed = ast.literal_eval(text)
        except (SyntaxError, ValueError):
            parsed = {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_toolresult(provider: str, result: JsonDict, tooluse_id: str) -> JsonDict:
    toolresult = {
        "role": "tool",
        "tool_call_id": tooluse_id,
        "content": "",
        "status": "success",
    }

    if provider == "deepseek" or provider == "openai":
        execution = result.get("execution") if isinstance(result, dict) else {}
        execution = execution if isinstance(execution, dict) else {}
        nested_result = (
            execution.get("result") if isinstance(execution.get("result"), dict) else {}
        )
        status_text = str(
            result.get("status")
            or execution.get("status")
            or nested_result.get("status")
            or ""
        ).lower()
        stdout = str(nested_result.get("stdout") or "").strip()
        stderr = str(nested_result.get("stderr") or "").strip()
        exit_code = nested_result.get("exit_code")
        failed_by_exit_code = "exit_code" in nested_result and exit_code not in (None, 0)
        error_text = str(
            result.get("error")
            or result.get("detail")
            or execution.get("error")
            or execution.get("detail")
            or nested_result.get("error")
            or nested_result.get("detail")
            or ""
        ).strip()
        if (
            failed_by_exit_code
            or error_text
            or (status_text in {"failed", "fail", "error"} and not stdout)
        ):
            toolresult["status"] = "fail"

        if stdout:
            toolresult["content"] = stdout
        elif stderr:
            toolresult["content"] = "Error: " + stderr
            toolresult["status"] = "fail"
        elif error_text:
            toolresult["content"] = "Error: " + error_text
        elif nested_result:
            toolresult["content"] = json.dumps(
                nested_result, ensure_ascii=False, default=str
            )[:4000]
        elif execution:
            toolresult["content"] = json.dumps(
                execution, ensure_ascii=False, default=str
            )[:4000]
        else:
            toolresult["content"] = json.dumps(result, ensure_ascii=False, default=str)[
                :4000
            ]
    # print(toolresult)
    return toolresult


class Task:
    max_iterations = 999
    context_char_limit = 18000
    message_char_limit = 5000
    decision_read_max_bytes = 8192
    tool_context_text_limit = 1200
    tool_context_stream_limit = 2000
    tool_context_hex_limit = 512
    llm_request_timeout_seconds = 45.0

    def __init__(
        self,
        task_type: str,
        payload: dict[str, object],
        tool_system: ToolSystem,
        session_storage: SessionStorage,
        memory_manager: MemoryManager,
        model_manager: ModelManager,
        skill_system: Any | None = None,
        threat_intelligence_resolver: Callable[[], JsonDict | None] | None = None,
    ) -> None:
        normalized_type = normalize_task_type(task_type)
        if normalized_type not in TASK_TYPE_DEFINITIONS:
            raise HTTPException(status_code=400, detail="任务类型不支持")

        definition = TASK_TYPE_DEFINITIONS[normalized_type]
        payload_json = json.dumps(payload, ensure_ascii=False, indent=2)

        self.id = uuid.uuid4().hex
        self.task_type = normalized_type
        self.task_name = definition["name"]
        self.payload = payload
        self.execution_mode = self.resolve_execution_mode(payload)
        self.tool_system = tool_system
        self.sandbox_client = self.get_active_sandbox_client()
        self.sandbox_disabled_reason = ""

        if self.sandbox_client:
            try:
                target_path = (
                    self.find_prompt_source_path() or self.find_prompt_file_path()
                )
            except SandboxClientError as exc:
                self.sandbox_disabled_reason = str(exc)
                self.sandbox_client = None
                target_path = extract_target_path_from_payload(payload)
        else:
            target_path = extract_target_path_from_payload(payload)
        self.system_prompt = definition["system_prompt"]
        self.user_prompt = definition["user_prompt"].format(
            payload_json=payload_json,
            target_path=target_path or "未提供目标程序路径",
        )

        self.session_storage = session_storage
        self.memory_manager = memory_manager
        self.model_manager = model_manager
        self.skill_system = skill_system
        self.threat_intelligence_resolver = threat_intelligence_resolver
        self.triggered_skill_ids: set[str] = set()
        self.allocation_error = ""
        self.session_id = self.session_storage.create_session(
            "task",
            {
                "task_id": self.id,
                "task_type": self.task_type,
                "task_name": self.task_name,
            },
        )
        self.status = "queued"
        self.created_at = utc_now()
        self.updated_at = self.created_at
        self.started_at = ""
        self.completed_at = ""
        self.iteration_count = 0
        self.tool_results: list[dict[str, object]] = []
        self.decisions: list[dict[str, object]] = []
        self.pending_tool_retry: list[dict[str, object]] = []

        self.context = ContextManager(session_storage)

        self.result: dict[str, object] = {}
        self.error = ""
        self.report_path = ""
        self.done_event = threading.Event()
        self.lock = threading.Lock()

    def resolve_execution_mode(self, payload: dict[str, object]) -> str:
        mode = str(
            payload.get("execution_mode")
            or payload.get("task_execution_mode")
            or payload.get("handler")
            or os.getenv("CODEX_TASK_EXECUTION_MODE")
            or "legacy"
        ).strip().lower()
        if mode in {"legacy", "local", "task_loop", "original"}:
            return "legacy"
        if mode in {"agent", "agent.py", "claude", "claude-code", "claude_code"}:
            return "agent"
        if payload.get("use_agent") is False:
            return "legacy"
        return "agent"

    def snapshot(self, include_details: bool = True) -> dict[str, object]:
        with self.lock:
            snapshot = build_task_snapshot_record(
                task_id=self.id,
                task_type=self.task_type,
                task_name=self.task_name,
                session_id=self.session_id,
                status=self.status,
                created_at=self.created_at,
                updated_at=self.updated_at,
                started_at=self.started_at,
                completed_at=self.completed_at,
                iteration_count=self.iteration_count,
                llm=self.llm_snapshot(),
                tool_result_count=len(self.tool_results),
                last_decision=self.decisions[-1] if self.decisions else {},
                result=self.result,
                error=self.error,
                report_path=self.report_path,
            )
            if self.sandbox_disabled_reason:
                snapshot["sandbox"] = {
                    "enabled_for_task": True,
                    "mode": "local_fallback",
                    "reason": self.sandbox_disabled_reason,
                }
            file_info = (
                self.payload.get("file_info")
                if isinstance(self.payload.get("file_info"), dict)
                else {}
            )
            if file_info:
                snapshot["file_info"] = dict(file_info)
            if include_details:
                snapshot["decisions"] = list(self.decisions)
                snapshot["tool_results"] = list(self.tool_results)
        if include_details:
            snapshot["runtime_trace"] = self.context_runtime_trace()
            return snapshot
        return compact_task_snapshot(snapshot)

    def context_runtime_trace(self, limit: int = 80) -> list[dict[str, object]]:
        messages = self.context.get_messagesContext().get("messages", [])
        if not isinstance(messages, list):
            return []
        trace: list[dict[str, object]] = []
        generated_at = utc_now()
        for index, message in enumerate(messages[-max(limit, 1):]):
            if not isinstance(message, dict):
                continue
            role = str(message.get("role") or "")
            if role == "assistant" and isinstance(message.get("tool_calls"), list):
                for call_index, tool_call in enumerate(message.get("tool_calls") or []):
                    if not isinstance(tool_call, dict):
                        continue
                    function = (
                        tool_call.get("function")
                        if isinstance(tool_call.get("function"), dict)
                        else {}
                    )
                    trace.append(
                        {
                            "id": str(tool_call.get("id") or f"context-tool-call-{index}-{call_index}"),
                            "type": "tool_call",
                            "tool_call_id": str(tool_call.get("id") or ""),
                            "tool_name": str(function.get("name") or ""),
                            "arguments": function.get("arguments") or {},
                            "content": str(message.get("content") or ""),
                            "created_at": generated_at,
                        }
                    )
            elif role == "tool":
                trace.append(
                    {
                        "id": str(message.get("tool_call_id") or f"context-tool-result-{index}"),
                        "type": "tool_result",
                        "tool_call_id": str(message.get("tool_call_id") or ""),
                        "status": str(message.get("status") or "success"),
                        "content": str(message.get("content") or "")[:2000],
                        "created_at": generated_at,
                    }
                )
            elif role in {"assistant", "user"}:
                content = str(message.get("content") or "").strip()
                if content:
                    trace.append(
                        {
                            "id": f"context-message-{index}",
                            "type": "message",
                            "role": role,
                            "content": content[:1000],
                            "created_at": generated_at,
                        }
                    )
        return trace[-limit:]
    
    def checkCorrectToolUse(self, toolName: str) -> str:
        os_name = platform.system()
        if self.sandbox_client:
            try:
                health = self.sandbox_client.environment_info()
                os_name = str(health.get("os_name") or os_name)
            except Exception:
                pass
        normalized_os = os_name.strip().lower()
        normalized_tool = str(toolName or "").strip().lower()
        if normalized_os == "windows" and normalized_tool == "bash":
            return "PowerShell"
        if normalized_os in {"linux", "ubuntu", "centos", "darwin", "macos", "mac os"} and normalized_tool in {
            "powershell",
        }:
            return "Bash"
        return toolName


    def task_execute(self) -> dict[str, object]:
        try:
            self.mark_status("running")
            self.started_at = utc_now()
            self.init_task_env()

            loop_result = self.normalize_loop_result(self.task_loop())
            # print("----------------finalReport---------------------")
            # print(loop_result)
            self.result = self.compose_task_result(loop_result)
            self.write_report()

            self.memory_manager.add_record(
                title=f"{self.task_name}任务记录 - {self.id}",
                content=(
                    f"任务类型：{self.task_name}\n"
                    f"Task：{self.id}\n"
                    f"Session：{self.session_id}\n"
                    f"报告：{self.report_path}\n"
                    f"摘要：{self.result.get('analysis_result', {}).get('summary', '')}"
                ),
                tags=["task", self.task_type],
                source="task-pool",
            )

            self.mark_status("completed")
        except Exception as exc:
            self.error = str(exc)
            self.mark_status("failed")
            self.session_storage.append_event(
                self.session_id,
                "task_failed",
                {"task_id": self.id, "error": self.error},
                agent_id=self.id,
            )
        finally:
            self.release_llm()
            self.completed_at = utc_now()
            self.updated_at = self.completed_at
            self.done_event.set()
        return self.snapshot()

    def mark_status(self, status: str) -> None:
        with self.lock:
            self.status = status
            self.updated_at = utc_now()

    def normalize_loop_result(self, loop_result: object) -> dict[str, object]:
        if isinstance(loop_result, dict):
            final_report = str(
                loop_result.get("finalReport")
                or loop_result.get("final_report")
                or loop_result.get("assistant_response")
                or ""
            ).strip()
            structured_report = (
                dict(loop_result.get("structuredReport"))
                if isinstance(loop_result.get("structuredReport"), dict)
                else (
                    dict(loop_result.get("structured_report"))
                    if isinstance(loop_result.get("structured_report"), dict)
                    else {}
                )
            )
            try:
                iterations = int(loop_result.get("iterations", self.iteration_count))
            except (TypeError, ValueError):
                iterations = self.iteration_count
            return {
                "finalReport": final_report,
                "structuredReport": structured_report,
                "iterations": max(iterations, self.iteration_count),
            }
        if isinstance(loop_result, str):
            return {
                "finalReport": loop_result.strip(),
                "structuredReport": {},
                "iterations": self.iteration_count,
            }
        return {
            "finalReport": "",
            "structuredReport": {},
            "iterations": self.iteration_count,
        }

    def init_task_env(self) -> None:
        TASK_RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        REPORT_DIR.mkdir(parents=True, exist_ok=True)

        # self.context_messages = [
        #     {"role": "system", "content": self.system_prompt},
        #     {"role": "user", "content": self.user_prompt},
        # ]

        self.context.update_systemContext(
            {"role": "system", "content": self.system_prompt}
        )
        self.context.update_userContext({"role": "user", "content": self.user_prompt})

        self.allocate_llm()
        self.session_storage.append_event(
            self.session_id,
            "task_environment_initialized",
            {
                "task_id": self.id,
                "task_type": self.task_type,
                "task_name": self.task_name,
                "llm": self.llm_snapshot(),
            },
            agent_id=self.id,
        )

    @property
    def llm_pool(self):
        return self.model_manager.llm_pool

    @property
    def llm_selection(self):
        return self.model_manager.llm_selection

    @property
    def llm_platform(self):
        return self.model_manager.llm_platform

    def allocate_llm(self) -> None:
        self.model_manager.allocate_llm()
        self.allocation_error = self.model_manager.allocation_error

    def release_llm(self) -> None:
        self.model_manager.release_llm()

    def llm_snapshot(self) -> dict[str, object]:
        return self.model_manager.llm_snapshot()

    def call_model(
        self,
        provider: str,
        api_key: str,
        messages: object,
        tools: list[JsonDict],
        response_format: JsonDict | None = None,
    ) -> JsonDict:
        return call_model(
            provider,
            api_key,
            self.llm_platform,
            messages,
            tools,
            response_format=response_format,
            timeout_seconds=self.llm_request_timeout_seconds,
        )

    def task_loop(self) -> dict[str, object]:
        if self.execution_mode == "legacy":
            return self.task_loop_legacy()
        return self.task_loop_agent()

    def task_loop_agent(self) -> dict[str, object]:
        from backend.services.agent import run_claude_code_task

        runtime_env = self.build_runtimeEnv_prompt()
        runtime_env_content = (
            str(runtime_env.get("content") or "")
            if isinstance(runtime_env, dict)
            else str(runtime_env or "")
        )
        system_prompt = self.build_dynamic_system_prompt()
        if runtime_env_content:
            system_prompt = f"{system_prompt}\n\n{runtime_env_content}"
        query = self.user_prompt

        self.iteration_count += 1
        self.session_storage.append_event(
            self.session_id,
            "task_loop_agent_started",
            {
                "task_id": self.id,
                "execution_mode": self.execution_mode,
                "command": "claude --dangerously-skip-permissions --append-system-prompt <system_prompt> -p <stdin-query>",
            },
            agent_id=self.id,
        )

        result = run_claude_code_task(
            system_prompt=system_prompt,
            query=query,
            cwd=ROOT_DIR,
            timeout_seconds=3600,
            llm_platform=self.llm_platform,
            provider=self.llm_pool.detect_provider(self.llm_platform)
            if self.llm_pool and self.llm_platform
            else "",
        )
        status = str(result.get("status") or "failed")
        env_debug = (
            result.get("env_debug")
            if isinstance(result.get("env_debug"), dict)
            else {}
        )
        final_report = str(result.get("stdout") or "").strip()
        stderr = str(result.get("stderr") or "").strip()
        if not final_report and stderr:
            final_report = stderr

        decision = {
            "id": f"claude-code-{self.iteration_count}",
            "name": "ClaudeCode",
            "source": "agent.py",
            "purpose": "Delegate task processing to Claude Code CLI",
            "arguments": {
                "cwd": str(result.get("cwd") or ROOT_DIR),
                "command": result.get("command", ""),
                "executable": result.get("executable", ""),
            },
        }
        self.decisions.append(decision)
        self.tool_results.append(
            build_tool_execution_record(
                f"claude-code-{self.iteration_count}",
                "ClaudeCode",
                "Run Claude Code CLI and capture stdout",
                "success" if status == "success" else "failed",
                {
                    "result": {
                        "cwd": result.get("cwd", ""),
                        "executable": result.get("executable", ""),
                        "exit_code": result.get("exit_code"),
                        "stdout": final_report[:4000],
                        "stderr": stderr[:4000],
                        "error": result.get("error", ""),
                        "timed_out": result.get("timed_out", False),
                    }
                },
            )
        )
        self.context.update_userContext({"role": "assistant", "content": final_report})
        self.session_storage.append_event(
            self.session_id,
            "task_loop_agent_completed" if status == "success" else "task_loop_agent_failed",
            {
                "task_id": self.id,
                "exit_code": result.get("exit_code"),
                "stdout_preview": final_report[:1200],
                "stderr_preview": stderr[:1200],
                "error": result.get("error", ""),
                "env_debug": env_debug,
            },
            agent_id=self.id,
        )
        if status != "success":
            failure_detail = str(
                result.get("error")
                or final_report
                or stderr
                or "Claude Code task failed"
            ).strip()
            raise RuntimeError(failure_detail)

        structured_report: JsonDict | None = None
        if is_structured_report_task(self.task_type):
            try:
                structured_report = self.extract_structured_report(final_report)
            except Exception as exc:
                self.session_storage.append_event(
                    self.session_id,
                    "structured_report_failed",
                    {"task_id": self.id, "error": str(exc)},
                    agent_id=self.id,
                )
                structured_report = {}
        return {
            "finalReport": final_report,
            "structuredReport": structured_report or {},
            "iterations": self.iteration_count,
        }

    def extract_structured_report(self, draft_report: str) -> JsonDict:
        file_info = (
            self.payload.get("file_info")
            if isinstance(self.payload.get("file_info"), dict)
            else {}
        )
        try:
            parsed = self.parse_json_from_text(draft_report)
            normalized = normalize_structured_report(self.task_type, parsed, file_info)
            if normalized.get("report_type") == self.task_type:
                return normalized
        except Exception:
            pass
        return self.generate_structured_report(draft_report)

    def task_loop_legacy(self) -> dict[str, object]:
        finalReport = ""
        structuredReport: JsonDict | None = None
        previous_llm_summary: dict[str, object] | None = None
        # decision_prompt = self.build_toolsystem_prompt()
        # self.context.set_systemContext("decision_prompt", decision_prompt)
        runtimeEnv_prompt = self.build_runtimeEnv_prompt()  # 运行时部分提示词
        self.context.set_systemContext("runtime_env", runtimeEnv_prompt)
        # 获取 LLM 平台类型
        provider = self.llm_pool.detect_provider(self.llm_platform)

        #发给LLM的消息
        message_bundle = {}
        try_count = 0

        while True:
            self.iteration_count += 1  # 当前循环次数加 1
            tryFlag = False
            
            # self.context.set_systemContext(
            #     "loop_policy",
            #     self.build_loop_policy_message(),
            # )
            
            # 判断是否发生错误导致需要重试
            if len(self.pending_tool_retry) > 0:
                message_bundle = self.build_retry_message_bundle()
                # self.pending_tool_retry.clear()

                self.pending_tool_retry.clear()
            else:
                # 没有发生错误则需要进行一次上下文压缩，需要对assistant内容进行压缩
                # self.compress_context_if_needed()  # 如果上下文过长，则进行压缩，避免超出模型上下文限制
                # self.fold_context_content()  # 折叠或整理上下文内容，使后续调用 LLM 时更紧凑
                message_bundle = self.context.get_messagesContext()
            

            print("-----------------------request-------------------------------")
            print(message_bundle)

            response = self.call_llm_decision(
                message_bundle
            )  # 调用大模型，让它决定下一步该做什么
            print("---------------------response------------------------------")
            print(response)
            if response.get("error_message"):
                self.session_storage.append_event(
                    self.session_id,
                    "task_loop_llm_error",
                    {
                        "task_id": self.id,
                        "iteration": self.iteration_count,
                        "error": response.get("error_message", ""),
                    },
                    agent_id=self.id,
                )
                raise RuntimeError(str(response.get("error_message") or "LLM call failed"))
            self.apply_response_skills(response)

            tool_calls = (
                response.get("tool_calls")
                if isinstance(response.get("tool_calls"), list)
                else []
            )

            if (not tool_calls) and (response.get("content") is not None) :
                finalReport = str(response["content"] or "").strip()
                if "分析报告" in finalReport and ("完成" in finalReport or "完整的" in finalReport):
                    break

            tool_result_list = []
            executable_tooluses: list[dict[str, object]] = []

            for tooluse in tool_calls:
                if not isinstance(tooluse, dict) or not isinstance(tooluse.get("function"), dict):
                    continue
                function = tooluse["function"]
                function["name"] = self.checkCorrectToolUse(function.get("name", ""))

                if "reasoning_content" in response:
                    decision = parese_LLMDecsion(provider, response["reasoning_content"], tooluse)
                elif "content" in response:
                    decision = parese_LLMDecsion(provider, response["content"], tooluse)
                else:
                    decision = parese_LLMDecsion(provider, "None", tooluse)

                self.decisions.append(decision)
                self.session_storage.append_event(
                    self.session_id,
                    "task_loop_decision",
                    {"iteration": self.iteration_count, "decision": decision},
                    agent_id=self.id,
                )

                tool_name = str(decision.get("name") or "").strip()
                if not tool_name:
                    self.context.update_userContext(
                        {
                            "role": "tool",
                            "content": "LLM returned a tooluse without a valid tool name. Continue only when you can provide a valid tool call or no tooluse at all.",
                        }
                    )
                    continue

                executable_tooluses.append(
                    {
                        "function": {
                            "name": tool_name,
                            "arguments": copy.deepcopy(decision.get("arguments") or {}),
                        },
                        "decision": decision,
                    }
                )

            executed_tool_results = self.execute_tooluses_concurrently(
                executable_tooluses,
                provider,
            )
            for item in executed_tool_results:
                tool_function = item.get("function") if isinstance(item.get("function"), dict) else {}
                tool_result = item.get("tool_result") if isinstance(item.get("tool_result"), dict) else {}
                print("-----------------------result-------------------------------")
                print(str(tool_function), tool_result)

                if tool_result.get("status") != "success":
                    if not tryFlag:
                        try_count += 1
                        tryFlag = True

                    if try_count < 3:
                        self.pending_tool_retry.append(response)
                    else:
                        reasoning = str(response.get("reasoning_content") or response.get("content") or "")
                        self.context.update_userContext(
                            {
                                "role": "user",
                                "content": "Do not take this kind of decision: " + reasoning + "\n",
                            }
                        )

                self.tool_results.append(tool_result)
                tool_result_list.append(tool_result)

            if tryFlag:
                if len(self.pending_tool_retry) == 0:# 如果连续重试次数超过3次，则忽略这次response的工具调用
                    try_count = 0
                    continue
                for res in tool_result_list:
                    self.pending_tool_retry.append(res)
                tool_result_list.clear()
                continue
            # 清空重试记录
            try_count = 0
            if tool_calls and not tool_result_list:
                self.context.update_userContext(
                    {
                        "role": "user",
                        "content": "模型返回了工具调用，但平台未解析到可执行的工具名称或参数。请重新发起一个有效工具调用。",
                    }
                )
                continue
            # 将assitant的响应在压缩后加入上下文中，压缩工具调用中的arguments内容
            self.context.update_userContext( self.compress_assitantTooluse(response) )

            if len(tool_result_list) > 0 :
                for tool_result in tool_result_list:
                    self.context.update_userContext(tool_result)
                tool_result_list.clear()

        if is_structured_report_task(self.task_type):
            try:
                structuredReport = self.generate_structured_report(finalReport)
            except Exception as exc:
                self.session_storage.append_event(
                    self.session_id,
                    "structured_report_failed",
                    {
                        "task_id": self.id,
                        "error": str(exc),
                    },
                    agent_id=self.id,
                )
                structuredReport = {}
        print("-----------------------finalReport-------------------------------")
        print(finalReport)
        print("-----------------------structuredReport-------------------------------")
        print(structuredReport)
        return {
            "finalReport": finalReport,
            "structuredReport": structuredReport or {},
            "iterations": self.iteration_count,
        }

    def build_loop_policy_message(self) -> JsonDict:
        recent_patterns = [
            pattern
            for pattern in (
                summarize_tool_pattern(item) for item in self.tool_results[-8:]
            )
            if pattern
        ]
        repeated_patterns = sorted(
            {
                pattern
                for pattern in recent_patterns
                if recent_patterns.count(pattern) > 1
            }
        )
        guidance_lines = [
            "Static analysis only. Never execute or launch the target binary unless the user explicitly requests dynamic execution.",
            "Do not repeat equivalent commands. If size, hash, directory listing, PE header, or metadata are already known, move to deeper analysis.",
            "Prefer evidence-producing steps: imports, strings, sections, suspicious APIs, registry/process/file/network capabilities.",
            "If evidence is sufficient for a stage conclusion, stop enumerating and provide the conclusion.",
        ]
        if any(
            pattern in recent_patterns
            for pattern in ("PowerShell:op=file_metadata", "PowerShell:op=file_hash")
        ):
            guidance_lines.append(
                "Known facts already collected: file metadata/hash/basic existence checks. Do not collect them again."
            )
        if (
            "PowerShell:op=hex_dump" in recent_patterns
            or "PowerShell:op=binary_read" in recent_patterns
        ):
            guidance_lines.append(
                "Hex/header data is already available. Next prefer extracting imports, printable strings, PE section structure, and suspicious API capabilities."
            )
        if "PowerShell:op=python_probe" in recent_patterns:
            guidance_lines.append(
                "Python is available in the sandbox. If PowerShell parsing is awkward, prefer a short Python-based PE parsing step over repeating shell metadata commands."
            )
        if repeated_patterns:
            guidance_lines.append(
                "Recently repeated command patterns: "
                + ", ".join(repeated_patterns[:6])
                + "."
            )
            guidance_lines.append(
                "Do not call the above repeated patterns again unless there is a clearly new target or parameter change that adds new evidence."
            )
        return {"role": "system", "content": "\n".join(guidance_lines)}

    def apply_response_skills(self, response: JsonDict) -> list[dict[str, object]]:
        if not self.skill_system:
            return []
        try:
            matched_skills = self.skill_system.match_skills(response)
        except Exception as exc:
            self.session_storage.append_event(
                self.session_id,
                "skill_match_failed",
                {"task_id": self.id, "error": str(exc)},
                agent_id=self.id,
            )
            return []

        triggered: list[dict[str, object]] = []
        for skill in matched_skills:
            skill_id = str(skill.get("id") or "").strip()
            if not skill_id or skill_id in self.triggered_skill_ids:
                continue
            prompt = self.skill_system.render_skill_prompt(skill)
            if not prompt:
                continue
            self.context.set_systemContext(
                f"skill:{skill_id}",
                {"role": "system", "content": prompt},
            )
            self.triggered_skill_ids.add(skill_id)
            triggered.append(skill)
            self.session_storage.append_event(
                self.session_id,
                "skill_triggered",
                {
                    "task_id": self.id,
                    "iteration": self.iteration_count,
                    "skill_id": skill_id,
                    "name": skill.get("name") or "",
                    "keywords": skill.get("keywords") or [],
                },
                agent_id=self.id,
            )
        return triggered

    def build_retry_message_bundle(self) -> JsonDict | None:
        runtimeEnv_prompt = self.build_runtimeEnv_prompt()
        newMessage = copy.deepcopy(self.pending_tool_retry)
        return {
            "system": [
                {
                    "role": "system",
                    "content": (
                        "Retry the failed tool call with a corrected invocation.\n"
                        "Use only the previous assistant response and the failed tool result below.\n"
                        "Do not reuse the same broken command unchanged.\n"
                        "Return one improved tooluse, or return no tooluse if you can now finish."
                    ),
                },
                runtimeEnv_prompt,
            ],
            "messages": newMessage,
        }

    def compress_assitantTooluse(self, assitResponse: JsonDict) -> JsonDict:
        compressResp = copy.deepcopy(assitResponse)
        tool_calls = (
            compressResp.get("tool_calls")
            if isinstance(compressResp.get("tool_calls"), list)
            else []
        )
        compressResp["tool_calls"] = tool_calls
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue
            function = tool_call.get("function")
            if isinstance(function, dict):
                function["arguments"] = "..."
        return compressResp
    
    def compress_context_if_needed(self) -> None:
        message_context = self.context.context_messages.get("messages", [])
        total_chars = self.context.total_chars()
        if total_chars <= self.context_char_limit or len(message_context) <= 8:
            return

        head = message_context[:2]
        tail = message_context[-6:]
        folded = message_context[2:-6]
        summary_lines = []
        for message in folded:
            content = str(message.get("content") or "").replace("\n", " ")
            summary_lines.append(f"{message.get('role', 'unknown')}: {content[:300]}")
        self.context.context_messages["messages"] = (
            head
            + [
                {
                    "role": "system",
                    "content": "以下为被压缩的历史上下文摘要：\n"
                    + "\n".join(summary_lines)[:5000],
                }
            ]
            + tail
        )
        self.session_storage.append_event(
            self.session_id,
            "task_context_compressed",
            {
                "task_id": self.id,
                "message_count": len(self.context.context_messages.get("messages", [])),
            },
            agent_id=self.id,
        )

    def fold_context_content(self) -> None:
        for message in self.context.context_messages.get("messages", []):
            content = str(message.get("content") or "")
            if len(content) <= self.message_char_limit:
                continue
            message["content"] = (
                content[: self.message_char_limit]
                + "\n\n[内容过长，已折叠；后续可通过工具重新读取原始材料。]"
            )

    def truncate_for_context(self, value: object, limit: int) -> object:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        text = "".join(
            char if char in "\n\r\t" or (ord(char) >= 32 and ord(char) != 127) else "."
            for char in str(value)
        )
        if len(text) <= limit:
            return text
        return f"{text[:limit]}\n\n[已截断，原始长度 {len(text)} 字符。]"

    def compact_json_value_for_context(
        self, value: object, limit: int = 800, depth: int = 0
    ) -> object:
        if value is None or isinstance(value, (bool, int, float)):
            return value
        if isinstance(value, str):
            return self.truncate_for_context(value, limit)
        if isinstance(value, dict):
            if depth >= 2:
                return self.truncate_for_context(
                    json.dumps(value, ensure_ascii=False, default=str), limit
                )
            compact: dict[str, object] = {}
            for index, (key, child) in enumerate(value.items()):
                if index >= 20:
                    compact["__truncated_keys__"] = len(value) - index
                    break
                compact[str(key)] = self.compact_json_value_for_context(
                    child, limit, depth + 1
                )
            return compact
        if isinstance(value, list):
            compact_items = [
                self.compact_json_value_for_context(item, limit, depth + 1)
                for item in value[:10]
            ]
            if len(value) > 10:
                compact_items.append({"__truncated_items__": len(value) - 10})
            return compact_items
        return self.truncate_for_context(value, limit)

    def compact_sandbox_info_for_context(self, sandbox: object) -> dict[str, object]:
        if not isinstance(sandbox, dict):
            return {}
        compact: dict[str, object] = {
            "platform_id": sandbox.get("platform_id", ""),
            "platform_name": sandbox.get("platform_name", ""),
            "url": sandbox.get("url", ""),
        }
        path_map = sandbox.get("path_map")
        if isinstance(path_map, dict):
            compact["path_map"] = self.compact_json_value_for_context(path_map, 300)
        install = sandbox.get("tool_install")
        if isinstance(install, dict):
            compact["tool_install"] = {
                "checked": install.get("checked", False),
                "installed": install.get("installed", False),
            }
        return compact

    def compact_sandbox_server_info_for_context(
        self, sandbox_server: object
    ) -> dict[str, object]:
        if not isinstance(sandbox_server, dict):
            return {}
        compact: dict[str, object] = {
            "root": sandbox_server.get("root", ""),
            "server": sandbox_server.get("server", ""),
        }
        materialized_files = sandbox_server.get("materialized_files")
        if isinstance(materialized_files, list):
            compact["materialized_file_count"] = len(materialized_files)
        return compact

    def compact_execution_result_for_context(
        self, result: object
    ) -> dict[str, object] | object:
        if not isinstance(result, dict):
            return self.compact_json_value_for_context(result, 1000)

        compact: dict[str, object] = {}
        passthrough_keys = (
            "path",
            "size",
            "sha256",
            "preview_bytes",
            "bytes_written",
            "command_line",
            "cwd",
            "timed_out",
            "timeout",
            "exit_code",
        )
        for key in passthrough_keys:
            if key in result:
                compact[key] = self.compact_json_value_for_context(result.get(key), 600)

        if looks_like_binary_preview(result.get("text_preview")):
            text_preview = str(result.get("text_preview") or "")
            printable_chunks = re.findall(r"[ -~]{6,}", text_preview)
            compact["text_preview"] = {
                "kind": "binary_preview",
                "markers": [
                    marker
                    for marker in (
                        "MZ" if text_preview.startswith("MZ") else "",
                        (
                            "PE"
                            if "PE\x00\x00" in text_preview
                            or "PE" in text_preview[:256]
                            else ""
                        ),
                        (
                            "DOS stub"
                            if "This program cannot be run in DOS mode." in text_preview
                            else ""
                        ),
                    )
                    if marker
                ],
                "printable_strings": printable_chunks[:12],
            }
            if "hex_preview" in result:
                compact["hex_preview"] = self.truncate_for_context(
                    result.get("hex_preview"), self.tool_context_hex_limit
                )
        elif "text_preview" in result:
            compact["text_preview"] = self.truncate_for_context(
                result.get("text_preview"), self.tool_context_text_limit
            )
        if "text_preview" in result:
            pass
        if "hex_preview" in result and "hex_preview" not in compact:
            compact["hex_preview"] = self.truncate_for_context(
                result.get("hex_preview"), self.tool_context_hex_limit
            )
        for key in ("stdout", "stderr"):
            if key in result:
                compact[key] = self.truncate_for_context(
                    result.get(key), self.tool_context_stream_limit
                )
        for key in (
            "matches",
            "files",
            "results",
            "tasks",
            "todos",
            "symbols",
            "locations",
            "counts",
        ):
            if key in result:
                compact[key] = self.compact_json_value_for_context(
                    result.get(key), 1200
                )

        sandbox = self.compact_sandbox_info_for_context(result.get("sandbox"))
        if sandbox:
            compact["sandbox"] = sandbox
        sandbox_server = self.compact_sandbox_server_info_for_context(
            result.get("sandbox_server")
        )
        if sandbox_server:
            compact["sandbox_server"] = sandbox_server

        skipped_keys = {
            *passthrough_keys,
            "text_preview",
            "hex_preview",
            "stdout",
            "stderr",
            "matches",
            "files",
            "results",
            "tasks",
            "todos",
            "symbols",
            "locations",
            "counts",
            "sandbox",
            "sandbox_server",
            "rendered",
            "search_text",
        }
        for key, value in result.items():
            if key in skipped_keys or key in compact:
                continue
            if isinstance(value, (str, int, float, bool)) or value is None:
                compact[key] = self.compact_json_value_for_context(value, 600)
        return compact

    def call_llm_decision(self, messages: dict[str, object]) -> JsonDict:
        if not self.llm_platform or not self.llm_pool:
            raise RuntimeError("未配置大模型能力")

        api_key = str(
            self.llm_platform.get("api_key") or self.llm_platform.get("token") or ""
        ).strip()
        if not api_key:
            raise RuntimeError("LLM 平台未配置认证信息")

        provider = self.llm_pool.detect_provider(self.llm_platform)

        try:
            response = self.call_model(
                provider, api_key, messages, self.tool_system.getTools(provider)
            )
            # print("---------------------response------------------------------")
            # print(response)

            if response is None:
                raise ValueError("LLM 返回空响应")
            if isinstance(response, dict):
                return response
            raise ValueError("LLM 返回了不支持的响应类型")
        except Exception as exc:  # 触发重试
            print(f"{DEBUG_LOG_PREFIX} raw_llm_exception={repr(exc)}")
            error_message = self.describe_llm_error(exc)
            return {
                "content": "",
                "tool_calls": [],
                "error_message": error_message,
                "error_type": exc.__class__.__name__,
            }

    def structured_report_response_format(self) -> JsonDict:
        return {
            "type": "json_schema",
            "json_schema": {
                "name": f"{self.task_type.replace('-', '_')}_report",
                "strict": True,
                "schema": structured_report_schema(self.task_type),
            },
        }

    def build_structured_report_messages(self, draft_report: str, retry_error: str = "") -> JsonDict:
        file_info = (
            self.payload.get("file_info")
            if isinstance(self.payload.get("file_info"), dict)
            else {}
        )
        tool_evidence = [
            {
                "tool": item.get("tool", ""),
                "status": item.get("status", ""),
                "purpose": item.get("purpose", ""),
                "summary": self.tool_result_summary(item),
            }
            for item in self.tool_results[-24:]
        ]
        retry_text = f"\n上一次输出无效，原因：{retry_error}\n请修正并重新输出完整 JSON。\n" if retry_error else ""
        return {
            "system": [
                {
                    "role": "system",
                    "content": structured_report_instruction(self.task_type),
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "请基于以下任务信息、工具证据与已有结论，生成最终结构化分析报告 JSON。"
                        f"{retry_text}\n"
                        f"任务类型: {self.task_type}\n"
                        f"文件信息: {json.dumps(file_info, ensure_ascii=False, default=str)}\n"
                        f"工具证据: {json.dumps(tool_evidence, ensure_ascii=False, default=str)}\n"
                        f"草稿结论: {draft_report or '无'}\n"
                    ),
                }
            ],
        }

    def generate_structured_report(self, draft_report: str) -> JsonDict:
        if not self.llm_platform or not self.llm_pool:
            raise RuntimeError("未配置大模型能力")
        provider = self.llm_pool.detect_provider(self.llm_platform)
        api_key = str(
            self.llm_platform.get("api_key") or self.llm_platform.get("token") or ""
        ).strip()
        if not api_key:
            raise RuntimeError("未配置大模型鉴权信息")

        last_error = ""
        allow_response_format = provider in {"openai", "deepseek"}
        cached_support = (
            self.llm_pool.supports_response_format_json_schema(self.llm_platform)
            if self.llm_pool and self.llm_platform
            else None
        )
        if cached_support is False:
            allow_response_format = False
        elif cached_support is True:
            allow_response_format = True
        for _ in range(2):
            for use_response_format in (
                [True, False] if allow_response_format else [False]
            ):
                try:
                    response = self.call_model(
                        provider,
                        api_key,
                        self.build_structured_report_messages(draft_report, last_error),
                        [],
                        response_format=(
                            self.structured_report_response_format()
                            if use_response_format
                            else None
                        ),
                    )
                    content = ""
                    if isinstance(response, dict):
                        content = str(response.get("content") or "").strip()
                    else:
                        content = str(response or "").strip()
                    parsed = self.parse_json_from_text(content)
                    file_info = (
                        self.payload.get("file_info")
                        if isinstance(self.payload.get("file_info"), dict)
                        else {}
                    )
                    return normalize_structured_report(self.task_type, parsed, file_info)
                except Exception as exc:
                    error_text = str(exc)
                    if use_response_format and (
                        "response_format" in error_text
                        or "json_schema" in error_text
                        or "unavailable now" in error_text
                    ):
                        last_error = (
                            "当前模型接口不支持 response_format=json_schema，已自动回退到提示词约束模式。"
                        )
                        allow_response_format = False
                        continue
                    last_error = error_text
        raise ValueError(f"结构化报告生成失败: {last_error or 'LLM 未返回有效 JSON'}")

    def describe_llm_error(self, exc: Exception) -> str:
        if isinstance(exc, json.JSONDecodeError):
            return "LLM未返回可解析JSON。"
        if isinstance(exc, ValueError) and "LLM返回空响应" in str(exc):
            return "LLM返回空响应。"
        message = f'LLM响应失败: "{exc.__class__.__name__}"'
        response = getattr(exc, "response", None)
        status_code = getattr(response, "status_code", None)
        if status_code is not None:
            message = f"{message} HTTP {status_code}"
            response_text = str(getattr(response, "text", "") or "").strip()
            if response_text:
                message = f"{message} {response_text[:500]}"
        elif str(exc):
            message = f"{message} {str(exc)[:300]}"
        return message

    def build_dynamic_system_prompt(self) -> str:

        # sandbox_execution = self.build_sandbox_execution_summary()
        # recent_tool_results = [
        #     {
        #         "tool": item.get("tool", ""),
        #         "purpose": item.get("purpose", ""),
        #         "status": item.get("status", ""),
        #         "summary": self.tool_result_summary(item),
        #     }
        #     for item in self.tool_results[-5:]
        # ]

        state = {
            # "task_id": self.id,
            # "task_type": self.task_type,
            # "task_name": self.task_name,
            # "iteration": self.iteration_count,
            # "tool_call_count": len(self.tool_results),
            # "sandbox_execution": sandbox_execution,
            # "recent_tool_results": recent_tool_results,
            # "available_tool_names": [
            #     tool.get("name", "") for tool in self.tool_system.list_tools()
            # ],
            "sumTokens": 10000,  # 剩余总token数
            "consumeTokens": 1000,  # 预计消耗token数
        }
        return (
            f"{self.system_prompt}\n\n"
            # f"[RuntimeState]\n{json.dumps(state, ensure_ascii=False, default=str)}"
        )

    def tool_result_summary(self, item: dict[str, object]) -> str:
        execution = (
            item.get("execution") if isinstance(item.get("execution"), dict) else {}
        )
        result = (
            execution.get("result")
            if isinstance(execution.get("result"), dict)
            else execution
        )
        if isinstance(result, dict):
            summary_fields = []
            for key in (
                "status",
                "path",
                "filePath",
                "size",
                "sha256",
                "exit_code",
                "stdout",
                "stderr",
                "text_preview",
                "content",
                "matches",
                "results",
                "error",
            ):
                if key in result:
                    value = str(result.get(key) or "")
                    summary_fields.append(f"{key}={value[:300]}")
            return "; ".join(summary_fields)[:1200]
        return str(result)[:1200]

    def build_runtimeEnv_prompt(self) -> str:
        if self.sandbox_client:
            health = self.sandbox_client.environment_info()
            target_path = self.find_prompt_file_path() or self.find_prompt_source_path()
            sandbox_root = str(health.get("root") or "")
            sandbox_cwd = str(health.get("cwd") or sandbox_root or "")
            environment_info = (
                " - 工作目录："
                + (sandbox_root or sandbox_cwd)
                + "\n"
                + " - workspace_root:"
                + sandbox_root
                + "\n"
                + " - sandbox_cwd: "
                + sandbox_cwd
                + "\n"
                + " - upload_dir: "
                + str(health.get("upload_dir") or "")
                + "\n"
                + " - target_path: "
                + target_path
                + "\n"
                + " - os_name: "
                + str(health.get("os_name") or "")
                + "\n"
                + " - os_release: "
                + str(health.get("os_release") or "")
                + "\n"
                + " - os_version:"
                + str(health.get("os_version") or "")
                + "\n"
                + " - machine: "
                + str(health.get("machine") or "")
                + "\n"
                + " - python_version: "
                + str(health.get("python_version") or "")
                + "\n"
            )
        else:
            process_cwd = str(Path(os.getcwd()).resolve())
            workspace_root = ""
            runtime = getattr(self.tool_system, "runtime", None)
            if runtime is not None:
                workspace_root = str(getattr(runtime, "root_dir", "") or "")
            target_path = extract_target_path_from_payload(self.payload)
            environment_info = (
                " - 工作目录："
                + process_cwd
                + "\n"
                + " - workspace_root:"
                + (workspace_root or process_cwd)
                + "\n"
                + " - target_path: "
                + target_path
                + "\n"
                + " - os_name: "
                + platform.system()
                + "\n"
                + " - os_release: "
                + platform.release()
                + "\n"
                + " - os_version:"
                + platform.version()
                + "\n"
                + " - machine: "
                + platform.machine()
                + "\n"
                + " - python_version: "
                + platform.python_version()
                + "\n"
            )
        return {
            "role": "system",
            "content": "Please answer in Chinese. Use the instructions below and the tools available to you to assist the user.\n"
            "# System\n"
            # " - 当对话接近上下文限制时，系统会自动压缩先前消息。这意味着你与用户的对话不受上下文窗口限制。\n"
            " - If os_name is Windows, prefer PowerShell/cmd for shell commands. If os_name is macOS, Darwin, Linux, Ubuntu, or CentOS, prefer Bash and avoid PowerShell unless pwsh is explicitly available."
            # " - 当没有工具调用时\n"
            "# Doing tasks\n"
            " - If a method fails, diagnose the cause before switching strategies—read the errors, examine the assumptions, and try targeted fixes. Don't blindly repeat the exact same operations, but don't abandon a viable method after one failure either.\n"
            " - Do not repeat equivalent commands. If size, hash, directory listing, PE header, or metadata are already known, move to deeper analysis.\n"
            " - If evidence is sufficient for a stage conclusion, stop enumerating and provide the conclusion.\n"
            "# Output efficiency\n"
            " - Important: Get straight to the point. Try the simplest method first; don't go in circles. Don't overcomplicate things. Be exceptionally concise."
            " - Keep text output concise and direct. Present the answer or action first, not the reasoning process. Skip filler phrases, introductions, and unnecessary transitions. Don't restate what the user has said—just do it. When explaining, only include the information necessary for the user to understand."
            " - If one sentence can express something, don't write three. Prioritize short, direct sentences over lengthy explanations. This doesn't apply to code or tool calls.\n"
            "# Environment\n" + environment_info,
            # "你已在以下环境中被调用：\n"
        }

    def build_sandbox_execution_summary(self) -> dict[str, object]:
        if self.task_type not in SANDBOX_TASK_TYPES:
            return {
                "enabled_for_task": False,
                "mode": "local",
                "reason": "task_type_not_sandboxed",
            }
        # sandbox_client = self.get_active_sandbox_client()
        if self.sandbox_client:
            return {
                "enabled_for_task": True,
                "mode": "sandbox",
                "platform_name": self.sandbox_client.platform.get("name", ""),
                "platform_url": self.sandbox_client.base_url,
            }
        return {
            "enabled_for_task": True,
            "mode": "local_fallback",
            "reason": "sandbox_offline_or_unavailable",
        }

    def get_active_sandbox_client(self):
        return self.tool_system.get_sandbox_client(self.task_type)

    def build_toolsystem_prompt(self) -> str:
        tool_specs = [
            {
                "name": tool.get("name", ""),
                "description": tool.get("description", ""),
                "input_schema": {
                    "$schema": "https://json-schema.org/draft/2020-12/schema",
                    **dict(tool.get("input_schema") or {}),
                },
            }
            for tool in self.tool_system.list_tools()
        ]
        decision_context = self.context.get_messagesContext()
        return (
            f"#Tool List\n{json.dumps(tool_specs, ensure_ascii=False)}\n\n"
        )

    def parse_json_from_text(self, text: str) -> dict[str, object]:
        stripped = text.strip()
        if stripped.startswith("```"):
            stripped = re.sub(r"^```(?:json)?", "", stripped).strip()
            stripped = re.sub(r"```$", "", stripped).strip()
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            start = stripped.find("{")
            end = stripped.rfind("}")
            if start < 0 or end <= start:
                raise
            parsed = json.loads(stripped[start : end + 1])
        if not isinstance(parsed, dict):
            raise ValueError("LLM返回内容不是JSON对象")
        return parsed

    def normalize_decision(self, response: dict[str, object]) -> dict[str, object]:
        tool = str(response.get("tool") or response.get("tool_name") or "").strip()
        arguments = (
            dict(response.get("arguments"))
            if isinstance(response.get("arguments"), dict)
            else {}
        )
        answer = str(response.get("answer") or response.get("summary") or "").strip()
        # 删除answer，将内容给purpose

        if not tool:
            return {
                "tool": "",
                "purpose": "",
                "arguments": {},
                "answer": str(
                    response.get("content")
                    or response.get("reasoning_content")
                    or "LLM未选择工具。"
                ).strip(),
            }
        if not answer:
            answer = str(
                response.get("content") or response.get("reasoning_content") or ""
            ).strip()
        if tool and not self.tool_system.get_tool(tool):
            return {
                "tool": "",
                "purpose": "",
                "arguments": {},
                "answer": f"LLM请求了不存在的工具：{tool}",
            }

        arguments = self.normalize_decision_arguments(tool, arguments)
        return {
            "tool": tool,
            "purpose": str(response.get("purpose") or "").strip(),
            "arguments": arguments,
            "answer": answer,
        }

    def normalize_decision_arguments(
        self, tool: str, arguments: dict[str, object]
    ) -> dict[str, object]:
        definition = self.tool_system.get_tool(tool)
        command_line = (
            str(definition.get("command_line") or "")
            if isinstance(definition, dict)
            else ""
        )
        if tool in {"Read", "读取文件"} or command_line == "builtin:read_file":
            try:
                requested = int(
                    arguments.get("max_bytes") or self.decision_read_max_bytes
                )
            except (TypeError, ValueError):
                requested = self.decision_read_max_bytes
            arguments["max_bytes"] = min(
                max(requested, 128), self.decision_read_max_bytes
            )
        return arguments

    def find_payload_file_path(self) -> str:
        path = extract_target_path_from_payload(self.payload)
        if self.sandbox_client and path:
            return self.sandbox_client.remote_materialized_path(path)
        return path

    def find_payload_source_path(self) -> str:
        for key in ("source_path", "folder_path", "project_path", "target_path"):
            if self.payload.get(key):
                path = str(self.payload[key])
                if self.sandbox_client and path:
                    return self.sandbox_client.remote_materialized_path(path)
                return path
        return ""

    def find_execution_file_path(self) -> str:
        return extract_target_path_from_payload(self.payload)

    def find_execution_source_path(self) -> str:
        for key in ("source_path", "folder_path", "project_path", "target_path"):
            if self.payload.get(key):
                return str(self.payload[key])
        return ""

    def find_prompt_file_path(self) -> str:
        return self.find_payload_file_path()

    def find_prompt_source_path(self) -> str:
        return self.find_payload_source_path()

    def escape_cmd_path(self, value: object) -> str:
        return str(value or "").replace('"', '\\"')

    def escape_powershell_path(self, value: object) -> str:
        return str(value or "").replace('"', '`"')

    def execute_decision_tool(
        self, decision: JsonDict, id: str, purpose: str
    ) -> JsonDict:
        tool_name = decision["name"]

        arguments = decision["arguments"]
        if isinstance(arguments, str):
            arguments = parse_tool_arguments(arguments)
        if not isinstance(arguments, dict):
            arguments = {}

        try:
            execution = self.tool_system.execute(
                tool_name,
                arguments,
                session_id=self.session_id,
                agent_id=self.id,
                task_type=self.task_type,
                use_sandbox=not bool(self.sandbox_disabled_reason),
            )
            
            status = str(execution.get("status") or "success")
        except HTTPException as exc:
            execution = {"error": exc.detail}
            status = "failed"
        except Exception as exc:
            execution = {
                "error": str(exc) or exc.__class__.__name__,
                "error_type": exc.__class__.__name__,
            }
            status = "failed"
        return build_tool_execution_record(
            id,
            tool_name,
            purpose,
            status,
            execution if isinstance(execution, dict) else {"value": execution},
        )

    def execute_tooluses_concurrently(
        self,
        executable_tooluses: list[dict[str, object]],
        provider: str,
    ) -> list[dict[str, object]]:
        if not executable_tooluses:
            return []
        max_workers = min(len(executable_tooluses), 8)
        results: list[dict[str, object] | None] = [None] * len(executable_tooluses)

        def run_tooluse(index: int, item: dict[str, object]) -> dict[str, object]:
            function = item.get("function") if isinstance(item.get("function"), dict) else {}
            decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
            decision_id = str(decision.get("id") or "")
            purpose = str(decision.get("purpose") or "")
            try:
                tool_result_ex = self.execute_decision_tool(function, decision_id, purpose)
                tool_result = normalize_toolresult(provider, tool_result_ex, decision_id)
            except Exception as exc:
                tool_result = {
                    "role": "tool",
                    "tool_call_id": decision_id,
                    "content": "Error: " + (str(exc) or exc.__class__.__name__),
                    "status": "fail",
                }
            return {
                "index": index,
                "function": function,
                "decision": decision,
                "tool_result": tool_result,
            }

        with ThreadPoolExecutor(
            max_workers=max_workers,
            thread_name_prefix=f"task-{self.id[:8]}-tool",
        ) as executor:
            future_map = {
                executor.submit(run_tooluse, index, item): index
                for index, item in enumerate(executable_tooluses)
            }
            for future in as_completed(future_map):
                index = future_map[future]
                try:
                    results[index] = future.result()
                except Exception as exc:
                    item = executable_tooluses[index]
                    decision = item.get("decision") if isinstance(item.get("decision"), dict) else {}
                    decision_id = str(decision.get("id") or "")
                    results[index] = {
                        "index": index,
                        "function": item.get("function") if isinstance(item.get("function"), dict) else {},
                        "decision": decision,
                        "tool_result": {
                            "role": "tool",
                            "tool_call_id": decision_id,
                            "content": "Error: " + (str(exc) or exc.__class__.__name__),
                            "status": "fail",
                        },
                    }

        return [item for item in results if isinstance(item, dict)]

    def compose_task_result(self, loop_result: dict[str, object]) -> dict[str, object]:
        successful_tools = [
            item for item in self.tool_results if item.get("status") == "success"
        ]
        failed_tools = [
            item for item in self.tool_results if item.get("status") != "success"
        ]
        finalReport = str(loop_result.get("finalReport")).strip()
        structuredReport = (
            dict(loop_result.get("structuredReport"))
            if isinstance(loop_result.get("structuredReport"), dict)
            else {}
        )

        file_info = (
            self.payload.get("file_info")
            if isinstance(self.payload.get("file_info"), dict)
            else {}
        )
        threat_intelligence = self.collect_threat_intelligence(file_info)
        raw_llm_analysis = finalReport
        final_llm_judgement: JsonDict = {}
        if self.task_type == "sample-analysis":
            synthesis_result = self.synthesize_final_sample_analysis(
                raw_llm_analysis,
                structuredReport,
                file_info,
                threat_intelligence,
            )
            finalReport = str(synthesis_result.get("text") or raw_llm_analysis).strip()
            final_llm_judgement = (
                dict(synthesis_result.get("judgement"))
                if isinstance(synthesis_result.get("judgement"), dict)
                else {}
            )
        if self.task_type == "sample-analysis":
            structuredReport = self.ensure_sample_structured_report(
                structuredReport,
                finalReport,
                file_info,
                threat_intelligence,
            )
        if structuredReport:
            summary = structured_report_summary(self.task_type, structuredReport)
        else:
            summary = (
                f"{self.task_name} task completed by Task Pool. "
                f"Iterations: {loop_result.get('iterations', 0)}. "
                f"Successful tool calls: {len(successful_tools)}."
            )
            if loop_result.get("finalReport"):
                summary = f"{summary} {loop_result['finalReport']}"
        integrated_analysis = self.build_integrated_analysis(
            structuredReport,
            finalReport,
            threat_intelligence,
        )
        if structuredReport:
            structuredReport["integrated_analysis"] = integrated_analysis
            structuredReport["llm_analysis"] = finalReport
            structuredReport["raw_llm_analysis"] = raw_llm_analysis
            structuredReport["llm_judgement"] = final_llm_judgement
            structuredReport["threat_intelligence"] = threat_intelligence
        threat_summary = (
            threat_intelligence.get("summary")
            if isinstance(threat_intelligence.get("summary"), dict)
            else {}
        )
        if threat_summary:
            verdict_bits = [
                str(threat_summary.get("threat_level") or "").strip(),
                str(threat_summary.get("malware_type") or "").strip(),
                str(threat_summary.get("malware_family") or "").strip(),
            ]
            verdict_text = " / ".join([item for item in verdict_bits if item])
            if verdict_text:
                summary = f"{summary} Threat intelligence: {verdict_text}."
        return {
            "task_id": self.id,
            "task_type": self.task_type,
            "task_name": self.task_name,
            "session_id": self.session_id,
            "agent_id": self.id,
            "file_info": file_info,
            "llm": self.llm_snapshot(),
            "system_prompt": self.system_prompt,
            "user_prompt": self.user_prompt,
            "decisions": self.decisions,
            "tool_results": self.tool_results,
            "assistant_response": finalReport,
            "analysis_result": {
                "summary": summary,
                "assistant_response": finalReport,
                "structured_report": structuredReport,
                "threat_intelligence": threat_intelligence,
                "integrated_analysis": integrated_analysis,
                "llm_analysis": finalReport,
                "raw_llm_analysis": raw_llm_analysis,
                "llm_judgement": final_llm_judgement,
                "risk_level": "pending-rule-engine",
                "failed_tool_count": len(failed_tools),
                "next_steps": [
                    "Add more specialized tooling to feed the task loop with higher-fidelity evidence.",
                    "Poll task status by task_id in the frontend and display the complete loop trace.",
                ],
            },
            "generated_at": utc_now(),
        }

    def ensure_sample_structured_report(
        self,
        structured_report: JsonDict,
        final_report: str,
        file_info: JsonDict,
        threat_intelligence: JsonDict,
    ) -> JsonDict:
        if structured_report.get("report_type") == "sample-analysis":
            return self.enrich_sample_report_with_threat_intelligence(
                structured_report,
                threat_intelligence,
            )
        fallback = self.build_sample_report_fallback(
            final_report,
            file_info,
            threat_intelligence,
        )
        return self.enrich_sample_report_with_threat_intelligence(
            fallback,
            threat_intelligence,
        )

    def synthesize_final_sample_analysis(
        self,
        raw_llm_analysis: str,
        structured_report: JsonDict,
        file_info: JsonDict,
        threat_intelligence: JsonDict,
    ) -> JsonDict:
        raw_text = str(raw_llm_analysis or "").strip()
        if not self.llm_platform or not self.llm_pool:
            return {"text": raw_text, "judgement": {}}
        api_key = str(
            self.llm_platform.get("api_key") or self.llm_platform.get("token") or ""
        ).strip()
        if not api_key:
            return {"text": raw_text, "judgement": {}}

        provider = self.llm_pool.detect_provider(self.llm_platform)
        threat_summary = (
            threat_intelligence.get("summary")
            if isinstance(threat_intelligence.get("summary"), dict)
            else {}
        )
        threat_response = (
            threat_intelligence.get("response")
            if isinstance(threat_intelligence.get("response"), dict)
            else {}
        )
        threat_data = (
            threat_response.get("data")
            if isinstance(threat_response.get("data"), dict)
            else {}
        )
        compact_threat_response = {
            "response_code": threat_response.get("response_code"),
            "verbose_msg": threat_response.get("verbose_msg") or threat_response.get("msg"),
            "data": {
                key: threat_data.get(key)
                for key in (
                    "summary",
                    "multiengines",
                    "signature",
                    "static",
                    "network",
                )
                if key in threat_data
            },
        }
        threat_response_text = json.dumps(
            compact_threat_response,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
        if len(threat_response_text) > 16000:
            threat_response_text = threat_response_text[:16000] + "\n...<truncated>"

        self.session_storage.append_event(
            self.session_id,
            "final_synthesis_started",
            {
                "task_id": self.id,
                "provider": provider,
                "raw_llm_chars": len(raw_text),
                "threat_response_chars": len(threat_response_text),
                "threat_enabled": bool(threat_intelligence.get("enabled")),
                "threat_status": threat_intelligence.get("status", ""),
            },
            agent_id=self.id,
        )

        messages = {
            "system": [
                {
                    "role": "system",
                    "content": (
                        "你是恶意样本分析报告整理专家。你需要把已有 LLM 分析结果与"
                        "威胁情报平台返回的固定 JSON 结果合并，生成最终样本分析研判。"
                        "只能输出一个 JSON 对象，不要输出 Markdown、代码块或额外说明。"
                        "不要编造未在输入中出现的证据；如果 LLM 与威胁情报冲突，必须"
                        "在 conflicts 字段中说明冲突和可信度判断。"
                    ),
                }
            ],
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "请基于以下材料生成固定字段 JSON。字段必须完整：\n"
                        "{\n"
                        '  "final_verdict": "最终结论，一句话",\n'
                        '  "malicious_assessment": "恶意/可疑/未证实/良性/需复核",\n'
                        '  "severity": "critical/high/medium/low/unknown",\n'
                        '  "confidence": "high/medium/low/unknown",\n'
                        '  "family": "家族或未识别",\n'
                        '  "summary": "3-5 句中文摘要",\n'
                        '  "key_evidence": [{"source": "llm|threat_intel|static|network|engine", "title": "证据标题", "detail": "证据详情", "weight": "high|medium|low"}],\n'
                        '  "threat_intel_interpretation": {"threat_level": "", "threat_score": "", "detect_rate": "", "malware_type": "", "malware_family": "", "meaning": "对情报结果的解释"},\n'
                        '  "behavior_judgement": [{"category": "持久化/网络/文件/进程/注册表/规避/其他", "assessment": "研判", "evidence": ["证据"]}],\n'
                        '  "iocs": [{"type": "hash/domain/ip/url/file/registry/other", "value": "IOC 值", "context": "上下文", "severity": "high|medium|low|unknown"}],\n'
                        '  "detection_recommendations": ["检测建议"],\n'
                        '  "response_actions": ["处置建议"],\n'
                        '  "conflicts": ["LLM 与威胁情报或证据之间的冲突"],\n'
                        '  "limitations": ["限制说明"]\n'
                        "}\n\n"
                        "要求：\n"
                        "- 合并重复内容，避免把同一证据在多个章节反复描述。\n"
                        "- 威胁情报 JSON 中的 threat_level、threat_score、multi_engines/"
                        "detect_rate、malware_type、malware_family、signature、tag、"
                        "static、network 要优先解析为可读结论。\n"
                        "- 保留 LLM 行为分析的上下文，但最终结论应结合威胁情报重新判断。\n"
                        "- 如果证据不足，不要直接断言恶意，写为可疑/需复核。\n"
                        "- 所有数组字段至少给出空数组，不要省略字段。\n\n"
                        f"文件信息：\n{json.dumps(file_info, ensure_ascii=False, indent=2, default=str)}\n\n"
                        f"已有结构化报告：\n{json.dumps(structured_report, ensure_ascii=False, indent=2, default=str)[:8000]}\n\n"
                        f"原始 LLM 分析结果：\n{raw_text or '无'}\n\n"
                        f"威胁情报摘要：\n{json.dumps(threat_summary, ensure_ascii=False, indent=2, default=str)}\n\n"
                        f"威胁情报平台固定 JSON 关键字段：\n{threat_response_text}\n"
                    ),
                }
            ],
        }

        try:
            response_format = None
            if provider in {"openai", "deepseek"}:
                response_format = {"type": "json_object"}
            response = call_model(
                provider,
                api_key,
                self.llm_platform,
                messages,
                [],
                response_format=response_format,
                timeout_seconds=self.llm_request_timeout_seconds,
                temperature=0.1,
                max_tokens=3200,
            )
            if isinstance(response, dict):
                content = str(
                    response.get("content")
                    or response.get("reasoning_content")
                    or response.get("answer")
                    or ""
                ).strip()
            else:
                content = str(response or "").strip()
            if not content:
                raise ValueError("final synthesis returned empty content")
            judgement = self.normalize_final_llm_judgement(
                self.parse_json_from_text(content),
                raw_text,
                threat_summary,
            )
            final_text = self.render_final_llm_judgement_markdown(judgement)
            self.session_storage.append_event(
                self.session_id,
                "final_synthesis_completed",
                {
                    "task_id": self.id,
                    "provider": provider,
                    "final_chars": len(final_text),
                    "fixed_fields": True,
                    "judgement": judgement,
                    "preview": final_text[:1200],
                },
                agent_id=self.id,
            )
            return {"text": final_text, "judgement": judgement}
        except Exception as exc:
            error_message = self.describe_llm_error(exc)
            self.session_storage.append_event(
                self.session_id,
                "final_synthesis_failed",
                {
                    "task_id": self.id,
                    "provider": provider,
                    "error": error_message,
                    "fallback": "raw_llm_analysis",
                },
                agent_id=self.id,
            )
            return {"text": raw_text, "judgement": {}}

    def normalize_final_llm_judgement(
        self,
        parsed: JsonDict,
        raw_text: str,
        threat_summary: JsonDict,
    ) -> JsonDict:
        def string_value(key: str, default: str = "") -> str:
            value = parsed.get(key)
            return str(value if value not in (None, [], {}) else default).strip()

        def string_list(key: str) -> list[str]:
            value = parsed.get(key)
            if isinstance(value, list):
                return [str(item).strip() for item in value if str(item).strip()]
            if value:
                return [str(value).strip()]
            return []

        def object_list(key: str, required: tuple[str, ...]) -> list[JsonDict]:
            value = parsed.get(key)
            if not isinstance(value, list):
                return []
            rows: list[JsonDict] = []
            for item in value:
                if not isinstance(item, dict):
                    continue
                row = {field: str(item.get(field) or "").strip() for field in required}
                if any(row.values()):
                    rows.append(row)
            return rows

        threat_interpretation = (
            dict(parsed.get("threat_intel_interpretation"))
            if isinstance(parsed.get("threat_intel_interpretation"), dict)
            else {}
        )
        return {
            "final_verdict": string_value("final_verdict", "样本分析完成，需结合证据复核。"),
            "malicious_assessment": string_value("malicious_assessment", "需复核"),
            "severity": string_value("severity", threat_summary.get("threat_level") or "unknown"),
            "confidence": string_value("confidence", "unknown"),
            "family": string_value("family", threat_summary.get("malware_family") or "未识别"),
            "summary": string_value("summary", raw_text[:1200]),
            "key_evidence": object_list(
                "key_evidence",
                ("source", "title", "detail", "weight"),
            ),
            "threat_intel_interpretation": {
                "threat_level": str(
                    threat_interpretation.get("threat_level")
                    or threat_summary.get("threat_level")
                    or ""
                ),
                "threat_score": str(
                    threat_interpretation.get("threat_score")
                    or threat_summary.get("threat_score")
                    or ""
                ),
                "detect_rate": str(
                    threat_interpretation.get("detect_rate")
                    or threat_summary.get("detect_rate")
                    or threat_summary.get("multi_engines")
                    or ""
                ),
                "malware_type": str(
                    threat_interpretation.get("malware_type")
                    or threat_summary.get("malware_type")
                    or ""
                ),
                "malware_family": str(
                    threat_interpretation.get("malware_family")
                    or threat_summary.get("malware_family")
                    or ""
                ),
                "meaning": str(threat_interpretation.get("meaning") or "").strip(),
            },
            "behavior_judgement": object_list(
                "behavior_judgement",
                ("category", "assessment", "evidence"),
            ),
            "iocs": object_list(
                "iocs",
                ("type", "value", "context", "severity"),
            ),
            "detection_recommendations": string_list("detection_recommendations"),
            "response_actions": string_list("response_actions"),
            "conflicts": string_list("conflicts"),
            "limitations": string_list("limitations"),
        }

    def render_final_llm_judgement_markdown(self, judgement: JsonDict) -> str:
        def render_list(items: object) -> str:
            if not isinstance(items, list) or not items:
                return "- 无"
            lines = []
            for item in items:
                if isinstance(item, dict):
                    detail = "；".join(
                        f"{key}: {value}" for key, value in item.items() if value
                    )
                    lines.append(f"- {detail or '未提供'}")
                else:
                    lines.append(f"- {item}")
            return "\n".join(lines)

        intel = (
            judgement.get("threat_intel_interpretation")
            if isinstance(judgement.get("threat_intel_interpretation"), dict)
            else {}
        )
        return "\n\n".join(
            [
                "# 最终结论",
                str(judgement.get("final_verdict") or ""),
                "## 摘要",
                str(judgement.get("summary") or ""),
                "## 研判字段",
                "\n".join(
                    [
                        f"- 恶意性：{judgement.get('malicious_assessment') or '未提供'}",
                        f"- 严重性：{judgement.get('severity') or 'unknown'}",
                        f"- 置信度：{judgement.get('confidence') or 'unknown'}",
                        f"- 家族：{judgement.get('family') or '未识别'}",
                    ]
                ),
                "## 关键证据",
                render_list(judgement.get("key_evidence")),
                "## 威胁情报解读",
                "\n".join(
                    [
                        f"- 威胁等级：{intel.get('threat_level') or '未提供'}",
                        f"- 威胁分：{intel.get('threat_score') or '未提供'}",
                        f"- 检出率：{intel.get('detect_rate') or '未提供'}",
                        f"- 类型/家族：{intel.get('malware_type') or '未提供'} / {intel.get('malware_family') or '未提供'}",
                        f"- 解读：{intel.get('meaning') or '未提供'}",
                    ]
                ),
                "## 行为与能力研判",
                render_list(judgement.get("behavior_judgement")),
                "## IOC",
                render_list(judgement.get("iocs")),
                "## 检测建议",
                render_list(judgement.get("detection_recommendations")),
                "## 处置建议",
                render_list(judgement.get("response_actions")),
                "## 冲突与限制",
                render_list(
                    list(judgement.get("conflicts") or [])
                    + list(judgement.get("limitations") or [])
                ),
            ]
        )

    def build_sample_report_fallback(
        self,
        final_report: str,
        file_info: JsonDict,
        threat_intelligence: JsonDict,
    ) -> JsonDict:
        threat_summary = (
            threat_intelligence.get("summary")
            if isinstance(threat_intelligence.get("summary"), dict)
            else {}
        )
        threat_level = str(threat_summary.get("threat_level") or "").strip()
        malware_family = str(threat_summary.get("malware_family") or "").strip()
        malware_type = str(threat_summary.get("malware_type") or "").strip()
        detect_rate = str(threat_summary.get("detect_rate") or threat_summary.get("multi_engines") or "").strip()
        engine_hits = (
            threat_summary.get("engine_hits")
            if isinstance(threat_summary.get("engine_hits"), list)
            else []
        )
        static_findings = (
            threat_summary.get("static_findings")
            if isinstance(threat_summary.get("static_findings"), list)
            else []
        )
        normalized_level = threat_level.lower()
        has_reputation_hit = normalized_level not in {"", "unknown", "clean", "safe"}
        has_suspicious_intel = bool(
            has_reputation_hit or malware_family or malware_type or engine_hits or static_findings
        )
        verdict = "需要人工复核"
        is_malicious = False
        if malware_family or malware_type or has_reputation_hit:
            verdict = "威胁情报命中，建议按可疑/恶意样本处置"
            is_malicious = True
        elif has_suspicious_intel:
            verdict = "威胁情报未给出明确恶意家族，但存在可疑信号，建议人工复核"
        elif final_report:
            verdict = "已生成 task_loop 分析，结论以 LLM 详细分析为准"

        iocs: list[JsonDict] = []
        for key in ("md5", "sha1", "sha256"):
            value = str(file_info.get(key) or "").strip()
            if value:
                iocs.append(
                    {
                        "type": key.upper(),
                        "value": value,
                        "context": "上传样本文件哈希",
                        "severity": threat_level or "unknown",
                    }
                )

        capabilities: list[JsonDict] = []
        capability_name = malware_type or malware_family
        if capability_name or engine_hits or static_findings:
            capabilities.append(
                {
                    "name": f"威胁情报融合信号：{capability_name or detect_rate or threat_level or '可疑静态特征'}",
                    "confidence": "external-intelligence",
                    "evidence": [
                        f"威胁情报平台返回 threat_level={threat_level or 'unknown'}",
                        f"malware_family={malware_family or 'unknown'}",
                        f"detect_rate={detect_rate or 'unknown'}",
                        *[
                            f"{hit.get('engine')}: {hit.get('verdict')}"
                            for hit in engine_hits[:3]
                            if isinstance(hit, dict)
                        ],
                        *[str(item) for item in static_findings[:3]],
                    ],
                    "mitre_techniques": [],
                }
            )

        summary = final_report[:1200] if final_report else "样本分析已完成，但未生成可解析的结构化报告。"
        return normalize_structured_report(
            "sample-analysis",
            {
                "report_type": "sample-analysis",
                "executive_summary": {
                    "verdict": verdict,
                    "is_malicious": is_malicious,
                    "confidence": "medium" if final_report else "unknown",
                    "severity": threat_level or "unknown",
                    "family": malware_family,
                    "summary": summary,
                },
                "sample_profile": {
                    "file_name": file_info.get("filename") or file_info.get("path") or "",
                    "file_type": file_info.get("content_type") or "",
                    "architecture": "",
                    "platform": "",
                    "size_bytes": file_info.get("size") or 0,
                    "hashes": {
                        "md5": file_info.get("md5") or "",
                        "sha256": file_info.get("sha256") or "",
                    },
                },
                "capabilities": capabilities,
                "behavior_summary": {
                    "persistence": [],
                    "network": [],
                    "filesystem": [],
                    "process": [],
                    "registry": [],
                    "defense_evasion": [],
                },
                "iocs": iocs,
                "detection_recommendations": [
                    "结合 task_loop 详细分析和威胁情报命中结果进行人工复核。",
                    "如需更高置信度，请在沙箱中补充动态行为分析。",
                ],
                "limitations": [
                    "结构化报告由 task_loop 原始输出兜底生成，部分行为字段可能需要人工补全。",
                ],
                "next_steps": [
                    "查看 LLM 详细分析和工具轨迹。",
                    "结合威胁情报原始响应确认样本处置优先级。",
                ],
            },
            file_info,
        )

    def enrich_sample_report_with_threat_intelligence(
        self,
        structured_report: JsonDict,
        threat_intelligence: JsonDict,
    ) -> JsonDict:
        if structured_report.get("report_type") != "sample-analysis":
            return structured_report
        threat_summary = (
            threat_intelligence.get("summary")
            if isinstance(threat_intelligence.get("summary"), dict)
            else {}
        )
        if not threat_summary:
            return structured_report
        enriched = dict(structured_report)
        executive = (
            dict(enriched.get("executive_summary"))
            if isinstance(enriched.get("executive_summary"), dict)
            else {}
        )
        threat_level = str(threat_summary.get("threat_level") or "").strip()
        malware_family = str(threat_summary.get("malware_family") or "").strip()
        malware_type = str(threat_summary.get("malware_type") or "").strip()
        threat_score = str(threat_summary.get("threat_score") or "").strip()
        detect_rate = str(threat_summary.get("detect_rate") or threat_summary.get("multi_engines") or "").strip()
        engine_hits = (
            threat_summary.get("engine_hits")
            if isinstance(threat_summary.get("engine_hits"), list)
            else []
        )
        static_findings = (
            threat_summary.get("static_findings")
            if isinstance(threat_summary.get("static_findings"), list)
            else []
        )
        normalized_level = threat_level.lower()
        has_reputation_hit = normalized_level not in {"", "unknown", "clean", "safe"}
        has_suspicious_intel = bool(
            has_reputation_hit or malware_family or malware_type or engine_hits or static_findings
        )
        tags = threat_summary.get("tags")
        tag_text = ", ".join(str(item) for item in tags if item) if isinstance(tags, list) else str(tags or "")
        if threat_level and executive.get("severity") in {"", "unknown", None}:
            executive["severity"] = threat_level
        if malware_family and not str(executive.get("family") or "").strip():
            executive["family"] = malware_family
        if has_suspicious_intel:
            if malware_family or malware_type or has_reputation_hit:
                executive["is_malicious"] = True
            external_bits = [
                f"威胁等级：{threat_level}" if threat_level else "",
                f"威胁分：{threat_score}" if threat_score else "",
                f"多引擎检出：{detect_rate}" if detect_rate else "",
                f"恶意类型：{malware_type}" if malware_type else "",
                f"恶意家族：{malware_family}" if malware_family else "",
                f"标签：{tag_text}" if tag_text else "",
                "引擎命中：" + "；".join(
                    f"{hit.get('engine')}={hit.get('verdict')}"
                    for hit in engine_hits[:3]
                    if isinstance(hit, dict)
                )
                if engine_hits
                else "",
                "静态信号：" + "；".join(str(item) for item in static_findings[:3])
                if static_findings
                else "",
            ]
            external_text = "；".join(item for item in external_bits if item)
            base_summary = str(executive.get("summary") or "").strip()
            if external_text and external_text not in base_summary:
                executive["summary"] = (
                    f"{base_summary}\n\n威胁情报融合结论：{external_text}"
                    if base_summary
                    else f"威胁情报融合结论：{external_text}"
                )
            if not str(executive.get("verdict") or "").strip():
                executive["verdict"] = (
                    "威胁情报命中，建议按可疑/恶意样本处置"
                    if executive.get("is_malicious")
                    else "威胁情报未给出明确恶意家族，但存在可疑信号，建议人工复核"
                )
        enriched["executive_summary"] = executive
        return enriched

    def build_integrated_analysis(
        self,
        structured_report: JsonDict,
        final_report: str,
        threat_intelligence: JsonDict,
    ) -> JsonDict:
        executive = (
            structured_report.get("executive_summary")
            if isinstance(structured_report.get("executive_summary"), dict)
            else {}
        )
        threat_summary = (
            threat_intelligence.get("summary")
            if isinstance(threat_intelligence.get("summary"), dict)
            else {}
        )
        threat_response = (
            threat_intelligence.get("response")
            if isinstance(threat_intelligence.get("response"), dict)
            else {}
        )
        threat_data = (
            threat_response.get("data")
            if isinstance(threat_response.get("data"), dict)
            else {}
        )
        capabilities = (
            structured_report.get("capabilities")
            if isinstance(structured_report.get("capabilities"), list)
            else []
        )
        iocs = (
            structured_report.get("iocs")
            if isinstance(structured_report.get("iocs"), list)
            else []
        )
        merged_iocs: list[JsonDict] = []
        seen_iocs: set[str] = set()
        for item in iocs:
            if not isinstance(item, dict):
                continue
            value = str(item.get("value") or "").strip().lower()
            if not value or value in seen_iocs:
                continue
            seen_iocs.add(value)
            merged_iocs.append(dict(item))

        threat_signals: list[str] = []
        seen_signals: set[str] = set()

        def append_threat_signal(label: str, value: object) -> None:
            values = value if isinstance(value, list) else [value]
            for raw in values:
                if raw in (None, "", [], {}):
                    continue
                text = normalize_debug_text(raw)
                if not text:
                    continue
                signature = f"{label}:{text}".lower()
                if signature in seen_signals:
                    continue
                seen_signals.add(signature)
                threat_signals.append(f"{label}: {text}")

        for key in (
            "threat_level",
            "threat_score",
            "malware_type",
            "malware_family",
            "signature",
            "signature_names",
            "tags",
            "multi_engines",
            "detect_rate",
            "engine_hits",
            "static_findings",
            "network_activity",
        ):
            value = threat_summary.get(key, threat_data.get(key))
            append_threat_signal(key, value)

        return {
            "verdict": executive.get("verdict") or threat_summary.get("threat_level") or "",
            "severity": executive.get("severity") or threat_summary.get("threat_level") or "",
            "family": executive.get("family") or threat_summary.get("malware_family") or "",
            "llm_summary": executive.get("summary") or final_report[:1200],
            "threatbook_summary": threat_summary,
            "threat_score": threat_summary.get("threat_score"),
            "detect_rate": threat_summary.get("detect_rate") or threat_summary.get("multi_engines"),
            "engine_hits": threat_summary.get("engine_hits") or [],
            "static_findings": threat_summary.get("static_findings") or [],
            "network_activity": threat_summary.get("network_activity") or [],
            "deduplicated_iocs": merged_iocs,
            "capability_count": len(capabilities),
            "ioc_count": len(merged_iocs),
            "threat_signals": threat_signals,
            "fusion_note": (
                "保留 LLM 结构化行为分析作为主线，并将威胁情报的检出率、引擎命中、标签、家族和静态信号作为外部证据合并展示。"
            ),
        }

    def collect_threat_intelligence(self, file_info: JsonDict) -> JsonDict:
        if not (
            file_info.get("sha256")
            or file_info.get("sha1")
            or file_info.get("md5")
        ):
            return {"enabled": False, "reason": "file_hash_missing"}
        if not self.threat_intelligence_resolver:
            return {"enabled": False, "reason": "threat_intelligence_not_configured"}
        platform = self.threat_intelligence_resolver()
        if not platform:
            return {"enabled": False, "reason": "threat_intelligence_offline"}
        result = fetch_file_report(platform, file_info)
        self.session_storage.append_event(
            self.session_id,
            "threat_intelligence_report",
            {
                "task_id": self.id,
                "platform_id": platform.get("id", ""),
                "platform_name": platform.get("name", ""),
                "status": result.get("status", ""),
                "summary": result.get("summary", {}),
                "error": result.get("error", ""),
            },
            agent_id=self.id,
        )
        return result

    def write_report(self) -> None:
        report_path = REPORT_DIR / f"{self.id}.html"
        structured_report = (
            self.result.get("analysis_result", {}).get("structured_report", {})
            if isinstance(self.result.get("analysis_result"), dict)
            else {}
        )
        if isinstance(structured_report, dict) and structured_report:
            report_content = render_structured_report_html(
                task_type=self.task_type,
                task_name=self.task_name,
                task_id=self.id,
                generated_at=str(self.result.get("generated_at") or utc_now()),
                file_info=(
                    self.payload.get("file_info")
                    if isinstance(self.payload.get("file_info"), dict)
                    else {}
                ),
                report=structured_report,
            )
        else:
            report_content = str(
                self.result.get("assistant_response")
                or self.result.get("analysis_result", {}).get("assistant_response", "")
                or self.result.get("analysis_result", {}).get("summary", "")
                or self.result.get("summary", "")
                or ""
            ).strip()
            if not report_content:
                report_content = json.dumps(
                    self.result, ensure_ascii=False, indent=2, default=str
                )
            report_content = self.render_html_report(report_content)
        write_result = self.tool_system.execute(
            "Write",
            {
                "path": str(report_path),
                "content": report_content,
                "overwrite": True,
            },
            session_id=self.session_id,
            agent_id=self.id,
        )
        result = write_result.get("result") if isinstance(write_result, dict) else {}
        self.report_path = str(
            result.get("path") or result.get("filePath") or report_path
        )
        self.result["report_path"] = self.report_path
        self.session_storage.append_event(
            self.session_id,
            "task_completed",
            {
                "task_id": self.id,
                "report_path": self.report_path,
                "summary": self.result.get("analysis_result", {}).get("summary", ""),
                "result": self.result,
            },
            agent_id=self.id,
        )

    def render_html_report(self, report_content: str) -> str:
        file_info = (
            self.payload.get("file_info")
            if isinstance(self.payload.get("file_info"), dict)
            else {}
        )
        filename = str(file_info.get("filename") or file_info.get("path") or "")
        escaped_title = html.escape(f"{self.task_name}报告")
        escaped_task = html.escape(self.task_name)
        escaped_task_id = html.escape(self.id)
        escaped_filename = html.escape(filename)
        escaped_generated = html.escape(
            str(self.result.get("generated_at") or utc_now())
        )
        rendered_body = markdown_like_to_html(report_content)
        return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escaped_title}</title>
  <style>
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      background: #f6f8fb;
      color: #17202a;
    }}
    .wrap {{
      max-width: 980px;
      margin: 32px auto;
      padding: 0 20px;
    }}
    .panel {{
      background: #fff;
      border: 1px solid #d8e1ea;
      border-radius: 10px;
      padding: 24px;
      box-shadow: 0 6px 24px rgba(15, 23, 42, 0.06);
    }}
    h1 {{
      margin: 0 0 12px;
      font-size: 28px;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 10px 18px;
      margin: 0 0 24px;
      font-size: 14px;
      color: #4b5563;
    }}
    .label {{
      font-weight: 600;
      color: #111827;
    }}
    .report-content {{
      color: #1f2937;
      line-height: 1.72;
      font-size: 14px;
    }}
    .report-content h1,
    .report-content h2,
    .report-content h3,
    .report-content h4 {{
      margin: 1.2em 0 0.55em;
      line-height: 1.35;
      color: #111827;
    }}
    .report-content h1:first-child,
    .report-content h2:first-child,
    .report-content h3:first-child {{
      margin-top: 0;
    }}
    .report-content h1 {{ font-size: 26px; }}
    .report-content h2 {{ font-size: 22px; }}
    .report-content h3 {{ font-size: 18px; }}
    .report-content p {{
      margin: 0 0 0.9em;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .report-content .report-bullet {{
      padding-left: 0.2em;
    }}
    .report-content code {{
      padding: 0.12em 0.35em;
      border-radius: 6px;
      background: #eef2f7;
      border: 1px solid #d7e0ea;
      font-size: 0.95em;
      font-family: Consolas, "SFMono-Regular", monospace;
    }}
    .report-code {{
      margin: 0 0 1em;
      overflow-x: auto;
      white-space: pre;
      word-break: normal;
      line-height: 1.6;
      font-size: 13px;
      font-family: Consolas, "SFMono-Regular", monospace;
      background: #f8fafc;
      border: 1px solid #e5e7eb;
      border-radius: 8px;
      padding: 18px;
    }}
    .report-code code {{
      padding: 0;
      border: 0;
      background: transparent;
    }}
    .report-table-wrap {{
      overflow-x: auto;
      margin: 0 0 1em;
    }}
    .report-table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
      background: #fff;
      border: 1px solid #dbe5ee;
      border-radius: 8px;
      overflow: hidden;
    }}
    .report-table th,
    .report-table td {{
      padding: 10px 12px;
      border-bottom: 1px solid #e5edf4;
      text-align: left;
      vertical-align: top;
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .report-table thead th {{
      background: #f4f7fb;
      color: #1f2937;
      font-weight: 700;
    }}
    .report-table tbody tr:nth-child(even) {{
      background: #fafcff;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="panel">
      <h1>{escaped_title}</h1>
      <div class="meta">
        <div><span class="label">任务类型：</span>{escaped_task}</div>
        <div><span class="label">任务ID：</span>{escaped_task_id}</div>
        <div><span class="label">目标文件：</span>{escaped_filename}</div>
        <div><span class="label">生成时间：</span>{escaped_generated}</div>
      </div>
      <div class="report-content">{rendered_body}</div>
    </div>
  </div>
</body>
</html>"""


class TaskPool:
    min_workers = 3
    max_workers = 10
    idle_timeout_seconds = 5.0

    def __init__(
        self,
        tool_system: ToolSystem,
        session_storage: SessionStorage,
        memory_manager: MemoryManager,
        model_manager: ModelManager,
        skill_system: Any | None = None,
        threat_intelligence_resolver: Callable[[], JsonDict | None] | None = None,
    ) -> None:
        self.tool_system = tool_system
        self.session_storage = session_storage
        self.memory_manager = memory_manager
        self.model_manager = model_manager
        self.skill_system = skill_system
        self.threat_intelligence_resolver = threat_intelligence_resolver
        self.tasks: dict[str, Task] = {}
        self.pending: queue.Queue[str] = queue.Queue()
        self.lock = threading.Lock()
        self.stop_event = threading.Event()
        self.workers: dict[str, threading.Thread] = {}
        self.worker_sequence = 0
        self.active_task_ids: dict[str, str] = {}

    def start(self) -> None:
        self.stop_event.clear()
        with self.lock:
            self.prune_dead_workers_locked()
            missing_workers = max(0, self.min_workers - len(self.workers))
        for _ in range(missing_workers):  # 创建初始woker在pool中
            self.spawn_worker()

    def stop(self) -> None:
        self.stop_event.set()
        with self.lock:
            workers = list(self.workers.values())
        for _ in workers:
            self.pending.put("")
        for worker in workers:
            if worker.is_alive():
                worker.join(timeout=2)
        with self.lock:
            self.prune_dead_workers_locked()
            self.active_task_ids.clear()

    def spawn_worker(self) -> None:
        with self.lock:
            self.prune_dead_workers_locked()
            if len(self.workers) >= self.max_workers:
                return
            self.worker_sequence += 1
            worker_name = f"task-pool-worker-{self.worker_sequence}"
            worker = threading.Thread(
                target=self.worker_loop,
                args=(worker_name,),
                name=worker_name,
                daemon=True,
            )
            self.workers[worker_name] = worker
        worker.start()

    def ensure_capacity(self) -> None:
        if self.stop_event.is_set():
            return
        with self.lock:
            self.prune_dead_workers_locked()
            worker_count = len(self.workers)
            active_count = len(self.active_task_ids)
            queued_count = self.pending.qsize()
            desired_count = min(
                self.max_workers,
                max(self.min_workers, active_count + queued_count),
            )
            missing_workers = max(0, desired_count - worker_count)
        for _ in range(missing_workers):
            self.spawn_worker()

    def worker_loop(self, worker_name: str) -> None:
        """
        worker 主循环，每个 worker 线程启动后都会执行这个函数。
        功能：
            1. 从任务队列中取任务
            2. 执行任务
            3. 维护 worker 活跃状态
            4. 空闲超时后自动退休
            5. worker 退出时清理状态
        """
        while not self.stop_event.is_set():
            try:
                task_id = self.pending.get(
                    timeout=self.idle_timeout_seconds
                )  # 从待处理队列中获取任务 ID
            except queue.Empty:  # 判断当前 worker 是否应该退休
                if self.should_retire_worker(worker_name):
                    break
                continue
            if not task_id:  # 说明这是一个无效任务
                self.pending.task_done()
                continue
            task = self.get_task_object(task_id)  # 根据 task_id 获取真正的任务对象
            if not task:  # 如果任务不存在
                self.pending.task_done()  # 标记队列任务完成
                continue  # 跳过当前任务
            with self.lock:  # 加锁，避免多线程竞争
                self.active_task_ids[worker_name] = (
                    task_id  # 记录当前 worker 正在执行哪个任务
                )

            try:
                task.task_execute()  # 任务对象真正的执行逻辑
            finally:  # 无论任务成功还是失败，都会执行清理逻辑
                with self.lock:
                    self.active_task_ids.pop(
                        worker_name, None
                    )  # 从活跃任务列表中移除当前 worker
                self.pending.task_done()  # 当前任务已经处理完成
                self.ensure_capacity()
        with self.lock:  # 加锁保护共享状态
            self.active_task_ids.pop(worker_name, None)  # 从活跃任务列表中移除 worker
            self.workers.pop(worker_name, None)  # 从 worker 列表中移除 worker

    def should_retire_worker(self, worker_name: str) -> bool:
        with self.lock:
            self.prune_dead_workers_locked(skip_name=worker_name)
            if len(self.workers) <= self.min_workers:
                return False
            if worker_name in self.active_task_ids:
                return False
            return self.pending.empty()

    def prune_dead_workers_locked(self, skip_name: str = "") -> None:
        for worker_name, worker in list(self.workers.items()):
            if worker_name == skip_name:
                continue
            if worker.ident is not None and not worker.is_alive():
                self.workers.pop(worker_name, None)
                self.active_task_ids.pop(worker_name, None)

    def submit_task(
        self, task_type: str, payload: dict[str, object] | None = None
    ) -> Task:
        task_model_manager = ModelManager(
            self.model_manager.get_llm_pool,
            self.model_manager.estimated_tokens,
        )
        task = Task(
            task_type=task_type,
            payload=payload or {},
            tool_system=self.tool_system,
            session_storage=self.session_storage,
            memory_manager=self.memory_manager,
            model_manager=task_model_manager,
            skill_system=self.skill_system,
            threat_intelligence_resolver=self.threat_intelligence_resolver,
        )
        with self.lock:
            self.tasks[task.id] = task
        self.session_storage.append_event(
            task.session_id,
            "task_queued",
            {
                "task_id": task.id,
                "task_type": task.task_type,
                "task_name": task.task_name,
            },
            agent_id=task.id,
        )
        self.pending.put(task.id)
        self.ensure_capacity()
        return task

    def get_task_object(self, task_id: str) -> Task | None:
        with self.lock:
            return self.tasks.get(task_id)

    def get_task(self, task_id: str, include_details: bool = True) -> dict[str, object]:
        task = self.get_task_object(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        return task.snapshot(include_details=include_details)

    def list_tasks(self, include_details: bool = False) -> list[dict[str, object]]:
        with self.lock:
            task_objects = list(self.tasks.values())
        snapshots = [
            task.snapshot(include_details=include_details)
            for task in task_objects
        ]
        return sorted(
            snapshots, key=lambda item: str(item.get("created_at", "")), reverse=True
        )

    def paginate_tasks(
        self,
        page: int = 1,
        page_size: int = 20,
        status: str = "",
        task_type: str = "",
        search: str = "",
    ) -> dict[str, object]:
        safe_page = max(1, int(page or 1))
        safe_page_size = min(max(1, int(page_size or 20)), 100)
        tasks = self.list_tasks()
        status_filter = str(status or "").strip().lower()
        type_filter = str(task_type or "").strip()
        search_filter = str(search or "").strip().lower()
        if status_filter:
            tasks = [
                task
                for task in tasks
                if str(task.get("status") or "").strip().lower() == status_filter
            ]
        if type_filter:
            tasks = [
                task
                for task in tasks
                if str(task.get("task_type") or "").strip() == type_filter
            ]
        if search_filter:
            filtered: list[dict[str, object]] = []
            for task in tasks:
                result = (
                    task.get("result") if isinstance(task.get("result"), dict) else {}
                )
                analysis_result = (
                    result.get("analysis_result")
                    if isinstance(result.get("analysis_result"), dict)
                    else {}
                )
                file_info = (
                    result.get("file_info")
                    if isinstance(result.get("file_info"), dict)
                    else {}
                )
                search_text = " ".join(
                    str(value or "")
                    for value in (
                        task.get("task_id"),
                        task.get("id"),
                        task.get("task_type"),
                        task.get("task_name"),
                        file_info.get("filename"),
                        file_info.get("path"),
                        analysis_result.get("summary"),
                        result.get("assistant_response"),
                    )
                ).lower()
                if search_filter in search_text:
                    filtered.append(task)
            tasks = filtered
        total = len(tasks)
        start = (safe_page - 1) * safe_page_size
        end = start + safe_page_size
        return {
            "items": tasks[start:end],
            "total": total,
            "page": safe_page,
            "page_size": safe_page_size,
            "total_pages": max(1, (total + safe_page_size - 1) // safe_page_size),
        }

    def wait_for_task(self, task_id: str, timeout: float = 180.0) -> dict[str, object]:
        task = self.get_task_object(task_id)
        if not task:
            raise HTTPException(status_code=404, detail="任务不存在")
        task.done_event.wait(timeout=timeout)
        return task.snapshot()

    def list_task_types(self) -> list[dict[str, str]]:
        return [
            {"id": task_type, "name": definition["name"]}
            for task_type, definition in TASK_TYPE_DEFINITIONS.items()
        ]

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            self.prune_dead_workers_locked()
            worker_names = sorted(self.workers)
            active_task_ids = dict(self.active_task_ids)
        return {
            "running": bool(worker_names),
            "min_workers": self.min_workers,
            "max_workers": self.max_workers,
            "idle_timeout_seconds": self.idle_timeout_seconds,
            "worker_count": len(worker_names),
            "active_worker_count": len(active_task_ids),
            "idle_worker_count": max(0, len(worker_names) - len(active_task_ids)),
            "workers": worker_names,
            "active_task_ids": active_task_ids,
            "queued_count": self.pending.qsize(),
            "task_count": len(self.tasks),
            "task_types": self.list_task_types(),
        }
