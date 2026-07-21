import html
import json

from backend.data_structures import JsonDict


STRUCTURED_REPORT_TASKS = {"vulnerability-mining", "sample-analysis"}


def is_structured_report_task(task_type: str) -> bool:
    return task_type in STRUCTURED_REPORT_TASKS


def structured_report_schema(task_type: str) -> JsonDict:
    meta_rows = [
        ("任务类型", task_name),
        ("任务 ID", task_id),
        ("目标文件", file_info.get("filename") or file_info.get("path") or ""),
        ("生成时间", generated_at),
    ]
    if task_type == "sample-analysis":
        body = _render_sample_report_body(task_name, meta_rows, report)
    elif task_type == "vulnerability-mining":
        return {
            "type": "object",
            "additionalProperties": False,
            "required": [
                "report_type",
                "executive_summary",
                "attack_surface",
                "findings",
                "iocs",
                "next_steps",
                "limitations",
            ],
            "properties": {
                "report_type": {"type": "string", "enum": ["vulnerability-mining"]},
                "executive_summary": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "affected_target",
                        "overall_risk",
                        "confidence",
                        "verdict",
                        "summary",
                    ],
                    "properties": {
                        "affected_target": {"type": "string"},
                        "overall_risk": {"type": "string"},
                        "confidence": {"type": "string"},
                        "verdict": {"type": "string"},
                        "summary": {"type": "string"},
                    },
                },
                "attack_surface": {"type": "array", "items": {"type": "string"}},
                "findings": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": [
                            "id",
                            "title",
                            "severity",
                            "confidence",
                            "status",
                            "category",
                            "location",
                            "evidence",
                            "impact",
                            "exploitability",
                            "reproduction_steps",
                            "remediation",
                        ],
                        "properties": {
                            "id": {"type": "string"},
                            "title": {"type": "string"},
                            "severity": {"type": "string"},
                            "confidence": {"type": "string"},
                            "status": {"type": "string"},
                            "category": {"type": "string"},
                            "location": {"type": "string"},
                            "evidence": {"type": "array", "items": {"type": "string"}},
                            "impact": {"type": "string"},
                            "exploitability": {"type": "string"},
                            "reproduction_steps": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "remediation": {"type": "array", "items": {"type": "string"}},
                        },
                    },
                },
                "iocs": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["type", "value", "context"],
                        "properties": {
                            "type": {"type": "string"},
                            "value": {"type": "string"},
                            "context": {"type": "string"},
                        },
                    },
                },
                "next_steps": {"type": "array", "items": {"type": "string"}},
                "limitations": {"type": "array", "items": {"type": "string"}},
            },
        }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "report_type",
            "executive_summary",
            "sample_profile",
            "capabilities",
            "behavior_summary",
            "iocs",
            "detection_recommendations",
            "limitations",
            "next_steps",
        ],
        "properties": {
            "report_type": {"type": "string", "enum": ["sample-analysis"]},
            "executive_summary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "verdict",
                    "is_malicious",
                    "confidence",
                    "severity",
                    "family",
                    "summary",
                ],
                "properties": {
                    "verdict": {"type": "string"},
                    "is_malicious": {"type": "boolean"},
                    "confidence": {"type": "string"},
                    "severity": {"type": "string"},
                    "family": {"type": "string"},
                    "summary": {"type": "string"},
                },
            },
            "sample_profile": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "file_name",
                    "file_type",
                    "architecture",
                    "platform",
                    "size_bytes",
                    "hashes",
                ],
                "properties": {
                    "file_name": {"type": "string"},
                    "file_type": {"type": "string"},
                    "architecture": {"type": "string"},
                    "platform": {"type": "string"},
                    "size_bytes": {"type": "integer"},
                    "hashes": {
                        "type": "object",
                        "additionalProperties": False,
                        "required": ["md5", "sha256"],
                        "properties": {
                            "md5": {"type": "string"},
                            "sha256": {"type": "string"},
                        },
                    },
                },
            },
            "capabilities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["name", "confidence", "evidence", "mitre_techniques"],
                    "properties": {
                        "name": {"type": "string"},
                        "confidence": {"type": "string"},
                        "evidence": {"type": "array", "items": {"type": "string"}},
                        "mitre_techniques": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                },
            },
            "behavior_summary": {
                "type": "object",
                "additionalProperties": False,
                "required": [
                    "persistence",
                    "network",
                    "filesystem",
                    "process",
                    "registry",
                    "defense_evasion",
                ],
                "properties": {
                    "persistence": {"type": "array", "items": {"type": "string"}},
                    "network": {"type": "array", "items": {"type": "string"}},
                    "filesystem": {"type": "array", "items": {"type": "string"}},
                    "process": {"type": "array", "items": {"type": "string"}},
                    "registry": {"type": "array", "items": {"type": "string"}},
                    "defense_evasion": {"type": "array", "items": {"type": "string"}},
                },
            },
            "iocs": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["type", "value", "context", "severity"],
                    "properties": {
                        "type": {"type": "string"},
                        "value": {"type": "string"},
                        "context": {"type": "string"},
                        "severity": {"type": "string"},
                    },
                },
            },
            "detection_recommendations": {
                "type": "array",
                "items": {"type": "string"},
            },
            "limitations": {"type": "array", "items": {"type": "string"}},
            "next_steps": {"type": "array", "items": {"type": "string"}},
        },
    }


def structured_report_instruction(task_type: str) -> str:
    schema = json.dumps(structured_report_schema(task_type), ensure_ascii=False, indent=2)
    if task_type == "vulnerability-mining":
        task_hint = (
            "面向漏洞挖掘结果生成结构化报告。只保留已从工具证据中得到支持的结论。"
            "如果某项无法确认，请在 limitations 中说明，不要编造。"
        )
    else:
        task_hint = (
            "面向样本分析结果生成结构化报告。区分已确认行为、合理推测和待验证点。"
            "IOC、能力、行为总结都必须有证据基础。"
        )
    return (
        "你现在只负责生成最终分析报告 JSON，不再调用任何工具。\n"
        f"{task_hint}\n"
        "严格要求：\n"
        "1. 只输出一个 JSON 对象。\n"
        "2. 不要输出 Markdown、代码块、解释文字、前后缀。\n"
        "3. 必须满足下面 schema 的字段结构。\n"
        "4. 字段缺失时使用空字符串、空数组、false 或 0，不要省略 required 字段。\n\n"
        f"{schema}"
    )


