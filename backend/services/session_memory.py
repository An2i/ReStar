import json
import re
import threading
import time
import uuid
from pathlib import Path
from threading import Lock
from html import unescape

from backend.config import REPORT_DIR, TOKEN_PATTERN
from backend.utils import append_jsonl, safe_record_id, utc_now


def truncate_text(value: object, limit: int = 1200) -> str:
    text = str(value or "")
    if len(text) <= limit:
        return text
    return text[:limit] + f"...<{len(text)} chars>"


def compact_task_snapshot(snapshot: dict[str, object]) -> dict[str, object]:
    compact = {
        key: value
        for key, value in snapshot.items()
        if key not in {"decisions", "last_decision", "tool_results", "runtime_trace"}
    }
    result = snapshot.get("result") if isinstance(snapshot.get("result"), dict) else {}
    analysis_result = (
        result.get("analysis_result")
        if isinstance(result.get("analysis_result"), dict)
        else {}
    )
    file_info = (
        snapshot.get("file_info")
        if isinstance(snapshot.get("file_info"), dict)
        else result.get("file_info")
        if isinstance(result.get("file_info"), dict)
        else {}
    )
    compact_result: dict[str, object] = {}
    if file_info:
        compact["file_info"] = dict(file_info)
        compact_result["file_info"] = dict(file_info)
    report_path = str(snapshot.get("report_path") or result.get("report_path") or "")
    if report_path:
        compact_result["report_path"] = report_path
    summary = str(analysis_result.get("summary") or "")
    assistant_response = str(
        result.get("assistant_response")
        or analysis_result.get("assistant_response")
        or ""
    )
    if summary or assistant_response:
        compact_result["analysis_result"] = {
            "summary": truncate_text(summary or assistant_response, 1200)
        }
    if assistant_response:
        compact_result["assistant_response"] = truncate_text(assistant_response, 1200)
    compact["result"] = compact_result
    return compact


