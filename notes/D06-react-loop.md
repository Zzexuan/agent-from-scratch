# D06 笔记：ReAct 循环与死循环熔断（草稿版）

> 固定格式：是什么 → 我的实现 → 面试官会追问什么 → 参考来源。
> 本文为 2026-09-06 手搓代码后的草稿，建议按自己口吻再润色。
> D6 代码：`src/afg/agents/core.py`（新建，今天的主角）、`src/afg/observability/retry.py`（新建）、`src/afg/cli.py`（新建）、`src/afg/config.py`（改）、`test_agent_loop.py` / `test_retry.py`（新建）

---

## Q1：ReAct 三个字母代表什么？解决什么问题？

**是什么**

**Rea**soning + **Act**ing，Yao et al. 2022 提出。它解决的是**两种极端都不够用**的问题：

| 只有推理（CoT） | 只有行动（Act） |
|---|---|
| 只"想"不做，闭门造车，容易幻觉 | 盲目试错，没有规划，浪费步数 |
| 数学题够用 | 简单查询够用 |
| **遇到需要外部信息就编** | **遇到需要多步推理就乱撞** |

ReAct 让两者**交替进行、互相校正**：**推理引导行动**（想清楚再调工具），**行动验证推理**（工具结果打脸了错误假设）。

**我的实现（D6 里可见的证据）**

`agents/core.py:69-113` 的主循环就是这个"交替"：

```python
        for iteration in range(1, limit + 1):
            ...
            resp = self._llm.chat(messages, tools=schemas)     # ← 模型推理（Thought）
            ...
            if not resp.tool_calls:                            # ← 不需要行动 → 结束
                return thought
            ...
            for tool_call in resp.tool_calls:                  # ← 行动（Action）
                observation = self._execute(tool_call)         # ← 观察（Observation）
                messages.append(Message(role="tool", content=observation, ...))
```

**循环一圈 = 想一次 → 做一次 → 看结果 → 再想。** 这个 while/for 循环就是 ReAct 的全部。

**面试官会追问什么**

- 追问 1："CoT 会幻觉，ReAct 就不会吗？" 答：**会，但幻觉会被工具结果打脸**。比如模型推理"北京今天很冷"，一查天气 31℃——它下一轮就得改口。**CoT 没有这个纠错机会**，因为它没有外部输入。所以 ReAct 不是消除幻觉，是**给幻觉一个被纠正的机会**。
- 追问 2："ReAct 一定要用工具吗？" 答：论文里的 Action 也可以是"查维基百科"这类外部检索。**在我们项目里 Action 就是工具调用**（`agents/core.py:101`），因为工具是唯一的外部接口。

**参考来源**
- Yao et al. 2022《ReAct: Synergizing Reasoning and Acting in Language Models》: https://arxiv.org/abs/2210.03629
- 知乎《为什么说 ReAct 才是现代 Agent 的底层逻辑》

---

## Q2：Thought / Action / Observation 分别是什么？

**是什么**

| 环节 | 是什么 | 在我们项目里对应的东西 |
|---|---|---|
| **Thought** | 模型的内部独白：分析现状、决定下一步、说明为什么 | assistant 消息的 `content` 字段 |
| **Action** | 结构化的工具调用（工具名 + 参数） | assistant 消息的 `tool_calls` 字段 |
| **Observation** | 工具结果**回注上下文** | `role="tool"` 的消息 |

循环直到模型**认为可以给出最终答案**（不再产生 tool_calls）。

**我的实现（D6 里可见的证据）**

三个环节在代码里是**同一轮 LLM 响应的三个字段**：

`agents/core.py:72-78`
```python
            resp = self._llm.chat(messages, tools=schemas)
            thought = resp.content                              # ← Thought
            ...
            messages.append(
                Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
            )
```
`agents/core.py:101-113`
```python
            for tool_call in resp.tool_calls:                   # ← Action
                observation = self._execute(tool_call)
                ...
                messages.append(
                    Message(role="tool", content=observation, tool_call_id=tool_call.id)
                )                                               # ← Observation
```

**`/trace` 就是把这三位打出来**（`agents/core.py:79-82 / 96-99 / 103-110`，由 `verbose` 开关控制）。真实输出：

