# D04 笔记：Function Calling 四步流程与 schema 设计（草稿版）

> 固定格式：是什么 → 我的实现 → 面试官会追问什么 → 参考来源。
> 本文为 2026-09-04 手搓代码后的草稿，建议按自己口吻再润色。
> D4 代码：`src/afg/exceptions.py`（新建）、`src/afg/tools/base.py`（新建）、`src/afg/tools/builtin.py`（新建）、`src/afg/demo_fc.py`（新建）、`src/afg/llm/deepseek_client.py`（修 bug）

---

## Q1：什么是 Function Calling？标准四步流程？

**是什么**

Function Calling（FC）= 让 LLM **输出结构化的工具调用指令（JSON）而不是纯文本**。它不是"模型会执行函数"，而是"模型会填表"。

标准四步：

| 步 | 谁做 | 做什么 |
|---|---|---|
| ① | 运行时 | 把工具清单（name / description / parameters schema）随请求传给 API |
| ② | LLM | 判断这个问题需不需要调工具、调哪个 |
| ③ | LLM | 返回 `tool_calls`（函数名 + 参数 JSON）**而不是**自然语言 |
| ④ | 运行时 | 执行函数 → 把结果作为 `role="tool"` 消息回填 → **再调一次 LLM** |

第 ④ 步的"再调一次"是闭环的关键：**模型不执行函数，它只看到执行结果后继续推理。**

**我的实现（D4 里可见的证据）**

四步在 `src/afg/demo_fc.py` 里是显式摊开的（**故意不进循环**，D6 才做循环）：

```python
messages = [Message(role="user", content=question)]          # ① 准备
resp = llm.chat(messages, tools=schemas)                     # ②③ 发请求，拿回 tool_calls
messages.append(Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls))
for tc in resp.tool_calls:                                   # ④ 执行
    result = tool.run(**tc.arguments)
    messages.append(Message(role="tool", content=result, tool_call_id=tc.id))
final = llm.chat(messages, tools=schemas)                    # ④ 再调一次
```

**真实运行证据**（`python -m afg.demo_fc`，问"帮我算 37*89"）：

```
fc.llm_call    call=1 messages=1 prompt_tokens=507 completion_tokens=55
fc.tool_request  tool=calculator arguments={'expr': '37*89'} call_id=call_00_EbWQ2...
fc.tool_call     tool=calculator result_length=4 latency_ms=0.1
fc.llm_call    call=2 messages=3 prompt_tokens=560 completion_tokens=10
fc.final_answer  content='37 × 89 = **3293**'
```

注意 `messages` 从 **1 条变 3 条**（user → assistant(tool_calls) → tool），这就是第 ④ 步"回填"的物理形态。

**面试官会追问什么**

- 追问 1："第 ④ 步为什么必须再调一次 LLM？" 答：因为模型看不到执行结果就没法回答用户。第一次调用它只说了"我要算 37*89"，第二次调用它才看到"结果是 3293"，然后才能组织成人话。**所以一次 FC 交互至少是 2 次 API 调用，成本要按 2 倍估。**
- 追问 2："能不能让模型自己算，省掉这步？" 答：能算的它确实会直接算（我另一个测试里问"现在几点"，它调了工具；但如果只是随口问"1+1"，它可能直接答）。**FC 的价值在于需要外部真实信息时**——时间、天气、数据库，模型自己造不出来。

**参考来源**
- 腾讯云《160+ 真题》工具调用章 Q1-Q8
- OpenAI Function Calling 官方文档

---

## Q2：LLM 自己执行函数吗？（必考送分题）

**是什么**

**不执行。** LLM 只负责决策"调用什么、传什么参数"，实际执行是**运行时（runtime）**的事。

一句话记法：**LLM 是指挥官，runtime 是执行者。** 模型输出的是"一张派工单"，不是"干活"。

这个设计不是能力限制而是**安全边界**：如果模型能直接执行代码，那就等于把服务器交给一个会幻觉的程序。所以协议强制切成两半——模型只能"说"，执行必须由你的代码决定**要不要执行、怎么执行、执行失败怎么办**。

