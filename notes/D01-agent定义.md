# D01 笔记：什么是 AI Agent？（草稿版）

> 固定格式：是什么 → 我的实现 → 面试官会追问什么 → 参考来源。
> 本文为 2026-08-31 联网调研+手搓代码后的草稿，建议按自己口吻再润色，并补"实际踩坑记录"。
> D1 代码：`src/afg/{context/messages.py, llm/base.py, llm/deepseek_client.py, chat.py}`

---

## Q1：一句话定义 AI Agent，它与普通 LLM 调用的本质区别？

**是什么**
Agent = 以 LLM 为推理核心，在多轮交互中**感知环境 - 规划 - 调用工具 - 观察结果并迭代**，直到目标达成的闭环系统。
本质区别三点：
1. **开环 vs 闭环**：普通 LLM 调用是"一问一答"的无状态函数；Agent 每步都依据 Observation 更新状态，直到完成。
2. **有工具/记忆/规划三特征**：LLM 只产文本，Agent 能调外部工具、跨会话记忆、拆解并规划目标。
3. **被动 vs 主动**：ChatBot 等你提问才回应；Agent 拿到目标后自己决定下一步、自己纠错重试。

**我的实现（D1 里可见的证据）**
`afg.chat` 里的 `messages` 列表就是"开环"被拉成"闭环"的最小骨架：
```python
messages.append(Message(role="user", content=text))
resp = llm.chat(messages)              # LLM 只是被调度的"推理引擎"
messages.append(Message(role="assistant", content=resp.content))  # 状态累积
```
真实验收：第 2 轮"我叫什么名字？"能回答"小明"——因为第 1 轮的 user+assistant 都被 append 进了 messages，Observation 回流到下一次推理。

**面试官会追问什么**
- 追问 1："那给 LLM 多塞点历史就算 Agent 吗？" 答：不是。历史回流只是前提；Agent 还要"自主决策+执行工具+按反馈迭代"，D1 只有决策没有执行，D4-D6 接入工具后闭环才完整。
- 追问 2："Agent 一定比普通 LLM 强吗？" 答：不强在单句生成，强在**杠杆**——20 步工具链里每一步都借用外部真实信息（引用来源：picassoia 观点）。

**参考来源**
- Anthropic《Building Effective Agents》: https://www.anthropic.com/research/building-effective-agents
- Blog Picasso《What Is an AI Agent and How It Differs》: https://blog.picassoia.com/what-is-an-ai-agent-and-how-is-it-different
- signals.tw《AI Agent 是什麼?和 chatbot、workflow 差在哪》: https://signals.tw/articles/what-is-ai-agent

---

## Q2：Agent 的基本架构由哪些核心组件构成？

**是什么**
主流一句话：**规划 Planner + 记忆 Memory + 工具 Tools + 执行循环 Loop**（有的答法加"感知/反思"）。
- 规划：把高目标拆成可执行子任务（ReAct 的 Thought、Plan-and-Execute 的 plan 阶段）。
- 记忆：短期=上下文窗口（当前对话+工具结果）；长期=跨会话持久化（向量库/DB）。
- 工具：让模型能"动手"——搜索、读文件、执行代码、调 API。
- 循环：Action→Observation→再决策，直到终止条件。

**我的实现**（对应 D1 已立的骨架，后续天正式填充）
| 组件 | 位置 | 状态 |
|---|---|---|
| LLM(推理核心) | `llm/base.py` + `deepseek_client.py` | ✅ D1 |
| 上下文(短期记忆载体) | `context/messages.py` | ✅ D1 |
| 工具 | `tools/` | 骨架占位，D4 填 |
| 循环(AgentCore) | `agents/` | 骨架占位，D6 填 |
| 长期记忆 | `memory/` | 骨架占位，D8 填 |
| 可观测 | `observability/` | 骨架占位，D2 填 |

**面试官会追问什么**
- 追问：这些组件怎么"装"进一个 Agent？ 答（呼应本项目热插拔架构）：都按协议实现 + `register()`，核心循环零修改。