```
agent.trace  iteration=1  kind=action       content='calculator({"expr": "12*34"}) + get_weather({"city": "北京"})'
agent.trace  iteration=1  kind=observation  tool=calculator  content=408
agent.trace  iteration=1  kind=observation  tool=get_weather  content='北京：晴，气温 24 摄氏度，湿度 40%'
agent.trace  iteration=2  kind=thought      content='结果如下：\n\n1. **12 × 34 = 408**\n2. **北京天气**：晴...'
```

**注意 kind=thought 那一轮内容是空的**——因为模型这一轮"没说话，直接动手"。这也是正常形态。

**面试官会追问什么**

- 追问 1："Thought 是模型显式写出来的，还是你猜的？" 答：**是模型写出来的**，但**不是它自己标注的**。OpenAI 协议里 assistant 消息可以同时有 `content`（文本）和 `tool_calls`（结构化调用）——我们把前者当 Thought、后者当 Action。**模型并没有被要求"先说想什么再动手"，它这么做是因为训练时见过这种模式。**
- 追问 2："如果模型 Thought 写错了但 Action 执行成功了，算成功吗？" 答：**不算**。这是 ReAct 的一个真实局限（见 Q5）：工具成功 ≠ 任务成功。比如它想算 `12*34` 却传了 `12+34`，工具返回 46 也是"成功"的。**所以最终得看它给出的答案对不对**，这也是 D20 评测日要做 trajectory 级评测的原因。

**参考来源**
- Yao et al. 2022（T/A/O 定义）
- 博客园《深入理解 Agent Loop》

---

## Q3：CoT / ReAct / Plan-and-Execute / Reflection 核心区别与选型？

**是什么**

| 范式 | 一句话 | 适合 | 代价 |
|---|---|---|---|
| **CoT**（思维链） | 纯内部推理，不接触外界 | 数学、逻辑、写作 | 无法获取实时信息，会幻觉 |
| **ReAct** | 边想边做，每步依赖反馈 | **实时信息 + 工具任务（工业默认）** | 上下文被 Observation 吃满 |
| **Plan-and-Execute** | 先全局规划，再逐步执行 | 长任务、步骤多的 | 需要规划器 + 执行器两个组件；计划错了全错 |
| **Reflection** | 执行后自我批判再改进 | 提质量（写作、代码） | 每次反思多一轮 LLM 调用 |

**怎么选**：**路径需要动态判断 → ReAct；路径能预先定死 → workflow**（见 Q7）；**任务长且步骤可预测 → Plan-and-Execute**；**对质量要求高于成本 → 加 Reflection**。

**我的实现（D6 里可见的证据）**

D6 实现的是**纯 ReAct**，没有 Plan 也没有 Reflection。这一点在代码里看得很清楚：

`agents/core.py:69` 的循环体里**只有"想-做-看"**，没有"先规划"的步骤：
```python
        for iteration in range(1, limit + 1):
```

**REPEAT_PROMPT 那套熔断机制其实算一个微型 Reflection**（`agents/core.py:115-126`）：发现"我在重复同一个动作"→ 注入提示让模型反思 → 强制总结退出。但它是**异常路径的补救**，不是正常流程。

**真实运行的一个反例（说明为什么不该盲目上 Plan）**：我给的 demo 任务是 `"先算 12*34，再查北京天气，最后告诉我现在几点"`——**任务书预期是"3 步串行"**，但模型实际在**一轮里并行发了 3 个工具调用**：

```
agent.trace  kind=action  content='calculator({"expr": "12*34"}) + get_weather({"city": "北京"}) + get_current_time({})'
```

**两轮就结束了**（不是 3 轮）。**这说明"先规划再执行"在这里反而是多余的**——模型一眼就看出这三件事互不依赖，直接一起做了。**Plan-and-Execute 的价值在"步骤多到模型自己理不清"时才体现。**

**面试官会追问什么**

- 追问 1："ReAct 和 Plan-and-Execute 能混用吗？" 答：能，而且是常见做法——**先让模型出一个 plan（Plan 阶段），再让每个 plan 步骤用 ReAct 执行（Execute 阶段）**。这样既有全局视野、又有局部灵活性。我们的 D18 orchestrator 就是这个思路。
- 追问 2："Reflection 什么时候值得加？" 答：**看错误代价**。写代码、写文案这类"错了很贵的"值得加；查天气、算数这类"错了立刻能看出来"的不值得——**因为工具结果本身就是反馈，不需要额外的自我批判**。

**参考来源**
- CSDN《Agent 推理范式 ReAct 与 CoT》
- 知乎《2026 Agent 大厂面试题汇总》

---

## Q4：为什么工业界默认 ReAct？