**我的实现（D4 里可见的证据）**

`demo_fc.py:55-70` 是"执行者"的角色：

```python
        tool = find_tool(tools, tc.name)            # 我们决定用哪个工具
        started_tool = time.perf_counter()
        try:
            result = tool.run(**tc.arguments)       # 我们决定怎么执行
        except ToolError as e:
            result = "工具执行失败：" + str(e)      # 执行失败也由我们决定怎么处理
            logger.warning("fc.tool_error", tool=tc.name, error=str(e), context=e.context)
```

三件事全是运行时做的：**工具查找、执行、错误处理**。模型全程不知情，它只看到最后回填的 `result` 字符串。

**真实运行证据**（强制模型查一个不存在的城市）：

```
fc.tool_error   context={'city': '广州', 'supported': ['北京', '上海', '深圳']}
                error=没有这个城市的天气数据
fc.final_answer content='...工具返回了失败：没有这个城市的天气数据...我不能编造一个广州的天气结果给你。'
```

模型收到的是我们**加工过的错误字符串**——它老老实实承认查不到，**没有编造广州的天气**。这就是"执行权在我们手里"的价值。

**面试官会追问什么**

- 追问 1："模型幻觉出一个不存在的工具怎么办？" 答：我的 `find_tool()`（`demo_fc.py:15-19`）在找不到时抛 `UnknownToolError`，不会去执行任何东西。**未知工具名是必须防御的**——模型有时会把两个工具名拼在一起（比如把 `get_weather` 写成 `get_temperature`）。
- 追问 2："工具执行很慢/卡死怎么办？" 答：现在是同步执行，没有超时保护——这是 D13 沙盒要解决的（`SandboxPolicy.timeout_seconds`）。**目前 demo 里的工具都是本地秒回的，所以问题还没暴露。**

**参考来源**
- 腾讯云《160+ 真题》"LLM 自己执行函数吗" 原题
- 知乎《2026 Agent 大厂面试题汇总》FC 节

---

## Q3：Tool Schema 包含哪些核心字段？

**是什么**

```json
{
  "type": "function",
  "function": {
    "name": "calculator",
    "description": "计算一个数学表达式的值。参数 expr 是表达式字符串...",
    "parameters": {
      "type": "object",
      "properties": {
        "expr": {"type": "string", "description": "要计算的数学表达式，例如：37*89"}
      },
      "required": ["expr"]
    }
  }
}
```

三层：
1. **外层 `type="function"`** —— 协议固定值（**这层漏了会 400**，见 Q1 的踩坑记录）
2. **`name` + `description`** —— 模型靠它决定"要不要调这个工具"
3. **`parameters`** —— 标准 JSON Schema：`properties`（参数名/类型/描述）、`required`（必填）

**描述质量决定调用准确率**——这是 FC 里最被低估的一点。

**我的实现（D4 里可见的证据）**

`tools/base.py:17-25` 的 `to_openai_schema()` 负责组装这三层：

```python
def to_openai_schema(tool):
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters(),
        },
    }
```

三个内置工具的 description 都是精心写的，`tools/builtin.py:87-92` 的天气工具是典型：

```python
    description = (
        "查询一个城市的当前天气。参数 city 是中文城市名，"
        "目前只支持北京、上海、深圳三个城市，其他城市会返回错误。"
        "返回该城市的天气状况、气温和湿度。"
    )
```

**真实运行证据（描述质量的直接证明）**：我问"火星的天气如何"，模型**没有调用工具**：

```
fc.no_tool_call content='抱歉，我这边查不了火星的天气...我的天气查询工具目前
                只支持北京、上海、深圳三个城市，火星不在支持范围内'
```

它读了 description 里"只支持三个城市，其他城市会返回错误"这句，判断调用必然失败，于是**跳过调用直接解释**。这是**描述写清楚带来的正确行为**——省了一次无用的工具调用。

**面试官会追问什么**

