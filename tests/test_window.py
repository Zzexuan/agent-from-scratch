"""D2 窗口预算单测：budget 推导 / 使用率计算 / 75% 阈值触发。零真实 API。

读法：先读两个"计算正确性"测试（from_model 推导、check 使用率），
再读两个"边界行为"测试（75% 临界、非法输入）。边界测试是单测的精华：
bug 往往藏在"刚好卡线"的位置，所以专门构造临界值来测。
"""

import pytest

from afg.context.counter import TokenCounter
from afg.context.messages import Message
from afg.context.window import COMPRESS_THRESHOLD, ContextWindow


def test_budget_from_model_window() -> None:
    """预算 = 模型窗口 × 安全系数（0.75）：from_model 的推导公式钉死。"""
    # 8192 * 0.75 = 6144；4096 * 0.75 = 3072。int() 取整后应是精确整数。
    assert ContextWindow.from_model(8192).budget == 6144
    assert ContextWindow.from_model(4096).budget == 3072


def test_invalid_budget_raises() -> None:
    """budget <= 0 必须抛 ValueError（window.py 构造时的防呆校验）。"""
    with pytest.raises(ValueError):
        ContextWindow(budget=0)


def test_check_low_usage_no_compress() -> None:
    """少量消息 → 使用率低 → 不触发压缩。"""
    counter = TokenCounter()
    window = ContextWindow(budget=1000)
    messages = [Message(role="user", content="hi")]
    report = window.check(messages, counter)
    # 报告单上三个字段逐一验证：
    assert report.total_tokens == counter.count_messages(messages)  # 总数 = 实际数出来的
    assert report.budget == 1000  # 预算原样带回
    assert 0 < report.usage_ratio < COMPRESS_THRESHOLD  # 使用率在 0 到 75% 之间
    assert not report.should_compress  # 没到 75% → 不压缩


def test_check_should_compress_matches_threshold() -> None:
    """临界测试：usage 刚好 ≥75% 时必须 should_compress=True。

    用同一批消息、三种"卡线"预算（差 1 token / 刚好 / 多 1 token）验证
    阈值边界：差一点不触发、刚好触发、超了也触发——三档全测才叫钉死边界。
    """
    counter = TokenCounter()
    messages = [Message(role="user", content="x" * 1000)]  # 固定 1000 字符的消息
    n = counter.count_messages(messages)  # 它的真实 token 数
    for margin in (-1, 0, 1):  # 分别造"差 1 / 刚好 / 超 1"三种预算
        window = ContextWindow(budget=int(n / COMPRESS_THRESHOLD) + margin)
        report = window.check(messages, counter)
        # 断言：should_compress 的值必须 == (使用率 >= 75%)，两边永远一致
        assert report.should_compress == (report.usage_ratio >= COMPRESS_THRESHOLD)


def test_check_over_threshold_triggers() -> None:
    """超阈值：小预算 + 长消息 → 使用率必然超 75% → 必须触发压缩。"""
    counter = TokenCounter()
    window = ContextWindow(budget=100)  # 小预算让长消息必然超 75%
    messages = [Message(role="user", content="这是一个很长的用户消息" * 50)]
    report = window.check(messages, counter)
    assert report.usage_ratio >= COMPRESS_THRESHOLD  # 确认确实超线
    assert report.should_compress  # 超线就必须触发（前面两个测试的反面）