**是什么**

四个理由，每个都对应一个工程诉求：

| 理由 | 含义 |
|---|---|
| **可控** | 每步都可审查、可校验、可回滚（不像 CoT 是一整段不可分的推理） |
| **可复现** | 完整的决策链留日志（T/A/O 一条条都在），出事能查 |
| **错误可恢复** | 失败变成一条 Observation 回注，模型改策略重试 |
| **可扩展** | 多工具随便组合，不需要改循环 |

**多 Agent 本质 = 多个 ReAct Agent 互传 T/A/O。**

**我的实现（D6 里可见的证据）**

四条在我的代码里逐条能对上：

**① 可控**：每一步的 Action 都先被 `_describe()` 转成字符串（`agents/core.py:90`），**在代码层面可比较、可记录**——熔断就是靠这个字符串比较实现的。
```python
            action = self._describe(resp.tool_calls)
            if action == last_action:              # ← 行动是"可比较的对象"，不是一段自由文本
```

**② 可复现**：每次 LLM 调用、每个工具执行都打日志（`agent.turn` / `agent.trace` / `agent.observation`）。**真实运行的两轮全在日志里，一步不落。**

**③ 错误可恢复**（这条最直观）：`agents/core.py:172-183` 的 `_execute` 捕获 `AfgError` 转成一句人话回填：
```python
        except AfgError as e:
            result = "工具执行失败：" + str(e)
```
**模型看到错误会自己改**——D5 已经验证过（它如实说"我没有这个工具"并列出真实能力）。

**④ 可扩展**：`register()`（`agents/core.py:35-48`）按类型挂载能力，**换一套工具组不需要改循环一行**。这是 D7 热插拔演练要验证的。

**面试官会追问什么**

- 追问 1："可控和可复现听起来是一回事？" 答：不一样。**可控是"我能干预"**（比如熔断、比如人工审核中间步骤）；**可复现是"事后能查"**（日志里有完整链条）。前者是运行时的能力，后者是事后的证据。
- 追问 2："ReAct 一定比 CoT 好吗？" 答：**数学题上 CoT 就够了甚至更好**（ReAct 多调工具反而增加出错面）。**选型看"需不需要外部信息"**——需要就 ReAct，不需要就 CoT。

**参考来源**
- Anthropic《Building Effective Agents》
- 博客园《深入理解 Agent Loop》

---

## Q5：ReAct 的局限？

**是什么**

四条：

1. **上下文配额被 Observation 吃满** —— 工具结果最占 token，多轮下来窗口爆炸（需要压缩/外部记忆）
2. **工具多则选择准确率降** —— 超过 20 个工具明显恶化（D5 的 Q1/Q2）
3. **Thought 推理错则调用全错** —— **工具成功 ≠ 任务成功**
4. **并行调用需额外改造** —— 执行层要从"逐个执行"改成并发

**我的实现（D6 里可见的证据）**

**① 上下文**：我接上了 D3 的压缩器。真实数据——两轮下来 49 → 163 token（这个 demo 很短，看不出来）。**但注意 `_check_context` 是每轮调用前都跑的**（`agents/core.py:70`），所以长任务里它会自己压。

**② 工具数量**：现在 3 个（`agent.register` 日志里能看到 `tools=['calculator', 'get_current_time', 'get_weather']`）。W2 加 skills、W3 加 MCP 之后会上去，那时要改 `to_openai_schemas` 做筛选。

**③ 工具成功≠任务成功**：这个我现在**没有防护**——`_execute` 只看"工具有没有抛异常"，不看"结果对不对"。**真实的例子**：让模型算 `12*34`，它如果传成 `12+34`，calculator 会老老实实返回 46，日志里一切正常，只有最终答案错了。**这是我知道的一个缺口**，D20 评测日要处理。

**④ 并行调用**：**意外发现——我的实现天然支持了**。因为 `agents/core.py:101` 是 `for tool_call in resp.tool_calls:`，而模型的响应里**本来就可以有多个 tool_call**。真实运行证明了这一点：

```
agent.trace  kind=action  content='calculator(...) + get_weather(...) + get_current_time(...)'
```

一轮发了 3 个，全部执行、全部回填，**代码零改动**。这是 D1 设计 `ToolCall.id` + D4 的 `for` 循环一起带来的红利。

**面试官会追问什么**

