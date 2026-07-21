import re
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent
FRONTEND_DIST = ROOT_DIR / "frontend" / "dist"
ASSETS_DIR = FRONTEND_DIST / "assets"
RUNTIME_DIR = ROOT_DIR / "runtime"
STATUS_CONFIG_FILE = RUNTIME_DIR / "status_configs.json"
KNOWLEDGE_BASE_FILE = RUNTIME_DIR / "knowledge_bases.json"
KNOWLEDGE_VECTOR_DIR = RUNTIME_DIR / "knowledge_vectors"
TOOLS_CONFIG_FILE = RUNTIME_DIR / "tools.json"
SKILLS_CONFIG_FILE = RUNTIME_DIR / "skills.json"
UPLOAD_DIR = RUNTIME_DIR / "uploads"
REPORT_DIR = RUNTIME_DIR / "reports"
SESSION_DIR = RUNTIME_DIR / "sessions"
MEMORY_DIR = RUNTIME_DIR / "memory"
MEMORY_FILE = MEMORY_DIR / "MEMORY.md"
TOOL_AUDIT_FILE = RUNTIME_DIR / "tool_audit.jsonl"
TASK_RUNTIME_DIR = RUNTIME_DIR / "tasks"
TOKEN_PATTERN = re.compile(r"[\w\u4e00-\u9fff]+", re.UNICODE)

DEFAULT_CAPABILITY_TYPE_NAME = "LLM 平台"
SANDBOX_CAPABILITY_TYPE_NAME = "沙箱"
THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME = "威胁情报平台"
LEGACY_CAPABILITY_TYPE_ALIASES = {
    "LLM平台": DEFAULT_CAPABILITY_TYPE_NAME,
    "LLM 平台": DEFAULT_CAPABILITY_TYPE_NAME,
    "sandbox": SANDBOX_CAPABILITY_TYPE_NAME,
    "Sandbox": SANDBOX_CAPABILITY_TYPE_NAME,
    "沙箱环境": SANDBOX_CAPABILITY_TYPE_NAME,
    "沙箱能力": SANDBOX_CAPABILITY_TYPE_NAME,
    "threat-intelligence": THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
    "Threat Intelligence": THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
    "威胁情报": THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
    "威胁情报平台": THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
}
LEGACY_STATUS_MODULE_NAMES = {
    "llm": ("LLM连接状态", DEFAULT_CAPABILITY_TYPE_NAME),
    "threat-intelligence": ("威胁情报平台连接", "其他"),
    "open-source-knowledge": ("开源知识库连接", "其他"),
    "online-platforms": ("其他在线平台连接", "其他"),
    "database-usage": ("数据库使用量", "其他"),
    "sandbox-runtime": ("沙箱运行情况", "其他"),
}


def normalize_capability_type_name(name: str) -> str:
    normalized = str(name or "").strip()
    return LEGACY_CAPABILITY_TYPE_ALIASES.get(normalized, normalized)


def is_sandbox_capability_type(name: str) -> bool:
    return normalize_capability_type_name(name) == SANDBOX_CAPABILITY_TYPE_NAME


def is_threat_intelligence_capability_type(name: str) -> bool:
    return normalize_capability_type_name(name) == THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME
