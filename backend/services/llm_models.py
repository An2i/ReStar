import json
import time
from threading import Event, Thread
from typing import Callable

from fastapi import HTTPException

from openai import OpenAI


from backend.config import DEFAULT_CAPABILITY_TYPE_NAME
from backend.data_structures import JsonDict, build_llm_snapshot_record
from backend.utils import utc_now

DEBUG_LOG_PREFIX = "[LLM_DEBUG]"


def capability_cache(platform: JsonDict | None) -> JsonDict:
    value = platform.get("capabilities") if isinstance(platform, dict) else {}
    return dict(value) if isinstance(value, dict) else {}


def configured_model(platform: JsonDict | None) -> str:
    if not platform:
        return ""
    for key in ("model", "model_name", "chat_model"):
        value = str(platform.get(key) or "").strip()
        if value:
            return value
    return ""


def select_chat_model(provider: str, platform: JsonDict | None) -> str:
    model = configured_model(platform)
    if model:
        return model
    if provider == "deepseek":
        return "deepseek-v4-pro"
    if provider == "claude":
        return "claude-3-5-haiku-latest"
    if provider == "gemini":
        return "gemini-1.5-flash"
    return "gpt-4o-mini"


class Pool:
    def __init__(self, capability_type: str) -> None:
        self.capability_type = capability_type
        self.platforms: dict[str, JsonDict] = {}
        self.occupied_counts: dict[str, int] = {}

    @property
    def platform_count(self) -> int:
        return len(self.platforms)

    def sync_platforms(self, platforms: list[JsonDict]) -> None:
        self.platforms = {str(platform["id"]): platform for platform in platforms}
        self.occupied_counts = {
            platform_id: self.occupied_counts.get(platform_id, 0)
            for platform_id in self.platforms
        }

    def occupy(self, platform_id: str) -> None:
        if platform_id in self.platforms:
            self.occupied_counts[platform_id] = (
                self.occupied_counts.get(platform_id, 0) + 1
            )

    def release(self, platform_id: str) -> None:
        if platform_id in self.occupied_counts:
            self.occupied_counts[platform_id] = max(
                0, self.occupied_counts[platform_id] - 1
            )

    def snapshot(self) -> JsonDict:
        return {
            "capability_type": self.capability_type,
            "platform_count": self.platform_count,
            "platforms": [
                {
                    "id": platform_id,
                    "name": platform.get("name", ""),
                    "occupied_count": self.occupied_counts.get(platform_id, 0),
                }
                for platform_id, platform in self.platforms.items()
            ],
        }