- 追问 1："你说并行天然支持，那真并发了吗？" 答：**没有，是顺序执行的**。3 个工具在 `for` 循环里一个接一个跑。因为这三个工具都是**本地微秒级**的（日志里 `latency_ms=0.0~0.4`），顺序跑和并发跑没区别。**真正需要并发是"工具是网络调用"的场景**——那是 D16 用线程池要做的。
- 追问 2："怎么防'工具成功但任务失败'？" 答：三个层次——**① 参数校验**（D5 的 `check_arguments`，挡掉格式错）；**② 结果合理性检查**（比如 calculator 的结果和参数类型对不对得上，这个我还没做）；**③ 最终答案评测**（D20 的 outcome eval）。**越往后越贵，所以能挡在前面就挡在前面。**

**参考来源**
- 腾讯云《160+ 真题》
- 主文档 D16（并发）、D20（评测）规格

---

## Q6：Agent 死循环怎么防？（高频工程题）

**是什么**

**三件套**，缺一不可：

| 防线 | 检测什么 | 触发后 |
|---|---|---|
| **max_iterations 硬上限** | 步数 | 强制总结退出 |
| **相同动作检测** | 连续 N 次同样的 `(tool, 参数)` | 强制总结退出 |
| **无进展检测** | 连续失败 / 结果没变化 | 强制总结退出 |

**关键**：**熔断后不是报错崩溃，而是"强制 LLM 带着已有信息总结退出"。** 用户拿到的是"完成度打折扣的答案"，而不是一个异常。

**我的实现（D6 里可见的证据）**

**两道防线都实现了**（第三道"无进展检测"没做，见追问）：

**第一道：max_iterations**　`agents/core.py:54-56` 读配置、`agents/core.py:69` 的 `range(1, limit + 1)` 封顶。

**第二道：相同动作检测**　`agents/core.py:90-95`
```python
            action = self._describe(resp.tool_calls)
            if action == last_action:
                repeat_count = repeat_count + 1
            else:
                repeat_count = 1
                last_action = action
```
`_describe`（`agents/core.py:165-170`）把 tool_calls 转成**可比较的字符串**：
```python
            arguments = json.dumps(tool_call.arguments, sort_keys=True, ensure_ascii=False)
            parts.append(tool_call.name + "(" + arguments + ")")
```
**`sort_keys=True` 很关键**：参数字典的键顺序不该影响判断——`{"a":1,"b":2}` 和 `{"b":2,"a":1}` 是同一个动作。

触发点　`agents/core.py:115-120`：
```python
            if repeat_count >= self._config.same_action_limit:
                stop_reason = (
                    f"你已经连续 {repeat_count} 次执行了完全相同的动作，"
                    "请不要再调用工具，直接基于已经获得的观察回答用户。"
                )
                break
```

**统一收尾**　`agents/core.py:122-135`（两条防线汇合到同一段）：
```python
        if not stop_reason:
            stop_reason = (
                f"你已经用完了全部 {limit} 步，"
                "请不要再调用工具，直接基于已经获得的观察回答用户。"
            )

        self._logger.warning("agent.circuit_break", reason=stop_reason)
        messages.append(Message(role="user", content=stop_reason))
        final = self._llm.chat(messages)          # ← 关键：这一轮【不传 tools】
        ...
        return answer
```

**收尾那一轮不传 tools**——这是设计要点：**拿掉工具，模型就只能用嘴回答**。如果还传工具，它可能又去调了。

**真实运行证据**（故意把 max_iterations 设成 1）：
```
agent.start         max_iterations=1
agent.turn          iteration=1  tokens=49
tool.call           name=calculator ...  name=get_weather ...  name=get_current_time ...
agent.circuit_break reason='你已经用完了全部 1 步，请不要再调用工具，直接基于已经获得的观察回答用户。'
agent.done          answer='结果如下：\n\n1. **12 × 34 = 408**\n2. **北京天气**：晴，气温 24 摄氏度，湿度 40%\n3. **现在时间**：2026-09-15 20:16:16（晚上 8 点 16 分）'
```

**步数用完了，但答案完整**——模型基于已经拿到的 3 个观察值组织出了最终回答。**这就是"熔断不是崩溃"的活证明。**

**面试官会追问什么**