- 追问 1："description 写不好会怎样？" 答：两种坏结果。**写太含糊**→ 该调不调（比如只写"查询信息"，模型不知道能查什么）；**写太宽泛**→ 不该调也调（比如写"查询任何城市的天气"，模型就会对广州也发起调用，然后吃一个错误）。我这次实测到的"火星不调、广州被强制要求才调"就是description 边界起作用。
- 追问 2："参数描述也要写吗？" 答：要，而且同样重要。比如 `city` 参数的描述写"中文城市名，可选值：北京、上海、深圳"——**枚举值直接写进参数描述**，能挡掉大部分无效调用。D5 要做 `@tool` 装饰器自动生成 schema，那时参数描述就是 docstring 的质量问题。

**参考来源**
- OpenAI Function Calling 文档（schema 规范）
- 腾讯云《160+ 真题》schema 字段题

---

## Q4：FC 和 Prompt+正则解析比好在哪？

**是什么**

| 维度 | FC | Prompt + 正则解析 |
|---|---|---|
| 输出通道 | 模型**原生训练过**的结构化通道 | 让模型"顺便"输出一段特定格式的文本，再正则抠 |
| 可靠性 | 协议保证 JSON 结构 | 模型会加解释、加 markdown、少括号，正则天天崩 |
| 参数类型 | schema 校验（类型/必填/enum） | 全是字符串，得自己转 |
| 嵌套参数 | 天然支持（JSON Schema 可以嵌套对象/数组） | 正则处理嵌套基本没戏 |
| 多工具 | 协议支持一次返回多个 tool_call | 要自己约定分隔符，容易切错 |

核心差别：**FC 是模型被专门训练过的输出模式，正则是在"模型自由发挥"里捞信息。**

**我的实现（D4 里可见的证据）**

D4 之前我确实想不出为什么不能用正则，直到**真实运行时报了 400**：

```
openai.BadRequestError: 400 - {'error': {'message': 'Invalid input: expected "function"',
                                          'param': 'messages.1.tool_calls.0.type'}}
```

这个错误恰恰证明了 FC 的价值：**协议在服务端做结构校验**。我的 `ToolCall` 是扁平的内部格式（`id`/`name`/`arguments`），回传时漏了 `type: "function"`，服务器**当场拒绝并精确指出是 `messages.1.tool_calls.0.type` 这个位置**。

如果是正则方案，同样的错误不会报错——它会**静默地把工具名解析错**，然后你的程序拿着一个错名字去执行，或者干脆不执行，你在日志里翻半天。

修复在 `deepseek_client.py:9-28` 的 `to_api_message()`：把内部扁平格式翻译成协议要求的嵌套格式（补 `type`、把 `name`/`arguments` 嵌进 `function`、`arguments` 用 `json.dumps` 还原成字符串）。

**面试官会追问什么**

- 追问 1："那 FC 就没缺点了？" 答：有。**①依赖模型支持**（不是所有模型都训练过 FC）；**②描述/schema 的质量直接决定效果**，调 prompt 调到 schema 上了；**③有些模型对小模型 FC 能力差**，反而不如"prompt 里给例子 + 严格输出格式"。所以工程上有个经验：**能用 FC 就用 FC，模型不支持才退回结构化 prompt。**
- 追问 2："你说正则'天天崩'，能举个例子吗？" 答：比如让模型输出 `调用：calculator(37*89)`，模型可能输出 `我将调用 calculator(37*89) 来计算` —— 你的正则 `^调用：(.*)\((.*)\)$` 直接匹配失败。而 FC 的 `tool_calls` 字段**要么有要么没有**，不存在"格式差不多但没对上"的中间态。

**参考来源**
- 腾讯云《160+ 真题》FC 对比题
- 本次真实 400 报错（见"今日真实体验记录"）

---

## Q5：为什么说 FC 是 Agent 的基石？

**是什么**

FC 解决了 Agent 的两个核心问题：

1. **什么时候调用** —— LLM 自主判断，不需要规则引擎（不用写一堆 `if "天气" in question`）
2. **传什么参数** —— 自然语言 → 结构化参数自动提取（"深圳今天热不热" → `{"city": "深圳"}`）

**Agent 循环本质 = FC 的循环编排**：

```
while 任务没完成:
    LLM 决定下一步（可能调工具，也可能直接回答）
    if 调工具: 执行 + 回填
    else: 结束
```