class LLMPool(Pool):
    refresh_interval_seconds = 300
    supported_providers = ("openai", "claude", "deepseek", "gemini")

    def __init__(self) -> None:
        super().__init__(DEFAULT_CAPABILITY_TYPE_NAME)
        self.token_records: dict[str, JsonDict] = {}
        self.last_refresh_ts = 0.0

    def sync_platforms(self, platforms: list[JsonDict]) -> None:
        super().sync_platforms(platforms)
        self.token_records = {
            platform_id: self.token_records.get(
                platform_id, self.create_token_record(platform)
            )
            for platform_id, platform in self.platforms.items()
        }

    def detect_provider(self, platform: JsonDict | None) -> str:
        if not platform:
            return "none"
        text = (
            f"{platform.get('name', '')} "
            f"{platform.get('url', '')} "
            f"{configured_model(platform)}"
        ).lower()
        if "deepseek" in text:
            return "deepseek"
        if "anthropic" in text or "claude" in text:
            return "claude"
        if "gemini" in text or "googleapis" in text or "generativelanguage" in text:
            return "gemini"
        if "openai" in text:
            return "openai"
        return "unknown"

    def create_token_record(self, platform: JsonDict) -> JsonDict:
        return {
            "platform_id": platform.get("id", ""),
            "provider": self.detect_provider(platform),
            "remaining_tokens": platform.get("remaining_tokens"),
            "checked_at": utc_now(),
            "status": "pending",
            "message": "等待下一次 token 刷新",
        }

    def refresh_token_balances(self, force: bool = False) -> dict[str, JsonDict]:
        current_ts = time.time()
        if (
            not force
            and current_ts - self.last_refresh_ts < self.refresh_interval_seconds
        ):
            return self.token_records
        self.last_refresh_ts = current_ts
        for platform_id, platform in self.platforms.items():
            self.token_records[platform_id] = self.probe_token_balance(platform)
        return self.token_records

    def probe_token_balance(self, platform: JsonDict) -> JsonDict:
        provider = self.detect_provider(platform)
        record: JsonDict = {
            "platform_id": platform.get("id", ""),
            "provider": provider,
            "remaining_tokens": platform.get("remaining_tokens"),
            "checked_at": utc_now(),
            "status": "unknown",
            "message": "",
        }
        if provider not in self.supported_providers:
            record["status"] = "unsupported"
            record["message"] = "暂未识别 LLM 平台类型"
            return record
        api_key = str(platform.get("api_key") or platform.get("token") or "").strip()
        if not api_key:
            record["status"] = "missing_credentials"
            record["message"] = "未配置 API Key 或 Token，无法探测 token 余额"
            return record
        request_info = self.build_token_probe_request(provider, api_key)
        if not request_info:
            record["status"] = "unsupported_probe"
            record["message"] = "该平台暂未配置 token 余额探测接口"
            return record
        try:
            import httpx

            with httpx.Client(timeout=8.0) as client:
                response = client.get(
                    request_info["url"],
                    headers=request_info.get("headers", {}),
                    params=request_info.get("params", {}),
                )
            record["http_status"] = response.status_code
            if response.status_code >= 400:
                record["status"] = "probe_failed"
                record["message"] = "token 余额探测接口返回错误"
                return record
            json_body = response.json() if response.content else {}
            remaining_tokens = self.extract_remaining_tokens(
                response.headers, json_body
            )
            record["remaining_tokens"] = remaining_tokens
            record["status"] = (
                "tracked"
                if remaining_tokens is not None
                else "tracked_without_token_value"
            )
            record["message"] = (
                "已记录剩余 token 数"
                if remaining_tokens is not None
                else "平台可访问，但未返回统一 token 余额字段"
            )
        except Exception as exc:
            record["status"] = "probe_error"
            record["message"] = f"token 余额探测失败: {exc.__class__.__name__}"
        return record

    def build_token_probe_request(self, provider: str, api_key: str) -> JsonDict | None:
        if provider == "openai":
            return {
                "url": "https://api.openai.com/v1/models",
                "headers": {"Authorization": f"Bearer {api_key}"},
            }
        if provider == "claude":
            return {
                "url": "https://api.anthropic.com/v1/models",
                "headers": {
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                },
            }
        if provider == "deepseek":
            return {
                "url": "https://api.deepseek.com/user/balance",
                "headers": {"Authorization": f"Bearer {api_key}"},
            }
        if provider == "gemini":
            return {
                "url": "https://generativelanguage.googleapis.com/v1beta/models",
                "params": {"key": api_key},
            }
        return None

    def extract_remaining_tokens(self, headers: object, body: object) -> float | None:
        token_header_candidates = (
            "x-ratelimit-remaining-tokens",
            "x-ratelimit-remaining-token",
            "x-remaining-tokens",
        )
        for header_name in token_header_candidates:
            header_value = headers.get(header_name) if hasattr(headers, "get") else None
            if header_value is not None:
                try:
                    return float(header_value)
                except (TypeError, ValueError):
                    pass
        body_candidates = (
            "remaining_tokens",
            "remaining_token",
            "total_remaining_tokens",
            "available_tokens",
            "tokens_remaining",
        )
        return self.find_numeric_value(body, body_candidates)

    def find_numeric_value(self, value: object, keys: tuple[str, ...]) -> float | None:
        if isinstance(value, dict):
            for key, item in value.items():
                if str(key).lower() in keys and isinstance(item, (int, float)):
                    return float(item)
            for item in value.values():
                found = self.find_numeric_value(item, keys)
                if found is not None:
                    return found
        if isinstance(value, list):
            for item in value:
                found = self.find_numeric_value(item, keys)
                if found is not None:
                    return found
        return None

    def select_platform(
        self, estimated_tokens: int = 0, provider: str = ""
    ) -> JsonDict:
        if not self.platforms:
            raise HTTPException(status_code=404, detail="暂无可用 LLM 平台")
        self.refresh_token_balances()
        candidates = []
        for platform_id, platform in self.platforms.items():
            record = self.token_records.get(platform_id, {})
            detected_provider = str(
                record.get("provider") or self.detect_provider(platform)
            )
            if provider and provider != detected_provider:
                continue
            remaining_tokens = record.get("remaining_tokens")
            token_score = (
                float(remaining_tokens)
                if isinstance(remaining_tokens, (int, float))
                else 1_000_000.0
            )
            occupied_count = self.occupied_counts.get(platform_id, 0)
            score = token_score - (occupied_count * max(estimated_tokens, 1) * 0.2)
            candidates.append((score, -occupied_count, platform_id, platform, record))
        if not candidates:
            raise HTTPException(status_code=404, detail="没有匹配的 LLM 平台")
        _, _, platform_id, platform, record = max(candidates, key=lambda item: item[:3])
        return {
            "platform": platform,
            "token_record": record,
            "occupied_count": self.occupied_counts.get(platform_id, 0),
        }

    def snapshot(self) -> JsonDict:
        base = super().snapshot()
        base["token_records"] = self.token_records
        base["last_refresh_ts"] = self.last_refresh_ts
        base["supported_providers"] = list(self.supported_providers)
        return base

    def supports_response_format_json_schema(self, platform: JsonDict | None) -> bool | None:
        capabilities = capability_cache(platform)
        value = capabilities.get("response_format_json_schema")
        if isinstance(value, bool):
            return value
        return None

    def probe_platform_capabilities(self, platform: JsonDict) -> JsonDict:
        provider = self.detect_provider(platform)
        api_key = str(platform.get("api_key") or platform.get("token") or "").strip()
        now = utc_now()
        current = capability_cache(platform)
        result: JsonDict = {
            **current,
            "checked_at": now,
            "provider": provider,
            "response_format_json_schema": None,
            "response_format_status": "unknown",
            "response_format_message": "",
        }
        if provider not in {"openai", "deepseek"}:
            result["response_format_status"] = "unsupported-provider"
            result["response_format_message"] = "当前 provider 不走 OpenAI 兼容 response_format 探测。"
            return result
        if not api_key:
            result["response_format_status"] = "missing-credentials"
            result["response_format_message"] = "缺少 API Key 或 Token，无法探测。"
            return result
        try:
            call_model(
                provider,
                api_key,
                platform,
                {"messages": [{"role": "user", "content": "Return {\"ok\":true}."}]},
                tools=[],
                response_format={
                    "type": "json_schema",
                    "json_schema": {
                        "name": "capability_probe",
                        "strict": True,
                        "schema": {
                            "type": "object",
                            "additionalProperties": False,
                            "required": ["ok"],
                            "properties": {"ok": {"type": "boolean"}},
                        },
                    },
                },
                timeout_seconds=12.0,
                max_tokens=32,
            )
            result["response_format_json_schema"] = True
            result["response_format_status"] = "supported"
            result["response_format_message"] = "探测成功，支持 response_format=json_schema。"
            return result
        except Exception as exc:
            message = str(exc)
            lowered = message.lower()
            if (
                "response_format" in lowered
                or "json_schema" in lowered
                or "unavailable now" in lowered
                or "invalid_request_error" in lowered
            ):
                result["response_format_json_schema"] = False
                result["response_format_status"] = "unsupported"
                result["response_format_message"] = message[:500]
                return result
            result["response_format_status"] = "probe_error"
            result["response_format_message"] = message[:500] or exc.__class__.__name__
            return result