- 追问 1："为什么用标志变量 + break，不用 for...else？" 答：`for...else` 也能实现（else 在循环没被 break 时执行），但**它反直觉**——绝大多数人不知道 else 是配 for 的。用 `stop_reason` 标志变量虽然多两行，但**任何人一眼看懂**。**可读性优先于语法技巧。**
- 追问 2："'无进展检测'你做了吗？" 答：**没做，而且我知道为什么先不做**。它要判断"结果有没有变化"——需要把上一次的 Observation 和这一次比对。**在只有 3 个无状态工具的现在是多余的**（三件套里的另两道已经够）。等 D13 有了 `exec_command` 这种"同一个命令可能成功也可能失败"的工具，才需要它。
- 追问 3："熔断阈值为什么是 3？" 答：**经验值 + 可配置**（`AgentConfig.same_action_limit`）。设太小会误杀（模型正常的重试也被挡）；设太大就失去意义。**3 是"试了两次还不换个思路就说明卡住了"的合理界限。**

**参考来源**
- 腾讯云《160+ 真题》死循环题
- 博客园《深入理解 Agent Loop》

---

## Q7：agent loop 和 workflow 怎么选？

**是什么**

一句话：**"你告诉系统怎么做" vs "你告诉它做什么"。**

| | workflow | agent loop |
|---|---|---|
| 路径 | **预先定义**（步骤、分支都写死在代码里） | **运行时决定** |
| 可预测性 | 高 | 低 |
| 灵活度 | 低（遇到没预设的情况就卡住） | 高 |
| 调试 | 容易 | 难 |

**选型标准**：**路径可预定义 → workflow；需要动态判断-行动-观察 → loop。**

**我的实现（D6 里可见的证据）**

**项目里两种都有，正好可以对照**：

- **workflow 形态**：`demo_fc.py`（D4）—— 步骤写死：问一次 → 如果有工具调用就执行 → 再问一次。**最多两轮，不会更多。** 它不知道"如果模型还要调工具怎么办"。
- **loop 形态**：`agents/core.py`（D6）—— 轮数由模型决定，代码只设上限。**同一份代码能跑 1 轮也能跑 10 轮。**

**真实运行里这个差别很明显**：同样的任务，`demo_fc` 需要**模型正好在第二轮给出答案**才行（否则它就漏了）；而 `AgentCore` 会**一直循环到模型不再调工具为止**。

**面试官会追问什么**

- 追问 1："那是不是都该用 agent loop？" 答：**不是**。workflow 有三个 loop 给不了的好处：**① 便宜**（固定轮数）；**② 快**（不用每轮重新决策）；**③ 稳**（不会绕路）。**Anthropic 那篇《Building Effective Agents》的核心观点就是"能用 workflow 就别上 agent"**——因为 agent 的不确定性是真实成本。
- 追问 2："怎么判断该用哪个？" 答：问自己"**如果用户换一种问法，步骤还一样吗**"。一样 → workflow（比如"翻译这段文本"）；不一样 → loop（比如"帮我把这个项目改好"）。

**参考来源**
- Anthropic《Building Effective Agents》（这是原文的核心论点）
- 知乎《为什么说 ReAct 才是现代 Agent 的底层逻辑》

---

## Q8：ReAct 论文的实验结论？

**是什么**

论文在 **HotpotQA**（多跳问答）和 **FEVER**（事实验证）两个任务上对比了三种方法：

| 方法 | 结果 |
|---|---|
| 纯 CoT | 会幻觉出事实上不存在的中间步骤 |
| 纯 Act | 没有推理引导，容易乱调 |
| **ReAct** | **显著优于前两者** |

**结论的关键**：**推理和行动互为上下文**——推理决定了下一步该查什么，查回来的结果又修正下一步的推理。

**多跳问答是最好的例证**：HotpotQA 的问题需要"先查 A，再用 A 的答案去查 B"。**纯 CoT 会把 A 的答案编出来**（因为它没法查），**ReAct 会真的去查 A，然后拿真实结果去查 B**。

**我的实现（D6 里可见的证据）**

**我们的 demo 任务其实就是个迷你版的多跳**——`"先算 12*34，再查北京天气，最后告诉我现在几点"`。

虽然这次模型**一轮并行做完了**（3 个调用无依赖），但代码结构支持真正的多跳：**下一轮的 `messages` 里带着上一轮的 Observation**（`agents/core.py:111-113`），所以模型能看到真实结果再决定下一步。

**如果要构造一个真正的多跳场景**，可以是："**北京现在几度？如果超过 30 度就帮我算 12*34，否则算 12+34**"——**第二步依赖第一步的真实结果**，纯 CoT 只能瞎猜，ReAct 必须真查。这正是论文要解决的问题。

