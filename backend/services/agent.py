import json
import os
import re
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Callable

from fastapi import HTTPException

from backend.config import REPORT_DIR, ROOT_DIR
from backend.data_structures import (
    build_agent_status_record,
    build_file_info_record,
    build_llm_snapshot_record,
    build_tool_execution_record,
)
from backend.services.llm_models import LLMPool, call_model
from backend.services.session_memory import MemoryManager, PromptManager, SessionStorage
from backend.services.tasks import TaskPool, normalize_task_type
from backend.services.tool_system import ToolSystem
from backend.utils import utc_now


def resolve_claude_command() -> list[str]:
    home_dir = Path.home()
    clawgod_original = home_dir / ".clawgod" / "cli.original.cjs"
    bun_candidates = [
        Path(shutil.which("bun")) if shutil.which("bun") else None,
        home_dir / ".bun" / "bin" / "bun.exe",
        home_dir / ".bun" / "bin" / "bun",
    ]
    for bun in bun_candidates:
        if bun and bun.exists() and clawgod_original.exists():
            return [str(bun), str(clawgod_original)]

    executable = shutil.which("claude")
    if executable:
        return [executable]
    candidates = [
        home_dir / ".local" / "bin" / "claude.cmd",
        home_dir / ".local" / "bin" / "claude.exe",
        home_dir / ".local" / "bin" / "claude",
        home_dir / ".bun" / "bin" / "claude",
        home_dir / ".npm-global" / "bin" / "claude",
        home_dir / "AppData" / "Roaming" / "npm" / "claude.cmd",
        home_dir / "AppData" / "Roaming" / "npm" / "claude.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return [str(candidate)]
    return ["claude"]


def resolve_claude_executable() -> str:
    return resolve_claude_command()[0]


def run_claude_code_task(
    system_prompt: str,
    query: str,
    cwd: str | Path | None = None,
    timeout_seconds: float | None = None,
    llm_platform: dict[str, object] | None = None,
    provider: str = "",
) -> dict[str, object]:
    """Run Claude Code CLI for a task and return its captured process output."""
    claude_command = resolve_claude_command()
    claude_executable = " ".join(claude_command)
    env = build_claude_code_env(llm_platform, provider)
    env_debug = claude_code_env_debug(env)
    command = [
        *claude_command,
        "--dangerously-skip-permissions",
        "--append-system-prompt",
        system_prompt,
        "-p",
    ]
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd or ROOT_DIR),
            input=query,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=env,
            check=False,
        )
        return {
            "status": "success" if completed.returncode == 0 else "failed",
            "command": "claude --dangerously-skip-permissions --append-system-prompt <system_prompt> -p <stdin-query>",
            "executable": claude_executable,
            "cwd": str(cwd or ROOT_DIR),
            "exit_code": completed.returncode,
            "stdout": completed.stdout,
            "stderr": completed.stderr,
            "env_debug": env_debug,
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "failed",
            "command": "claude --dangerously-skip-permissions --append-system-prompt <system_prompt> -p <stdin-query>",
            "executable": claude_executable,
            "cwd": str(cwd or ROOT_DIR),
            "exit_code": None,
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
            "error": f"Claude Code timed out after {timeout_seconds} seconds",
            "timed_out": True,
            "env_debug": env_debug,
        }
    except FileNotFoundError:
        return {
            "status": "failed",
            "command": "claude --dangerously-skip-permissions --append-system-prompt <system_prompt> -p <stdin-query>",
            "executable": claude_executable,
            "cwd": str(cwd or ROOT_DIR),
            "exit_code": None,
            "stdout": "",
            "stderr": "",
            "error": (
                "Claude Code CLI executable was not found in PATH or known install "
                f"locations. Tried executable: {claude_executable}"
            ),
            "env_debug": env_debug,
        }


