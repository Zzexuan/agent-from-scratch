"""结构化日志：structlog 双输出（控制台人类可读 + chat.log 纯 JSON 行）。

D2 工程化增量：**从此全面禁止 print**，一切输出走事件日志。
统一字段：ts / level / component / event / trace_id / step。
- trace_id：一次会话（一次 `python -m afg.chat` 进程）一个 id，置入 contextvars，
  跨多轮对话与未来全部组件（工具/压缩/子代理）自动共享；D19 的 span 树基于它串。
- step：当前轮次，同样在 contextvars 里，每轮对话更新一次。

新手阅读顺序（这是全项目最"魔法"的文件，分两层看）：
【使用层——你只需要会这 3 行，其余可先跳过】
    trace_id = setup_logging()      # 程序启动时调用一次（见 chat.py main()）
    logger = get_logger("chat")     # 拿一个 logger，参数是组件名
    logger.info("chat.turn", turn=1, tokens=42)   # 记一条事件日志
    # 之后你每次 logger.xxx() 都会自动带上 ts/level/component/trace_id/step。
【原理层——文件里下面每一段都在回答"上面 3 行为什么能自动带字段"】
    1. structlog 是什么：日志"流水线"。你 logger.info("chat.turn", turn=1) 时，
       它把你的事件(chat.turn)和字段(turn=1)装进一个字典（事件字典），
       让一串【处理器(processor)】排队加工，最后渲染成一行文本输出。
    2. 处理器 = 流水线上的工人：每个工人往字典里加一个字段——
       add_log_level 加 level、TimeStamper 加 ts、merge_contextvars 加
       trace_id/step……工人在 _shared_processors() 里按顺序排好。
    3. 为什么要两套输出（双 handler）：同一份日志，控制台走"人类可读"
       的渲染（ConsoleRenderer，彩色），文件走"机器可读"的渲染
       （JSONRenderer，每行一个 JSON，方便回放/脚本分析）。日志先经过
       同一串工人加工，到出口才分流成两种格式——这就是 ProcessorFormatter
       干的事（一个日志，两个出口，共用一套字段）。
    4. contextvars = "每线程独立的全局变量"。trace_id 绑进去后，不管代码
       调用层级多深，任何 logger 打日志时 merge_contextvars 都能取到它——
       同一会话的所有日志天然带同一个 trace_id，方便 grep 串起来看。
"""

import logging  # Python 标准库日志（structlog 底层复用它的 handler 机制）
import sys  # sys.stdout = 标准输出（控制台），日志往这写
import uuid  # uuid4() 生成随机 id，用作 trace_id
from pathlib import Path
from typing import Any

import structlog  # 结构化日志库（pyproject 依赖之一，见模块 docstring 原理层）

_LOG_FILE = "chat.log"


def rename_logger_to_component(
    _logger: Any, _method: str, event_dict: dict[str, Any]
) -> dict[str, Any]:
    """把 structlog 的 `logger` 字段改名为契约字段 `component`。

    这个函数的签名是 structlog 处理器要求的固定格式：
        (_logger, _method, event_dict) → event_dict
    即：接收当前 logger、方法名、事件字典，加工后【原样返回事件字典】。
    参数名前加 _ 表示"我们不用它"（_logger/_method 只是占位）。
    """
    if "logger" in event_dict:
        # pop = "取出并删除"：把 logger 的值拿出来，同时把键改名成 component。
        # 为什么改名：项目契约规定每条日志都要有 component（组件名）字段，
        # 而 structlog 默认加的叫 logger，不统一的话回放脚本就得兼容两种。
        event_dict["component"] = event_dict.pop("logger")
    return event_dict


