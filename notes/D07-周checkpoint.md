# D07 笔记：第 1 周 checkpoint（15 题自测 + v0.1 拼装）

> 固定格式：是什么 → 我的实现 → 面试官会追问什么 → 参考来源。
> 本文为 2026-09-21 补写的 checkpoint 记录，对应 2026-09-07 那一天的工作。
> D7 代码：`src/afg/__init__.py`（公共 API）、`src/afg/demo_hotswap.py`（热插拔演练）、`tests/test_log_replay.py`（日志回放测试）、`src/afg/agents/core.py`（加 `registry_names()`）。

---

## 一、15 题自测清单

**用法**：遮住笔记，口头回答，卡壳的当场在最后一列记一笔。题目和答案都在你自己写的笔记里，出处已标好——**不要看本表作答，本表只是记录表**。

| # | 题目 | 答案出处 | 卡壳？怎么补的 |
|---|---|---|---|
| 1 | Agent 定义与三特征 | `D01-agent定义.md · Q1` | |
| 2 | Agent vs Prompt Chain | `D01-agent定义.md · Q3` | |
| 3 | 四类上下文内容 | `D02-上下文预算.md · Q1` | |
| 4 | 上下文五类问题 | `D02-上下文预算.md · Q3` | |
| 5 | Lost in the Middle | `D02-上下文预算.md · Q4` | |
| 6 | 上下文工程四策略 | `D03-上下文压缩.md · Q1` | |
| 7 | 三段式压缩 | `D03-上下文压缩.md · Q4` | |
| 8 | 溢出五级降级 | `D03-上下文压缩.md · Q6` | |
| 9 | FC 四步流程 | `D04-function-calling.md · Q1` | |
| 10 | LLM 执行函数吗 | `D04-function-calling.md · Q2` | |
| 11 | Tool Schema 字段 | `D04-function-calling.md · Q3` | |
| 12 | 工具选择四策略 | `D05-工具注册与幻觉.md · Q1` | |
| 13 | 工具调用幻觉与防范 | `D05-工具注册与幻觉.md · Q4` | |
| 14 | ReAct 三字母与循环 | `D06-react-loop.md · Q1` | |
| 15 | 死循环怎么防 | `D06-react-loop.md · Q6` | |

**其中 5 题可以直接对照代码验证**——口答完翻一眼代码，答错会立刻露馅：

| # | 题目 | 代码在哪行 |
|---|---|---|
| 9 | FC 四步 | `agents/core.py:75` 发请求带 `tools=schemas` → `:105-117` 执行工具并回填 `role=tool` → `:134` 再要一轮 |
| 10 | LLM 执行函数吗 | **不执行**。真正的调用在 `agents/core.py:181` 的 `result = tool.run(**tool_call.arguments)` —— 在**我的进程**里，模型只给了函数名和参数 |
| 11 | Tool Schema 字段 | `tools/base.py:17-25` 的 `to_openai_schema()`：`type` / `function.name` / `function.description` / `function.parameters` |
| 13 | 工具幻觉防范 | `tools/registry.py:14-20` 查不到就抛 `UnknownToolError`；`tools/decorator.py:87-100` 校参数；`agents/core.py:182-186` 执行失败包成"工具执行失败：xxx"回填给模型自纠 |
| 15 | 死循环三防 | `agents/core.py:72` 的 `max_iterations` 上限；`:95-99` 连续相同动作计数；`:119-124` 熔断提示 + `:134` **不传 `tools`** 强制模型收尾 |

---

## 二、热插拔演练结论

**是什么**

v0.1 要证明的核心命题：**能力组合与核心循环正交**——换工具、加记忆，内核 `run()` 一行都不用改。

**我的实现（D7 里可见的证据）**

`demo_hotswap.py` 用**同一个 `AgentCore` 实例**跑了两次：`:28` 只注册 `calculator`，`:33` 整组换成三个内置工具，两次都问同一个问题 `12*34`。为了让演练能打印"这一轮装了哪几个工具"，给内核加了 `registry_names()`（`agents/core.py:196-197`，只读转发，不碰 `_registry`）。