D4 做的是**跑一次** FC 闭环；D6 要把它包进 `while` 循环 + 熔断。

**我的实现（D4 里可见的证据）**

`demo_fc.py:22-84` 的 `main()` 就是"循环体的一次展开"——把 `while` 拆开只跑一遍：

- `demo_fc.py:35` 第一问 → `demo_fc.py:55-70` 执行工具 → `demo_fc.py:75-84` 第二问
- **要变成 D6 的 Agent 循环，只需把这三段包进 `while True:` 并加"没有 tool_calls 就 break"**

我特意让 demo **不进循环**（任务书要求）：先看清一轮的每个环节，再做循环才有意义。**哪一步没看懂，循环起来就是一锅粥。**

**真实运行证据（一次 FC = 2 次 LLM 调用）**：

```
fc.llm_call call=1  prompt_tokens=507  completion_tokens=55
fc.llm_call call=2  prompt_tokens=560  completion_tokens=10
```

**token 成本要按 2 倍估**——而且注意第二次的 `prompt_tokens` 反而涨了（507 → 560），因为要重发全部历史（含工具 schema）。这正好接上 D2/D3 的上下文管理：**FC 循环会加速上下文膨胀，因为工具结果也要占 token。**

**面试官会追问什么**

- 追问 1："Agent 循环和普通 while 循环有什么本质区别？" 答：**循环的退出条件由模型决定，不由代码决定**。代码不知道任务什么时候完成，只能问模型（看它这轮有没有 tool_calls）。这也是为什么必须有熔断——模型可能永远不"觉得"任务完成。
- 追问 2："FC 循环里最容易出的问题是什么？" 答：**同一个工具被反复调用，参数完全一样**（模型卡在死循环里）。D6 的熔断设计里就有"连续 3 次相同 (tool, arguments) 强制退出"。这个坑我现在还没踩到，因为 demo 只跑一轮。

**参考来源**
- 主文档《核心接口规格》内核节（AgentCore 循环）
- Anthropic《Building Effective Agents》

---

## Q6：FC 和结构化输出的关系？

**是什么**

**FC 是结构化输出的一个特殊场景**：

```
结构化输出（广义）：按指定 JSON Schema 返回任意数据
    └─ FC（狭义）：输出内容固定是"工具调用指令"
    └─ RAG：可视为"检索工具"的 FC
```

三者关系：
- **结构化输出**是能力，"我让你按这个格式回"
- **FC** 是这个能力的一个专门用途，"我让你按这个格式回，而且这个格式表示你要调工具"
- **RAG** 可以看成 FC 的特例：把"检索"包装成一个工具，模型调用它、拿回文档、再组织答案

**我的实现（D4 里可见的证据）**

D4 的代码里两层都存在：

- **结构化输出的底层是 JSON Schema** —— `tools/builtin.py:57-67` 的 `parameters()` 返回的就是标准 JSON Schema：
```python
        return {
            "type": "object",
            "properties": {
                "expr": {"type": "string", "description": "要计算的数学表达式，例如：37*89"},
            },
            "required": ["expr"],
        }
```

- **FC 是它的特定用法** —— 这个 schema 不是用来约束"模型回复长什么样"，而是用来描述"工具要什么参数"。**同一套 schema 语法，两个不同用途。**

- **D1 的 `Message` 模型本身就是"结构化输出"的产物**：模型不返回纯文本，而是返回 `tool_calls` 里的结构化字段，由 D1 的 `ToolCall`（`context/messages.py:8-11`）接住。

**面试官会追问什么**

- 追问 1："RAG 为什么算 FC？" 答：因为从运行时的角度看，**"检索"和"查天气"没有本质区别**——都是"模型决定要外部信息 → 调一个函数 → 结果回填"。这个视角的好处：D9 做 RAG 时不用另起一套，直接实现一个 `search_notes` 工具注册进去就行。**这是我这个项目"D9 = 一个工具"设计的理由。**
- 追问 2："那什么时候该用纯结构化输出而不是 FC？" 答：**当不需要外部信息时**。比如"把这段话抽成 {name, age, city} 三个字段"——没有函数要执行，只是要个格式化结果。用 FC 反而绕（要造一个假工具），直接要求 JSON 输出更合适。