def _shared_processors() -> list[Any]:
    """structlog.configure 与 ProcessorFormatter.foreign_pre_chain 共用的预处理链。"""
    return [
        structlog.contextvars.merge_contextvars,  # 注入 trace_id / step
        structlog.stdlib.add_log_level,  # 加 level 字段（info/warning/...）
        structlog.stdlib.add_logger_name,  # logger 名 = get_logger(component) 的 component
        rename_logger_to_component,  # 上面定义的：把 logger 改名成 component
        structlog.processors.TimeStamper(fmt="iso", key="ts"),  # 加 ISO 时间戳
        structlog.processors.format_exc_info,  # 异常堆栈转成字符串（出错时）
        structlog.processors.StackInfoRenderer(),  # 附带调用栈信息
    ]


def setup_logging(log_file: str | Path = _LOG_FILE) -> str:
    """初始化双输出日志，绑定新会话的 trace_id，返回该 id。

    程序启动时调用一次即可；之后所有 get_logger 拿到的 logger 都走这套配置。
    """
    shared = _shared_processors()

    # 出口 1：控制台。ProcessorFormatter 是"出口转换器"——告诉它
    # foreign_pre_chain=shared（进来的日志先过 shared 这串工人），
    # 再交给 processors 里最后一个工人渲染成最终文本。
    console_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,  # 清掉加工痕迹
            structlog.dev.ConsoleRenderer(),  # colors=None：自动检测是否终端
        ],
    )
    # 出口 2：chat.log 文件。同一串工人，但最后渲染成 JSON 行（机器读）。
    file_formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            # ensure_ascii=False：JSON 里的中文不转成 \uXXXX，文件里直接可读。
            structlog.processors.JSONRenderer(ensure_ascii=False),
        ],
    )

    # logging.getLogger() 拿到 Python 标准库的根 logger；handlers = 出口列表。
    # root.handlers.clear() 先清掉默认出口，避免重复输出。
    root = logging.getLogger()
    root.handlers.clear()
    # StreamHandler(sys.stdout) = "写到控制台"的出口；setFormatter 给它配渲染格式。
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(console_formatter)
    # FileHandler = "追加写到文件"的出口；mode="a" = append（不清空旧日志）。
    file_handler = logging.FileHandler(log_file, mode="a", encoding="utf-8")
    file_handler.setFormatter(file_formatter)
    root.addHandler(console_handler)  # 把两个出口挂到根 logger 上
    root.addHandler(file_handler)
    root.setLevel(logging.INFO)  # 只放行 INFO 及以上（debug 太吵）

    # 静音底层 HTTP 库的 info 日志：LLM 调用信息由 chat.turn 等业务事件统一记录
    # （此环境 openai SDK 依赖的 fork 包 logger 名为 httpx2，一并覆盖）
    for noisy_logger in ("httpx", "httpx2", "openai", "httpcore"):
        logging.getLogger(noisy_logger).setLevel(logging.WARNING)

    # structlog.configure：告诉 structlog"全局按这套配置工作"。
    # processors = shared + wrap_for_formatter：先过 shared 加字段，
    # 再包一层"交给上面的出口转换器"。
    structlog.configure(
        processors=shared + [structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,  # 性能：同一 logger 只初始化一次
    )

    # uuid4() = 生成一个随机 UUID（全球几乎不会重复的 id）；.hex 取它的
    # 十六进制字符串；[:8] 只取前 8 位（够用且短，日志里不占地方）。
    trace_id = uuid.uuid4().hex[:8]
    # bind_contextvars：把 trace_id、step 绑进"线程级全局变量"，
    # 之后任何 logger 打日志都会自动带上这两个字段（见 docstring 原理层 4）。
    structlog.contextvars.bind_contextvars(trace_id=trace_id, step=0)
    return trace_id  # 把 trace_id 交还给调用方，需要时可记录/展示


def get_logger(component: str) -> structlog.stdlib.BoundLogger:
    """获取事件 logger；component 即字段 `component` 的值（如 "chat" / "tool"）。

    返回类型 BoundLogger = structlog 的"绑定式 logger"——你在它上面调
    logger.info(...) 时，component 会自动作为 logger 名进入事件字典。
    """
    return structlog.get_logger(component)