**真实证据**（`chat.log`，同一个 `trace_id=2c4d247d`）：

```
agent.register  capability=ToolRegistry tools=['calculator']
hotswap.round   round=1 tools=['calculator']
hotswap.answer  round=1 answer='12 × 34 = **408**'
agent.register  capability=ToolRegistry tools=['calculator', 'get_current_time', 'get_weather']
hotswap.round   round=2 tools=['calculator', 'get_current_time', 'get_weather']
hotswap.answer  round=2 answer='12 × 34 = **408**'
```

两次 `agent.register` 之间**没有任何内核代码被执行修改**——只是把 `self._registry` 换了引用。

**这个结论为什么是后面 14 天的基础**：D8 加记忆时，`register()` 里只多了一个 `isinstance` 分支（`elif isinstance(capability, BaseMemory)`），`run()` 的循环体一行没动。D10 的 Skills、D11 的 MCP、D13 的沙盒（`sandbox/` 目录已经建好占位）都会走同一条路：**新能力 = 一个新的 `isinstance` 分支 + 一个新的协议实现**。这就是"插件化内核"四个字的实际含义。

**面试官会追问什么**

- 追问 1："`isinstance` 分发会不会越写越长？" 答：**会，而且这是已知的债**。能力类型到 5-6 种时，应该换成"注册表 + 能力声明的接口方法"（每个能力自己说 `provides()` 返回什么类型），`register()` 里只留一个循环。今天只有 2 种，`isinstance` 更直白，**过早抽象反而增加阅读成本**。
- 追问 2："`registry_names()` 为什么不直接暴露 `_registry`？" 答：**暴露内部对象等于把内核的私有状态交出去**。转发一个只读方法能保证"外面只能看名字，不能从外部改写注册表"。

**参考来源**

- `tests/test_log_replay.py`（日志回放测试：逐行 `json.loads` + 断言三类事件都在）
- 任务书 W1-tasks.md 的 D7 节

---

## 三、v0.1 仓库结构

```
src/afg/
├── llm/            BaseLLM 抽象 → DeepSeekClient（OpenAI 兼容）
├── context/        messages.py(消息模型) + counter.py(token 计数)
│                   + window.py(预算检查) + compressor.py(三段式压缩)
├── tools/          base.py(BaseTool 协议) + decorator.py(@tool 生成 schema)
│                   + registry.py(注册器) + builtin.py(三个内置工具)
├── agents/         core.py —— AgentCore：ReAct 主循环 + 双重熔断
├── observability/  logging.py(structlog 双输出) + retry.py(指数退避)
├── memory/         (D8 填)
├── skills/ mcp/ sandbox/   占位，D10-D13 填
├── chat.py         D1 多轮对话 CLI
├── cli.py          D6 ReAct CLI（/tools /trace /exit）
├── demo_fc.py demo_registry.py    D4/D5 演示
├── demo_hotswap.py                D7 热插拔演练
└── config.py       pydantic-settings（LLMConfig / ContextConfig / AgentConfig）
```

**本周 7 天的落点**（git log 可查）：

| 天 | 成果 |
|---|---|
| D1 | 消息模型 + BaseLLM + DeepSeek 客户端 + 多轮对话 CLI |
| D2 | tiktoken 计数 + ContextWindow 预算 + structlog JSON 日志 |
| D3 | 三段式压缩器 + 自动压缩接进 chat.py |
| D4 | Function Calling 四步闭环 + BaseTool + 三个内置工具 + 异常层次 |
| D5 | `@tool` 装饰器自动生成 schema + ToolRegistry + 参数校验 |
| D6 | ReAct 主循环 + 双重熔断 + `with_retry` + agent CLI |
| D7 | v0.1 公共 API + 热插拔演练 + 日志回放测试 |

**下周预告**：D8 记忆 → D9 RAG 检索工具 → D10 Skills → D11 MCP server → D12 MCP client → D13 沙盒与注入防御 → D14 v0.2 checkpoint。
