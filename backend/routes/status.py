import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException

from backend.config import (
    DEFAULT_CAPABILITY_TYPE_NAME,
    is_threat_intelligence_capability_type,
    normalize_capability_type_name,
)
from backend.data_structures import (
    build_capability_type_record,
    build_status_module_record,
)
from backend.schemas import (
    CapabilityTypeCreate,
    LLMReleaseRequest,
    LLMScheduleRequest,
    StatusModuleConfig,
    StatusModuleCreate,
    StatusModuleUpdate,
)
from backend.state import (
    capability_types,
    get_capability_type_list,
    get_llm_pool,
    pool_registry,
    save_status_state_and_sync_pools,
    status_module_lock,
    status_modules,
    sync_pool_registry,
)
from backend.stores.status_store import extract_status_module_config
from backend.services.threat_intelligence import test_threatbook_platform
from backend.utils import utc_now


router = APIRouter()


def probe_status_module(module: dict[str, object]) -> dict[str, object]:
    capability_type = str(module.get("capability_type") or "")
    if is_threat_intelligence_capability_type(capability_type):
        return test_threatbook_platform(module)
    url = str(module.get("url") or "").strip()
    if not url:
        return {"ok": False, "error": "url is required"}
    try:
        request = Request(url, headers={"Accept": "application/json,text/plain,*/*"})
        with urlopen(request, timeout=10) as response:
            return {
                "ok": True,
                "http_status": getattr(response, "status", 200),
                "endpoint": url,
            }
    except HTTPError as exc:
        return {
            "ok": 200 <= exc.code < 500,
            "http_status": exc.code,
            "endpoint": url,
            "error": str(exc.reason),
        }
    except (URLError, TimeoutError) as exc:
        return {"ok": False, "endpoint": url, "error": str(getattr(exc, "reason", exc))}


def apply_probe_result(module: dict[str, object]) -> dict[str, object]:
    probe = probe_status_module(module)
    module["capabilities"] = {
        **(
            dict(module.get("capabilities"))
            if isinstance(module.get("capabilities"), dict)
            else {}
        ),
        "probe": probe,
    }
    module["status"] = "online" if probe.get("ok") else "offline"
    return module


@router.get("/api/status-configs")
def get_status_configs() -> dict[str, dict[str, str]]:
    return {
        module_id: extract_status_module_config(module)
        for module_id, module in status_modules.items()
    }


@router.get("/api/status-configs/{module_id}")
def get_status_config(module_id: str) -> dict[str, str]:
    module = status_modules.get(module_id)
    if module:
        return extract_status_module_config(module)
    return {"url": "", "model": "", "api_key": "", "token": "", "cookie": ""}


@router.post("/api/status-configs/{module_id}")
def save_status_config(module_id: str, config: StatusModuleConfig) -> dict[str, object]:
    now = utc_now()
    with status_module_lock:
        existing = status_modules.get(module_id)
        saved_config = {
            "id": module_id,
            "capability_type": str(
                existing.get("capability_type") if existing else DEFAULT_CAPABILITY_TYPE_NAME
            ),
            "name": str(existing.get("name") if existing else module_id),
            "url": config.url,
            "model": config.model,
            "api_key": config.api_key,
            "token": config.token,
            "cookie": config.cookie,
            "status": str(existing.get("status") if existing else "online"),
            "created_at": str(existing.get("created_at") if existing else now),
            "updated_at": now,
        }
        status_modules[module_id] = saved_config
        save_status_state_and_sync_pools()
    return {"saved": True, "module_id": module_id, "config": extract_status_module_config(saved_config)}


@router.get("/api/capability-types")
def get_capability_types() -> list[dict[str, object]]:
    return get_capability_type_list()


@router.post("/api/capability-types")
def create_capability_type(payload: CapabilityTypeCreate) -> dict[str, object]:
    name = normalize_capability_type_name(payload.name)
    if not name:
        raise HTTPException(status_code=400, detail="能力类型名称不能为空")
    if name == DEFAULT_CAPABILITY_TYPE_NAME or name in capability_types:
        raise HTTPException(status_code=409, detail="能力类型已存在")

    now = utc_now()
    record = build_capability_type_record(
        name=name,
        is_default=False,
        created_at=now,
        updated_at=now,
    )
    with status_module_lock:
        capability_types[name] = record
        save_status_state_and_sync_pools()

    pool = pool_registry.get(name)
    return build_capability_type_record(
        name=name,
        is_default=False,
        created_at=str(record.get("created_at") or now),
        updated_at=str(record.get("updated_at") or now),
        platform_count=pool.platform_count if pool else 0,
        pool_class=pool.__class__.__name__ if pool else "Pool",
    )


@router.delete("/api/capability-types/{capability_name:path}")
def delete_capability_type(capability_name: str, force: bool = False) -> dict[str, object]:
    name = normalize_capability_type_name(capability_name)
    if name == DEFAULT_CAPABILITY_TYPE_NAME:
        raise HTTPException(status_code=400, detail="系统默认LLM 平台能力类型不可删除")
    if name not in capability_types:
        raise HTTPException(status_code=404, detail="能力类型不存在")

    platform_ids = [
        module_id
        for module_id, module in status_modules.items()
        if module.get("capability_type") == name
    ]
    if platform_ids and not force:
        raise HTTPException(
            status_code=409,
            detail={
                "message": "是否强制删除",
                "requires_force": True,
                "platform_count": len(platform_ids),
            },
        )

    with status_module_lock:
        for module_id in platform_ids:
            status_modules.pop(module_id, None)
        capability_types.pop(name, None)
        save_status_state_and_sync_pools()
    return {"deleted": name, "deleted_platform_ids": platform_ids}


