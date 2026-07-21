from pydantic import BaseModel, Field, field_validator, model_validator

from backend.config import normalize_capability_type_name


class StatusModuleConfig(BaseModel):
    url: str = Field(..., min_length=1)
    model: str = ""
    api_key: str = ""
    token: str = ""
    cookie: str = ""

    @field_validator("url", "model", "api_key", "token", "cookie", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("url")
    @classmethod
    def url_is_required(cls, value: str) -> str:
        if not value:
            raise ValueError("URL为必填项")
        return value


class StatusModuleCreate(BaseModel):
    capability_type: str = Field(..., min_length=1)
    name: str = Field(..., min_length=1)
    url: str = Field(..., min_length=1)
    model: str = ""
    api_key: str = ""
    token: str = ""
    cookie: str = ""

    @model_validator(mode="before")
    @classmethod
    def support_legacy_type_field(cls, values: object) -> object:
        if isinstance(values, dict) and "capability_type" not in values and "type" in values:
            values["capability_type"] = values["type"]
        return values

    @field_validator("capability_type", "name", "url", "model", "api_key", "token", "cookie", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("capability_type")
    @classmethod
    def normalize_capability_type_value(cls, value: str) -> str:
        return normalize_capability_type_name(value)

    @field_validator("url")
    @classmethod
    def url_is_required(cls, value: str) -> str:
        if not value:
            raise ValueError("URL为必填项")
        return value


class StatusModuleUpdate(StatusModuleCreate):
    pass


class CapabilityTypeCreate(BaseModel):
    name: str = Field(..., min_length=1)

    @field_validator("name", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return normalize_capability_type_name(str(value))


class LLMScheduleRequest(BaseModel):
    estimated_tokens: int = Field(default=0, ge=0)
    reserve: bool = True
    provider: str = ""

    @field_validator("provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip().lower()


class LLMReleaseRequest(BaseModel):
    platform_id: str = Field(..., min_length=1)


class KnowledgeBaseCreate(BaseModel):
    name: str = Field(..., min_length=1)
    folder_path: str = Field(..., min_length=1)

    @field_validator("name", "folder_path", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class KnowledgeBaseDelete(BaseModel):
    ids: list[str] = Field(default_factory=list)


class KnowledgeBaseQuery(BaseModel):
    query: str = Field(..., min_length=1)
    knowledge_base_ids: list[str] = Field(default_factory=list)
    top_k: int = Field(default=5, ge=1, le=20)

    @field_validator("query", mode="before")
    @classmethod
    def normalize_query(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class ToolConfigCreate(BaseModel):
    name: str = Field(..., min_length=1)
    command_line: str = Field(..., min_length=1)
    sandbox_command_line: str = ""
    description: str = Field(..., min_length=1)
    input_schema: dict[str, object] = Field(default_factory=dict)

    @field_validator("name", "command_line", "sandbox_command_line", "description", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("name", "command_line", "description")
    @classmethod
    def fields_are_required(cls, value: str) -> str:
        if not value:
            raise ValueError("工具名称、命令行和描述均为必填项")
        return value

    @field_validator("command_line")
    @classmethod
    def command_line_must_be_external(cls, value: str) -> str:
        if value.startswith("builtin:"):
            raise ValueError("用户外置工具不能使用 builtin: 内置工具命令")
        return value

    @field_validator("sandbox_command_line")
    @classmethod
    def sandbox_command_line_must_be_external(cls, value: str) -> str:
        if value.startswith("builtin:"):
            raise ValueError("用户外置工具的沙箱命令不能使用 builtin: 内置工具命令")
        return value

    @field_validator("input_schema")
    @classmethod
    def input_schema_must_be_object_schema(
        cls, value: dict[str, object]
    ) -> dict[str, object]:
        if not value:
            return {}
        if value.get("type") != "object":
            raise ValueError("input_schema type must be object")
        if not isinstance(value.get("properties", {}), dict):
            raise ValueError("input_schema properties must be an object")
        if not isinstance(value.get("required", []), list):
            raise ValueError("input_schema required must be a list")
        return value


class ToolConfigUpdate(ToolConfigCreate):
    pass


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1)
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    content: str = Field(..., min_length=1)
    source: str = "editor"

    @field_validator("name", "description", "content", "source", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("keywords", mode="before")
    @classmethod
    def normalize_keywords(cls, value: object) -> list[str]:
        if isinstance(value, str):
            raw_items = value.replace("，", ",").replace("\n", ",").split(",")
        elif isinstance(value, list):
            raw_items = value
        else:
            raw_items = []
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            text = str(item or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    @field_validator("keywords")
    @classmethod
    def keywords_are_required(cls, value: list[str]) -> list[str]:
        if not value:
            raise ValueError("Skill 至少需要一个触发关键字")
        return value


class SkillUpdate(SkillCreate):
    pass


class ManagerRequest(BaseModel):
    module: str = Field(..., min_length=1)
    action: str = Field(..., min_length=1)
    payload: dict[str, object] = Field(default_factory=dict)

    @field_validator("module", "action", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class ToolExecutionRequest(BaseModel):
    tool: str = Field(..., min_length=1)
    arguments: dict[str, object] = Field(default_factory=dict)
    session_id: str = ""
    agent_id: str = ""

    @field_validator("tool", mode="before")
    @classmethod
    def normalize_tool_name(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()


class MemoryRecordCreate(BaseModel):
    title: str = Field(..., min_length=1)
    content: str = Field(..., min_length=1)
    tags: list[str] = Field(default_factory=list)

    @field_validator("title", "content", mode="before")
    @classmethod
    def normalize_text(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()