**面试官会追问什么**

- 追问 1："你的项目里能验证论文结论吗？" 答：**能，但要构造依赖链的任务**。我现在的 demo 是无依赖的（所以并行做完了），看不出 ReAct 的优势。**要验证得用"链式依赖"的任务**——这也是我下一步想补的实验。
- 追问 2："ReAct 在多跳上比 CoT 好，那单跳呢？" 答：**单跳 CoT 可能就够了**。比如"北京天气"——如果模型知道（训练数据里有），它直接答比调工具快。**ReAct 的优势在"模型不可能知道的信息"上**（实时数据、私有数据）。

**参考来源**
- Yao et al. 2022《ReAct》（HotpotQA 与 FEVER 实验结果）
- 知乎《为什么说 ReAct 才是现代 Agent 的底层逻辑》

---

## Q9：什么信息留在上下文里会"越跑越偏"？

**是什么**

**早期的错误推理和失败尝试**——如果原样留着、不加标注，会持续误导模型。

**工程做法**（两种）：
1. **保留错误但显式标注**："尝试 X 失败，原因 Y"
2. **压缩时总结成教训**（D3 的压缩器 prompt 里就有"保留犯过的错误"这一条）

**反模式**：把"错误的上下文"清掉。看起来是"清理"，实际上**让 Agent 把已经踩过的坑再踩一遍**——因为它失去了"这条路走不通"的记忆。

**我的实现（D6 里可见的证据）**

**D3 的压缩器就已经处理了这一点**——`context/compressor.py:3-8` 的压缩指令里明确要求：
```
"1. 保留：任务目标、关键决策、重要发现、还没解决的问题、犯过的错误。"
```
**"犯过的错误"是刻意写进去的**（D3 笔记 Q8 讲过）。

**D6 把这套压缩接进了循环**（`agents/core.py:137-163` 的 `_check_context`），所以**长任务里这个保护自动生效**。

**而"显式标注"这件事，D6 已经在做了**——`_execute` 的错误回填格式是：
```python
            result = "工具执行失败：" + str(e)
```
**"工具执行失败："这个前缀就是标注**。模型下一轮看到这条 Observation，知道"这次尝试失败了"，而不是把它当成正常结果。

**真实证据**（D6 的单元测试钉死的）：
```
seen[3].content = "工具执行失败：没有这个工具"
```
如果只回填 `"没有这个工具"`（不带前缀），模型可能理解成"这个工具查不到数据"——**前缀把语义定死了**。

**面试官会追问什么**

- 追问 1："那失败信息要留多久？" 答：**留到压缩的那一刻**，压缩时按"保留错误"的规则总结成教训留下。**永久保留原始错误没有意义**（占 token 且细节无用），但"教训"要留。
- 追问 2："为什么错误信息不直接丢掉、让模型重新试？" 答：**因为会重试同样的错**。这正是熔断要解决的问题的另一面——**不记录失败 = 每次都在同一个坑里打转**。所以"保留错误"和"相同动作检测"是一对：前者给模型信息，后者兜底它没学会。

**参考来源**
- 主文档 D3 压缩器规格
- Anthropic《Effective context engineering for AI agents》

---

## Q10：max_iterations 设多少合适？怎么权衡？

**是什么**

**任务复杂度决定**：

| 任务类型 | 建议步数 |
|---|---|
| 简单查询 | 3-5 |
| 一般工具链 | 5-10 |
| 调研类 | 10-20 |

**要配合 token 预算做双保险**——**步数 + 成本两条红线**。

**核心原则**：**宁可早熔断给用户中间结果，不可无限烧钱。**

**我的实现（D6 里可见的证据）**

**默认 10**（`config.py` 的 `AgentConfig.max_iterations`），**可配**：
- 环境变量：`MAX_ITERATIONS=1`（我验收时就是这么触发的熔断）
- 代码里：`agent.run(task, max_iterations=3)`

**双保险已经实现了**——`agents/core.py:70` 每轮开头都过一遍 `_check_context`：
```python
            messages = self._check_context(messages, iteration)
```
它同时做两件事：**打用量日志**（`agent.turn`，含 tokens / budget / usage_pct）+ **超阈值就压缩**。所以"步数红线"和"成本红线"在同一处生效。