class ModelManager:
    def __init__(
        self, get_llm_pool: Callable[[], LLMPool], estimated_tokens: int = 4096
    ) -> None:
        self.get_llm_pool = get_llm_pool
        self.estimated_tokens = estimated_tokens
        self.llm_pool: LLMPool | None = None
        self.llm_selection: JsonDict | None = None
        self.llm_platform: JsonDict | None = None
        self.allocation_error = ""

    def allocate_llm(self) -> None:
        self.llm_pool = self.get_llm_pool()
        try:
            self.llm_selection = self.llm_pool.select_platform(
                estimated_tokens=self.estimated_tokens
            )
            platform_id = str(self.llm_selection["platform"].get("id", ""))
            if platform_id:
                self.llm_pool.occupy(platform_id)
                self.llm_selection["occupied_count"] = (
                    self.llm_pool.occupied_counts.get(platform_id, 0)
                )
            self.llm_platform = self.llm_selection.get("platform")
            self.allocation_error = ""
        except HTTPException as exc:
            self.allocation_error = str(exc.detail)
            self.llm_selection = None
            self.llm_platform = None
        except Exception as exc:
            self.allocation_error = exc.__class__.__name__
            self.llm_selection = None
            self.llm_platform = None

    def release_llm(self) -> None:
        if not self.llm_pool or not self.llm_platform:
            return
        platform_id = str(self.llm_platform.get("id") or "")
        if platform_id:
            self.llm_pool.release(platform_id)

    def llm_snapshot(self) -> JsonDict:
        return build_llm_snapshot_record(
            self.llm_platform,
            self.llm_pool,
            self.llm_selection,
            self.allocation_error,
        )