**参考来源**
- OpenAI 结构化输出文档
- 主文档 D9 规格（search_notes 作为工具）

---

## Q7：并行工具调用是什么？适用场景？

**是什么**

模型**一次返回多个 tool_call**，运行时**并行执行**，适合**无依赖**的任务：

- ✅ 可以并行："北京和深圳的天气怎么样" —— 两次查天气互不依赖
- ❌ 必须串行："先搜索深圳的天气，再根据结果推荐穿什么" —— 第二步依赖第一步的结果

**判断标准：任务 B 的输入是否需要任务 A 的输出。** 需要 → 串行；不需要 → 可并行。

**我的实现（D4 里可见的证据）**

D4 的代码结构**已经为并行留好了位置**，但故意没做并行：

`demo_fc.py:53-70` 是一个 `for` 循环：
```python
    for tc in resp.tool_calls:
        logger.info("fc.tool_request", ...)
        tool = find_tool(tools, tc.name)
        ...
        messages.append(Message(role="tool", content=result, tool_call_id=tc.id))
```

- **`for tc in resp.tool_calls`** —— 说明响应里本来就可以有**多个** tool_call（不是设计成单个）
- **`tool_call_id=tc.id`** —— 每个结果按 id 回填，这正是"多调用并行"能对上号的前提
- **但循环是顺序的** —— D4 不并行（任务书把"执行层从逐个执行改造成并发处理"留给后续）

改成并行只需把 `for` 里的执行换成线程池，**回填顺序仍按 id 对应，不受执行顺序影响**。这个接口是 D1 的 `ToolCall.id` 就设计好的。

**面试官会追问什么**

- 追问 1："并行执行时结果顺序乱了怎么办？" 答：**不会乱**。协议要求每个 `tool_call` 都要有对应的 `role="tool"` 消息，靠 `tool_call_id` 对上，不靠数组顺序。但**回填时必须保证每个 id 都有结果**——有一个 `tool_call` 没回填，下一次请求就会 400。这是我 D6 要处理的重点，也是任务书 Q10 的考点。
- 追问 2："并行一定更快吗？" 答：不一定。**①工具本身是 IO 密集才划算**（调 API、查数据库），CPU 密集的并行反而抢 GIL；**②并发数要限制**，模型一次返回 10 个 tool_call 你起 10 个线程，可能把下游打挂；**③错误处理变复杂**，一个失败要不要取消其他？**所以并行是"确认无依赖 + 有限并发"才做。**

**参考来源**
- OpenAI 并行工具调用文档
- 主文档 D16 规格（线程池 + 超时）

---

## Q8：工具返回结果直接塞给 LLM 吗？

**是什么**

**不能直接塞。** 要清理四件事：

| 清理项 | 为什么 | 怎么做 |
|---|---|---|
| **长度截断** | 工具输出可能几万字符，直接塞进去 token 爆炸 | 设上限（如 16000 字符），超了截断 + 标记 |
| **敏感信息脱敏** | 工具输出里可能有密钥、手机号、内部路径 | 正则替换成 `***` |
| **大结果压缩/分页** | 一页 1000 条数据不该全给模型 | 只给摘要 + "需要更多可以说" |
| **格式规范化** | 原始输出可能是 HTML/二进制 | 转成模型好读的文本/JSON |

不清理的后果是任务书说的两个：**Token 爆炸 + 上下文污染**（无关内容挤掉关键信息，还干扰模型判断）。

**我的实现（D4 里可见的证据）**

D4 只做了**最小版本**，因为内置工具的输出都短（最长 23 字符）：

`demo_fc.py:66-72` 记录了结果的长度：
```python
        logger.info(
            "fc.tool_call",
            tool=tc.name,
            arguments=tc.arguments,
            result_length=len(result),
            latency_ms=round((time.perf_counter() - started_tool) * 1000, 1),
        )
```

