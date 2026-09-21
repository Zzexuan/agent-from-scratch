from afg.context.messages import Message
from afg.memory.sqlite import SQLiteMemory


def make_memory():
    return SQLiteMemory(":memory:", session_id="test")


def test_save_and_load_roundtrip_in_order():
    memory = make_memory()
    memory.save(
        [
            Message(role="user", content="第一句"),
            Message(role="assistant", content="第二句"),
        ]
    )

    loaded = memory.load_context(k=5)

    assert len(loaded) == 2
    assert loaded[0].role == "user"
    assert loaded[0].content == "第一句"
    assert loaded[1].role == "assistant"
    assert loaded[1].content == "第二句"


def test_load_context_keeps_only_last_k():
    memory = make_memory()
    for index in range(5):
        memory.save([Message(role="user", content="第 " + str(index) + " 句")])

    loaded = memory.load_context(k=2)

    assert len(loaded) == 2
    assert loaded[0].content == "第 3 句"
    assert loaded[1].content == "第 4 句"


def test_empty_memory_returns_empty_list():
    memory = make_memory()

    assert memory.load_context() == []


def test_tool_and_empty_messages_are_skipped():
    memory = make_memory()
    memory.save(
        [
            Message(role="tool", content="工具结果", tool_call_id="c1"),
            Message(role="assistant", content=None),
        ]
    )

    assert memory.load_context() == []
