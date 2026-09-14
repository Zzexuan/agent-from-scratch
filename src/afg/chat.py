"""多轮对话 CLI：`python -m afg.chat`

D1 手搓核心体验 —— **上下文 = 你自己维护的 messages 列表**（append-only）。
D2 升级：每轮输出 token 统计（使用率 / 预算），≥75% 红色警告（只警告，D3 才接压缩）；
全部输出走 structlog（chat.turn / context.near_full / chat.reply 事件），禁止 print。

新手阅读顺序（这个文件是 D1+D2 的"总装车间"，把前面模块串起来）：
1. 先读 main() 开头：认识"上下文 = 一个列表"这个核心思想。
2. 再读 while 循环：看一轮对话怎么"追加消息 → 问模型 → 再追加"。
3. 最后读循环里的 token 统计段：D2 的仪表盘逻辑。
4. 记一个总纲：LLM 本身没记忆，你发给它的 messages 列表里有什么，
   它就"记得"什么——所谓上下文管理，就是管好这个列表。

为什么用 `python -m afg.chat` 运行而不是 `python afg/chat.py`：
-m 让 Python 按【包路径】导入模块，里面的 `from afg.xxx import ...`
（绝对导入）才能正确找到兄弟模块；直接跑文件会因找不到 afg 包报错。
"""

import time  # time.perf_counter() 精确测耗时（比 time.time 更准）

import structlog  # 结构化日志库：logger.info("事件名", 字段=值) 输出 JSON 行

from afg.config import ContextConfig, LLMConfig  # 从 .env / 环境变量读配置
from afg.context.counter import TokenCounter  # D2：数 token
from afg.context.messages import Message  # D1：一条消息
from afg.context.window import ContextWindow  # D2：预算窗口（RAM 配额）
from afg.llm.deepseek_client import DeepSeekClient  # D1：真正发请求给模型的客户端
from afg.observability.logging import get_logger, setup_logging  # D2：日志（见该文件注释）

# SYSTEM_PROMPT 是全大写命名：Python 约定"常量"用大写。它会被放进列表
# 第一条（role=system），告诉模型"你是谁、怎么说话"。
SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用简体中文回答。"


def main() -> None:
    """一轮"启动对话"的完整流程（下面按行讲）。"""
    # setup_logging() 一次性初始化双输出日志（控制台 + chat.log），
    # 并生成本次会话的 trace_id（8 位随机 id，用于串起同一会话的所有日志）。
    setup_logging()
    config = LLMConfig()  # 读 .env：api_key / base_url / model
    ctx_cfg = ContextConfig()  # 读上下文配置：窗口大小 / 安全系数 / 压缩阈值
    logger = get_logger("chat")  # 拿一个"名叫 chat 的日志器"，输出时自动带 component=chat
    llm = DeepSeekClient(config)  # 真正会调用模型的客户端（接口见 base.py）
    counter = TokenCounter()  # 会数 token 的工具（tiktoken 优先，见 counter.py）
    window = ContextWindow.from_model(ctx_cfg.context_window_tokens, ctx_cfg.safety_ratio)
    # from_model：预算 = 模型窗口 × 0.75。例：窗口 8192 → 预算 6144。
    # 为什么留 25%：要给模型"这轮要输出的内容"留地方（见 window.py 注释）。

    # ⭐ 核心思想：上下文 = 你自己维护的 messages 列表。
    # 列表 = 模型的"记忆"，我们只往里【追加】(append)，从不删除/修改历史
    # （append-only）。模型每次回答都基于当前列表的全部内容。
    messages: list[Message] = [Message(role="system", content=SYSTEM_PROMPT)]

    # logger.info 的第一个参数"chat.session_start"是【事件名】（机器可读，
    # 用于检索），后面跟的 = 键值对是事件附带的结构化字段（便于回放分析）。
    logger.info(
        "chat.session_start",
        model=config.model,
        base_url=config.base_url,
        budget=window.budget,
    )

    turn = 0  # 记录第几轮对话，会写进日志的 step 字段
    while True:  # 无限循环，靠下面 input 的异常 / exit 退出
        try:
            # input("你 > ")：在终端等用户输入一行。.strip() 去掉首尾空格。
            text = input("你 > ").strip()
        except (EOFError, KeyboardInterrupt):
            # 用户按 Ctrl+C（KeyboardInterrupt）或输入流结束（EOFError，
            # 比如管道关闭）时，优雅退出循环，而不是打印一堆堆栈。
            break
        if not text:  # 用户只按了回车 → 跳过这轮，重新等输入
            continue
        if text.lower() in {"exit", "quit"}:  # 输入 exit/quit 退出
            break

        turn += 1
        # bind_contextvars：把 step=turn 绑到"本次会话的上下文变量"上，
        # 之后这条链上所有日志都会自动带上 step 字段（见 logging.py 注释）。
        structlog.contextvars.bind_contextvars(step=turn)
        started = time.perf_counter()  # 记下这轮开始的时间（用于算延迟）

        # 【一问】把用户的话追加进上下文（这是"记忆"增长的地方）。
        messages.append(Message(role="user", content=text))
        # 把【整个】messages 列表发给模型。模型看到完整历史，所以能
        # 记住前面说过的话（D1 验收：第二轮能回答第一轮提到的名字）。
        resp = llm.chat(messages)
        # 【一答】把模型的回复也追加进上下文——如果不追加，下一轮模型
        # 就看不到自己刚说过什么（就像人失忆）。这行是闭环的关键。
        messages.append(Message(role="assistant", content=resp.content))

        latency_ms = (time.perf_counter() - started) * 1000  # 本轮耗时（毫秒）

        # ===== D2 仪表盘 =====
        # window.check()：数一遍当前 messages 的总 token，算"用了预算的
        # 百分之几"，返回一张 ContextReport 报告单（见 window.py）。
        report = window.check(messages, counter)
        usage_pct = round(report.usage_ratio * 100, 1)  # 0.1523 → 15.2
        logger.info(
            "chat.turn",  # 每轮一条结构化日志：tokens/预算/使用率/耗时
            turn=turn,
            tokens=report.total_tokens,
            budget=report.budget,
            usage_pct=usage_pct,
            latency_ms=round(latency_ms, 1),
        )
        if report.should_compress:
            # 使用率 ≥75%：只警告不压缩（D2 的边界）；D3 起这里改调 Compressor。
            # 为什么 75% 就警告而不是等满了：要给"这轮要发出去的问题 + 模型
            # 要输出的答案"预留空间，满了再处理往往已经溢出（详见 D02 笔记 Q2）。
            logger.warning("context.near_full", usage_pct=usage_pct, threshold=75.0)
        logger.info("chat.reply", content=resp.content)  # 把回复内容也落一条日志


if __name__ == "__main__":
    # 这行的作用：只有"直接运行本文件"时才执行 main()；
    # 当本文件被别的模块 import 时不会自动跑（防止副作用）。
    # 这也是 `python -m afg.chat` 的入口开关。
    main()