def build_claude_code_env(
    llm_platform: dict[str, object] | None,
    provider: str = "",
) -> dict[str, str]:
    env = os.environ.copy()
    if not isinstance(llm_platform, dict):
        return env
    api_key = str(llm_platform.get("api_key") or llm_platform.get("token") or "").strip()
    if api_key:
        env["ANTHROPIC_API_KEY"] = api_key
    base_url = str(llm_platform.get("url") or "").strip().rstrip("/")
    provider_name = str(provider or "").strip().lower()
    if base_url:
        if provider_name == "deepseek" and not base_url.lower().endswith("/anthropic"):
            base_url = f"{base_url}/anthropic"
        env["ANTHROPIC_BASE_URL"] = base_url
    model = str(
        llm_platform.get("model")
        or llm_platform.get("model_name")
        or llm_platform.get("chat_model")
        or ""
    ).strip()
    if model:
        env["ANTHROPIC_MODEL"] = model
    return env


def claude_code_env_debug(env: dict[str, str]) -> dict[str, str]:
    api_key = str(env.get("ANTHROPIC_API_KEY") or "")
    return {
        "anthropic_key_suffix": api_key[-4:] if api_key else "",
        "anthropic_base_url": str(env.get("ANTHROPIC_BASE_URL") or ""),
        "anthropic_model": str(env.get("ANTHROPIC_MODEL") or ""),
    }


