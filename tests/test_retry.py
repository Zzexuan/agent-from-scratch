import pytest

from afg.observability.retry import with_retry

FAST_BACKOFF = 1.001
FAST_DELAY = 0.001


class FlakyCall:
    def __init__(self, fail_times, error=None):
        self.fail_times = fail_times
        self.calls = 0
        self.error = error
        if self.error is None:
            self.error = TimeoutError("假装超时")

    def run(self):
        self.calls = self.calls + 1
        if self.calls <= self.fail_times:
            raise self.error
        return "成功"


class Adder:
    def __init__(self):
        self.calls = 0

    def run(self, a, b, extra=0):
        self.calls = self.calls + 1
        return a + b + extra


def test_succeeds_after_two_failures():
    flaky = FlakyCall(fail_times=2)
    wrapped = with_retry(flaky.run, retries=3, backoff=FAST_BACKOFF, initial_delay=FAST_DELAY)

    assert wrapped() == "成功"
    assert flaky.calls == 3


def test_gives_up_after_retries_exhausted():
    flaky = FlakyCall(fail_times=99)
    wrapped = with_retry(flaky.run, retries=3, backoff=FAST_BACKOFF, initial_delay=FAST_DELAY)

    with pytest.raises(TimeoutError):
        wrapped()

    assert flaky.calls == 3


def test_no_retry_when_first_call_succeeds():
    flaky = FlakyCall(fail_times=0)
    wrapped = with_retry(flaky.run, retries=3, backoff=FAST_BACKOFF, initial_delay=FAST_DELAY)

    assert wrapped() == "成功"
    assert flaky.calls == 1


def test_wraps_keeps_original_function_name():
    flaky = FlakyCall(fail_times=0)
    wrapped = with_retry(flaky.run, retries=3, backoff=FAST_BACKOFF, initial_delay=FAST_DELAY)

    assert wrapped.__name__ == "run"


def test_retry_on_narrows_which_errors_are_retried():
    flaky = FlakyCall(fail_times=99, error=ValueError("参数错，重试也没用"))
    wrapped = with_retry(
        flaky.run,
        retries=3,
        backoff=FAST_BACKOFF,
        initial_delay=FAST_DELAY,
        retry_on=TimeoutError,
    )

    with pytest.raises(ValueError):
        wrapped()

    assert flaky.calls == 1


def test_arguments_and_keywords_pass_through():
    adder = Adder()
    wrapped = with_retry(adder.run, retries=3, backoff=FAST_BACKOFF, initial_delay=FAST_DELAY)

    assert wrapped(1, 2, extra=10) == 13
    assert adder.calls == 1
