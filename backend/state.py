from threading import Lock

from backend.config import (
    DEFAULT_CAPABILITY_TYPE_NAME,
    MEMORY_FILE,
    SKILLS_CONFIG_FILE,
    SESSION_DIR,
    is_sandbox_capability_type,
    is_threat_intelligence_capability_type,
)
from backend.services.agent import RequestManager
from backend.services.llm_models import LLMRegistryManager, LLMPool, ModelManager, Pool
from backend.services.session_memory import MemoryManager, PromptManager, SessionStorage
from backend.services.skill_system import SkillSystem
from backend.services.tasks import TaskPool
from backend.services.tool_system import ToolSystem
from backend.stores.knowledge_store import load_knowledge_bases, save_knowledge_bases
from backend.stores.status_store import load_status_state, save_status_state
from backend.stores.tool_store import ensure_default_tools, load_tool_configs, save_tool_configs


status_modules, capability_types = load_status_state()
status_module_lock = Lock()

knowledge_bases: dict[str, dict[str, object]] = load_knowledge_bases()
knowledge_base_lock = Lock()

tool_configs: dict[str, dict[str, object]] = load_tool_configs()
tool_config_lock = Lock()
ensure_default_tools(tool_configs)

llm_registry = LLMRegistryManager()
pool_registry: dict[str, Pool] = llm_registry.pool_registry


def sync_pool_registry() -> None:
    llm_registry.sync_pool_registry(capability_types, status_modules)


def get_llm_pool() -> LLMPool:
    return llm_registry.get_llm_pool(status_modules)


def save_status_state_and_sync_pools() -> None:
    sync_pool_registry()
    save_status_state(status_modules, capability_types)


def save_knowledge_bases_state() -> None:
    save_knowledge_bases(knowledge_bases)


def save_tool_configs_state() -> None:
    save_tool_configs(tool_configs)


def get_capability_type_list() -> list[dict[str, object]]:
    sync_pool_registry()
    return llm_registry.get_capability_type_list(capability_types)


def get_online_sandbox_platform() -> dict[str, object] | None:
    for module in status_modules.values():
        if not is_sandbox_capability_type(str(module.get("capability_type") or "")):
            continue
        if str(module.get("status") or "").lower() != "online":
            continue
        if not str(module.get("url") or "").strip():
            continue
        return module
    return None


def get_online_threat_intelligence_platform() -> dict[str, object] | None:
    for module in status_modules.values():
        if not is_threat_intelligence_capability_type(
            str(module.get("capability_type") or "")
        ):
            continue
        if str(module.get("status") or "").lower() != "online":
            continue
        if not str(module.get("api_key") or module.get("token") or "").strip():
            continue
        return module
    return None


def start_llm_pool_refresh_worker() -> None:
    llm_registry.start_refresh_worker(lambda: status_modules)


def stop_llm_pool_refresh_worker() -> None:
    llm_registry.stop_refresh_worker()


def start_background_workers() -> None:
    session_storage.start_cache_worker()
    start_llm_pool_refresh_worker()
    task_pool.start()


def stop_background_workers() -> None:
    session_storage.stop_cache_worker()
    stop_llm_pool_refresh_worker()
    task_pool.stop()


sync_pool_registry()

session_storage = SessionStorage(SESSION_DIR)
memory_manager = MemoryManager(MEMORY_FILE)
prompt_manager = PromptManager(memory_manager)
tool_system = ToolSystem(
    tool_configs,
    session_storage,
    sandbox_resolver=get_online_sandbox_platform,
)
skill_system = SkillSystem(SKILLS_CONFIG_FILE)
task_pool = TaskPool(
    tool_system=tool_system,
    session_storage=session_storage,
    memory_manager=memory_manager,
    model_manager=ModelManager(get_llm_pool),
    skill_system=skill_system,
    threat_intelligence_resolver=get_online_threat_intelligence_platform,
)
request_manager = RequestManager(
    tool_system=tool_system,
    session_storage=session_storage,
    prompt_manager=prompt_manager,
    memory_manager=memory_manager,
    get_llm_pool=get_llm_pool,
    task_pool=task_pool,
)