def _str(value: object, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _bool(value: object, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "1"}:
            return True
        if lowered in {"false", "no", "0"}:
            return False
    return default


def _int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _list_of_str(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = _str(item)
        if text:
            items.append(text)
    return items


def _dict(value: object) -> JsonDict:
    return dict(value) if isinstance(value, dict) else {}


def normalize_structured_report(
    task_type: str,
    payload: JsonDict,
    file_info: JsonDict | None = None,
) -> JsonDict:
    report = _dict(payload)
    file_info = _dict(file_info)
    if task_type == "vulnerability-mining":
        executive = _dict(report.get("executive_summary"))
        findings = []
        for item in report.get("findings", []):
            row = _dict(item)
            findings.append(
                {
                    "id": _str(row.get("id")) or f"V-{len(findings) + 1:03d}",
                    "title": _str(row.get("title")),
                    "severity": _str(row.get("severity"), "unknown"),
                    "confidence": _str(row.get("confidence"), "unknown"),
                    "status": _str(row.get("status"), "confirmed"),
                    "category": _str(row.get("category")),
                    "location": _str(row.get("location")),
                    "evidence": _list_of_str(row.get("evidence")),
                    "impact": _str(row.get("impact")),
                    "exploitability": _str(row.get("exploitability")),
                    "reproduction_steps": _list_of_str(row.get("reproduction_steps")),
                    "remediation": _list_of_str(row.get("remediation")),
                }
            )
        iocs = []
        for item in report.get("iocs", []):
            row = _dict(item)
            iocs.append(
                {
                    "type": _str(row.get("type")),
                    "value": _str(row.get("value")),
                    "context": _str(row.get("context")),
                }
            )
        return {
            "report_type": "vulnerability-mining",
            "executive_summary": {
                "affected_target": _str(executive.get("affected_target"))
                or _str(file_info.get("filename")),
                "overall_risk": _str(executive.get("overall_risk"), "unknown"),
                "confidence": _str(executive.get("confidence"), "unknown"),
                "verdict": _str(executive.get("verdict")),
                "summary": _str(executive.get("summary")),
            },
            "attack_surface": _list_of_str(report.get("attack_surface")),
            "findings": findings,
            "iocs": iocs,
            "next_steps": _list_of_str(report.get("next_steps")),
            "limitations": _list_of_str(report.get("limitations")),
        }
    executive = _dict(report.get("executive_summary"))
    profile = _dict(report.get("sample_profile"))
    hashes = _dict(profile.get("hashes"))
    capabilities = []
    for item in report.get("capabilities", []):
        row = _dict(item)
        capabilities.append(
            {
                "name": _str(row.get("name")),
                "confidence": _str(row.get("confidence"), "unknown"),
                "evidence": _list_of_str(row.get("evidence")),
                "mitre_techniques": _list_of_str(row.get("mitre_techniques")),
            }
        )
    behavior = _dict(report.get("behavior_summary"))
    iocs = []
    for item in report.get("iocs", []):
        row = _dict(item)
        iocs.append(
            {
                "type": _str(row.get("type")),
                "value": _str(row.get("value")),
                "context": _str(row.get("context")),
                "severity": _str(row.get("severity"), "unknown"),
            }
        )
    return {
        "report_type": "sample-analysis",
        "executive_summary": {
            "verdict": _str(executive.get("verdict")),
            "is_malicious": _bool(executive.get("is_malicious")),
            "confidence": _str(executive.get("confidence"), "unknown"),
            "severity": _str(executive.get("severity"), "unknown"),
            "family": _str(executive.get("family")),
            "summary": _str(executive.get("summary")),
        },
        "sample_profile": {
            "file_name": _str(profile.get("file_name")) or _str(file_info.get("filename")),
            "file_type": _str(profile.get("file_type")),
            "architecture": _str(profile.get("architecture")),
            "platform": _str(profile.get("platform")),
            "size_bytes": _int(profile.get("size_bytes") or file_info.get("size")),
            "hashes": {
                "md5": _str(hashes.get("md5")) or _str(file_info.get("md5")),
                "sha256": _str(hashes.get("sha256")) or _str(file_info.get("sha256")),
            },
        },
        "capabilities": capabilities,
        "behavior_summary": {
            "persistence": _list_of_str(behavior.get("persistence")),
            "network": _list_of_str(behavior.get("network")),
            "filesystem": _list_of_str(behavior.get("filesystem")),
            "process": _list_of_str(behavior.get("process")),
            "registry": _list_of_str(behavior.get("registry")),
            "defense_evasion": _list_of_str(behavior.get("defense_evasion")),
        },
        "iocs": iocs,
        "detection_recommendations": _list_of_str(report.get("detection_recommendations")),
        "limitations": _list_of_str(report.get("limitations")),
        "next_steps": _list_of_str(report.get("next_steps")),
    }


def structured_report_summary(task_type: str, report: JsonDict) -> str:
    executive = _dict(report.get("executive_summary"))
    if task_type == "vulnerability-mining":
        findings = report.get("findings") if isinstance(report.get("findings"), list) else []
        return (
            f"漏洞挖掘报告已生成：总体风险 {_str(executive.get('overall_risk'), 'unknown')}，"
            f"发现 {len(findings)} 个结构化问题项。"
        )
    iocs = report.get("iocs") if isinstance(report.get("iocs"), list) else []
    capabilities = report.get("capabilities") if isinstance(report.get("capabilities"), list) else []
    verdict = "恶意" if _bool(executive.get("is_malicious")) else "可疑/未证实"
    return (
        f"样本分析报告已生成：结论 {verdict}，"
        f"提取 {len(capabilities)} 项能力与 {len(iocs)} 条 IOC。"
    )


def _escape(value: object) -> str:
    return html.escape(_str(value))


def _render_list(items: list[str], empty_text: str = "无") -> str:
    if not items:
        return f'<p class="empty">{_escape(empty_text)}</p>'
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _render_kv_rows(rows: list[tuple[str, object]]) -> str:
    return "".join(
        f"<div class=\"meta-item\"><span>{_escape(label)}</span><strong>{_escape(value)}</strong></div>"
        for label, value in rows
    )


def _render_ioc_table(rows: list[JsonDict], empty_cols: int = 4) -> str:
    if not rows:
        return f'<tr><td colspan="{empty_cols}">无</td></tr>'
    return "".join(
        f"<tr><td>{_escape(item.get('type'))}</td><td>{_escape(item.get('value'))}</td><td>{_escape(item.get('context'))}</td><td>{_escape(item.get('severity'))}</td></tr>"
        for item in rows
    )


def _severity_class(value: object) -> str:
    text = _str(value).lower()
    if text in {"critical", "high", "严重", "高"}:
        return "sev-high"
    if text in {"medium", "中"}:
        return "sev-medium"
    if text in {"low", "低"}:
        return "sev-low"
    return "sev-unknown"


def _render_list(items: list[str], empty_text: str = "无") -> str:
    if not items:
        return f'<p class="empty">{_escape(empty_text)}</p>'
    return "<ul>" + "".join(f"<li>{_escape(item)}</li>" for item in items) + "</ul>"


def _render_ioc_table(rows: list[JsonDict], empty_cols: int = 4) -> str:
    if not rows:
        return f'<tr><td colspan="{empty_cols}">无</td></tr>'
    return "".join(
        f"<tr><td>{_escape(item.get('type'))}</td><td>{_escape(item.get('value'))}</td><td>{_escape(item.get('context'))}</td><td>{_escape(item.get('severity'))}</td></tr>"
        for item in rows
    )


def _severity_class(value: object) -> str:
    text = _str(value).lower()
    if text in {"critical", "high", "严重", "高"}:
        return "sev-high"
    if text in {"medium", "中"}:
        return "sev-medium"
    if text in {"low", "低"}:
        return "sev-low"
    return "sev-unknown"


def _render_object_list(items: object, fields: list[str], empty_cols: int) -> str:
    rows = items if isinstance(items, list) else []
    if not rows:
        return f'<tr><td colspan="{empty_cols}">无</td></tr>'
    rendered = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        rendered.append(
            "<tr>"
            + "".join(f"<td>{_escape(item.get(field))}</td>" for field in fields)
            + "</tr>"
        )
    return "".join(rendered) or f'<tr><td colspan="{empty_cols}">无</td></tr>'


def _render_sample_report_body(task_name: str, meta_rows: list[tuple[str, object]], report: JsonDict) -> str:
    executive = _dict(report.get("executive_summary"))
    profile = _dict(report.get("sample_profile"))
    hashes = _dict(profile.get("hashes"))
    capabilities = report.get("capabilities") if isinstance(report.get("capabilities"), list) else []
    behavior = _dict(report.get("behavior_summary"))
    iocs = report.get("iocs") if isinstance(report.get("iocs"), list) else []
    integrated = _dict(report.get("integrated_analysis"))
    llm_judgement = _dict(report.get("llm_judgement"))
    llm_analysis = _str(report.get("llm_analysis"))
    threat_intelligence = _dict(report.get("threat_intelligence"))
    threat_summary = _dict(threat_intelligence.get("summary"))
    threat_response = _dict(threat_intelligence.get("response"))
    threat_data = _dict(threat_response.get("data"))
    data_summary = _dict(threat_data.get("summary"))
    multiengines = _dict(threat_data.get("multiengines"))
    engine_result = _dict(multiengines.get("result"))
    safe_values = {"", "safe", "clean", "undetected", "none", "ok"}
    engine_hits = integrated.get("engine_hits") if isinstance(integrated.get("engine_hits"), list) else []
    if not engine_hits:
        engine_hits = threat_summary.get("engine_hits") if isinstance(threat_summary.get("engine_hits"), list) else []
    if not engine_hits and engine_result:
        engine_hits = [
            {"engine": engine, "verdict": verdict}
            for engine, verdict in engine_result.items()
            if str(verdict or "").strip().lower() not in safe_values
        ]
    static_findings = _list_of_str(integrated.get("static_findings") or threat_summary.get("static_findings"))
    network_activity = _list_of_str(integrated.get("network_activity") or threat_summary.get("network_activity"))
    deduplicated_iocs = (
        integrated.get("deduplicated_iocs")
        if isinstance(integrated.get("deduplicated_iocs"), list)
        else []
    )
    threat_tags = threat_summary.get("tags") or threat_summary.get("tag") or data_summary.get("tags") or data_summary.get("tag") or []
    threat_tags = _list_of_str(threat_tags)
    intel = _dict(llm_judgement.get("threat_intel_interpretation"))
    key_evidence = llm_judgement.get("key_evidence") if isinstance(llm_judgement.get("key_evidence"), list) else []
    behavior_judgement = (
        llm_judgement.get("behavior_judgement")
        if isinstance(llm_judgement.get("behavior_judgement"), list)
        else []
    )
    judgement_iocs = llm_judgement.get("iocs") if isinstance(llm_judgement.get("iocs"), list) else []
    recommendations = _list_of_str(
        llm_judgement.get("detection_recommendations") or report.get("detection_recommendations")
    )
    response_actions = _list_of_str(llm_judgement.get("response_actions") or report.get("next_steps"))
    conflicts = _list_of_str(llm_judgement.get("conflicts"))
    limitations = _list_of_str(llm_judgement.get("limitations") or report.get("limitations"))
    threat_score = integrated.get("threat_score") or threat_summary.get("threat_score") or data_summary.get("threat_score")
    detect_rate = (
        integrated.get("detect_rate")
        or threat_summary.get("detect_rate")
        or threat_summary.get("multi_engines")
        or multiengines.get("detect_rate")
    )
    family = (
        llm_judgement.get("family")
        or integrated.get("family")
        or threat_summary.get("malware_family")
        or data_summary.get("malware_family")
        or executive.get("family")
        or "未识别"
    )
    verdict = (
        llm_judgement.get("final_verdict")
        or integrated.get("verdict")
        or executive.get("verdict")
        or threat_summary.get("threat_level")
        or "未提供"
    )
    severity = (
        llm_judgement.get("severity")
        or integrated.get("severity")
        or executive.get("severity")
        or threat_summary.get("threat_level")
        or "unknown"
    )
    engine_hit_text = [
        f"{item.get('engine')}: {item.get('verdict')}"
        for item in engine_hits
        if isinstance(item, dict)
    ]
    signature_names = []
    if isinstance(threat_data.get("signature"), list):
        signature_names = [
            str(item.get("name") or item.get("sig_name") or "").strip()
            for item in threat_data.get("signature")
            if isinstance(item, dict) and str(item.get("name") or item.get("sig_name") or "").strip()
        ]
    capability_cards = "".join(
        (
            '<article class="finding-card">'
            f'<div class="finding-head"><span class="badge {_severity_class(item.get("confidence"))}">{_escape(item.get("confidence") or "unknown")}</span>'
            f'<strong>{_escape(item.get("name") or f"能力 {index + 1}")}</strong></div>'
            f'<section><h4>证据</h4>{_render_list(_list_of_str(item.get("evidence")), "无证据条目")}</section>'
            f'<section><h4>MITRE</h4>{_render_list(_list_of_str(item.get("mitre_techniques")), "未映射到 MITRE")}</section>'
            "</article>"
        )
        for index, item in enumerate(capabilities)
        if isinstance(item, dict)
    )
    behavior_sections = "".join(
        f"<section><h4>{_escape(label)}</h4>{_render_list(_list_of_str(behavior.get(key)), '无')}</section>"
        for key, label in (
            ("persistence", "持久化"),
            ("network", "网络"),
            ("filesystem", "文件系统"),
            ("process", "进程"),
            ("registry", "注册表"),
            ("defense_evasion", "规避"),
        )
    )
    evidence_cards = "".join(
        (
            '<article class="evidence-card">'
            f'<span>{_escape(item.get("source") or "evidence")}</span>'
            f'<strong>{_escape(item.get("title") or f"证据 {index + 1}")}</strong>'
            f'<p>{_escape(item.get("detail") or "未提供详情")}</p>'
            f'<small>{_escape(item.get("weight") or "unknown")}</small>'
            "</article>"
        )
        for index, item in enumerate(key_evidence)
        if isinstance(item, dict)
    )
    behavior_judgement_cards = "".join(
        (
            '<article class="finding-card">'
            f'<strong>{_escape(item.get("category") or "其他")}</strong>'
            f'<p>{_escape(item.get("assessment") or "未提供研判")}</p>'
            f'{_render_list(_list_of_str(item.get("evidence")), "暂无证据")}'
            "</article>"
        )
        for item in behavior_judgement
        if isinstance(item, dict)
    )
    raw_threat = (
        json.dumps(threat_response, ensure_ascii=False, indent=2, default=str)
        if threat_response
        else ""
    )
    return f"""
    <section class="hero">
      <div>
        <p class="eyebrow">Structured Malware Report</p>
        <h1>{_escape(task_name)}</h1>
        <p class="summary">{_escape(executive.get('summary') or llm_judgement.get('summary') or integrated.get('llm_summary'))}</p>
      </div>
      <div class="hero-card">
        {_render_kv_rows([('综合结论', verdict), ('威胁等级', severity), ('威胁分 / 检出率', f'{threat_score or "未提供"} / {detect_rate or "未提供"}'), ('家族 / 置信度', f'{family} / {llm_judgement.get("confidence") or executive.get("confidence") or "unknown"}')])}
      </div>
    </section>
    <section class="meta-grid">{_render_kv_rows(meta_rows)}</section>
    <section class="panel outcome-panel">
      <p class="eyebrow">完成态输出</p>
      <h2>样本分析综合研判</h2>
      <p>{_escape(integrated.get('fusion_note') or '已将 LLM 行为分析、结构化样本画像和威胁情报平台返回结果合并为单一结论视图。')}</p>
    </section>
    <section class="two-col">
      <section class="panel">
        <h2>LLM 固定研判</h2>
        {_render_kv_rows([('恶意性', llm_judgement.get('malicious_assessment') or ('恶意' if _bool(executive.get('is_malicious')) else '需复核')), ('严重性', severity), ('置信度', llm_judgement.get('confidence') or executive.get('confidence')), ('家族', family)])}
        <h3>最终结论</h3>
        <p>{_escape(llm_judgement.get('final_verdict') or verdict)}</p>
        <h3>摘要</h3>
        <p>{_escape(llm_judgement.get('summary') or llm_analysis or executive.get('summary'))}</p>
        <h3>关键证据</h3>
        <div class="evidence-list">{evidence_cards or '<p class="empty">暂无关键证据。</p>'}</div>
        <h3>威胁情报解读</h3>
        {_render_kv_rows([('威胁等级', intel.get('threat_level') or threat_summary.get('threat_level')), ('威胁分', intel.get('threat_score') or threat_score), ('检出率', intel.get('detect_rate') or detect_rate), ('类型', intel.get('malware_type') or threat_summary.get('malware_type')), ('家族', intel.get('malware_family') or family), ('解读', intel.get('meaning'))])}
      </section>
      <section class="panel">
        <h2>证据汇总</h2>
        <h3>外部引擎命中</h3>{_render_list(engine_hit_text, '暂无多引擎命中')}
        <h3>静态与网络信号</h3>{_render_list([*static_findings[:5], *network_activity[:5]], '暂无静态或网络信号')}
        <h3>情报标签</h3>{_render_list([*threat_tags, *signature_names], '暂无标签')}
        {_render_kv_rows([('引擎命中', len(engine_hits)), ('能力项', integrated.get('capability_count') or len(capabilities)), ('去重 IOC', integrated.get('ioc_count') or len(deduplicated_iocs))])}
      </section>
    </section>
    <section class="panel">
      <h2>行为与能力研判</h2>
      {behavior_judgement_cards or '<p class="empty">暂无行为研判。</p>'}
    </section>
    <section class="panel">
      <h2>ThreatBook 固定 JSON 解析</h2>
      {_render_kv_rows([('响应码', threat_response.get('response_code') or threat_summary.get('response_code')), ('消息', threat_response.get('verbose_msg') or threat_response.get('msg') or threat_summary.get('verbose_msg')), ('样本 SHA256', data_summary.get('sample_sha256') or threat_data.get('sample_sha256')), ('提交时间', data_summary.get('submit_time') or threat_data.get('submit_time')), ('最后检出', data_summary.get('last_detection_time') or threat_data.get('last_detection_time')), ('沙箱类型', data_summary.get('sandbox_type') or threat_data.get('sandbox_type')), ('恶意类型', data_summary.get('malware_type') or threat_summary.get('malware_type')), ('恶意家族', data_summary.get('malware_family') or threat_summary.get('malware_family'))])}
      <h3>原始威胁情报 JSON</h3>
      {f'<pre class="detail-pre">{_escape(raw_threat)}</pre>' if raw_threat else '<p class="empty">当前任务没有威胁情报平台原始结果。</p>'}
    </section>
    <section class="panel"><h2>样本画像</h2>{_render_kv_rows([('文件名', profile.get('file_name')), ('文件类型', profile.get('file_type')), ('架构', profile.get('architecture')), ('平台', profile.get('platform')), ('大小', profile.get('size_bytes')), ('MD5', hashes.get('md5')), ('SHA256', hashes.get('sha256'))])}</section>
    <section class="panel"><h2>能力画像</h2>{capability_cards or '<p class="empty">当前没有结构化能力项。</p>'}</section>
    <section class="panel"><h2>行为摘要</h2><div class="behavior-grid">{behavior_sections}</div></section>
    <section class="two-col">
      <section class="panel"><h2>IOC</h2><table><thead><tr><th>类型</th><th>值</th><th>上下文</th><th>严重性</th></tr></thead><tbody>{_render_ioc_table(iocs)}</tbody></table></section>
      <section class="panel"><h2>去重 IOC</h2><table><thead><tr><th>类型</th><th>值</th><th>上下文</th><th>严重性</th></tr></thead><tbody>{_render_ioc_table(deduplicated_iocs)}</tbody></table></section>
    </section>
    <section class="panel"><h2>LLM 研判 IOC</h2><table><thead><tr><th>类型</th><th>值</th><th>上下文</th><th>严重性</th></tr></thead><tbody>{_render_object_list(judgement_iocs, ['type', 'value', 'context', 'severity'], 4)}</tbody></table></section>
    <section class="two-col">
      <section class="panel"><h2>检测建议</h2>{_render_list(recommendations, '暂无检测建议')}</section>
      <section class="panel"><h2>处置建议</h2>{_render_list(response_actions, '暂无处置建议')}</section>
    </section>
    <section class="two-col">
      <section class="panel"><h2>冲突说明</h2>{_render_list(conflicts, '暂无冲突说明')}</section>
      <section class="panel"><h2>限制说明</h2>{_render_list(limitations, '暂无限制说明')}</section>
    </section>
    """


def _render_structured_report_page(task_name: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(task_name)} \u62a5\u544a</title>
  <style>
    :root {{
      --bg: #f3f7fb;
      --panel: #ffffff;
      --line: #d7e3ef;
      --ink: #132238;
      --muted: #5b6b7f;
      --accent: #0f766e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background: linear-gradient(180deg, #f8fbfe 0%, var(--bg) 100%);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{ display: grid; grid-template-columns: minmax(0, 1.6fr) minmax(280px, 1fr); gap: 20px; margin-bottom: 20px; }}
    .hero > div:first-child {{ padding: 28px; border-radius: 18px; background: #132238; color: #f8fbff; }}
    .hero-card, .panel, .meta-grid {{ background: var(--panel); border: 1px solid var(--line); border-radius: 12px; box-shadow: 0 10px 30px rgba(15, 23, 42, 0.06); }}
    .hero-card {{ padding: 20px; display: grid; gap: 10px; }}
    .eyebrow {{ margin: 0 0 10px; text-transform: uppercase; letter-spacing: .08em; font-size: 12px; color: var(--muted); }}
    .hero .eyebrow {{ color: rgba(248,251,255,.75); }}
    h1 {{ margin: 0 0 12px; font-size: 32px; }}
    h2 {{ margin: 0 0 16px; font-size: 21px; }}
    h3 {{ margin: 18px 0 10px; font-size: 16px; }}
    h4 {{ margin: 0 0 10px; font-size: 14px; color: var(--muted); }}
    p {{ margin: 0; line-height: 1.72; }}
    .summary {{ color: rgba(248,251,255,.9); }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; padding: 18px 20px; margin-bottom: 20px; }}
    .meta-item {{ display: grid; gap: 6px; padding: 12px 14px; border-radius: 10px; background: #f8fafc; border: 1px solid #e5edf4; }}
    .meta-item span {{ color: var(--muted); font-size: 12px; }}
    .meta-item strong {{ word-break: break-word; }}
    .panel {{ padding: 22px; margin-bottom: 20px; }}
    .two-col {{ display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 20px; }}
    .behavior-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; }}
    .finding-card, .evidence-card {{ border: 1px solid var(--line); border-radius: 12px; padding: 16px; background: #f8fafc; margin-bottom: 14px; }}
    .finding-head {{ display: flex; gap: 12px; align-items: center; flex-wrap: wrap; margin-bottom: 12px; }}
    .badge {{ display: inline-flex; align-items: center; justify-content: center; min-width: 72px; padding: 6px 10px; border-radius: 999px; font-size: 12px; font-weight: 700; color: #fff; }}
    .sev-high {{ background: #b91c1c; }}
    .sev-medium {{ background: #b45309; }}
    .sev-low {{ background: #166534; }}
    .sev-unknown {{ background: #475569; }}
    .detail-pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; padding: 14px; border-radius: 8px; background: #f8fafc; border: 1px solid var(--line); line-height: 1.65; font-size: 13px; }}
    ul {{ margin: 0; padding-left: 20px; line-height: 1.7; }}
    li + li {{ margin-top: 6px; }}
    .empty {{ color: var(--muted); }}
    table {{ width: 100%; border-collapse: collapse; border: 1px solid var(--line); border-radius: 10px; overflow: hidden; }}
    th, td {{ padding: 12px 14px; border-bottom: 1px solid var(--line); text-align: left; vertical-align: top; word-break: break-word; }}
    th {{ background: #eef4fa; color: var(--muted); }}
    @media (max-width: 900px) {{ .hero, .two-col {{ grid-template-columns: 1fr; }} }}
  </style>
</head>
<body>
  <div class="wrap">{body}</div>
</body>
</html>"""


def render_structured_report_html(
    *,
    task_type: str,
    task_name: str,
    task_id: str,
    generated_at: str,
    file_info: JsonDict | None,
    report: JsonDict,
) -> str:
    file_info = _dict(file_info)
    executive = _dict(report.get("executive_summary"))
    if task_type == "sample-analysis":
        meta_rows = [
            ("\u4efb\u52a1\u7c7b\u578b", task_name),
            ("\u4efb\u52a1 ID", task_id),
            ("\u76ee\u6807\u6587\u4ef6", file_info.get("filename") or file_info.get("path") or ""),
            ("\u751f\u6210\u65f6\u95f4", generated_at),
        ]
        body = _render_sample_report_body(task_name, meta_rows, report)
        return _render_structured_report_page(task_name, body)
    meta_rows = [
        ("任务类型", task_name),
        ("任务 ID", task_id),
        ("目标文件", file_info.get("filename") or file_info.get("path") or ""),
        ("生成时间", generated_at),
    ]
    if task_type == "vulnerability-mining":
        findings = report.get("findings") if isinstance(report.get("findings"), list) else []
        iocs = report.get("iocs") if isinstance(report.get("iocs"), list) else []
        finding_cards = "".join(
            (
                "<article class=\"finding-card\">"
                f"<div class=\"finding-head\"><span class=\"badge {_severity_class(item.get('severity'))}\">{_escape(item.get('severity'))}</span>"
                f"<strong>{_escape(item.get('id'))} { _escape(item.get('title')) }</strong></div>"
                f"<div class=\"finding-grid\">{_render_kv_rows([('状态', item.get('status')), ('分类', item.get('category')), ('位置', item.get('location')), ('置信度', item.get('confidence'))])}</div>"
                f"<section><h4>影响</h4><p>{_escape(item.get('impact'))}</p></section>"
                f"<section><h4>可利用性</h4><p>{_escape(item.get('exploitability'))}</p></section>"
                f"<section><h4>证据</h4>{_render_list(_list_of_str(item.get('evidence')))}</section>"
                f"<section><h4>复现步骤</h4>{_render_list(_list_of_str(item.get('reproduction_steps')))}</section>"
                f"<section><h4>修复建议</h4>{_render_list(_list_of_str(item.get('remediation')))}</section>"
                "</article>"
            )
            for item in findings
        )
        ioc_rows = "".join(
            f"<tr><td>{_escape(item.get('type'))}</td><td>{_escape(item.get('value'))}</td><td>{_escape(item.get('context'))}</td></tr>"
            for item in iocs
        )
        body = f"""
        <section class="hero">
          <div>
            <p class="eyebrow">Structured Security Report</p>
            <h1>{_escape(task_name)}</h1>
            <p class="summary">{_escape(executive.get('summary'))}</p>
          </div>
          <div class="hero-card">
            {_render_kv_rows([('总体风险', executive.get('overall_risk')), ('结论', executive.get('verdict')), ('置信度', executive.get('confidence')), ('目标', executive.get('affected_target'))])}
          </div>
        </section>
        <section class="meta-grid">{_render_kv_rows(meta_rows)}</section>
        <section class="panel"><h2>攻击面</h2>{_render_list(_list_of_str(report.get('attack_surface')))}</section>
        <section class="panel"><h2>核心发现</h2>{finding_cards or '<p class="empty">未识别到结构化漏洞发现。</p>'}</section>
        <section class="panel"><h2>IOC</h2><table><thead><tr><th>类型</th><th>值</th><th>上下文</th></tr></thead><tbody>{ioc_rows or '<tr><td colspan="3">无</td></tr>'}</tbody></table></section>
        <section class="two-col">
          <section class="panel"><h2>后续建议</h2>{_render_list(_list_of_str(report.get('next_steps')))}</section>
          <section class="panel"><h2>限制说明</h2>{_render_list(_list_of_str(report.get('limitations')))}</section>
        </section>
        """
    else:
        profile = _dict(report.get("sample_profile"))
        hashes = _dict(profile.get("hashes"))
        capabilities = report.get("capabilities") if isinstance(report.get("capabilities"), list) else []
        behavior = _dict(report.get("behavior_summary"))
        iocs = report.get("iocs") if isinstance(report.get("iocs"), list) else []
        capability_cards = "".join(
            (
                "<article class=\"finding-card\">"
                f"<div class=\"finding-head\"><span class=\"badge {_severity_class(item.get('confidence'))}\">{_escape(item.get('confidence'))}</span>"
                f"<strong>{_escape(item.get('name'))}</strong></div>"
                f"<section><h4>证据</h4>{_render_list(_list_of_str(item.get('evidence')))}</section>"
                f"<section><h4>MITRE</h4>{_render_list(_list_of_str(item.get('mitre_techniques')))}</section>"
                "</article>"
            )
            for item in capabilities
        )
        behavior_sections = "".join(
            f"<section><h4>{_escape(label)}</h4>{_render_list(_list_of_str(behavior.get(key)))}</section>"
            for key, label in (
                ("persistence", "持久化"),
                ("network", "网络"),
                ("filesystem", "文件系统"),
                ("process", "进程"),
                ("registry", "注册表"),
                ("defense_evasion", "规避"),
            )
        )
        ioc_rows = "".join(
            f"<tr><td>{_escape(item.get('type'))}</td><td>{_escape(item.get('value'))}</td><td>{_escape(item.get('context'))}</td><td>{_escape(item.get('severity'))}</td></tr>"
            for item in iocs
        )
        threat_intelligence = _dict(report.get("threat_intelligence"))
        threat_summary = _dict(threat_intelligence.get("summary"))
        threat_response = _dict(threat_intelligence.get("response"))
        threat_rows = [
            ("启用状态", threat_intelligence.get("enabled")),
            ("查询状态", threat_intelligence.get("status")),
            ("平台", threat_intelligence.get("platform_name")),
            ("查询资源", threat_intelligence.get("resource")),
            ("响应码", threat_summary.get("response_code") or threat_response.get("response_code")),
            ("威胁等级", threat_summary.get("threat_level")),
            ("威胁分", threat_summary.get("threat_score")),
            ("多引擎检出", threat_summary.get("detect_rate") or threat_summary.get("multi_engines")),
            ("恶意类型", threat_summary.get("malware_type")),
            ("恶意家族", threat_summary.get("malware_family")),
            ("消息", threat_summary.get("verbose_msg") or threat_intelligence.get("error")),
        ]
        threat_section = (
            f"<section class=\"panel\"><h2>威胁情报摘要</h2>{_render_kv_rows(threat_rows)}</section>"
            if threat_intelligence and threat_intelligence.get("enabled")
            else ""
        )
        integrated = _dict(report.get("integrated_analysis"))
        deduplicated_iocs = [
            dict(item)
            for item in integrated.get("deduplicated_iocs", [])
            if isinstance(item, dict)
        ]
        engine_hits = [
            f"{item.get('engine')}: {item.get('verdict')}"
            for item in integrated.get("engine_hits", [])
            if isinstance(item, dict)
        ]
        if not engine_hits:
            engine_hits = [
                f"{item.get('engine')}: {item.get('verdict')}"
                for item in threat_summary.get("engine_hits", [])
                if isinstance(item, dict)
            ]
        static_findings = _list_of_str(
            integrated.get("static_findings") or threat_summary.get("static_findings")
        )
        network_activity = _list_of_str(
            integrated.get("network_activity") or threat_summary.get("network_activity")
        )
        dedup_ioc_rows = _render_ioc_table(deduplicated_iocs)
        integrated_section = (
            "<section class=\"panel\"><h2>融合分析</h2>"
            + _render_kv_rows(
                [
                    ("综合结论", integrated.get("verdict")),
                    ("综合严重性", integrated.get("severity")),
                    ("家族/标签", integrated.get("family")),
                    ("威胁分", integrated.get("threat_score") or threat_summary.get("threat_score")),
                    ("多引擎检出", integrated.get("detect_rate") or threat_summary.get("detect_rate") or threat_summary.get("multi_engines")),
                    ("能力项数量", integrated.get("capability_count")),
                    ("去重 IOC 数量", integrated.get("ioc_count")),
                    ("融合说明", integrated.get("fusion_note")),
                ]
            )
            + "<div class=\"three-col\">"
            + f"<section><h3>引擎命中</h3>{_render_list(engine_hits)}</section>"
            + f"<section><h3>静态可疑信号</h3>{_render_list(static_findings)}</section>"
            + f"<section><h3>网络活动</h3>{_render_list(network_activity)}</section>"
            + "</div>"
            + "<h3>威胁情报信号</h3>"
            + _render_list(_list_of_str(integrated.get("threat_signals")))
            + "<h3>去重 IOC</h3>"
            + f"<table><thead><tr><th>类型</th><th>值</th><th>上下文</th><th>严重性</th></tr></thead><tbody>{dedup_ioc_rows}</tbody></table>"
            + "</section>"
            if integrated
            else ""
        )
        llm_analysis = _str(report.get("llm_analysis"))
        llm_section = (
            f"<section class=\"panel\"><h2>LLM 详细分析</h2><pre class=\"detail-pre\">{_escape(llm_analysis)}</pre></section>"
            if llm_analysis
            else ""
        )
        threat_raw = (
            json.dumps(threat_response, ensure_ascii=False, indent=2, default=str)
            if threat_response
            else ""
        )
        threat_raw_section = (
            f"<section class=\"panel\"><h2>威胁情报原始结果</h2><pre class=\"detail-pre\">{_escape(threat_raw)}</pre></section>"
            if threat_raw
            else ""
        )
        body = f"""
        <section class="hero">
          <div>
            <p class="eyebrow">Structured Malware Report</p>
            <h1>{_escape(task_name)}</h1>
            <p class="summary">{_escape(executive.get('summary'))}</p>
          </div>
          <div class="hero-card">
            {_render_kv_rows([('结论', executive.get('verdict')), ('恶意性', '是' if _bool(executive.get('is_malicious')) else '否/未证实'), ('严重性', executive.get('severity')), ('家族', executive.get('family')), ('置信度', executive.get('confidence'))])}
          </div>
        </section>
        <section class="meta-grid">{_render_kv_rows(meta_rows)}</section>
        <section class="panel"><h2>样本画像</h2>{_render_kv_rows([('文件名', profile.get('file_name')), ('文件类型', profile.get('file_type')), ('架构', profile.get('architecture')), ('平台', profile.get('platform')), ('大小', profile.get('size_bytes')), ('MD5', hashes.get('md5')), ('SHA256', hashes.get('sha256'))])}</section>
        <section class="panel"><h2>能力画像</h2>{capability_cards or '<p class="empty">未提取到结构化能力项。</p>'}</section>
        <section class="panel"><h2>行为总结</h2><div class="behavior-grid">{behavior_sections}</div></section>
        <section class="panel"><h2>IOC</h2><table><thead><tr><th>类型</th><th>值</th><th>上下文</th><th>严重性</th></tr></thead><tbody>{ioc_rows or '<tr><td colspan="4">无</td></tr>'}</tbody></table></section>
        {integrated_section}
        {threat_section}
        {llm_section}
        {threat_raw_section}
        <section class="two-col">
          <section class="panel"><h2>检测建议</h2>{_render_list(_list_of_str(report.get('detection_recommendations')))}</section>
          <section class="panel"><h2>限制说明</h2>{_render_list(_list_of_str(report.get('limitations')))}</section>
        </section>
        <section class="panel"><h2>后续动作</h2>{_render_list(_list_of_str(report.get('next_steps')))}</section>
        """
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{_escape(task_name)} 报告</title>
  <style>
    :root {{
      --bg: #f3f7fb;
      --panel: rgba(255,255,255,0.92);
      --line: #d7e3ef;
      --ink: #132238;
      --muted: #5b6b7f;
      --accent: #0f766e;
      --accent-2: #1d4ed8;
      --critical: #b91c1c;
      --medium: #b45309;
      --low: #166534;
      --unknown: #475569;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", "Microsoft YaHei", sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(29,78,216,0.10), transparent 32%),
        radial-gradient(circle at top right, rgba(15,118,110,0.12), transparent 28%),
        linear-gradient(180deg, #f8fbfe 0%, var(--bg) 100%);
    }}
    .wrap {{ max-width: 1180px; margin: 0 auto; padding: 32px 20px 48px; }}
    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.8fr) minmax(280px, 1fr);
      gap: 20px;
      margin-bottom: 20px;
      align-items: stretch;
    }}
    .hero-card, .panel, .meta-grid {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 20px;
      backdrop-filter: blur(12px);
      box-shadow: 0 14px 40px rgba(15, 23, 42, 0.08);
    }}
    .hero > div:first-child {{
      padding: 28px;
      border-radius: 24px;
      background: linear-gradient(135deg, #0f172a 0%, #13335f 58%, #0f766e 100%);
      color: #f8fbff;
      box-shadow: 0 20px 46px rgba(15, 23, 42, 0.18);
    }}
    .eyebrow {{
      margin: 0 0 12px;
      text-transform: uppercase;
      letter-spacing: .12em;
      font-size: 12px;
      opacity: .78;
    }}
    h1 {{ margin: 0 0 12px; font-size: 34px; line-height: 1.15; }}
    h2 {{ margin: 0 0 16px; font-size: 22px; }}
    h4 {{ margin: 0 0 10px; font-size: 14px; color: var(--muted); }}
    .summary {{ margin: 0; line-height: 1.75; font-size: 15px; color: rgba(248,251,255,0.92); }}
    .detail-pre {{ white-space: pre-wrap; word-break: break-word; margin: 0; padding: 14px; border-radius: 8px; background: #f8fafc; border: 1px solid var(--line); color: var(--ink); line-height: 1.65; font-size: 13px; }}
    .hero-card {{ padding: 22px; display: grid; gap: 10px; }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      padding: 18px 20px;
      margin-bottom: 20px;
    }}
    .meta-item {{
      display: grid;
      gap: 6px;
      align-content: start;
      padding: 12px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
      border: 1px solid rgba(215,227,239,0.9);
    }}
    .meta-item span {{ color: var(--muted); font-size: 12px; }}
    .meta-item strong {{ word-break: break-word; }}
    .panel {{ padding: 22px; margin-bottom: 20px; }}
    .two-col {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 20px;
    }}
    .three-col {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 14px;
      margin: 18px 0;
    }}
    .three-col section {{
      padding: 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: #f8fafc;
    }}
    .three-col h3 {{
      margin: 0 0 10px;
      font-size: 15px;
      color: var(--ink);
    }}
    .behavior-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
    }}
    .finding-card {{
      border: 1px solid var(--line);
      border-radius: 18px;
      padding: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.96) 0%, rgba(245,249,253,0.94) 100%);
      margin-bottom: 16px;
    }}
    .finding-head {{
      display: flex;
      gap: 12px;
      align-items: center;
      flex-wrap: wrap;
      margin-bottom: 14px;
    }}
    .finding-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      margin-bottom: 14px;
    }}
    .badge {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 72px;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      color: #fff;
    }}
    .sev-high {{ background: linear-gradient(135deg, #dc2626, #b91c1c); }}
    .sev-medium {{ background: linear-gradient(135deg, #f59e0b, #b45309); }}
    .sev-low {{ background: linear-gradient(135deg, #16a34a, #166534); }}
    .sev-unknown {{ background: linear-gradient(135deg, #64748b, #475569); }}
    ul {{ margin: 0; padding-left: 20px; line-height: 1.7; }}
    li + li {{ margin-top: 6px; }}
    p {{ margin: 0; line-height: 1.7; }}
    .empty {{ color: var(--muted); }}
    table {{
      width: 100%;
      border-collapse: collapse;
      overflow: hidden;
      border-radius: 16px;
      border: 1px solid var(--line);
    }}
    th, td {{
      padding: 12px 14px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      word-break: break-word;
    }}
    th {{
      background: #eef4fa;
      font-size: 13px;
      color: var(--muted);
    }}
    tr:nth-child(even) td {{ background: rgba(248,251,255,0.7); }}
    @media (max-width: 900px) {{
      .hero, .two-col, .three-col {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <div class="wrap">{body}</div>
</body>
</html>"""