**真实数据**（D6 验收的两轮）：
```
agent.turn  iteration=1  tokens=49   usage_pct=0.8
agent.turn  iteration=2  tokens=163  usage_pct=2.7
```
这个 demo 太短，用不到压缩。但**长任务里 `context.compress` 会在同一个位置出现**——D3 已经验证过它的行为（30 轮实验里第 22 轮触发，压缩率 0.349）。

**面试官会追问什么**

- 追问 1："设 10 会不会太保守？" 答：**看场景**。我的 demo 两轮就完了，10 绰绰有余。**真正的调研任务可能要 20+**——那就调配置。关键是**它必须可配**，而不是写死在代码里（这也是 `config.py` 存在的意义）。
- 追问 2："步数用完了就熔断，会不会过早？" 答：**这正是"宁可早熔断"的取舍**。真实运行证明了熔断的代价很小——`max_iterations=1` 时模型仍然给出了**完整答案**（因为前面已经拿到了 3 个观察值）。**用户拿到 90% 的答案，比等 10 分钟拿到 100% 好。**
- 追问 3："为什么不用 token 预算单独作为红线？" 答：**也用了**（`_check_context` 里的压缩），但**两者管的不是一回事**：token 红线管"上下文撑不撑得住"，步数红线管"任务是不是绕住了"。**一个任务可能每步都很短（token 没超）但无限绕圈**——那只能靠步数拦。

**参考来源**
- 腾讯云《160+ 真题》max_iterations 题
- 主文档 D6 规格

---

## Q11：一轮 ReAct 循环里上下文是怎么流动的？

**是什么**

**append-only**：`messages` 逐轮追加，**从不删改**（压缩是唯一的特例）。

序列长这样：
```
user task
  → assistant(tool_calls)     ← 第 1 轮：想 + 决定调什么
  → tool(result)              ← 观察 1
  → assistant(tool_calls)     ← 第 2 轮：基于观察 1 再想
  → tool(result)              ← 观察 2
  → ...
  → assistant(content)        ← 最后一轮：没有 tool_calls，这就是答案
```

**为什么 append-only 重要**：**模型没有记忆**（D1 就讲过）。它每一轮看到的都是**你重发的那一整条链**——链条断了，它就不记得自己做过什么。

**我的实现（D6 里可见的证据）**

`agents/core.py:58-61` 起步两条：
```python
        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=task),
        ]
```
之后**只 append，从不修改**（`agents/core.py:76-78`、`111-113`、`129`）。

**单元测试把这条顺序钉死了**（`tests/test_agent_loop.py` 的第一个用例）——真实断言：
```python
    final_seen = fake.calls[3]
    assert len(final_seen) == 8
    assert final_seen[0].role == "system"
    assert final_seen[1].role == "user"
    assert final_seen[2].tool_calls[0].name == "calculator"
    assert final_seen[3].role == "tool"
    assert final_seen[3].content == "408"
    assert final_seen[4].tool_calls[0].name == "get_weather"
    assert final_seen[5].tool_call_id == "c2"
    assert final_seen[6].tool_calls[0].name == "get_current_time"
    assert final_seen[7].tool_call_id == "c3"
```

**8 条消息 = 2 起步 + 3 轮 × 2（assistant + tool）**，顺序完全符合 append-only 的序列。**这是"上下文怎么流动"最硬的证据。**

**唯一的例外是压缩**　`agents/core.py:150-163`——它**重建**整个列表（不是 append）。所以压缩是"append-only 规则的已知破坏者"，这也是为什么它必须打日志（`context.compress` 事件里记了前后条数和压缩率）。

**面试官会追问什么**

- 追问 1："为什么熔断的那条提示是 `role='user'` 而不是 system？" 答：**因为它是一条"来自系统的新指令"，但在协议里它必须是 user 位置的消息**。用 system 会破坏"system 只在最前"的惯例（D3 的摘要消息已经破过一次例，那是任务书要求的）。**用 user 更保险**，而且模型的训练数据里"用户催它给答案"很常见。
- 追问 2："压缩会不会破坏这个链条的语义？" 答：**会，这是有损压缩的代价**。压缩后中间那段变成了摘要，模型看到的链条是"头 3 条 → 一段摘要 → 最近 N 条"。**丢失的是细节，保住的是决策和结论**（D3 的压缩 prompt 就是这么写的）。**代价是真实的，所以要日志记录、要能追查。**

**参考来源**
- 主文档《核心接口规格》内核节
- 博客园《深入理解 Agent Loop》

---

## 今日真实体验记录（附：跑真实验收）

**验收命令**：`python -m afg.cli`（真实 API，commandcode 通道）

