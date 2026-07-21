import json
import re
import threading
import uuid
from pathlib import Path

from backend.utils import safe_record_id, utc_now


class SkillSystem:
    """Persistent skill registry and keyword matcher."""

    def __init__(self, config_file: Path) -> None:
        self.config_file = config_file
        self.lock = threading.Lock()
        self.skills: dict[str, dict[str, object]] = self.load_skills()

    def load_skills(self) -> dict[str, dict[str, object]]:
        if not self.config_file.exists():
            return {}
        try:
            data = json.loads(self.config_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        if not isinstance(data, dict):
            return {}
        return {
            str(skill_id): self.normalize_skill_record(str(skill_id), skill)
            for skill_id, skill in data.items()
            if isinstance(skill, dict)
        }

    def save_skills(self) -> None:
        self.config_file.parent.mkdir(parents=True, exist_ok=True)
        self.config_file.write_text(
            json.dumps(self.skills, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def list_skills(self) -> list[dict[str, object]]:
        with self.lock:
            return sorted(
                (dict(skill) for skill in self.skills.values()),
                key=lambda item: str(item.get("updated_at") or item.get("created_at") or ""),
                reverse=True,
            )

    def get_skill(self, skill_id: str) -> dict[str, object] | None:
        with self.lock:
            skill = self.skills.get(skill_id)
            return dict(skill) if skill else None

    def create_skill(
        self,
        name: str,
        keywords: list[str],
        content: str,
        description: str = "",
        source: str = "editor",
    ) -> dict[str, object]:
        now = utc_now()
        skill_id = safe_record_id(name) or uuid.uuid4().hex
        with self.lock:
            if skill_id in self.skills:
                skill_id = f"{skill_id}-{uuid.uuid4().hex[:8]}"
            record = self.build_skill_record(
                skill_id=skill_id,
                name=name,
                keywords=keywords,
                content=content,
                description=description,
                source=source,
                created_at=now,
                updated_at=now,
            )
            self.skills[skill_id] = record
            self.save_skills()
            return dict(record)

    def update_skill(
        self,
        skill_id: str,
        name: str,
        keywords: list[str],
        content: str,
        description: str = "",
        source: str = "editor",
    ) -> dict[str, object] | None:
        now = utc_now()
        with self.lock:
            existing = self.skills.get(skill_id)
            if not existing:
                return None
            record = self.build_skill_record(
                skill_id=str(existing.get("id") or skill_id),
                name=name,
                keywords=keywords,
                content=content,
                description=description,
                source=source,
                created_at=str(existing.get("created_at") or now),
                updated_at=now,
            )
            self.skills[skill_id] = record
            self.save_skills()
            return dict(record)

    def delete_skill(self, skill_id: str) -> bool:
        with self.lock:
            if skill_id not in self.skills:
                return False
            self.skills.pop(skill_id, None)
            self.save_skills()
            return True

    def match_skills(self, value: object) -> list[dict[str, object]]:
        text = self.searchable_text(value)
        if not text:
            return []
        lowered_text = text.lower()
        matches: list[dict[str, object]] = []
        with self.lock:
            for skill in self.skills.values():
                keywords = skill.get("keywords") if isinstance(skill.get("keywords"), list) else []
                if any(self.keyword_matches(lowered_text, str(keyword)) for keyword in keywords):
                    matches.append(dict(skill))
        return matches

    def render_skill_prompt(self, skill: dict[str, object]) -> str:
        keywords = skill.get("keywords") if isinstance(skill.get("keywords"), list) else []
        keyword_text = ", ".join(str(keyword) for keyword in keywords if str(keyword).strip())
        return (
            f"Triggered skill: {skill.get('name') or skill.get('id')}\n"
            f"Trigger keywords: {keyword_text}\n\n"
            f"{str(skill.get('content') or '').strip()}"
        ).strip()

    def build_skill_record(
        self,
        skill_id: str,
        name: str,
        keywords: list[str],
        content: str,
        description: str,
        source: str,
        created_at: str,
        updated_at: str,
    ) -> dict[str, object]:
        normalized_keywords = self.normalize_keywords(keywords)
        if not normalized_keywords:
            raise ValueError("Skill 至少需要一个触发关键字")
        normalized_name = str(name or "").strip()
        normalized_content = str(content or "").strip()
        if not normalized_name:
            raise ValueError("Skill 名称不能为空")
        if not normalized_content:
            raise ValueError("Skill 内容不能为空")
        return {
            "id": skill_id,
            "name": normalized_name,
            "description": str(description or "").strip(),
            "keywords": normalized_keywords,
            "content": normalized_content,
            "source": str(source or "editor").strip() or "editor",
            "created_at": created_at,
            "updated_at": updated_at,
        }

    def normalize_skill_record(self, skill_id: str, skill: dict[str, object]) -> dict[str, object]:
        now = utc_now()
        return {
            "id": str(skill.get("id") or skill_id),
            "name": str(skill.get("name") or skill_id).strip(),
            "description": str(skill.get("description") or "").strip(),
            "keywords": self.normalize_keywords(
                skill.get("keywords") if isinstance(skill.get("keywords"), list) else []
            ),
            "content": str(skill.get("content") or "").strip(),
            "source": str(skill.get("source") or "editor").strip() or "editor",
            "created_at": str(skill.get("created_at") or now),
            "updated_at": str(skill.get("updated_at") or skill.get("created_at") or now),
        }

    @staticmethod
    def normalize_keywords(keywords: list[str]) -> list[str]:
        seen: set[str] = set()
        normalized: list[str] = []
        for keyword in keywords:
            text = str(keyword or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(text)
        return normalized

    @staticmethod
    def searchable_text(value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except TypeError:
            return str(value)

    @staticmethod
    def keyword_matches(lowered_text: str, keyword: str) -> bool:
        normalized = keyword.strip().lower()
        if not normalized:
            return False
        if re.fullmatch(r"[a-z0-9_./:-]+", normalized):
            return re.search(rf"(?<![a-z0-9_./:-]){re.escape(normalized)}(?![a-z0-9_./:-])", lowered_text) is not None
        return normalized in lowered_text
