# 🔩 AFG — Agent From Scratch

> 不依赖任何框架，**21 天从零手搓一个 Agent 内核**：消息模型 → 工具 → ReAct → 记忆 → Skills → MCP → 沙盒 → 多 Agent 编排。
> 八股驱动学习，每天手搓出真实可运行的代码，配套「是什么 → 我的实现 → 面试官追问」八股笔记。

![progress](https://img.shields.io/badge/进度-D1%2F21%20·%20骨架期-2f6fdb)
![python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![framework](https://img.shields.io/badge/框架-零依赖%20(无%20LangChain)-ff6b35)
![llm](https://img.shields.io/badge/LLM-DeepSeek%20·%20OpenAI%20兼容-00b386)
![tests](https://img.shields.io/badge/tests-pytest%20·%20FakeLLM%20零%20API-8a2be2)

---

## 🎯 这个项目是什么

面向 **AI 应用 / Agent 工程岗求职**的硬核学习项目：不调框架、不套模板，从第一行代码开始搭建自己的 Agent 内核。

每个知识点先看**面试官怎么问**（八股），再**手搓出来看见它真实运行**，最终沉淀为面试可直接讲的答案。

## ✅ 已完成

- **D1 骨架期**：消息模型（`Message`/`ToolCall`/`TokenUsage`）+ `BaseLLM` 抽象 + DeepSeek 客户端 + 多轮对话 CLI + FakeLLM 零 API 单测
- **D01 八股笔记**：AI Agent 定义 / 核心组件架构（Planner · Memory · Tools · Loop），含面试追问与参考来源

## 🗓️ 21 天路线图

| 周 | 天数 | 主题 | 产出 |
|---|---|---|---|
| **W1** | D1–D7 | 上下文 · Function Calling · ReAct | 消息模型、结构化日志、工具协议、AgentCore + ReAct 循环 |
| **W2** | D8–D14 | 记忆 · RAG · Skills · MCP · 沙盒 | SQLite/摘要记忆、MCP server/client、执行护栏 |
| **W3** | D15–D21 | Subagent · 通信 · 编排 · 可观测 · 评测 | 多 Agent 协作、trace 成本统计、21 天总 checkpoint |

## 🏗️ 仓库结构（D1 定型，插件化内核）

```
agent-from-scratch/
├── src/afg/
│   ├── llm/            ✅ D1  BaseLLM 抽象 → DeepSeekClient（OpenAI 兼容）
│   ├── context/        ✅ D1  消息模型（Pydantic，OpenAI 协议转换唯一入口）
│   ├── observability/  ◻ D2  structlog JSON 日志 + OTel 风格 span + 成本统计
│   ├── tools/          ◻ D4  BaseTool 协议 + @tool 注册器
│   ├── agents/         ◻ D5  AgentCore 最小内核 / ReAct loop
│   ├── memory/         ◻ D8  BaseMemory 协议 → SQLiteMemory / SummaryMemory
│   ├── skills/         ◻ D11 BaseSkill + 渐进披露加载器
│   ├── mcp/            ◻ D12 手写 JSON-RPC 2.0 server(stdio) + client
│   ├── sandbox/        ◻ D13 执行护栏：超时 / 黑名单 / 注入防御
│   └── config.py       ✅ D1  pydantic-settings（密钥不硬编码）
├── tests/              ✅ D1  消息模型单测 + FakeLLM 替身（零真实 API）
├── notes/              ✅ D1  21 篇八股笔记（D01-agent定义.md … D21-总checkpoint.md）
├── pyproject.toml      ✅ D1  ruff + pytest
└── .env.example        ✅ D1  DEEPSEEK_API_KEY 占位
```

## 🔌 热插拔内核（目标形态）

加记忆 / Skill / MCP 都只是 **实现协议 + 一行 register**，核心循环零修改：

```python
agent = AgentCore(llm=DeepSeekClient(config))
agent.register(memory)      # 任何 BaseMemory 实现
agent.register(skill_lib)   # 任何 BaseSkill 集
agent.register(mcp_client)  # 外部 MCP server 的工具
agent.run("...")            # 内核循环不改一行
```

## 📐 两条架构纪律

- **接口先行**：每个组件先写协议（ABC/Protocol）与类型注解，再写实现——契约错误提前到开发期。
- **显式状态**：任务进度用结构化对象跟踪，不依赖 LLM「记住」。LLM 是推理引擎，复杂逻辑交给代码，模糊判断才交给模型。

## 🚀 快速开始

```bash
# 安装（Python 3.11+）
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# 配置（复制 .env.example 并填入 DEEPSEEK_API_KEY）
cp .env.example .env

# 多轮对话 CLI（D1 手搓核心体验：上下文 = 自己维护的 messages 列表）
python -m afg.chat

# 运行单测（FakeLLM 替身，零真实 API 调用）
pytest -q
```

## 📓 学习笔记（八股）

`notes/` 每日一篇，固定格式 **是什么 → 我的实现 → 面试官会追问什么 → 参考来源**：

| 文件 | 主题 |
|---|---|
| `notes/D01-agent定义.md` ✅ | AI Agent 定义与基本架构（Planner/Memory/Tools/Loop） |
| `notes/D02-*.md` | 上下文管理（待完成） |
| … | 每日随代码同步更新 |

---

*21 天持续更新中 — 求职直给，代码说话。*