### 发现 1：模型选择了**并行**，不是任务书预期的串行

任务书说 demo 任务是"**验证 3 步工具链自主串行执行**"。但真实运行是：

```
agent.trace  iteration=1  kind=action
  content='calculator({"expr": "12*34"}) + get_weather({"city": "北京"}) + get_current_time({})'
```

**模型在一轮里并行发了 3 个工具调用，两轮就结束了**（不是 3 轮）。

**为什么**：这三个调用**互不依赖**——算数不用等天气、天气不用等时间。模型判断出这一点，直接批量发出。

**这验证了两件事**：
1. **D4/D5 笔记里"无依赖可并行"的结论是真的**（Q7/Q9 考点）
2. **我的执行层天然支持**——因为 `agents/core.py:101` 是 `for tool_call in resp.tool_calls:`，而响应本来就可以有多个 tool_call。**代码零改动扛住了。**

**要构造真正的"串行链"得让第二步依赖第一步的结果**，比如："北京现在几度？超过 30 度就帮我算 12*34，否则算 12+34"。

### 发现 2：熔断的"优雅收尾"是真实的

故意把 `MAX_ITERATIONS=1`，只让循环跑一轮：

```
agent.turn          iteration=1  tokens=49
tool.call           calculator / get_weather / get_current_time   ← 三个都执行了
agent.circuit_break reason='你已经用完了全部 1 步，请不要再调用工具，直接基于已经获得的观察回答用户。'
agent.done          answer='结果如下：1. **12 × 34 = 408**  2. **北京天气**：晴，24℃  3. **现在时间**：2026-09-15 20:16:16（晚上 8 点 16 分）'
```

**步数用完了，答案却完整**——模型基于已经拿到的 3 个观察值组织出了最终回答。

**这个对比很有说服力**：如果熔断是"抛异常"，用户看到的是一个报错；而现在是**一个完成度 100% 的答案**（因为这个任务本来只需要一轮工具）。**"熔断 = 降级交付，不是失败"**——这是 ReAct 工程化里最容易被忽略的一点。

### 发现 3：重试默认 `retry_on=Exception` 太宽，测试里暴露了

写 `with_retry` 时默认参数是 `retry_on=Exception`（重试所有异常）。这在测试里立刻出问题：**`FakeLLM` 响应序列耗尽时抛 `AssertionError`，被重试了 3 次**（还带 sleep），测试从 1.2 秒涨到 5.4 秒。

**根因**：`AssertionError` 是"代码写错了"，重试一万次也没用。**`except Exception` 把编程错误当成了可重试故障。**

**修法有两层**：
1. **测试里** `retry_times=1`（`tests/test_agent_loop.py` 的 `make_agent`）——测试不该重试
2. **给 `with_retry` 加 `initial_delay` 参数**（默认 1.0 秒）——测试传 0.001，跑得快

**遗留的认识**：**生产环境应该把 `retry_on` 收窄成具体的网络异常类型**（超时、限流），而不是 `Exception`。现在这样写是"能跑但不够严谨"。这个判断记在这里，接真实网络层时再收窄。

### 发现 4：两轮 token 增长

```
agent.turn  iteration=1  messages=2  tokens=49   usage_pct=0.8
agent.turn  iteration=2  messages=6  tokens=163  usage_pct=2.7
```
一轮多了 4 条消息（assistant + 3 个 tool），token 从 49 涨到 163。**这个斜率（+114/轮）比 D3 实验的纯对话（+214/轮）低**，因为这次工具结果都很短（4~21 字符）。**等 D13 接了 `exec_command`（可能返回几万行），这个斜率会立刻爆掉**——那时才是压缩器真正高频触发的时候。

**成本记录**：D6 验证共约 8 次真实调用（2 次验收任务 × 各 2 轮 + 若干重试）。

---

## 参考资料完整清单

- Yao et al. 2022《ReAct: Synergizing Reasoning and Acting in Language Models》: https://arxiv.org/abs/2210.03629
- Anthropic《Building Effective Agents》: https://www.anthropic.com/research/building-effective-agents
- 博客园《深入理解 Agent Loop》
- 知乎《为什么说 ReAct 才是现代 Agent 的底层逻辑》
- CSDN《Agent 推理范式 ReAct 与 CoT》
- 腾讯云《160+ 真题》死循环 / max_iterations 题
- 主文档《核心接口规格》内核节、D16 并发规格、D20 评测规格
