"""结构化日志：structlog 双输出（控制台人类可读 + chat.log 纯 JSON 行）。

D2 工程化增量：**从此全面禁止 print**，一切输出走事件日志。
统一字段：ts / level / component / event / trace_id / step。
- trace_id：一次会话（一次 `python -m afg.chat` 进程）一个 id，置入 contextvars，
  跨多轮对话与未来全部组件（工具/压缩/子代理）自动共享；D19 的 span 树基于它串。
- step：当前轮次，同样在 contextvars 里，每轮对话更新一次。

用法：
    trace_id = setup_logging()          # 会话启动时调用一次
    logger = get_logger("chat")         # component 字段 = "chat"
    logger.info("chat.turn", turn=1, tokens=42)   # 文件名 JSONRenderer 直出中文
"""

import logging
import sys
import uuid
from pathlib import Path
from typing import Any

import structlog

_LOG_FILE = "chat.log"


def rename_logger_to_component(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """把 structlog 的 `logger` 字段改名为契约字段 `component`。

    只用 event_dict，不碰 logger 参数——ProcessorFormatter 渲染阶段会以
    logger=None 重跑 pre_chain，任何依赖 logger 对象本身的 processor 都会炸。
    """
    if "logger" in event_dict:
        event_dict["component"] = event_dict.pop("logger")
    return event_dict


def _shared_processors() -> list[Any]:
    """structlog.configure 与 ProcessorFormatter.foreign_pre_chain 共用的预处理链。"""
    return [
        structlog.contextvars.merge_contextvars,  # 注入 trace_id / step
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,  # logger 名 = get_logger(component) 的 component
        rename_logger_to_component,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.format_exc_info,
        structlog.processors.StackInfoRenderer(),
    ]


def setup_logging(log_file: str | Path = _LOG_FILE) -> str:
    """初始化双输出日志，绑定新会话的 trace_id，返回该 id。

    控制台走 ConsoleRenderer（终端自动着色、非终端自动无色）；
    文件追加写纯 JSON 行（UTF-8），供回放与验收。
    """
    shared = _shared_processors()

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),  # colors=None：自动检测是否终端
        ],
    )
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )

    root = logging.getLogger()
    root.handlers.clear()
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    root.addHandler(console_handler)
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)

    # 静音底层 HTTP 库的 info 日志：LLM 调用信息由 chat.turn 等业务事件统一记录
    # （此环境 openai SDK 依赖的 fork 包 logger 名为 httpx2，一并覆盖）
    for noisy_logger in ("httpx", "httpx2", "openai", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    trace_id = uuid.uuid4().hex[:8]
    structlog.contextvars.bind_contextvars(trace_id=trace_id, step=0)
    return trace_id


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    """获取事件 logger；component 即字段 `component` 的值（如 "chat" / "tool"）。"""
    return structlog.get_logger(component)