**`result_length` 这个字段就是"将来该截断谁"的依据**——现在三个工具都返回 20 出头，等 D13 接了 `exec_command`（可能返回几万行），这个字段会立刻暴露问题。

真实数据：
```
tool=calculator    result_length=4     ← "3293"
tool=get_weather   result_length=23    ← "深圳：雷阵雨，气温 31 摄氏度，湿度 80%"
tool=get_current_time result_length=19 ← "2026-09-14 20:10:36"
```

**注意 `ToolError` 的处理其实已经是"清理"的一种**（`demo_fc.py:61-63`）：执行失败不抛给上层崩掉，而是转成一句人话回填，让模型有机会自己纠正（实测它确实解释了原因并给出替代方案）。

**面试官会追问什么**

- 追问 1："截断的话截哪部分？" 答：**优先保头尾**（中间截断，见 D03 笔记 Q7）。工具输出常常开头有结构（字段名）、结尾有结论（统计结果），中间是重复的明细。另外**截断时要明确告知模型**"内容被截断了"——否则模型会以为数据就这么多，得出错误结论。
- 追问 2："脱敏会不会破坏数据？" 答：要看工具。**日志/HTTP 响应类**必须脱敏（可能有 token）；**纯计算类**不用。工程上一般做成可配置的（`SandboxPolicy` 里的开关），而不是全局一刀切。这是我 D13 的设计方向。

**参考来源**
- 腾讯云《160+ 真题》工具结果处理题
- 主文档 D13 沙盒规格（output_max_chars）

---

## Q9：LLM 怎么"学会"调用工具的？

**是什么**

**训练出来的，不是运行时教的。**

模型在训练/后处理阶段见过大量"对话 + 工具定义 + 正确的工具调用"样本，被微调成"看到 schema 就知道该输出什么格式的 tool_calls"。这个过程叫 **指令跟随 + 格式对齐**。

推论（很重要）：
- **模型的 FC 能力是学出来的** → 描述和 schema 写得**越规范**（越接近它训练时见过的样子），调用越准
- **模型没见过的工具类型** → 描述写得再"创新"也可能调用失败
- **不同模型的 FC 能力差别很大** → 这是选型时要实测的指标

**我的实现（D4 里可见的证据）**

D4 代码里能观察到这个"学出来的模式匹配"行为：

1. **它对描述里的"边界词"很敏感**。我在 `tools/builtin.py:87-92` 的 description 里写了"**只支持**北京、上海、深圳"和"**其他城市会返回错误**"——真实运行时，问"火星的天气"，它**直接跳过了工具调用**并复述了我的边界说明。这说明模型读描述时是在**做条件判断**，不只是关键词匹配。

2. **它对"无参数工具"的处理也是学来的**。`tools/builtin.py:120-128` 的 `get_current_time` 参数 schema 是空的：
```python
        return {"type": "object", "properties": {}}
```
真实运行时它返回了 `arguments={}`：
```
fc.tool_request arguments={} call_id=call_00_ET_Fko6zy0cgZtvi6aJ2wSd0780
```
**没有参数它就不编参数**——这是训练时对齐好的行为（模型知道空 schema 就该给空对象）。

3. **它对工具名的理解来自 `name` 字段**。三个工具的名字是 `calculator` / `get_weather` / `get_current_time`（`tools/builtin.py:50 / :87 / :121`），模型能正确对应到"算数 / 查天气 / 查时间"三种意图——**这正是它训练时见过的大量同类样本的效果。**

**面试官会追问什么**

- 追问 1："那如果我自己发明一个模型没见过的工具类型？" 答：**靠描述把它"翻译"成模型熟悉的形状**。比如你要做一个内部工单系统查询工具，模型没见过，但你可以把它描述成"查询类工具，输入工单号，返回工单状态"——**描述的作用就是让模型把它归到已知的类别里。**
- 追问 2："怎么提高调用准确率？" 答：三个手段，按性价比排：**① 名字写清楚**（`get_weather` 比 `query` 好）；**② 描述里写边界和反例**（"不支持 xx 城市"）；**③ 参数描述里写枚举值**。这三个我 D4 都做了，实测下来"火星不调、强制才调广州"说明边界描述是有效的。**实在不行才考虑微调**——那是最后手段，成本极高。

