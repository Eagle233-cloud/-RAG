from pathlib import Path

from app.conversation import ConversationStore


def test_conversation_persists_and_builds_context(tmp_path: Path):
    store = ConversationStore(tmp_path)
    store.add("user", "我想了解项目结构")
    store.add("assistant", "项目包含 app 和 tests 目录")

    reloaded = ConversationStore(tmp_path)
    assert reloaded.status()["message_count"] == 2
    assert "项目结构" in reloaded.context()


def test_conversation_clear_and_summary(tmp_path: Path):
    store = ConversationStore(tmp_path)
    store.add("user", "问题")
    store.replace_with_summary("用户希望了解问题的解决方案。")
    assert store.messages == []
    assert store.summary == "用户希望了解问题的解决方案。"
    store.clear()
    assert store.summary == ""
    assert store.messages == []