**参考来源**
- Arize《What are AI agents?》: https://arize.com/blog/ai-agents/
- Alice Labs《4 Core Layers of Agent Architecture》: https://alicelabs.ai/en/insights/ai-agent-architecture-patterns

---

## Q3：Agent 和 Prompt Chain 的本质区别？

**是什么**
一句话：**Chain 的控制流写在代码里（开发者说了算），Agent 的控制流在模型决策+环境反馈里（模型说了算）。**
- Chain：工程侧固定拓扑——步骤、顺序、输入输出在编码时就确定，确定性、可调试、便宜。
- Agent：运行时在动作空间里做选择，依赖 Observation 更新信念——适合输入与路径都不确定的任务。
- 二者可结合：Chain 负责稳定流程，Agent 负责链内需要灵活分支的某一段。

**我的实现（D1 可讲的对照）**
D1 的 `chat.py` 是"人工版循环"：开发者亲手排 user→assistant 的顺序。D6 的 `AgentCore` 会把这一步的**顺序决定权交还给模型**（LLM 返回 tool_call 还是最终答案），到时候同一个 messages 列表，控制权转移——这就是 Chain→Agent 在代码上的分界。

**面试官会追问什么**
- 追问：Chain 比 Agent 便宜多少？ 答：Chain 调用次数固定；Agent 多轮+工具+重试，复杂任务常 3-10 倍 token（aipatternbook / agentmelt 观点）。所以工程原则是"能用 Chain 就不用 Agent"。

**参考来源**
- CSDN《搞懂 AI Agent：与 ChatBot、LLM Chain 的本质区别》: https://blog.csdn.net/qq_32146369/article/details/161744517
- aipatternbook《Prompt Chaining》: https://aipatternbook.com/prompt-chaining
- agentmelt《AI Agent vs Prompt Chain》: https://agentmelt.com/compare/ai-agent-vs-prompt-chain

---

## Q4：ChatBot 加上插件就是 Agent 了吗？RAG+Chat 算不算？

**是什么**
**不一定。**判断标准 = 是否具备**多步自主决策 + 反馈闭环**：
- 插件由固定规则触发（如关键词"天气"就调天气 API）→ 只是"带工具的 Bot"。
- 由模型在多步推理中**自主选择工具+参数**并闭环迭代 → 才是 Agent。
- RAG+Chat：单次检索→塞上下文→回答，是"增强型 Chat"；若有多轮检索策略（查不到换查询词/拆子问题/交叉验证）→ 具备 Agent 特征。
- 名称不重要，面试要讲清楚**控制流底层差异**。

**我的实现（D1 的教训式论据）**
D1 的 `Message` 模型已经有 `tool_calls`/`tool_call_id` 字段，但 chat.py 不带 `tools` 参数调用——所以现在它只是 ChatBot。D4 接入工具注册 + demo_fc 的"决策→执行→回填→再决策"后，模型才真正具备"自主选工具"能力。这个对照值得写进笔记：**"字段有位 ≠ 能力生效"**。

**面试官会追问什么**
- 追问：单次 RAG 检索算不算 tool？ 答：算一个检索工具，但用法是"一次性注入"而非"按需决策"，所以更接近增强检索，不是 Agentic RAG。

**参考来源**
- CSDN《Agent 面试必备 2—与 ChatBot、LLM Chain 的本质区别》: https://blog.csdn.net/qq_32146369/article/details/161744517
- Anil/orchestration 判断口径见 Anthropic《Building Effective Agents》workflow 节

---

## Q5：Workflow 和 Agent 怎么选？（Anthropic 送分题）

**是什么**
- **Workflow**：LLM+工具通过**预定义代码路径**编排——可预测、稳定、便宜、易调试，适合步骤已知且稳定的流程（数据管道、审批流）。
- **Agent**：LLM **动态指挥自己的流程与工具**——灵活、适合开放任务，但更贵、更慢、错误会累积。
- 一句话：workflow 是"告诉系统**怎么做**"，agent 是"告诉系统**做什么**"。
- **决策口诀**：能不能在餐巾纸上画出步骤？能→workflow；步骤不可预知且"完成"判据清晰→才考虑 agent。绝大多数应用只要把单次 LLM 调用 + 检索 + 示例做好就够了（Anthropic 原话：最成功的是简单可组合模式，不是复杂框架）。

