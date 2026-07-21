import json

from backend.config import (
    DEFAULT_CAPABILITY_TYPE_NAME,
    LEGACY_STATUS_MODULE_NAMES,
    RUNTIME_DIR,
    STATUS_CONFIG_FILE,
    THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
    normalize_capability_type_name,
)
from backend.data_structures import (
    build_capability_type_record,
    build_status_module_record,
)
from backend.utils import utc_now


def default_capability_type_record() -> dict[str, object]:
    return build_capability_type_record(
        name=DEFAULT_CAPABILITY_TYPE_NAME,
        is_default=True,
    )


def default_threat_intelligence_capability_type_record() -> dict[str, object]:
    return build_capability_type_record(
        name=THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME,
        is_default=True,
    )


def normalize_capability_type_record(
    name: str,
    data: dict[str, object] | None = None,
) -> dict[str, object]:
    record = data or {}
    normalized_name = normalize_capability_type_name(str(record.get("name") or name))
    now = utc_now()
    return build_capability_type_record(
        name=normalized_name,
        is_default=normalized_name == DEFAULT_CAPABILITY_TYPE_NAME
        or bool(record.get("is_default")),
        created_at=str(record.get("created_at") or now),
        updated_at=str(record.get("updated_at") or now),
    )


def normalize_status_module(module_id: str, data: dict[str, object]) -> dict[str, object]:
    fallback_name, fallback_capability_type = LEGACY_STATUS_MODULE_NAMES.get(
        module_id, (module_id, DEFAULT_CAPABILITY_TYPE_NAME)
    )
    now = utc_now()
    capability_type = normalize_capability_type_name(
        str(data.get("capability_type") or data.get("type") or fallback_capability_type)
    )

    return build_status_module_record(
        module_id=str(data.get("id") or module_id),
        capability_type=capability_type,
        name=str(data.get("name") or fallback_name).strip(),
        url=str(data.get("url") or "").strip(),
        model=str(data.get("model") or data.get("model_name") or "").strip(),
        api_key=str(data.get("api_key") or "").strip(),
        token=str(data.get("token") or "").strip(),
        cookie=str(data.get("cookie") or "").strip(),
        capabilities=(
            dict(data.get("capabilities"))
            if isinstance(data.get("capabilities"), dict)
            else {}
        ),
        status=str(data.get("status") or "online").strip(),
        created_at=str(data.get("created_at") or now),
        updated_at=str(data.get("updated_at") or now),
    )


def load_status_payload() -> dict[str, object]:
    if not STATUS_CONFIG_FILE.exists():
        return {}
    try:
        data = json.loads(STATUS_CONFIG_FILE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def load_status_state() -> tuple[dict[str, dict[str, object]], dict[str, dict[str, object]]]:
    data = load_status_payload()
    source = data.get("modules") if isinstance(data.get("modules"), dict) else data
    modules = {
        str(module_id): normalize_status_module(str(module_id), module)
        for module_id, module in source.items()
        if isinstance(module, dict)
    }

    capability_types: dict[str, dict[str, object]] = {
        DEFAULT_CAPABILITY_TYPE_NAME: default_capability_type_record(),
        THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME: default_threat_intelligence_capability_type_record(),
    }
    raw_capability_types = data.get("capability_types")
    if isinstance(raw_capability_types, dict):
        for name, record in raw_capability_types.items():
            normalized_record = (
                normalize_capability_type_record(str(name), record)
                if isinstance(record, dict)
                else normalize_capability_type_record(str(name))
            )
            capability_types[str(normalized_record["name"])] = normalized_record

    for module in modules.values():
        capability_type = normalize_capability_type_name(
            str(module.get("capability_type") or DEFAULT_CAPABILITY_TYPE_NAME)
        )
        module["capability_type"] = capability_type
        if capability_type not in capability_types:
            capability_types[capability_type] = normalize_capability_type_record(capability_type)

    capability_types[DEFAULT_CAPABILITY_TYPE_NAME]["is_default"] = True
    capability_types[THREAT_INTELLIGENCE_CAPABILITY_TYPE_NAME]["is_default"] = True
    return modules, capability_types


def save_status_state(
    status_modules: dict[str, dict[str, object]],
    capability_types: dict[str, dict[str, object]],
) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    temp_file = STATUS_CONFIG_FILE.with_suffix(".json.tmp")
    temp_file.write_text(
        json.dumps(
            {
                "capability_types": capability_types,
                "modules": status_modules,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temp_file.replace(STATUS_CONFIG_FILE)


def extract_status_module_config(module: dict[str, object]) -> dict[str, str]:
    return {
        "url": str(module.get("url") or ""),
        "model": str(module.get("model") or ""),
        "api_key": str(module.get("api_key") or ""),
        "token": str(module.get("token") or ""),
        "cookie": str(module.get("cookie") or ""),
    }
