import logging
import sys
import uuid

import structlog

_LOG_FILE = "chat.log"


def rename_logger_to_component(_logger, _method, event_dict):
    if "logger" in event_dict:
        event_dict["component"] = event_dict.pop("logger")
    return event_dict


def _shared_processors():
    return [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        rename_logger_to_component,
        structlog.processors.TimeStamper(fmt="iso", key="ts"),
        structlog.processors.format_exc_info,
        structlog.processors.StackInfoRenderer(),
    ]


def setup_logging(log_file=_LOG_FILE):
    shared = _shared_processors()

    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            structlog.dev.ConsoleRenderer(),
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


def get_logger(component):
    return structlog.get_logger(component)
