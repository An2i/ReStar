from backend.data_structures import JsonDict
from backend.services.session_memory import SessionStorage


class ContextManager:
    """."""

    def __init__(
        self,
        session_storage: SessionStorage | None = None,
        # sandbox_resolver: Any | None = None,
    ) -> None:
        self.base_system_messages = []
        self.system_slots = {}
        self.context_messages = {
            "system": [],  #[{ role: "system", content: "..." },]
            "messages": [], #[{ role: "user", content: "..." },]
        }
        self.sessionStorage = session_storage
        # self.sandboxResolver = sandbox_resolver
    
    def update_systemContext(self, message: JsonDict):
        self.base_system_messages.append(message)
        self._sync_system_messages()
        return

    def set_systemContext(self, slot: str, message: JsonDict):
        self.system_slots[str(slot)] = message
        self._sync_system_messages()
        return

    def _sync_system_messages(self):
        ordered_slots = [self.system_slots[key] for key in sorted(self.system_slots.keys())]
        self.context_messages["system"] = [*self.base_system_messages, *ordered_slots]

    def update_userContext(self, message: JsonDict):
        self.context_messages["messages"].append(message)
        return
    
    def get_messagesContext(self) -> JsonDict:
        return self.context_messages

    def total_chars(self) -> int:
        return sum(
            len(str(message.get("content") or ""))
            for key in ("system", "messages")
            for message in self.context_messages.get(key, [])
            if isinstance(message, dict)
        )
