# 写代码前必读：本目录的语法约束

本目录（`agent-from-scratch/`）下所有 `.py` / `.toml` / `.env.example` 文件，必须遵守
**《代码写法约束》**：`../agent-learning/代码写法约束.md`

两条铁律：

1. **只能用白名单里的基础语法** —— 变量、`if`/`for`/`while`、`def`、`class` + 继承、`self`、列表/字典、
   f-string、`try`/`except`、`with`、`append`。
   **禁止**：列表/字典推导式、生成器表达式、三元表达式 `A if c else B`、`*`/`**` 解包、类型注解、
   泛型 `list[X]`、装饰器（pydantic 字段和已存档的 5 个装饰器除外）、`functools`/`itertools`。
   确实需要白名单外的语法时：**先停下来解释并征得用户同意，才能写**，并在代码里用一行注释标记。

2. **默认不写注释** —— 只在"踩过坑、不知道就会犯错"的地方写**一行**，讲"为什么"，不讲"是什么"。

用户是只掌握 Python 基础语法的新手（不熟悉 pydantic / openai / structlog / tiktoken 等任何库）。
**用户看不懂的代码 = 没完成。**
