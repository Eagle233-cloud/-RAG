from dataclasses import asdict, dataclass
import json
from pathlib import Path


@dataclass
class Message:
    role: str
    content: str


class ConversationStore:
    filename = "conversation.json"

    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.path = data_dir / self.filename
        self.summary = ""
        self.messages: list[Message] = []
        self._load()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.summary = str(data.get("summary", "")).strip()
            self.messages = [
                Message(str(item["role"]), str(item["content"]))
                for item in data.get("messages", [])
                if item.get("role") in {"user", "assistant"} and str(item.get("content", "")).strip()
            ]
        except (OSError, ValueError, KeyError, TypeError):
            self.summary = ""
            self.messages = []

    def _save(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(
                {"summary": self.summary, "messages": [asdict(item) for item in self.messages]},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    def add(self, role: str, content: str) -> None:
        self.messages.append(Message(role, content))
        self._save()

    def clear(self) -> None:
        self.summary = ""
        self.messages = []
        self._save()

    def replace_with_summary(self, summary: str) -> None:
        self.summary = summary.strip()
        self.messages = []
        self._save()

    def context(self) -> str:
        parts = []
        if self.summary:
            parts.append(f"此前对话摘要：\n{self.summary}")
        if self.messages:
            parts.append(
                "最近对话：\n"
                + "\n".join(f"{item.role}：{item.content}" for item in self.messages)
            )
        return "\n\n".join(parts)

    def status(self) -> dict[str, str | int]:
        return {
            "conversation_file": str(self.path.resolve()),
            "message_count": len(self.messages),
            "has_summary": bool(self.summary),
            "summary": self.summary,
        }