**参考来源**
- OpenAI Function Calling 文档（模型侧行为说明）
- 腾讯云《160+ 真题》"模型怎么学会调工具" 原题

---

## Q10：如果同时触发多个 function call，运行时怎么处理？

**是什么**

规则来自 OpenAI 协议，硬性要求：

1. **按 `id` 一一对应执行** —— 每个 `tool_call` 有自己的 `id`
2. **全部回填后再请求下一轮** —— 协议要求**每个** `tool_call` 都必须有对应的 `role="tool"` 消息
3. **无依赖的可并发** —— 缩短总延迟

**第 2 条是硬性的**：漏回填一个 → 下一次请求 400。因为模型看到"我发了 3 张派工单，只回来 2 张"，它无法继续推理。

**我的实现（D4 里可见的证据）**

D4 的 `for` 循环天然满足第 1、2 条：

`demo_fc.py:53-73`：
```python
    for tc in resp.tool_calls:
        ...
        messages.append(Message(role="tool", content=result, tool_call_id=tc.id))
```

关键设计点：**`tool_call_id=tc.id` 写在循环体内，每次 appending 一条**。所以无论 `resp.tool_calls` 里有 1 个还是 5 个，循环结束时**每个 id 都有对应的回填消息**——"全部回填"是被循环结构保证的。

**而 `role="tool"` 必须带 `tool_call_id` 这件事，D1 就已经用防呆校验拦住了**（`context/messages.py:20-24` 的 `@model_validator`）：
```python
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("role='tool' 的消息必须带 tool_call_id")
```

这条校验在 D1 写的时候还没法验证（那时没有工具），**D4 是它第一次真正被用上**。如果漏了 id，本地构造时就报错，不会等到 API 给你一个难懂的 400。

**真实运行证据**：D4 的测试里跑 1 个 tool_call 时，`messages` 从 1 条变 3 条：

```
fc.llm_call call=1 messages=1
fc.llm_call call=2 messages=3     ← user + assistant(tool_calls) + tool
```

`3 = 1 + 1 + 1`。如果有 3 个 tool_call，第二次调用时应该是 `1 + 1 + 3 = 5` 条。

**面试官会追问什么**

- 追问 1："能不能只回填一部分？" 答：**不行，会被 API 拒绝**。协议把 `tool_calls` 和 `tool` 消息看作一对一的配对关系。如果某个工具执行失败，也必须回填——**回填错误信息**（我 D4 就是这么做的，`demo_fc.py:61-63` 把 `ToolError` 转成 `"工具执行失败：..."` 字符串回填，而不是跳过）。
- 追问 2："并行执行时某个工具抛异常怎么办？" 答：**异常要在各自的分支里被吃掉并转成回填内容**，不能向上冒泡——否则一个工具的失败会导致其他工具的结果也回填不了，整个请求作废。这是 D16 做线程池时要特别注意的点（`concurrent.futures` 的异常默认是吞掉存在 future 里的，要用 `.result()` 显式取）。

**参考来源**
- OpenAI 并行工具调用文档（配对规则）
- 主文档 D16 规格（线程池 + 超时 + 失败聚合）

---

## 今日真实体验记录（附：跑真实验收）

**验收命令**：`python -m afg.demo_fc`（真实 API，commandcode 通道的 `deepseek/deepseek-v4.1-flash`）

**覆盖的 5 个分支，全部实测通过**

| 分支 | 提问 | 结果 |
|---|---|---|
| 算数（带参数工具） | 帮我算 37*89 | 调 calculator，`arguments={'expr': '37*89'}` → 回填 `3293` → 最终答"37 × 89 = **3293**" |
| 天气（带参数工具） | 深圳天气怎么样 | 调 get_weather，`arguments={'city': '深圳'}` → 模型组织成带 emoji 的天气卡片 |
| 时间（**无参数**工具） | 现在几点了 | 调 get_current_time，**`arguments={}`**（模型没有编参数） |
| **工具报错** | 强制调 get_weather 查广州 | 抛 `ToolError` → context 完整记录 → 回填错误 → **模型没编造数据**，诚实解释并给替代方案 |
| **不需要工具** | 你好，你叫什么名字 | `fc.no_tool_call`，一次 LLM 调用就结束 |

