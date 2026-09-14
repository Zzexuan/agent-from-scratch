from afg.context.compressor import SUMMARY_PREFIX, SUMMARY_SYSTEM_PROMPT, Compressor
from afg.context.counter import TokenCounter
from afg.context.messages import Message
from tests.fakes import FakeLLM


def make_messages(count, body_chars=10):
    messages = [Message(role="system", content="你是助手")]
    for i in range(count - 1):
        if i % 2 == 0:
            role = "user"
        else:
            role = "assistant"
        body = "字" * body_chars
        messages.append(Message(role=role, content="第" + str(i) + "条：" + body))
    return messages


def test_compress_three_part_structure():
    counter = TokenCounter()
    compressor = Compressor(budget=1000000)
    llm = FakeLLM(["这是摘要"])
    messages = make_messages(10)

    result = compressor.compress(messages, llm, counter, keep_recent=3)

    assert len(result) == 3 + 1 + 3
    assert result[0:3] == messages[0:3]
    assert result[4:7] == messages[7:10]


def test_summary_message_format_and_position():
    counter = TokenCounter()
    compressor = Compressor(budget=1000000)
    llm = FakeLLM(["关键决策：用三段式压缩"])

    result = compressor.compress(make_messages(10), llm, counter, keep_recent=3)

    summary = result[3]
    assert summary.role == "system"
    assert summary.content == SUMMARY_PREFIX + "关键决策：用三段式压缩"
    assert summary.content.startswith("[历史摘要] ")

    sent_to_llm = llm.calls[0]
    assert sent_to_llm[0].role == "system"
    assert sent_to_llm[0].content == SUMMARY_SYSTEM_PROMPT
    assert sent_to_llm[1].role == "user"


def test_compress_reaches_target_ratio():
    counter = TokenCounter()
    messages = make_messages(41, body_chars=200)
    original_tokens = counter.count_messages(messages)
    budget = int(original_tokens / 0.75)

    compressor = Compressor(budget=budget)
    llm = FakeLLM(["摘要"] * 6)

    result = compressor.compress(messages, llm, counter, keep_recent=20)
    compressed_tokens = counter.count_messages(result)

    assert compressed_tokens <= budget * 0.375
    assert compressed_tokens < original_tokens


def test_no_llm_call_when_nothing_to_compress():
    counter = TokenCounter()
    compressor = Compressor(budget=1000000)
    llm = FakeLLM([])
    messages = make_messages(4)

    result = compressor.compress(messages, llm, counter, keep_recent=20)

    assert result == messages
    assert len(llm.calls) == 0


def test_shrink_retries_with_fresh_summary():
    counter = TokenCounter()
    messages = make_messages(41, body_chars=200)
    original_tokens = counter.count_messages(messages)
    budget = int(original_tokens / 0.75)

    compressor = Compressor(budget=budget)
    llm = FakeLLM(["摘要"] * 6)

    compressor.compress(messages, llm, counter, keep_recent=20)

    assert len(llm.calls) >= 2


def test_never_summarizes_the_last_message():
    counter = TokenCounter()
    compressor = Compressor(budget=10)
    llm = FakeLLM(["摘要"])
    messages = make_messages(5)

    result = compressor.compress(messages, llm, counter, keep_recent=20)

    assert result[-1] == messages[-1]
    assert len(llm.calls) == 1