class LLMRegistryManager:
    def __init__(self) -> None:
        self.pool_registry: dict[str, Pool] = {}
        self.stop_event = Event()
        self.worker: Thread | None = None

    def sync_pool_registry(
        self,
        capability_types: dict[str, JsonDict],
        status_modules: dict[str, JsonDict],
    ) -> None:
        next_registry: dict[str, Pool] = {}
        for capability_type in capability_types:
            existing_pool = self.pool_registry.get(capability_type)
            if capability_type == DEFAULT_CAPABILITY_TYPE_NAME:
                pool = (
                    existing_pool if isinstance(existing_pool, LLMPool) else LLMPool()
                )
            else:
                pool = (
                    existing_pool
                    if isinstance(existing_pool, Pool)
                    and not isinstance(existing_pool, LLMPool)
                    else Pool(capability_type)
                )
            platforms = [
                module
                for module in status_modules.values()
                if module.get("capability_type") == capability_type
            ]
            pool.sync_platforms(platforms)
            next_registry[capability_type] = pool
        self.pool_registry.clear()
        self.pool_registry.update(next_registry)

    def get_llm_pool(self, status_modules: dict[str, JsonDict]) -> LLMPool:
        pool = self.pool_registry.get(DEFAULT_CAPABILITY_TYPE_NAME)
        if not isinstance(pool, LLMPool):
            pool = LLMPool()
            pool.sync_platforms(
                [
                    module
                    for module in status_modules.values()
                    if module.get("capability_type") == DEFAULT_CAPABILITY_TYPE_NAME
                ]
            )
            self.pool_registry[DEFAULT_CAPABILITY_TYPE_NAME] = pool
        return pool

    def get_capability_type_list(
        self, capability_types: dict[str, JsonDict]
    ) -> list[JsonDict]:
        records = []
        for name, record in capability_types.items():
            pool = self.pool_registry.get(name)
            records.append(
                {
                    **record,
                    "platform_count": pool.platform_count if pool else 0,
                    "pool_class": pool.__class__.__name__ if pool else "Pool",
                }
            )
        return sorted(
            records,
            key=lambda item: (
                0 if item.get("name") == DEFAULT_CAPABILITY_TYPE_NAME else 1,
                str(item.get("name", "")),
            ),
        )

    def start_refresh_worker(
        self, status_modules_supplier: Callable[[], dict[str, JsonDict]]
    ) -> None:
        self.stop_event.clear()
        if self.worker and self.worker.is_alive():
            return
        self.get_llm_pool(status_modules_supplier()).refresh_token_balances(force=True)

        def loop() -> None:
            while not self.stop_event.wait(LLMPool.refresh_interval_seconds):
                self.get_llm_pool(status_modules_supplier()).refresh_token_balances(
                    force=True
                )

        self.worker = Thread(target=loop, daemon=True)
        self.worker.start()

    def stop_refresh_worker(self) -> None:
        self.stop_event.set()


def normalize_message_bundle(messages: object) -> tuple[str, list[JsonDict]]:
    system_parts: list[str] = []
    provider_messages: list[JsonDict] = []

    def append_message(role: str, content: object) -> None:
        text = str(content or "")
        if role == "system":
            if text.strip():
                system_parts.append(text)
            return
        normalized_role = role if role in {"user", "assistant"} else "user"
        if normalized_role == "user" and role not in {"user", "assistant"}:
            text = f"[{role}]\n{text}"
        provider_messages.append({"role": normalized_role, "content": text})

    if isinstance(messages, dict):
        for message in (
            messages.get("system", [])
            if isinstance(messages.get("system"), list)
            else []
        ):
            if isinstance(message, dict):
                append_message(
                    str(message.get("role") or "system"), message.get("content")
                )
        for message in (
            messages.get("messages", [])
            if isinstance(messages.get("messages"), list)
            else []
        ):
            if isinstance(message, dict):
                append_message(
                    str(message.get("role") or "user"), message.get("content")
                )
    elif isinstance(messages, list):
        for message in messages:
            if isinstance(message, dict):
                append_message(
                    str(message.get("role") or "user"), message.get("content")
                )

    if not provider_messages:
        provider_messages = [{"role": "user", "content": ""}]
    return "\n\n".join(part for part in system_parts if part.strip()), provider_messages