@router.get("/api/pools")
def get_pools() -> dict[str, object]:
    sync_pool_registry()
    return {name: pool.snapshot() for name, pool in pool_registry.items()}


@router.post("/api/llm-pool/refresh")
def refresh_llm_pool() -> dict[str, object]:
    pool = get_llm_pool()
    return {"token_records": pool.refresh_token_balances(force=True)}


@router.post("/api/llm-pool/probe-capabilities")
def probe_llm_capabilities() -> dict[str, object]:
    pool = get_llm_pool()
    refreshed = []
    with status_module_lock:
        for module_id, module in status_modules.items():
            if module.get("capability_type") != DEFAULT_CAPABILITY_TYPE_NAME:
                continue
            capabilities = pool.probe_platform_capabilities(module)
            module["capabilities"] = capabilities
            module["updated_at"] = utc_now()
            refreshed.append(
                {
                    "module_id": module_id,
                    "name": module.get("name", ""),
                    "capabilities": capabilities,
                }
            )
        save_status_state_and_sync_pools()
    return {"items": refreshed}


@router.post("/api/llm-pool/schedule")
def schedule_llm_platform(payload: LLMScheduleRequest) -> dict[str, object]:
    pool = get_llm_pool()
    selection = pool.select_platform(
        estimated_tokens=payload.estimated_tokens,
        provider=payload.provider,
    )
    platform_id = str(selection["platform"].get("id", ""))
    if payload.reserve and platform_id:
        pool.occupy(platform_id)
        selection["occupied_count"] = pool.occupied_counts.get(platform_id, 0)
    return selection


@router.post("/api/llm-pool/release")
def release_llm_platform(payload: LLMReleaseRequest) -> dict[str, object]:
    pool = get_llm_pool()
    pool.release(payload.platform_id)
    return {
        "platform_id": payload.platform_id,
        "occupied_count": pool.occupied_counts.get(payload.platform_id, 0),
    }


@router.get("/api/status-modules")
def get_status_modules() -> list[dict[str, object]]:
    return sorted(
        status_modules.values(),
        key=lambda item: str(item.get("created_at", "")),
        reverse=True,
    )


@router.post("/api/status-modules")
def create_status_module(payload: StatusModuleCreate) -> dict[str, object]:
    capability_type = normalize_capability_type_name(payload.capability_type)
    if capability_type not in capability_types:
        raise HTTPException(status_code=400, detail="能力类型不存在，请先在能力管理中添加")

    module_id = uuid.uuid4().hex
    now = utc_now()
    module = build_status_module_record(
        module_id=module_id,
        capability_type=capability_type,
        name=payload.name,
        url=payload.url,
        model=payload.model,
        api_key=payload.api_key,
        token=payload.token,
        cookie=payload.cookie,
        capabilities={},
        status="online",
        created_at=now,
        updated_at=now,
    )
    module = apply_probe_result(module)
    with status_module_lock:
        status_modules[module_id] = module
        save_status_state_and_sync_pools()
    return module


@router.put("/api/status-modules/{module_id}")
def update_status_module(module_id: str, payload: StatusModuleUpdate) -> dict[str, object]:
    capability_type = normalize_capability_type_name(payload.capability_type)
    if capability_type not in capability_types:
        raise HTTPException(status_code=400, detail="能力类型不存在，请先在能力管理中添加")

    now = utc_now()
    with status_module_lock:
        existing = status_modules.get(module_id)
        if not existing:
            raise HTTPException(status_code=404, detail="模块功能不存在")
        updated_module = build_status_module_record(
            module_id=str(existing.get("id") or module_id),
            capability_type=capability_type,
            name=payload.name,
            url=payload.url,
            model=payload.model,
            api_key=payload.api_key,
            token=payload.token,
            cookie=payload.cookie,
            capabilities=(
                dict(existing.get("capabilities"))
                if isinstance(existing.get("capabilities"), dict)
                else {}
            ),
            status=str(existing.get("status") or "online"),
            created_at=str(existing.get("created_at") or now),
            updated_at=now,
        )
        updated_module = apply_probe_result(updated_module)
        status_modules[module_id] = updated_module
        save_status_state_and_sync_pools()
    return updated_module


@router.post("/api/status-modules/{module_id}/probe")
def probe_status_module_route(module_id: str) -> dict[str, object]:
    now = utc_now()
    with status_module_lock:
        module = status_modules.get(module_id)
        if not module:
            raise HTTPException(status_code=404, detail="模块功能不存在")
        module = apply_probe_result(dict(module))
        module["updated_at"] = now
        status_modules[module_id] = module
        save_status_state_and_sync_pools()
    return module


@router.delete("/api/status-modules/{module_id}")
def delete_status_module(module_id: str) -> dict[str, object]:
    with status_module_lock:
        if module_id not in status_modules:
            raise HTTPException(status_code=404, detail="模块功能不存在")
        status_modules.pop(module_id, None)
        save_status_state_and_sync_pools()
    return {"deleted": module_id}
