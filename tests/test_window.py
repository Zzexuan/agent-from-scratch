import pytest

from afg.context.counter import TokenCounter
from afg.context.messages import Message
from afg.context.window import COMPRESS_THRESHOLD, ContextWindow


def test_budget_from_model_window() -> None:
    assert ContextWindow.from_model(8192).budget == 6144
    assert ContextWindow.from_model(4096).budget == 3072


def test_invalid_budget_raises() -> None:
    with pytest.raises(ValueError):
        ContextWindow(budget=0)


def test_check_low_usage_no_compress() -> None:
    counter = TokenCounter()
    window = ContextWindow(budget=1000)
    messages = [Message(role="user", content="hi")]
    report = window.check(messages, counter)
    assert report.total_tokens == counter.count_messages(messages)
    assert report.budget == 1000
    assert 0 < report.usage_ratio < COMPRESS_THRESHOLD
    assert not report.should_compress


def test_check_should_compress_matches_threshold() -> None:
    counter = TokenCounter()
    messages = [Message(role="user", content="x" * 1000)]
    n = counter.count_messages(messages)
    for margin in (-1, 0, 1):
        window = ContextWindow(budget=int(n / COMPRESS_THRESHOLD) + margin)
        report = window.check(messages, counter)
        assert report.should_compress == (report.usage_ratio >= COMPRESS_THRESHOLD)


def test_check_over_threshold_triggers() -> None:
    counter = TokenCounter()
    window = ContextWindow(budget=100)
    messages = [Message(role="user", content="这是一个很长的用户消息" * 50)]
    report = window.check(messages, counter)
    assert report.usage_ratio >= COMPRESS_THRESHOLD
    assert report.should_compress