def call_model(
    provider: str,
    api_key: str,
    platform: JsonDict | None,
    messages: object,
    tools: list[JsonDict] | None = None,
    response_format: JsonDict | None = None,
    timeout_seconds: float = 45.0,
    temperature: float = 0.1,
    max_tokens: int = 1200,
) -> JsonDict:
    system_prompt, provider_messages = normalize_message_bundle(messages)
    # print(
    #     f"{DEBUG_LOG_PREFIX} provider={provider} "
    #     f"model={select_chat_model(provider, platform)} "
    #     f"system_len={len(system_prompt)} "
    #     f"message_count={len(provider_messages)} "
    #     f"tool_count={len(tool_payload)}"
    # )
    # if provider_messages:
    #     print(f"{DEBUG_LOG_PREFIX} first_message={str(provider_messages[0])[:500]}")

    if provider == "openai":
        base_url = (
            str((platform or {}).get("url") or "").strip().rstrip("/")
            or "https://api.openai.com/v1"
        )
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=select_chat_model(provider, platform),
            messages=(
                [{"role": "system", "content": system_prompt}] if system_prompt else []
            )
            + provider_messages,
            tools=tools or None,
            response_format=response_format or None,
            extra_body={"thinking": {"type": "enabled"}},
        )
        
        message = response.choices[0].message.model_dump()
        # print("------------------message-----------------")
        # print(message)
        return message

    if provider == "deepseek":
        base_url = (
            str((platform or {}).get("url") or "").strip().rstrip("/")
            or "https://api.deepseek.com"
        )
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=select_chat_model(provider, platform),
            messages=(
                [{"role": "system", "content": system_prompt}] if system_prompt else []
            )
            + provider_messages,
            tools=tools or None,
            response_format=response_format or None,
            extra_body={"thinking": {"type": "enabled"}},
        )
        
        message = response.choices[0].message.model_dump()
        # print("------------------message-----------------")
        # print(message)
        return message
    if provider == "claude":
        import httpx

        base_url = (
            str((platform or {}).get("url") or "https://api.anthropic.com/v1/messages")
            .strip()
            .rstrip("/")
        )
        endpoint = (
            base_url if base_url.endswith("/messages") else f"{base_url}/messages"
        )
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                endpoint,
                headers={"x-api-key": api_key, "anthropic-version": "2023-06-01"},
                json={
                    "model": select_chat_model(provider, platform),
                    "max_tokens": max_tokens,
                    "system": system_prompt,
                    "messages": provider_messages,
                },
            )
        response.raise_for_status()
        content = response.json().get("content", [])
        return str(content[0].get("text", "")) if content else ""

    if provider == "gemini":
        base_url = str((platform or {}).get("url") or "").strip().rstrip("/")
        if not base_url:
            model = select_chat_model(provider, platform)
            base_url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        endpoint = (
            base_url
            if "generateContent" in base_url
            else f"{base_url}/models/{select_chat_model(provider, platform)}:generateContent"
        )
        separator = "&" if "?" in endpoint else "?"
        endpoint = f"{endpoint}{separator}key={api_key}"
        contents = [
            {
                "role": message.get("role", "user"),
                "parts": [{"text": str(message.get("content") or "")}],
            }
            for message in provider_messages
        ]
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(
                endpoint,
                json={
                    "systemInstruction": (
                        {"parts": [{"text": system_prompt}]} if system_prompt else None
                    ),
                    "contents": contents,
                },
            )
        response.raise_for_status()
        return str(response.json()["candidates"][0]["content"]["parts"][0]["text"])

    raise ValueError("暂不支持该 LLM 平台类型")


def _tool_calls_to_json(
    tool_calls: object,
    content: str = "",
    reasoning_content: str = "",
) -> str:
    calls = []
    if isinstance(tool_calls, list):
        for item in tool_calls:
            function = getattr(item, "function", None)
            if not function:
                continue
            raw_arguments = getattr(function, "arguments", "{}") or "{}"
            try:
                arguments = json.loads(raw_arguments)
            except json.JSONDecodeError:
                arguments = {}
            calls.append(
                {
                    "id": str(getattr(item, "id", "") or ""),
                    "type": str(getattr(item, "type", "function") or "function"),
                    "function": {
                        "name": str(getattr(function, "name", "") or ""),
                        "arguments": raw_arguments,
                    },
                    # "tool": str(getattr(function, "name", "") or ""),
                    # "arguments": arguments,
                }
            )
    if not calls:
        return ""
    return json.dumps(
        {
            "complete": False,
            "content": content,
            "reasoning_content": reasoning_content,
            "tool_calls": calls,
        },
        ensure_ascii=False,
    )