**我的实现（工程判断的落点）**
本项目 21 天主线是"手搓 Agent"，但 D1 验收我只做了多轮对话（ChatBot 级）。这样安排的**工程理由是**：先用最简单可行的形态打地基，每引入一层复杂度（工具 D4、循环 D6、记忆 D8）都对应一个"当时确实需要它"的理由——这正是 Anthropic"先简单、按需增复杂"的实践。笔记里写清这个取舍，面试时就是加分项。

**面试官会追问什么**
- 追问：什么时候 workflow 可以嵌套 agent、agent 可以套 workflow？ 答：常见混合——workflow 某一步交给 agent 处理歧义子任务后回到固定路径；或 agent 作为编排者决定调用哪个 chain。两者不是非此即彼。

**参考来源**
- Anthropic《Building Effective Agents》原文: https://www.anthropic.com/research/building-effective-agents
- 中文拆解: https://geekinney.com/share/demo-anthropic-building-effective-agents-summary
- CSDN《读懂 Building Effective Agents》: https://blog.csdn.net/hust_wangyajun/article/details/163428695

---

## Q6：Agent 记忆一般怎么设计？（预习 D8）

**是什么**
分层设计（行业已从两层收敛到四层）：
1. **上下文窗口记忆**：当前对话直接进 prompt，最快但容量最小。
2. **工作记忆**：当前任务的 状态/目标/中间成果物——解决长任务"失忆"。
3. **会话记忆**：一次会话完整历史，靠滚动摘要控制长度。
4. **长期记忆**：跨会话持久化（向量库/知识图谱），按需检索召回。
- 写入注意区分**事实 vs 推断**、带时间戳与来源、可更新可撤销、控制写入量（不什么都记）。
- 一句话：记忆=给无状态的 LLM 补上**状态管理能力**，读写闭环=Retrieve(召回注入)→Reason→Record(写回)。

**我的实现（D1 的种子）**
D1 的 `messages` 列表 = "会话记忆"的原型，但它是**易失**的（进程退出即丢）。D8 会用 `BaseMemory` + `SQLiteMemory` 把它落盘成跨会话记忆；D9 再上向量检索。这正好印证学习文档里"D8 记忆 + D9 RAG = 热插拔"的分阶段设计。

**面试官会追问什么**
- 追问：长期记忆和 RAG 有什么区别？ 答（预习）：技术同构（都向量化+检索+注入），但 RAG 面向静态外部知识库，记忆面向用户/会话的动态历史（持续 Record/Retrieve、可更新遗忘）。详见 D8。

**参考来源**
- 字节面经《从两层到四层记忆架构》: https://blog.csdn.net/crazymakercircle/article/details/162000636
- CSDN《Agent 记忆系统（面试导向）》: https://blog.csdn.net/2403_87845034/article/details/162212315
- AI Master《Agent 的记忆系统如何设计?》: https://www.ai-master.cc/interview/agent-memory-001

---

## Q7：什么是工具调用幻觉？

**是什么**
LLM 在 tool calling 时**编造不存在的工具 / 传错参数 / 漏填必填 / 甚至绕过工具直接假装执行**。典型表现（按严重度）：
1. **工具选择幻觉**：调用不存在或语义不符的工具（工具多时显著恶化，>15 个工具命中率下降，实测注册 30 工具在复杂任务下幻觉率可达 12%）。
2. **参数幻觉**：伪造 schema 里没有的参数名/值，或漏必填。
3. **工具绕过**：不真调工具，自己编一个像样的"工具结果"塞进回答（对金融/系统最致命）。
工程防范（分层，非靠 prompt）：
- 工具名**白名单**校验，未知工具返回结构化错误让模型自行纠正（不要抛异常崩掉）。
- 参数 **schema 强校验**（本项目的 pydantic 派上用场）。
- 工具执行前门禁（权限/限流/HITL）、执行反馈（成功/失败结构化透传）。
- 观测+评测：记录调用理由/入参/出参，做成回归集。

