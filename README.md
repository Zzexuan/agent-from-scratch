# 🔩 AFG — Agent From Scratch

> 不依赖任何框架，**21 天从零手搓一个 Agent 内核**：消息模型 → 工具 → ReAct → 记忆 → Skills → MCP → 沙盒 → 多 Agent 编排。
> 八股驱动学习，每天手搓出真实可运行的代码，配套「是什么 → 我的实现 → 面试官追问」八股笔记。

![progress](https://img.shields.io/badge/进度-D10%2F21%20·%20W2%20进行中-2f6fdb)
![python](https://img.shields.io/badge/Python-3.11%2B-3776AB?logo=python&logoColor=white)
![framework](https://img.shields.io/badge/框架-零%20Agent%20框架%20(无%20LangChain)-ff6b35)
![llm](https://img.shields.io/badge/LLM-DeepSeek%20·%20OpenAI%20兼容-00b386)
![embed](https://img.shields.io/badge/embedding-本地%20bge--small--zh%20·%20torch%20CPU-9b59b6)
![tests](https://img.shields.io/badge/tests-pytest%20·%20FakeLLM%20零%20API-8a2be2)

---

## 🎯 这个项目是什么

面向 **AI 应用 / Agent 工程岗求职**的硬核学习项目：不调框架、不套模板，从第一行代码开始搭建自己的 Agent 内核。

每个知识点先看**面试官怎么问**（八股），再**手搓出来看见它真实运行**，最终沉淀为面试可直接讲的答案。

## ✅ 已完成（D1-D10）

- **D1 骨架**：`Message`/`ToolCall`/`TokenUsage` 消息模型 + `BaseLLM` 抽象 + DeepSeek 客户端 + 多轮对话 CLI
- **D2 上下文预算**：tiktoken 计数 + `ContextWindow` 预算检查 + structlog 双输出日志（`chat.log` 纯 JSON 行）
- **D3 上下文压缩**：`Compressor` 三段式（保留开头 + LLM 摘要 + 保留最近 N 条），用量 75% 触发
- **D4 Function Calling**：`BaseTool` 协议 + 三个内置工具 + 完整 FC 闭环
- **D5 装饰器与注册器**：`@tool` 从类型注解自动生成 JSON Schema + `ToolRegistry` + 幻觉防范
- **D6 ReAct 主循环**：`AgentCore.run()` 想-行动-观察循环 + 双重熔断 + 指数退避重试 + 终端 REPL
- **D7 checkpoint**：`afg` 公共 API（`from afg import AgentCore, tool`）+ 热插拔演练 + 日志回放测试
- **D8 记忆**：`BaseMemory` 协议 + `SQLiteMemory`（跨进程记住对话）+ 内核挂载点 `_remember` 增量写回
- **D9 RAG 检索**：本地 `bge-small-zh-v1.5` 编码 + 笔记分块/向量缓存/余弦 Top-K，封装成普通 `search_notes` 工具
- **D10 Skills**：`BaseSkill` + `SkillLoader`（frontmatter 解析）+ 渐进披露两跳（system 只注入 name/description 索引，`load_skill` 按需取全文）

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
│   ├── observability/  ✅ D2/D6  structlog JSON 日志 + 重试（span / 成本统计留到 W3）
│   ├── tools/          ✅ D4/D5/D9  BaseTool 协议 + @tool 装饰器 + ToolRegistry
│   │                            + search_notes（RAG 检索工具）
│   ├── agents/         ✅ D6   AgentCore 最小内核 / ReAct loop / 熔断
│   ├── memory/         ✅ D8   BaseMemory 协议 + SQLiteMemory（SummaryMemory 留到 D14）
│   ├── rag/            ✅ D9   本地 embedding + 分块 + 向量缓存 + 余弦检索
│   ├── skills/         ✅ D10  BaseSkill 协议 + SkillLoader（frontmatter 解析）+ load_skill 工具
│   ├── mcp/            ◻ D11/D12  手写 JSON-RPC 2.0 server(stdio) + client
│   ├── sandbox/        ◻ D13  执行护栏：超时 / 黑名单 / 注入防御
│   └── config.py       ✅ D1/D8/D9/D10  pydantic-settings（LLM / Context / Agent / Memory / Search / Skill）
├── models/             D9 本地模型（bge-small-zh-v1.5，92MB，不入库，见快速开始）
├── skills/             D10 技能手册（*.md，frontmatter 带 name/description）
├── tests/              ✅ D1-D10  13 个测试文件 + FakeLLM/FakeEmbedder 替身（零真实 API）
├── notes/              ✅ D1-D10  十篇八股笔记（D01-agent定义.md … D10-skills.md）
├── pyproject.toml      ✅ D1  ruff + pytest
└── .env.example        ✅ D1  DEEPSEEK_API_KEY 占位
```

## 🔌 热插拔内核（目标形态）

加记忆 / Skill / MCP 都只是 **实现协议 + 一行 register**，核心循环零修改：

```python
agent = AgentCore(llm=DeepSeekClient(config))
agent.register(memory)         # 任何 BaseMemory 实现（D8 已落地）
agent.register(skill_loader)   # 任何 SkillLoader（D10 已落地）
agent.register(mcp_client)     # 外部 MCP server 的工具（D11-D12 待做）
agent.run("...")               # 内核循环不改一行
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

# ReAct Agent CLI（D6：/tools 列工具、/trace 逐步显示、/exit 退出）
python -m afg.cli

# 热插拔演练（D7：同一个内核换两组工具，内核代码零修改）
python -m afg.demo_hotswap

# 记忆演练（D8：跨两次进程，第二次仍记得你的名字）
python -m afg.demo_memory "我叫小明"

# Skills 演练（D10：先注入技能索引，模型自己决定要不要加载手册）
python -m afg.demo_skills

# 运行单测（FakeLLM / FakeEmbedder 替身，零真实 API 调用、零模型加载）
pytest -q
```

**D9 的 RAG 检索需要先下本地 embedding 模型**（一次性，约 92MB，下到 `models/`）：

```bash
pip install torch --index-url https://download.pytorch.org/whl/cpu   # CPU 版足够，CUDA 版要多 3GB
pip install transformers

python -m afg.rag.download        # 下载 BAAI/bge-small-zh-v1.5 到 models/bge-small-zh-v1.5
python -m afg.demo_rag            # 问"我哪篇笔记讲过 function calling 的四步流程"
```

国内网络下载失败时改用镜像：`export HF_ENDPOINT=https://hf-mirror.com` 再跑一次下载命令。
`models/` 与 `search-index.json` 都在 `.gitignore` 里——**模型能重新下载、索引能从笔记重建**，都不入库。

## 📓 学习笔记（八股）

`notes/` 每日一篇，固定格式 **是什么 → 我的实现 → 面试官会追问什么 → 参考来源**：

| 文件 | 主题 |
|---|---|
| `notes/D01-agent定义.md` ✅ | AI Agent 定义与基本架构（Planner/Memory/Tools/Loop） |
| `notes/D02-上下文预算.md` ✅ | 上下文四要素、token 预算、Context Rot |
| `notes/D03-上下文压缩.md` ✅ | 四策略框架、三段式压缩、降级顺序 |
| `notes/D04-function-calling.md` ✅ | FC 四步流程、schema 设计、并行工具调用 |
| `notes/D05-工具注册与幻觉.md` ✅ | 工具选择策略、装饰器注册、幻觉防范 |
| `notes/D06-react-loop.md` ✅ | ReAct 三要素、死循环熔断、上下文流动 |
| `notes/D07-周checkpoint.md` ✅ | 第 1 周 15 题自测清单 + 热插拔演练结论 + v0.1 结构 |
| `notes/D08-记忆系统.md` ✅ | 记忆分层、Record/Retrieve 闭环、记忆与 RAG 的区别 |
| `notes/D09-rag.md` ✅ | RAG 两阶段、双塔与 CLS 池化、相似≠相关、Rerank、评估三层 |
| `notes/D10-skills.md` ✅ | Skill 是什么、Skills vs Few-shot vs MCP、渐进披露、Skills vs Subagents |

---

*21 天持续更新中 — 求职直给，代码说话。*