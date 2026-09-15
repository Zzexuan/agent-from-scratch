import functools
import time

from afg.observability.logging import get_logger

INITIAL_DELAY_SECONDS = 1.0


def with_retry(fn, retries=3, backoff=1.5, retry_on=Exception, initial_delay=INITIAL_DELAY_SECONDS):
    total = max(1, retries)

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        logger = get_logger("retry")
        delay = initial_delay

        for attempt in range(1, total + 1):
            try:
                return fn(*args, **kwargs)
            except retry_on as e:
                if attempt >= total:
                    logger.warning(
                        "retry.give_up",
                        function=fn.__name__,
                        attempts=attempt,
                        error=str(e),
                    )
                    raise
                logger.warning(
                    "retry.attempt",
                    function=fn.__name__,
                    attempt=attempt,
                    error=str(e),
                    next_delay_seconds=round(delay, 2),
                )
                time.sleep(delay)
                delay = delay * backoff

    return wrapper


class RetryingLLM:
    """把重试过的 chat 再装回一个对象，好让 Compressor 能像用普通客户端一样用它。

    Compressor 要的是"一个有 chat 方法的对象"，而 with_retry 返回的是函数。
    这个类就是那层适配。
    """

    def __init__(self, llm, retries=3, backoff=1.5):
        self._llm = llm
        self.chat = with_retry(llm.chat, retries=retries, backoff=backoff)