**我的实现（D1 的埋点与断言位）**
- `Message` 校验器 `role=tool 必须带 tool_call_id` 就是"结构化约束防幻觉"的第一道（数据层）。
- `DeepSeekClient.chat()` 里解析 `arguments` 用 `json.loads`——一旦 fail，说明模型吐了非法 JSON，D4 会把它作为"参数错误"回给模型重试。
- D5 的 `ToolRegistry.get()` 会做**工具名白名单**（UnknownToolError 回给 LLM 而非崩溃）——今天先把坑注记在 `src/afg/llm/deepseek_client.py:31` 的注释里。

**面试官会追问什么**
- 追问：为什么纯靠 prompt"别乱调工具"没用？ 答：因为模型是采样生成，schema 对它只是"建议"不是"法律"；可靠防线必须放在**运行时**（白名单/校验/门禁），模型之外。
- 追问：工具幻觉和回答幻觉什么关系？ 答：回答幻觉=编事实；工具幻觉=编"动作"。后者更危险——它可能真的触发副作用（查完账告诉你退款成功了但根本没执行）。

**参考来源**
- CSDN《LLM Tool Call 工程避坑指南（7 失效模式）》: https://blog.csdn.net/cmzznet/article/details/161832689
- CSDN《后端转 Agent：Function Call 5 道送命题》: https://blog.csdn.net/huang9604/article/details/162944574
- TianPan《Phantom Tool Calls》: https://tianpan.co/blog/2026-04-14-phantom-tool-calls-when-ai-agents-invoke-tools-that-dont-exist
- 快手真题《FC 幻觉治理》: https://mianshidashi.cn/interview-questions/kuaishou/backend-development/kuaishou-backend-function-call-hallucination-mitigation

---

## Q8：为什么校招面试偏爱"你手搓过 Agent 吗"？

**是什么**
因为框架（LangChain 等）的 Runnable/AgentExecutor 抽象**掩盖了原理**：
- 框架用好=能跑 demo；只有手搓过才能回答追问题："tool 层怎么定义、运行时怎么被调用、上下文怎么流动、幻觉/死循环/溢出怎么防"。
- 90% 的 Agent 项目**死于工程化而非模型**（无日志、无护栏、无测试）——手搓出工程化能力是核心卖点。
- 这也是本项目"八股+手搓+工程化"三线并行的设计动机。

**我的实现（D1 的自我印证）**
今天从零写了 `messages.py`（消息模型）、`base.py`（ABC 抽象）、`deepseek_client.py`（SDK 封装）、`chat.py`（循环）。当被追问"tool 消息为什么必须带 tool_call_id"时，我能直接答出来并指出写法——这是"用过框架"给不了的深度。仓库里 `src/afg/__init__.py` 从空到 D7 逐步导出公共 API，就是"手搓工程化"的成长线。

**面试官会追问什么**
- 追问：你选 LangChain 会怎么想？ 答：本项目故意不碰框架（依赖白名单约束），目标是把机制自己搭一遍；真到生产会权衡——框架省事但掩盖底层，正如 Anthropic 提醒"若用框架必须理解其底层代码"。

**参考来源**
- 本项目主文档《核心接口规格》与《依赖白名单》（本地契约）
- Anthropic《Building Effective Agents》"When and how to use frameworks"节

---

## Q9：Agent、Chatbot、Workflow 三者适用场景？

**是什么**
| 形态 | 特征 | 适用 |
|---|---|---|
| Chatbot | 语言交互、被动响应 | 问答、闲聊、简单引导、写作/翻译/总结 |
| Workflow | 固定流程编排、确定性 | 数据管道、审批流、可预定义步骤的 ETL |
| Agent | 自主决策+持续行动 | 开放研究、多文件修 bug、动态客服工单 |
工程美德：**40% 场景只需要 ChatBot、30% 用 Workflow，仅约 20% 真需要 Agent**——选最简单够用的方案。工具导航类文章同样总结："写文案/翻译/总结，普通 chatbot 更快更省更可控；步骤清晰优先 workflow；目标清晰但路径不确定才上 agent。"