class SessionStorage:
    """Append-only session/transcript storage inspired by Claude Code's session traces."""

    def __init__(self, root_dir: Path) -> None:
        self.root_dir = root_dir
        self.lock = Lock()
        self.cache_lock = Lock()
        self.cache_stop_event = threading.Event()
        self.cache_dirty_event = threading.Event()
        self.cache_thread: threading.Thread | None = None
        self.task_snapshot_cache: list[dict[str, object]] = []
        self.task_snapshot_cache_by_id: dict[str, dict[str, object]] = {}
        self.task_snapshot_cache_loaded = False

    def create_session(self, module: str, metadata: dict[str, object] | None = None) -> str:
        session_id = uuid.uuid4().hex
        self.append_event(
            session_id,
            "session_created",
            {
                "module": module,
                "metadata": metadata or {},
            },
        )
        return session_id

    def session_file(self, session_id: str) -> Path:
        return self.root_dir / f"{safe_record_id(session_id)}.jsonl"

    def append_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, object] | None = None,
        agent_id: str = "",
    ) -> dict[str, object]:
        event = {
            "id": uuid.uuid4().hex,
            "session_id": safe_record_id(session_id),
            "agent_id": safe_record_id(agent_id) if agent_id else "",
            "type": event_type,
            "payload": payload or {},
            "created_at": utc_now(),
        }
        with self.lock:
            append_jsonl(self.session_file(session_id), event)
            if agent_id:
                agent_file = (
                    self.root_dir
                    / safe_record_id(session_id)
                    / "agents"
                    / f"{safe_record_id(agent_id)}.jsonl"
                )
                append_jsonl(agent_file, event)
        if event_type in {
            "session_created",
            "task_queued",
            "task_completed",
            "task_failed",
        }:
            self.invalidate_task_snapshot_cache()
        return event

    def start_cache_worker(self) -> None:
        if self.cache_thread and self.cache_thread.is_alive():
            return
        self.cache_stop_event.clear()
        self.cache_dirty_event.set()
        self.cache_thread = threading.Thread(
            target=self.task_snapshot_cache_loop,
            name="session-task-cache",
            daemon=True,
        )
        self.cache_thread.start()

    def stop_cache_worker(self) -> None:
        self.cache_stop_event.set()
        self.cache_dirty_event.set()
        if self.cache_thread and self.cache_thread.is_alive():
            self.cache_thread.join(timeout=2)

    def invalidate_task_snapshot_cache(self) -> None:
        self.cache_dirty_event.set()

    def task_snapshot_cache_loop(self) -> None:
        while not self.cache_stop_event.is_set():
            self.cache_dirty_event.wait(timeout=5)
            if self.cache_stop_event.is_set():
                break
            if not self.cache_dirty_event.is_set() and self.task_snapshot_cache_loaded:
                continue
            self.cache_dirty_event.clear()
            try:
                self.refresh_task_snapshot_cache()
            except Exception:
                self.cache_dirty_event.set()
                time.sleep(1)

    def refresh_task_snapshot_cache(self) -> list[dict[str, object]]:
        snapshots = self.scan_task_snapshots()
        by_id = {
            str(task.get("task_id") or task.get("id") or ""): task
            for task in snapshots
            if str(task.get("task_id") or task.get("id") or "")
        }
        with self.cache_lock:
            self.task_snapshot_cache = snapshots
            self.task_snapshot_cache_by_id = by_id
            self.task_snapshot_cache_loaded = True
        return snapshots

    def read_events(self, session_id: str, limit: int = 200) -> list[dict[str, object]]:
        path = self.session_file(session_id)
        if not path.exists():
            return []
        lines = self.read_recent_lines(path, max(limit, 1))
        records = []
        for line in lines:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(parsed, dict):
                records.append(parsed)
        return records

    def read_recent_lines(self, path: Path, limit: int) -> list[str]:
        if limit <= 0:
            return []
        chunk_size = 64 * 1024
        with path.open("rb") as file_obj:
            file_obj.seek(0, 2)
            position = file_obj.tell()
            buffer = b""
            line_breaks = 0
            while position > 0 and line_breaks <= limit:
                read_size = min(chunk_size, position)
                position -= read_size
                file_obj.seek(position)
                chunk = file_obj.read(read_size)
                buffer = chunk + buffer
                line_breaks = buffer.count(b"\n")
        lines = buffer.decode("utf-8", errors="replace").splitlines()
        return lines[-limit:]

    def list_sessions(self) -> list[dict[str, object]]:
        if not self.root_dir.exists():
            return []
        sessions = []
        for path in self.root_dir.glob("*.jsonl"):
            events = self.read_events(path.stem, limit=1000)
            if not events:
                continue
            sessions.append(
                {
                    "session_id": path.stem,
                    "event_count": len(events),
                    "first_event": events[0].get("type", ""),
                    "last_event": events[-1].get("type", ""),
                    "created_at": events[0].get("created_at", ""),
                    "updated_at": events[-1].get("created_at", ""),
                }
            )
        return sorted(sessions, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def list_task_snapshots(self, include_details: bool = False) -> list[dict[str, object]]:
        with self.cache_lock:
            if self.task_snapshot_cache_loaded:
                snapshots = [dict(task) for task in self.task_snapshot_cache]
                return snapshots if include_details else [compact_task_snapshot(task) for task in snapshots]
        self.invalidate_task_snapshot_cache()
        return []

    def scan_task_snapshots(self) -> list[dict[str, object]]:
        if not self.root_dir.exists():
            return []
        tasks: list[dict[str, object]] = []
        for path in self.root_dir.glob("*.jsonl"):
            events = self.read_events(path.stem, limit=10000)
            snapshot = self.build_task_snapshot_from_events(path.stem, events)
            if snapshot:
                tasks.append(snapshot)
        return sorted(tasks, key=lambda item: str(item.get("updated_at", "")), reverse=True)

    def get_task_snapshot(self, task_id: str) -> dict[str, object] | None:
        safe_task_id = safe_record_id(task_id)
        with self.cache_lock:
            cached = self.task_snapshot_cache_by_id.get(safe_task_id)
            if cached:
                return dict(cached)
        if not self.task_snapshot_cache_loaded:
            self.refresh_task_snapshot_cache()
            with self.cache_lock:
                cached = self.task_snapshot_cache_by_id.get(safe_task_id)
                if cached:
                    return dict(cached)
        for path in self.root_dir.glob("*.jsonl"):
            events = self.read_events(path.stem, limit=10000)
            snapshot = self.build_task_snapshot_from_events(path.stem, events)
            if snapshot and str(snapshot.get("task_id") or "") == safe_task_id:
                return snapshot
        return None

    def build_task_snapshot_from_events(
        self, session_id: str, events: list[dict[str, object]]
    ) -> dict[str, object] | None:
        if not events:
            return None
        task_id = ""
        task_type = ""
        task_name = ""
        status = ""
        report_path = ""
        error = ""
        llm: dict[str, object] = {}
        last_decision: dict[str, object] = {}
        tool_result_count = 0
        result: dict[str, object] = {}
        created_at = str(events[0].get("created_at") or "")
        updated_at = str(events[-1].get("created_at") or created_at)
        started_at = ""
        completed_at = ""

        for event in events:
            event_type = str(event.get("type") or "")
            payload = event.get("payload") if isinstance(event.get("payload"), dict) else {}
            event_time = str(event.get("created_at") or "")

            if event_type == "session_created":
                metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
                task_id = task_id or str(metadata.get("task_id") or "")
                task_type = task_type or str(metadata.get("task_type") or "")
                task_name = task_name or str(metadata.get("task_name") or "")
            elif event_type == "task_queued":
                task_id = task_id or str(payload.get("task_id") or "")
                task_type = task_type or str(payload.get("task_type") or "")
                task_name = task_name or str(payload.get("task_name") or "")
                status = "queued"
            elif event_type == "task_environment_initialized":
                task_id = task_id or str(payload.get("task_id") or "")
                task_type = task_type or str(payload.get("task_type") or "")
                task_name = task_name or str(payload.get("task_name") or "")
                llm = payload.get("llm") if isinstance(payload.get("llm"), dict) else llm
                status = "running"
                started_at = started_at or event_time
            elif event_type == "task_loop_decision":
                decision = payload.get("decision") if isinstance(payload.get("decision"), dict) else {}
                if decision:
                    last_decision = decision
                status = "running"
            elif event_type == "tool_result":
                tool_result_count += 1
                nested = payload.get("payload") if isinstance(payload.get("payload"), dict) else {}
                rendered = nested.get("rendered") if isinstance(nested.get("rendered"), dict) else {}
                summary = str(rendered.get("summary") or rendered.get("transcript") or "")
                if summary:
                    result.setdefault("analysis_result", {}).setdefault(
                        "summary", summary[:220]
                    )
                if status not in {"completed", "failed"}:
                    status = "running"
            elif event_type == "task_completed":
                task_id = task_id or str(payload.get("task_id") or "")
                report_path = str(payload.get("report_path") or report_path)
                completed_result = (
                    payload.get("result")
                    if isinstance(payload.get("result"), dict)
                    else {}
                )
                if completed_result:
                    result = dict(completed_result)
                    if not report_path:
                        report_path = str(result.get("report_path") or "")
                summary = str(payload.get("summary") or "")
                if summary:
                    result.setdefault("analysis_result", {})["summary"] = summary
                status = "completed"
                completed_at = event_time
            elif event_type == "task_failed":
                task_id = task_id or str(payload.get("task_id") or "")
                error = str(payload.get("error") or "")
                status = "failed"
                completed_at = event_time

        if not task_id:
            return None
        if status not in {"completed", "failed"}:
            recovered_report_path = report_path
            if not recovered_report_path:
                candidate_report = REPORT_DIR / f"{safe_record_id(task_id)}.html"
                if candidate_report.exists():
                    recovered_report_path = str(candidate_report)
            recovered_report = self.resolve_report_path(recovered_report_path)
            if recovered_report and recovered_report.exists():
                status = "completed"
                report_path = recovered_report_path
                completed_at = completed_at or updated_at
        if not status:
            status = "running"
        if status == "completed" and report_path and not self.has_displayable_result(result):
            result = self.recover_result_from_report_html(
                report_path=report_path,
                task_id=task_id,
                task_type=task_type,
                task_name=task_name,
                result=result,
            )
        return {
            "id": safe_record_id(task_id),
            "task_id": safe_record_id(task_id),
            "task_type": task_type,
            "task_name": task_name or task_type,
            "session_id": safe_record_id(session_id),
            "status": status,
            "created_at": created_at,
            "updated_at": updated_at,
            "started_at": started_at,
            "completed_at": completed_at,
            "iteration_count": int(
                max(
                    [
                        int(event.get("payload", {}).get("iteration", 0))
                        for event in events
                        if isinstance(event.get("payload"), dict)
                    ]
                    or [0]
                )
            ),
            "llm": llm,
            "tool_result_count": tool_result_count,
            "last_decision": last_decision,
            "result": result,
            "error": error,
            "report_path": report_path,
        }

    @staticmethod
    def has_displayable_result(result: dict[str, object]) -> bool:
        analysis_result = (
            result.get("analysis_result")
            if isinstance(result.get("analysis_result"), dict)
            else {}
        )
        structured_report = (
            analysis_result.get("structured_report")
            if isinstance(analysis_result.get("structured_report"), dict)
            else {}
        )
        return bool(
            result.get("assistant_response")
            or analysis_result.get("assistant_response")
            or structured_report
        )

    def recover_result_from_report_html(
        self,
        *,
        report_path: str,
        task_id: str,
        task_type: str,
        task_name: str,
        result: dict[str, object],
    ) -> dict[str, object]:
        path = self.resolve_report_path(report_path)
        if not path or not path.exists():
            return result
        try:
            html = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return result
        text = self.html_to_text(html)
        if not text:
            return result

        recovered = dict(result)
        recovered.setdefault("task_id", safe_record_id(task_id))
        recovered.setdefault("task_type", task_type)
        recovered.setdefault("task_name", task_name or task_type)
        recovered.setdefault("assistant_response", text)
        recovered.setdefault("report_path", str(path))
        analysis_result = (
            recovered.get("analysis_result")
            if isinstance(recovered.get("analysis_result"), dict)
            else {}
        )
        summary = self.extract_report_summary(html, text)
        structured_report = self.extract_structured_report_from_html(html, task_type, summary)
        if structured_report:
            analysis_result["structured_report"] = structured_report
        analysis_result.setdefault("summary", summary or text[:220])
        analysis_result.setdefault("assistant_response", text)
        recovered["analysis_result"] = analysis_result
        return recovered

    @staticmethod
    def resolve_report_path(report_path: str) -> Path | None:
        value = str(report_path or "").strip()
        if not value:
            return None
        path = Path(value)
        if path.exists():
            return path
        return REPORT_DIR / path.name

    @staticmethod
    def html_to_text(html: str) -> str:
        text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", html)
        text = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text = re.sub(r"(?i)</(p|div|section|article|li|h[1-6]|tr)>", "\n", text)
        text = re.sub(r"(?s)<[^>]+>", " ", text)
        text = unescape(text)
        text = re.sub(r"[ \t]+", " ", text)
        text = re.sub(r"\n\s*\n+", "\n\n", text)
        return text.strip()

    @staticmethod
    def extract_report_summary(html: str, fallback_text: str) -> str:
        match = re.search(r'<p class="summary">(.*?)</p>', html, re.IGNORECASE | re.DOTALL)
        if match:
            return SessionStorage.html_to_text(match.group(1))[:1200]
        lines = [line.strip() for line in fallback_text.splitlines() if line.strip()]
        return lines[0][:1200] if lines else ""

    def extract_structured_report_from_html(
        self, html: str, task_type: str, summary: str
    ) -> dict[str, object]:
        if task_type not in {"vulnerability-mining", "sample-analysis"}:
            return {}
        if task_type == "sample-analysis":
            return {
                "report_type": "sample-analysis",
                "executive_summary": {
                    "verdict": "",
                    "is_malicious": False,
                    "confidence": "",
                    "severity": "",
                    "family": "",
                    "summary": summary,
                },
                "sample_profile": {},
                "capabilities": [],
                "behavior_summary": {},
                "iocs": self.extract_iocs_from_html(html),
                "detection_recommendations": [],
                "limitations": self.extract_list_after_heading(html, "限制说明"),
                "next_steps": self.extract_list_after_heading(html, "后续建议"),
            }
        return {
            "report_type": "vulnerability-mining",
            "executive_summary": {
                "affected_target": "",
                "overall_risk": self.extract_hero_metric(html, "总体风险"),
                "confidence": self.extract_hero_metric(html, "置信度"),
                "verdict": self.extract_hero_metric(html, "结论"),
                "summary": summary,
            },
            "attack_surface": [],
            "findings": self.extract_findings_from_html(html),
            "iocs": self.extract_iocs_from_html(html),
            "next_steps": self.extract_list_after_heading(html, "后续建议"),
            "limitations": self.extract_list_after_heading(html, "限制说明"),
        }

    @staticmethod
    def extract_hero_metric(html: str, label: str) -> str:
        pattern = rf"<span>{re.escape(label)}</span>\s*<strong>(.*?)</strong>"
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        return SessionStorage.html_to_text(match.group(1)) if match else ""

    def extract_findings_from_html(self, html: str) -> list[dict[str, object]]:
        findings: list[dict[str, object]] = []
        cards = re.findall(
            r'<article class="finding-card">(.*?)</article>',
            html,
            re.IGNORECASE | re.DOTALL,
        )
        for index, card in enumerate(cards, start=1):
            title_match = re.search(r"<strong>(.*?)</strong>", card, re.IGNORECASE | re.DOTALL)
            severity_match = re.search(
                r'<span class="badge[^"]*">(.*?)</span>',
                card,
                re.IGNORECASE | re.DOTALL,
            )
            meta = dict(
                re.findall(
                    r'<div class="meta-item"><span>(.*?)</span><strong>(.*?)</strong></div>',
                    card,
                    re.IGNORECASE | re.DOTALL,
                )
            )
            sections = self.extract_named_sections(card)
            title_text = self.html_to_text(title_match.group(1)) if title_match else f"Finding {index}"
            finding_id, title = self.split_finding_title(title_text, index)
            findings.append(
                {
                    "id": finding_id,
                    "title": title,
                    "severity": self.html_to_text(severity_match.group(1)) if severity_match else "",
                    "confidence": self.html_to_text(meta.get("置信度", "")),
                    "status": self.html_to_text(meta.get("状态", "")),
                    "category": self.html_to_text(meta.get("分类", "")),
                    "location": self.html_to_text(meta.get("位置", "")),
                    "evidence": sections.get("证据", []),
                    "impact": " ".join(sections.get("影响", [])),
                    "exploitability": " ".join(sections.get("可利用性", [])),
                    "reproduction_steps": sections.get("复现步骤", []),
                    "remediation": sections.get("修复建议", []),
                }
            )
        return findings

    @staticmethod
    def split_finding_title(value: str, index: int) -> tuple[str, str]:
        match = re.match(r"^([A-Za-z]+-\d+)\s+(.+)$", value)
        if match:
            return match.group(1), match.group(2)
        return f"F-{index:03d}", value

    def extract_named_sections(self, html: str) -> dict[str, list[str]]:
        sections: dict[str, list[str]] = {}
        for title, body in re.findall(
            r"<section><h4>(.*?)</h4>(.*?)</section>",
            html,
            re.IGNORECASE | re.DOTALL,
        ):
            title_text = self.html_to_text(title)
            items = re.findall(r"<li>(.*?)</li>", body, re.IGNORECASE | re.DOTALL)
            if items:
                sections[title_text] = [self.html_to_text(item) for item in items]
            else:
                body_text = self.html_to_text(body)
                sections[title_text] = [body_text] if body_text else []
        return sections

    def extract_list_after_heading(self, html: str, heading: str) -> list[str]:
        pattern = rf"<h2>{re.escape(heading)}</h2>\s*<ul>(.*?)</ul>"
        match = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        return [
            self.html_to_text(item)
            for item in re.findall(r"<li>(.*?)</li>", match.group(1), re.IGNORECASE | re.DOTALL)
        ]

    def extract_iocs_from_html(self, html: str) -> list[dict[str, object]]:
        match = re.search(r"<h2>IOC</h2>\s*<table>.*?<tbody>(.*?)</tbody>", html, re.IGNORECASE | re.DOTALL)
        if not match:
            return []
        rows = re.findall(r"<tr>(.*?)</tr>", match.group(1), re.IGNORECASE | re.DOTALL)
        iocs: list[dict[str, object]] = []
        for row in rows:
            cells = [self.html_to_text(cell) for cell in re.findall(r"<td>(.*?)</td>", row, re.IGNORECASE | re.DOTALL)]
            if len(cells) >= 3:
                iocs.append({"type": cells[0], "value": cells[1], "context": cells[2]})
        return iocs


class MemoryManager:
    """Project-local memory store used when building agent prompts."""

    def __init__(self, memory_file: Path) -> None:
        self.memory_file = memory_file
        self.lock = Lock()
        self.ensure_memory_file()

    def ensure_memory_file(self) -> None:
        if self.memory_file.exists():
            return
        self.memory_file.parent.mkdir(parents=True, exist_ok=True)
        self.memory_file.write_text(
            "# CodeX Memory\n\n"
            "用于记录agent在任务执行中可复用的项目知识、工具经验和分析偏好。\n",
            encoding="utf-8",
        )

    def add_record(
        self,
        title: str,
        content: str,
        tags: list[str] | None = None,
        source: str = "manual",
    ) -> dict[str, object]:
        record = {
            "id": uuid.uuid4().hex,
            "title": title.strip(),
            "content": content.strip(),
            "tags": [str(tag).strip() for tag in tags or [] if str(tag).strip()],
            "source": source,
            "created_at": utc_now(),
        }
        block = (
            f"\n\n## {record['title']}\n"
            f"- id: {record['id']}\n"
            f"- source: {record['source']}\n"
            f"- tags: {', '.join(record['tags']) if record['tags'] else '无'}\n"
            f"- created_at: {record['created_at']}\n\n"
            f"{record['content']}\n"
        )
        with self.lock:
            self.ensure_memory_file()
            with self.memory_file.open("a", encoding="utf-8") as file_obj:
                file_obj.write(block)
        return record

    def raw_text(self) -> str:
        self.ensure_memory_file()
        return self.memory_file.read_text(encoding="utf-8")

    def list_records(self) -> list[dict[str, object]]:
        text = self.raw_text()
        sections = re.split(r"\n(?=## )", text)
        records = []
        for section in sections:
            if not section.startswith("## "):
                continue
            title = section.splitlines()[0].replace("##", "", 1).strip()
            records.append({"title": title, "content": section.strip()})
        return records

    def recall(self, query: str, limit: int = 5) -> list[dict[str, object]]:
        query_tokens = set(TOKEN_PATTERN.findall(query.lower()))
        candidates = []
        for record in self.list_records():
            text = f"{record['title']} {record['content']}".lower()
            tokens = set(TOKEN_PATTERN.findall(text))
            score = len(query_tokens & tokens)
            if score > 0:
                candidates.append((score, record))
        candidates.sort(key=lambda item: item[0], reverse=True)
        return [record for _, record in candidates[:limit]]

    def context_for(self, query: str, limit: int = 5, max_chars: int = 4000) -> str:
        records = self.recall(query, limit=limit)
        if not records:
            return "暂无相关Memory。"
        text = "\n\n".join(record["content"] for record in records)
        return text[:max_chars]


class PromptManager:
    """Builds layered prompts instead of embedding all instructions in agent code."""

    base_policy = (
        "你是软件安全工作平台中的后端agent。你必须只使用系统提供的工具，"
        "优先读取事实，再规划，最后执行；不要编造工具结果。"
    )

    def __init__(self, memory_manager: MemoryManager) -> None:
        self.memory_manager = memory_manager

    #创建初始系统提示词
    def build_program_analysis_prompt( 
        self,
        file_info: dict[str, object],
        analysis_type: str,
        tools: list[dict[str, object]],
        session_events: list[dict[str, object]] | None = None,
    ) -> str:
        memory_context = self.memory_manager.context_for(
            f"程序分析 {analysis_type} {file_info.get('filename', '')}"
        )
        tool_specs = [
            {
                "name": tool.get("name", ""),
                "command_line": tool.get("command_line", ""),
                "description": tool.get("description", ""),
                "search_hint": tool.get("search_hint", ""),
                "prompt_excerpt": str(tool.get("prompt", ""))[:1600],
                "input_schema": tool.get("input_schema", {}),
                "permission": tool.get("permission", {}),
            }
            for tool in tools
        ]
        session_summary = [
            {"type": event.get("type", ""), "created_at": event.get("created_at", "")}
            for event in (session_events or [])[-8:]
        ]
        return (
            "请只返回JSON，不要返回Markdown或解释性文本。\n"
            # "JSON格式：{\"summary\":\"...\",\"steps\":[{\"tool\":\"工具名称\","
            # "\"purpose\":\"目的\",\"arguments\":{...}}]}。\n\n"
            # f"[System]\n{self.base_policy}\n\n"
            # f"[Task]\n分析类型：{analysis_type}\n"
            # f"上传文件：{json.dumps(file_info, ensure_ascii=False)}\n\n"
            # f"[Memory]\n{memory_context}\n\n"
            # f"[Session]\n{json.dumps(session_summary, ensure_ascii=False)}\n\n"
            # "[ToolPrompt]\n"
            # "工具系统中保存了每个工具的完整prompt；此处只展示prompt_excerpt以控制上下文。"
            # "请依据description、prompt_excerpt和input_schema选择工具。\n\n"
            # f"[Tools]\n{json.dumps(tool_specs, ensure_ascii=False)}\n"
        )