class LLMDecisionClient:
    def __init__(
        self,
        platform: dict[str, object] | None,
        tool_system: ToolSystem,
        prompt_manager: PromptManager,
        llm_pool: LLMPool,
    ) -> None:
        self.platform = platform
        self.tool_system = tool_system
        self.prompt_manager = prompt_manager
        self.llm_pool = llm_pool
        self.provider = llm_pool.detect_provider(platform) if platform else "none"

    def create_program_analysis_plan(
        self,
        file_info: dict[str, object],
        analysis_type: str,
        session_events: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        fallback_plan = self.local_program_analysis_plan(file_info, analysis_type)
        if not self.platform:
            fallback_plan["source"] = "local-fallback"
            fallback_plan["message"] = "未分配到LLM平台，已使用本地默认计划"
            return fallback_plan

        api_key = str(self.platform.get("api_key") or self.platform.get("token") or "").strip()
        if not api_key:
            fallback_plan["source"] = "local-fallback"
            fallback_plan["message"] = "LLM平台未配置认证信息，已使用本地默认计划"
            return fallback_plan

        try:
            generated = self.call_llm_for_plan(
                file_info,
                analysis_type,
                api_key,
                session_events=session_events,
            )
            steps = self.normalize_llm_steps(generated.get("steps", []))
            if not steps:
                raise ValueError("LLM未返回可执行工具步骤")
            return {
                "source": "llm",
                "provider": self.provider,
                "message": generated.get("summary") or "LLM已生成程序分析计划",
                "steps": steps,
            }
        except Exception as exc:
            fallback_plan["source"] = "llm-fallback"
            fallback_plan["message"] = f"LLM规划失败，已使用本地默认计划: {exc.__class__.__name__}"
            return fallback_plan

    def local_program_analysis_plan(
        self,
        file_info: dict[str, object],
        analysis_type: str,
    ) -> dict[str, object]:
        file_path = str(file_info.get("path") or "")
        escaped_path = file_path.replace('"', '\\"')
        return {
            "source": "local",
            "provider": self.provider,
            "message": "本地默认程序分析计划",
            "steps": [
                {
                    "tool": "Read",
                    "purpose": "读取文件内容",
                    "arguments": {"path": file_path, "max_bytes": 8192},
                },
                {
                    "tool": "PowerShell",
                    "purpose": "通过系统命令对文件进行分析",
                    "arguments": {
                        "command": f'Get-Item -LiteralPath "{escaped_path}" | Select-Object FullName,Length,LastWriteTime',
                        "timeout": 15,
                    },
                },
            ],
            "analysis_type": analysis_type,
        }

    def call_llm_for_plan(
        self,
        file_info: dict[str, object],
        analysis_type: str,
        api_key: str,
        session_events: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        prompt = self.build_prompt(file_info, analysis_type, session_events=session_events)
        response_text = call_model(
            self.provider,
            api_key,
            self.platform,
            [{"role": "user", "content": prompt}],
            timeout_seconds=20.0,
        )
        return self.parse_json_from_text(response_text)

    def build_prompt(
        self,
        file_info: dict[str, object],
        analysis_type: str,
        session_events: list[dict[str, object]] | None = None,
    ) -> str:
        return self.prompt_manager.build_program_analysis_prompt(
            file_info=file_info,
            analysis_type=analysis_type,
            tools=self.tool_system.list_tools(),
            session_events=session_events,
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

    def normalize_llm_steps(self, steps: object) -> list[dict[str, object]]:
        normalized_steps = []
        if not isinstance(steps, list):
            return normalized_steps
        for step in steps[:8]:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool") or "").strip()
            if not self.tool_system.get_tool(tool_name):
                continue
            arguments = step.get("arguments") if isinstance(step.get("arguments"), dict) else {}
            normalized_steps.append(
                {
                    "tool": tool_name,
                    "purpose": str(step.get("purpose") or "执行工具步骤").strip(),
                    "arguments": arguments,
                }
            )
        return normalized_steps


class Agent:
    def __init__(
        self,
        agent_id: str,
        session_id: str,
        tool_system: ToolSystem,
        session_storage: SessionStorage,
        prompt_manager: PromptManager,
        llm_pool: LLMPool,
        llm_selection: dict[str, object] | None = None,
        allocation_error: str = "",
    ) -> None:
        self.id = agent_id
        self.session_id = session_id
        self.tool_system = tool_system
        self.session_storage = session_storage
        self.prompt_manager = prompt_manager
        self.llm_pool = llm_pool
        self.llm_selection = llm_selection
        self.llm_platform = (
            llm_selection.get("platform") if isinstance(llm_selection, dict) else None
        )
        self.allocation_error = allocation_error
        self.created_at = utc_now()
        self.session_storage.append_event(
            self.session_id,
            "agent_created",
            {"agent_id": self.id, "llm": self.llm_snapshot()},
            agent_id=self.id,
        )

    def run_program_analysis(
        self,
        file_info: dict[str, object],
        analysis_type: str,
    ) -> dict[str, object]:
        self.session_storage.append_event(
            self.session_id,
            "program_analysis_started",
            {"file_info": file_info, "analysis_type": analysis_type},
            agent_id=self.id,
        )
        planner = LLMDecisionClient(
            self.llm_platform,
            self.tool_system,
            self.prompt_manager,
            self.llm_pool,
        )
        plan = planner.create_program_analysis_plan(
            file_info,
            analysis_type,
            session_events=self.session_storage.read_events(self.session_id, limit=80),
        )
        self.session_storage.append_event(
            self.session_id,
            "agent_plan",
            {"plan": plan},
            agent_id=self.id,
        )
        tool_results = []

        for step in plan.get("steps", []):
            if not isinstance(step, dict):
                continue
            try:
                execution = self.tool_system.execute(
                    str(step.get("tool") or ""),
                    step.get("arguments") if isinstance(step.get("arguments"), dict) else {},
                    session_id=self.session_id,
                    agent_id=self.id,
                )
                status = "success"
            except HTTPException as exc:
                execution = {"error": exc.detail}
                status = "failed"
            except Exception as exc:
                execution = {"error": exc.__class__.__name__}
                status = "failed"

            tool_results.append(
                build_tool_execution_record(
                    str(step.get("id") or uuid.uuid4().hex),
                    str(step.get("tool", "")),
                    str(step.get("purpose", "")),
                    status,
                    execution if isinstance(execution, dict) else {"value": execution},
                )
            )

        analysis_result = self.compose_program_analysis_result(
            file_info,
            analysis_type,
            plan,
            tool_results,
        )
        report = {
            "agent_id": self.id,
            "session_id": self.session_id,
            "file_info": file_info,
            "analysis_type": analysis_type,
            "llm": self.llm_snapshot(),
            "plan": plan,
            "tool_results": tool_results,
            "analysis_result": analysis_result,
            "generated_at": utc_now(),
        }
        report_path = REPORT_DIR / f"{self.id}.json"
        write_result = self.tool_system.execute(
            "Write",
            {
                "path": str(report_path),
                "content": json.dumps(report, ensure_ascii=False, indent=2, default=str),
                "overwrite": True,
            },
            session_id=self.session_id,
            agent_id=self.id,
        )
        write_result_payload = write_result.get("result") if isinstance(write_result, dict) else {}
        report["report_path"] = (
            write_result_payload.get("path")
            or write_result_payload.get("filePath")
            or str(report_path)
        )
        self.session_storage.append_event(
            self.session_id,
            "program_analysis_completed",
            {
                "agent_id": self.id,
                "report_path": report["report_path"],
                "summary": analysis_result.get("summary", ""),
            },
            agent_id=self.id,
        )
        return report

    def llm_snapshot(self) -> dict[str, object]:
        return build_llm_snapshot_record(
            self.llm_platform,
            self.llm_pool,
            self.llm_selection,
            self.allocation_error,
        )

    def compose_program_analysis_result(
        self,
        file_info: dict[str, object],
        analysis_type: str,
        plan: dict[str, object],
        tool_results: list[dict[str, object]],
    ) -> dict[str, object]:
        successful_tools = [item for item in tool_results if item.get("status") == "success"]
        failed_tools = [item for item in tool_results if item.get("status") != "success"]
        mode_text = "漏洞分析" if analysis_type == "vulnerability" else "样本分析"
        return {
            "summary": (
                f"{mode_text}任务已完成基础后端流程：文件已保存，"
                f"agent已生成计划并调用{len(successful_tools)}个工具。"
            ),
            "risk_level": "待规则引擎接入",
            "next_steps": [
                "接入反编译、字符串提取、YARA或SAST等专用工具后可扩展深度分析。",
                "工作台后续可按任务ID异步轮询agent执行状态。",
            ],
            "plan_source": plan.get("source", ""),
            "failed_tool_count": len(failed_tools),
            "file_name": file_info.get("filename", ""),
        }


class RequestManager:
    def __init__(
        self,
        tool_system: ToolSystem,
        session_storage: SessionStorage,
        prompt_manager: PromptManager,
        memory_manager: MemoryManager,
        get_llm_pool: Callable[[], LLMPool],
        task_pool: TaskPool | None = None,
    ) -> None:
        self.tool_system = tool_system
        self.session_storage = session_storage
        self.prompt_manager = prompt_manager
        self.memory_manager = memory_manager
        self.get_llm_pool = get_llm_pool
        self.task_pool = task_pool
        self.agents: dict[str, dict[str, object]] = {}

    def route_request(self, request: object) -> dict[str, object]:
        module = request.module.lower()
        action = request.action.lower()
        if module in {"tool-system", "tools", "工具系统", "工具管理"} and action == "execute":
            tool = str(request.payload.get("tool") or "")
            arguments = request.payload.get("arguments")
            return self.tool_system.execute(
                tool,
                arguments if isinstance(arguments, dict) else {},
                session_id=str(request.payload.get("session_id") or ""),
                agent_id=str(request.payload.get("agent_id") or ""),
            )
        if module in {"program-analysis", "程序分析"}:
            raise HTTPException(status_code=400, detail="程序分析请求需要通过文件上传接口提交")
        if module in {"task", "tasks", "工作台", "任务"} and action in {"create", "submit"}:
            task_type = str(request.payload.get("task_type") or request.payload.get("type") or "")
            payload = request.payload.get("payload")
            return self.create_task(task_type, payload if isinstance(payload, dict) else request.payload)
        raise HTTPException(status_code=404, detail="未找到对应的后端功能实现")

    def create_task(
        self,
        task_type: str,
        payload: dict[str, object] | None = None,
        wait: bool = False,
    ) -> dict[str, object]:
        if not self.task_pool:
            raise HTTPException(status_code=500, detail="Task Pool尚未初始化")
        task = self.task_pool.submit_task(task_type, payload or {})
        if wait:
            snapshot = self.task_pool.wait_for_task(task.id)
            return {
                "request_id": uuid.uuid4().hex,
                "task": snapshot,
                **(snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}),
            }
        return {
            "request_id": uuid.uuid4().hex,
            "task": task.snapshot(),
        }

    def create_program_analysis_task(
        self,
        file_path: Path,
        original_filename: str,
        analysis_type: str,
        execution_mode: str = "agent",
    ) -> dict[str, object]:
        if self.task_pool:
            file_info = self.build_file_info(file_path, original_filename)
            task_type = normalize_task_type(analysis_type)
            result = self.create_task(
                task_type,
                {
                    "analysis_type": analysis_type,
                    "execution_mode": execution_mode,
                    "file_info": file_info,
                    "file_path": str(file_path),
                    "original_filename": original_filename,
                },
                wait=True,
            )
            task = result.get("task") if isinstance(result.get("task"), dict) else {}
            return {
                "request_id": result.get("request_id", uuid.uuid4().hex),
                "session_id": task.get("session_id", ""),
                "agent_id": task.get("task_id", ""),
                "task_id": task.get("task_id", ""),
                "module": "program-analysis",
                "analysis_type": analysis_type,
                "file_info": file_info,
                **{
                    key: value
                    for key, value in result.items()
                    if key not in {"request_id", "task"}
                },
            }

        file_info = self.build_file_info(file_path, original_filename)
        session_id = self.session_storage.create_session(
            "program-analysis",
            {"analysis_type": analysis_type, "filename": original_filename},
        )
        agent = self.create_agent(session_id)
        self.agents[agent.id] = build_agent_status_record(
            agent_id=agent.id,
            session_id=session_id,
            created_at=agent.created_at,
            agent_type="program-analysis",
            file_name=original_filename,
            status="running",
            llm=agent.llm_snapshot(),
        )

        try:
            result = agent.run_program_analysis(file_info, analysis_type)
            status = "completed"
        except Exception as exc:
            result = {"error": exc.__class__.__name__}
            status = "failed"
        finally:
            self.release_agent_llm(agent)

        current_record = dict(self.agents.get(agent.id, {}))
        self.agents[agent.id] = {
            **current_record,
            **build_agent_status_record(
                agent_id=agent.id,
                session_id=session_id,
                created_at=str(current_record.get("created_at") or agent.created_at),
                agent_type=str(current_record.get("type") or "program-analysis"),
                file_name=str(current_record.get("file_name") or original_filename),
                status=status,
                llm=agent.llm_snapshot(),
                updated_at=utc_now(),
            ),
        }

        if status == "failed":
            raise HTTPException(status_code=500, detail="程序分析任务执行失败")

        self.memory_manager.add_record(
            title=f"程序分析记录 - {original_filename}",
            content=(
                f"分析类型：{analysis_type}\n"
                f"文件SHA256：{file_info['sha256']}\n"
                f"Agent：{agent.id}\n"
                f"报告：{result.get('report_path', '')}\n"
                f"摘要：{result.get('analysis_result', {}).get('summary', '')}"
            ),
            tags=["program-analysis", analysis_type],
            source="agent",
        )

        return {
            "request_id": uuid.uuid4().hex,
            "session_id": session_id,
            "agent_id": agent.id,
            "module": "program-analysis",
            "analysis_type": analysis_type,
            "file_info": file_info,
            **result,
        }

    def create_agent(self, session_id: str) -> Agent:
        llm_pool = self.get_llm_pool()
        selection = None
        allocation_error = ""
        try:
            selection = llm_pool.select_platform(estimated_tokens=4096)
            platform_id = str(selection["platform"].get("id", ""))
            if platform_id:
                llm_pool.occupy(platform_id)
                selection["occupied_count"] = llm_pool.occupied_counts.get(platform_id, 0)
        except HTTPException as exc:
            allocation_error = str(exc.detail)

        return Agent(
            agent_id=uuid.uuid4().hex,
            session_id=session_id,
            tool_system=self.tool_system,
            session_storage=self.session_storage,
            prompt_manager=self.prompt_manager,
            llm_pool=llm_pool,
            llm_selection=selection,
            allocation_error=allocation_error,
        )

    def release_agent_llm(self, agent: Agent) -> None:
        if not agent.llm_platform:
            return
        platform_id = str(agent.llm_platform.get("id") or "")
        if platform_id:
            self.get_llm_pool().release(platform_id)

    def build_file_info(self, file_path: Path, original_filename: str) -> dict[str, object]:
        return build_file_info_record(file_path, original_filename)

    def list_agents(self) -> list[dict[str, object]]:
        return sorted(
            self.agents.values(),
            key=lambda item: str(item.get("created_at", "")),
            reverse=True,
        )

    def get_agent(self, agent_id: str) -> dict[str, object]:
        agent = self.agents.get(agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="agent不存在")
        return agent