**我的实现（用本项目三类实体对照）**
- ChatBot 级 = D1 的 `afg.chat`（已跑通）。
- Workflow 级 = 未来 `Orchestrator`（D18）里固定编排的一部分。
- Agent 级 = `AgentCore`（D6）→ 热插拔 register 出三形态（纯对话/工具型/多 agent，D21 demo_assemble）。
D21 的"从零组装"演示恰恰是这道题的活答案：同一内核，register 组合不同 = 形态不同。

**面试官会追问什么**
- 追问：三类边界会重叠吗？ 答：会，是一条光谱（Arize 的 autonomy spectrum：single-call → RAG → workflow → agent → high-autonomy）。面试能画出这条谱并指出"三者是架构选择不是标签"，很加分。

**参考来源**
- toolnavs《What is an AI Agent? vs chatbots and workflows》: https://toolnavs.com/en/article/1288
- Arize《What are AI agents?（autonomy spectrum）》: https://arize.com/blog/ai-agents/
- signals.tw《AI Agent 是什麼?》: https://signals.tw/articles/what-is-ai-agent

---

## OOP 小结（D1 提示要求）：为什么 BaseLLM 用 ABC 而不是 duck typing / Protocol？

**是什么**
- **ABC + @abstractmethod**：强制"实现类必须声明继承关系并实现所有抽象方法"。忘实现会在（子类）实例化时直接报错——**契约错误在开发期暴露**。还能统一挂共享逻辑（参数校验/日志/重试）。
- **Protocol（structural typing）**：不要求继承关系，只要"长这样"就认——适合鸭子类型自由组合（如给任意对象加个 `.read()` 就视为文件对象）。
- **纯 duck typing**：只在运行时 `hasattr` / AttributeError——无契约，最后关头才炸。

**我的实现**
`src/afg/llm/base.py` 用 ABC：
```python
class BaseLLM(ABC):
    @abstractmethod
    def chat(self, messages: list[Message], tools=None, temperature=0.7) -> LLMResponse: ...
```
`DeepSeekClient(BaseLLM)` 和 `FakeLLM(BaseLLM)`（tests/fakes.py）都显式继承它。为什么选 ABC 而非 duck/Protocol：BaseLLM 是"实现方必须先声明身份"的抽象层次，且我要长期在基类上加重试/日志这类**横切逻辑**（D6 的 `with_retry` 就挂在调用点）——ABC 的继承层次更适合。
换一个角度：将来 `register()`（D6）按 isinstance 分发挂载能力时，靠 ABC 的类层次做"显式身份判断"更稳；Protocol 会给"碰巧像"的对象放行，埋隐患。

**追问与答法**
- 追问：那 Protocol 什么时候更合适？ 答：当一个协议"没有任何共享实现、只描述形状"时——例如 `Iterable`、自定义 `.iter_chunks()` 接口；没有代码复用诉求时用它比继承更轻。本项目既要统一 API 又要共享横切逻辑，ABC 更贴。

---

## 今日真实体验记录（附：跑真实验收）

- 用 `afg.chat` 输入"先记住：我叫小明，住在杭州" → 第二轮"我叫什么名字？"答"小明，杭州" ✅ 上下文自管生效。
- 本机模型走**本地网关** `http://127.0.0.1:15721/v1`（OpenAI 兼容通道，slug `gpt-5.6-luna`，上游 DeepSeek）。**注意**：网关的 OpenAI 通道和 Anthropic 通道模型名不同，日后换模型要注意。
- 坑：curl 直接发中文 JSON 被网关拒（解析错误）——用 Python/openai SDK 发 UTF-8 则正常；shell 里测试中文要留意编码。

## 参考资料完整清单

1. Anthropic《Building Effective Agents》: https://www.anthropic.com/research/building-effective-agents（原文+中文拆解若干）
2. 腾讯云/CSDN 大厂真题与送命题系列（工具幻觉、Chain/Agent 区别、记忆架构、FC 五送命题）
3. signals.tw / toolnavs / picassoia / arize / alicelabs 英文综述（agent vs chatbot vs workflow 对比）
4. 本项目规格来源：`W1-tasks.md` D1 节 + 主文档《核心接口规格》《执行协议》