**发现 1（最重要）：D1 埋的一个 bug，D4 才暴露**

第一次跑 demo 直接 400：

```
openai.BadRequestError: Error code: 400 -
{'error': {'message': 'Invalid input: expected "function"',
           'param': 'messages.1.tool_calls.0.type'}}
```

**根因**：D1 写的 `deepseek_client.py` 只处理了**读**（`tc.function.name` / `arguments` 解析），**没处理写**——把 assistant 的 `tool_calls` 发回 API 时，直接用 `model_dump()` 导出了内部的**扁平**格式：

```python
{"id": "...", "name": "calculator", "arguments": {"expr": "37*89"}}
```

而协议要求的是**嵌套 + 带 type**：

```python
{"id": "...", "type": "function",
 "function": {"name": "calculator", "arguments": "{\"expr\": \"37*89\"}"}}
```

三个差异：**①缺 `type`**（就是报错点）；**②`name`/`arguments` 要嵌进 `function`**；**③`arguments` 要从字典还原成 JSON 字符串**（进方向是 `json.loads`，出方向就得 `json.dumps`）。

**为什么 D1-D3 没暴露**：D1/D2/D3 的主循环根本没有工具，`tool_calls` 这条路径**从来没被走过**。D4 是第一次真正"回传 assistant 的 tool_calls"，一跑就露馅。

**修法**：在 `deepseek_client.py:9-28` 加 `to_api_message()`，把"内部扁平格式 → 协议嵌套格式"的翻译收在这一个函数里（**翻译的活归翻译官**，`ToolCall` 保持干净的内部模型）。同时补了回归测试 `test_tool_call_message_serializes_for_api` 钉死 `type` 字段，改回去就红。

**教训**：**"我写了但没跑过的代码路径，等于没写。"** D1 时我写了 tool_calls 的解析并自认为"为 D4 准备好了"，但只准备了读的一半。**真正的验证是端到端跑通，不是"代码看起来对了"。**

**发现 2：描述质量直接改变了模型行为**

问"火星的天气如何"，模型**没调用工具**，而是复述我 description 里写的"只支持北京、上海、深圳"。**这是 description 的边界描述在起作用**——它判断调用必然失败，主动跳过，省了一次无效工具调用 + 一次错误往返。

反过来说：如果 description 写"查询任意城市的天气"，模型就会对广州也发起调用然后吃错误。**描述写得准 = 调用准，这是 FC 里最划算的投入。**

**发现 3：成本要按 2 倍估，而且上下文加速膨胀**

```
fc.llm_call call=1  prompt_tokens=507  completion_tokens=55
fc.llm_call call=2  prompt_tokens=560  completion_tokens=10
```

- **一次 FC = 2 次 API 调用**（模型"说要调"一次、"看着结果回答"一次）
- 第二次的 `prompt_tokens` 反而**涨了**（507 → 560），因为要重发全部历史 + 工具 schema + 工具结果

**这直接接上 D2/D3 的上下文管理**：FC 循环里每一轮都会往 `messages` 里塞"assistant 的 tool_calls"和"tool 的结果"，**上下文膨胀速度比纯聊天快得多**——这是 D3 压缩器在 D6 之后会频繁被触发的原因。

**成本记录**：D4 验证共约 12 次真实调用（demo 跑 6 次 + 第一次失败的 1 次 + 若干重试）。

---

## 参考资料完整清单

- 腾讯云《160+ 真题》工具调用章 Q1-Q8
- 知乎《2026 Agent 大厂面试题汇总》FC 节
- OpenAI Function Calling 官方文档: https://platform.openai.com/docs/guides/function-calling
- OpenAI 并行工具调用文档
- Anthropic《Building Effective Agents》: https://www.anthropic.com/research/building-effective-agents
- 主文档《核心接口规格》工具系统节、内核节、D13 沙盒节、D16 规格
- 本次真实 400 报错记录（见"今日真实体验记录"发现 1）
