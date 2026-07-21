import json
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from backend.config import is_threat_intelligence_capability_type
from backend.data_structures import JsonDict


DEFAULT_THREATBOOK_FILE_REPORT_URL = "https://api.threatbook.cn/v3/file/report"


class ThreatIntelligenceError(RuntimeError):
    pass


def configured_threat_platforms(
    status_modules: dict[str, JsonDict],
) -> list[JsonDict]:
    return [
        module
        for module in status_modules.values()
        if is_threat_intelligence_capability_type(
            str(module.get("capability_type") or "")
        )
        and str(module.get("status") or "").lower() == "online"
        and str(module.get("api_key") or module.get("token") or "").strip()
    ]


def first_online_threat_platform(
    status_modules: dict[str, JsonDict],
) -> JsonDict | None:
    platforms = configured_threat_platforms(status_modules)
    return platforms[0] if platforms else None


def threatbook_endpoint(platform: JsonDict) -> str:
    return str(platform.get("url") or DEFAULT_THREATBOOK_FILE_REPORT_URL).strip()


def threatbook_api_key(platform: JsonDict) -> str:
    return str(platform.get("api_key") or platform.get("token") or "").strip()


def request_json(url: str, params: dict[str, object], timeout: float = 20) -> JsonDict:
    separator = "&" if "?" in url else "?"
    request_url = f"{url}{separator}{urlencode(params)}"
    request = Request(request_url, headers={"Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = getattr(response, "status", 200)
    except HTTPError as exc:
        raw = exc.read()
        status = exc.code
    except (URLError, TimeoutError) as exc:
        raise ThreatIntelligenceError(str(getattr(exc, "reason", exc))) from exc
    try:
        parsed = json.loads(raw.decode("utf-8", errors="replace") or "{}")
    except json.JSONDecodeError as exc:
        raise ThreatIntelligenceError("Threat intelligence response is not JSON") from exc
    if not isinstance(parsed, dict):
        raise ThreatIntelligenceError("Threat intelligence response is not an object")
    parsed.setdefault("_http_status", status)
    return parsed


def test_threatbook_platform(platform: JsonDict) -> JsonDict:
    api_key = threatbook_api_key(platform)
    if not api_key:
        return {"ok": False, "error": "api_key is required"}
    url = threatbook_endpoint(platform)
    try:
        response = request_json(
            url,
            {"apikey": api_key, "resource": "0" * 64},
            timeout=12,
        )
    except ThreatIntelligenceError as exc:
        return {"ok": False, "error": str(exc)}
    response_code = response.get("response_code")
    # ThreatBook returns structured error codes for invalid resources; reaching
    # that JSON API still proves the endpoint and key path are accessible.
    return {
        "ok": True,
        "endpoint": url,
        "response_code": response_code,
        "http_status": response.get("_http_status"),
        "message": response.get("verbose_msg") or response.get("msg") or "",
    }


def fetch_file_report(platform: JsonDict, file_info: JsonDict) -> JsonDict:
    resource = str(
        file_info.get("sha256")
        or file_info.get("sha1")
        or file_info.get("md5")
        or ""
    ).strip()
    if not resource:
        return {"enabled": False, "error": "file hash is missing"}
    api_key = threatbook_api_key(platform)
    if not api_key:
        return {"enabled": False, "error": "api_key is missing"}
    url = threatbook_endpoint(platform)
    try:
        response = request_json(
            url,
            {
                "apikey": api_key,
                "resource": resource,
            },
            timeout=30,
        )
    except ThreatIntelligenceError as exc:
        return {"enabled": True, "status": "failed", "error": str(exc)}
    return {
        "enabled": True,
        "status": "success",
        "platform_id": str(platform.get("id") or ""),
        "platform_name": str(platform.get("name") or ""),
        "endpoint": url,
        "resource": resource,
        "response": response,
        "summary": summarize_threatbook_report(response),
    }


def summarize_threatbook_report(report: JsonDict) -> JsonDict:
    data = report.get("data") if isinstance(report.get("data"), dict) else {}
    file_summary = data.get("summary") if isinstance(data.get("summary"), dict) else {}
    multiengines = (
        data.get("multiengines") if isinstance(data.get("multiengines"), dict) else {}
    )
    static_details = (
        data.get("static", {}).get("details")
        if isinstance(data.get("static"), dict)
        and isinstance(data.get("static", {}).get("details"), dict)
        else {}
    )
    summary: dict[str, Any] = {
        "response_code": report.get("response_code"),
        "verbose_msg": report.get("verbose_msg") or report.get("msg") or "",
    }
    for key in (
        "sha1",
        "md5",
        "sample_sha256",
        "file_name",
        "file_type",
        "file_size",
        "malware_type",
        "malware_family",
        "threat_level",
        "threat_score",
        "severity",
        "sandbox_type",
        "sandbox_type_list",
        "multi_engines",
        "signature",
        "tag",
        "tags",
        "submit_time",
        "last_detection_time",
    ):
        if key in file_summary:
            summary[key] = file_summary.get(key)
        elif key in data:
            summary[key] = data.get(key)
    tags = flatten_threatbook_tags(summary.get("tags") or summary.get("tag"))
    if tags:
        summary["tags"] = tags
    detect_rate = multiengines.get("detect_rate") or summary.get("multi_engines")
    if detect_rate:
        summary["detect_rate"] = detect_rate
    engine_hits = extract_engine_hits(multiengines.get("result"))
    if engine_hits:
        summary["engine_hits"] = engine_hits
    signature_names = extract_signature_names(data.get("signature"))
    if signature_names:
        summary["signature_names"] = signature_names
    static_findings = extract_static_findings(static_details)
    if static_findings:
        summary["static_findings"] = static_findings
    network_activity = extract_network_activity(data.get("network"))
    if network_activity:
        summary["network_activity"] = network_activity
    return summary


def flatten_threatbook_tags(raw_tags: Any) -> list[str]:
    tags: list[str] = []

    def append(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text and text not in tags:
                tags.append(text)
        elif isinstance(value, list):
            for item in value:
                append(item)
        elif isinstance(value, dict):
            for item in value.values():
                append(item)

    append(raw_tags)
    return tags


def extract_engine_hits(results: Any) -> list[JsonDict]:
    if not isinstance(results, dict):
        return []
    safe_values = {"safe", "clean", "undetected", "none", "ok", ""}
    hits: list[JsonDict] = []
    for engine, verdict in results.items():
        verdict_text = str(verdict or "").strip()
        if verdict_text.lower() in safe_values:
            continue
        hits.append({"engine": str(engine), "verdict": verdict_text})
    return hits[:12]


def extract_signature_names(signature: Any) -> list[str]:
    if not isinstance(signature, list):
        return []
    names: list[str] = []
    for item in signature:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or item.get("sig_name") or "").strip()
        if name and name not in names:
            names.append(name)
    return names[:12]


def extract_static_findings(details: Any) -> list[str]:
    if not isinstance(details, dict):
        return []
    findings: list[str] = []
    for section in details.get("pe_sections") or []:
        if not isinstance(section, dict):
            continue
        name = str(section.get("name") or "").strip() or "unknown"
        characteristics = str(section.get("characteristics") or "").upper()
        if "RWE" in characteristics or (
            "W" in characteristics and "X" in characteristics
        ):
            findings.append(f"PE section {name} has writable and executable permissions")
    suspicious_imports = {
        "IsDebuggerPresent": "Anti-debug import IsDebuggerPresent",
        "CheckRemoteDebuggerPresent": "Anti-debug import CheckRemoteDebuggerPresent",
        "SetUnhandledExceptionFilter": "Exception-filter based anti-analysis signal",
        "VirtualAlloc": "Memory allocation API VirtualAlloc imported",
        "VirtualProtect": "Memory permission API VirtualProtect imported",
        "WriteProcessMemory": "Process injection API WriteProcessMemory imported",
        "CreateRemoteThread": "Remote thread API CreateRemoteThread imported",
    }
    imports = details.get("pe_imports") or details.get("imports") or []
    import_text = json.dumps(imports, ensure_ascii=False)
    for api_name, description in suspicious_imports.items():
        if api_name in import_text:
            findings.append(description)
    for key in ("pdb_path", "debug_file", "debug_path"):
        value = str(details.get(key) or "").strip()
        if value:
            findings.append(f"PDB/debug path exposed: {value}")
    unique: list[str] = []
    for finding in findings:
        if finding not in unique:
            unique.append(finding)
    return unique[:12]


def extract_network_activity(network: Any) -> list[str]:
    if not isinstance(network, dict):
        return []
    values: list[str] = []
    for key in ("domains", "hosts", "dns", "http", "tcp", "udp"):
        raw = network.get(key)
        if not raw:
            continue
        if isinstance(raw, (list, tuple)):
            count = len(raw)
        elif isinstance(raw, dict):
            count = len(raw)
        else:
            count = 1
        if count:
            values.append(f"{key}: {count}")
    return values
