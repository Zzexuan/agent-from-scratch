import json
import time

from afg.config import AgentConfig, ContextConfig
from afg.context.compressor import Compressor
from afg.context.counter import TokenCounter
from afg.context.messages import Message
from afg.context.window import ContextWindow
from afg.exceptions import AfgError
from afg.observability.logging import get_logger
from afg.observability.retry import RetryingLLM
from afg.tools.registry import ToolRegistry

SYSTEM_PROMPT = "你是一个乐于助人的 AI 助手，请用简体中文回答。"


class AgentCore:
    def __init__(self, llm, config: AgentConfig):
        self._llm = RetryingLLM(llm, retries=config.retry_times, backoff=config.retry_backoff)
        self._config = config
        self._registry = ToolRegistry()
        self._counter = TokenCounter()
        self._logger = get_logger("agent")

        ctx_config = ContextConfig()
        window = ContextWindow.from_model(
            ctx_config.context_window_tokens, ctx_config.safety_ratio
        )
        self._window = window
        self._compressor = Compressor(
            budget=window.budget, target_ratio=ctx_config.compress_target_ratio
        )
        self._keep_recent = ctx_config.compress_keep_recent

    def register(self, capability) -> "AgentCore":
        if isinstance(capability, ToolRegistry):
            self._registry = capability
        else:
            raise AfgError(
                "AgentCore 不认识这种能力，目前只支持 ToolRegistry",
                context={"type": type(capability).__name__},
            )
        self._logger.info(
            "agent.register",
            capability=type(capability).__name__,
            tools=self._registry.names(),
        )
        return self

    def tools(self) -> list:
        return self._registry.all()

    def run(self, task, max_iterations=None, verbose=False) -> str:
        limit = max_iterations
        if limit is None:
            limit = self._config.max_iterations

        messages = [
            Message(role="system", content=SYSTEM_PROMPT),
            Message(role="user", content=task),
        ]
        schemas = self._registry.to_openai_schemas()
        self._logger.info("agent.start", task=task, max_iterations=limit, tool_count=len(schemas))

        last_action = ""
        repeat_count = 0
        stop_reason = ""

        for iteration in range(1, limit + 1):
            messages = self._check_context(messages, iteration)

            resp = self._llm.chat(messages, tools=schemas)
            thought = resp.content
            if thought is None:
                thought = ""
            messages.append(
                Message(role="assistant", content=resp.content, tool_calls=resp.tool_calls)
            )
            if verbose:
                self._logger.info(
                    "agent.trace", iteration=iteration, kind="thought", content=thought
                )

            if not resp.tool_calls:
                self._logger.info(
                    "agent.done", iteration=iteration, reason="模型给出最终答案", answer=thought
                )
                return thought

            action = self._describe(resp.tool_calls)
            if action == last_action:
                repeat_count = repeat_count + 1
            else:
                repeat_count = 1
                last_action = action
            if verbose:
                self._logger.info(
                    "agent.trace", iteration=iteration, kind="action", content=action
                )

            for tool_call in resp.tool_calls:
                observation = self._execute(tool_call)
                if verbose:
                    self._logger.info(
                        "agent.trace",
                        iteration=iteration,
                        kind="observation",
                        tool=tool_call.name,
                        content=observation,
                    )
                messages.append(
                    Message(role="tool", content=observation, tool_call_id=tool_call.id)
                )

            if repeat_count >= self._config.same_action_limit:
                stop_reason = (
                    f"你已经连续 {repeat_count} 次执行了完全相同的动作，"
                    "请不要再调用工具，直接基于已经获得的观察回答用户。"
                )
                break

        if not stop_reason:
            stop_reason = (
                f"你已经用完了全部 {limit} 步，"
                "请不要再调用工具，直接基于已经获得的观察回答用户。"
            )

        self._logger.warning("agent.circuit_break", reason=stop_reason)
        messages.append(Message(role="user", content=stop_reason))
        final = self._llm.chat(messages)
        answer = final.content
        if answer is None:
            answer = ""
        self._logger.info("agent.done", reason=stop_reason, answer=answer)
        return answer

    def _check_context(self, messages, iteration) -> list:
        report = self._window.check(messages, self._counter)
        self._logger.info(
            "agent.turn",
            iteration=iteration,
            messages=len(messages),
            tokens=report.total_tokens,
            budget=report.budget,
            usage_pct=round(report.usage_ratio * 100, 1),
        )
        if not report.should_compress:
            return messages

        before_tokens = report.total_tokens
        compressed = self._compressor.compress(
            messages, self._llm, self._counter, self._keep_recent
        )
        after_report = self._window.check(compressed, self._counter)
        self._logger.info(
            "context.compress",
            messages_before=len(messages),
            messages_after=len(compressed),
            before_tokens=before_tokens,
            after_tokens=after_report.total_tokens,
            ratio=round(after_report.total_tokens / before_tokens, 3),
        )
        return compressed

    def _describe(self, tool_calls) -> str:
        parts = []
        for tool_call in tool_calls:
            arguments = json.dumps(tool_call.arguments, sort_keys=True, ensure_ascii=False)
            parts.append(tool_call.name + "(" + arguments + ")")
        return " + ".join(parts)

    def _execute(self, tool_call) -> str:
        started = time.perf_counter()
        try:
            tool = self._registry.get(tool_call.name)
            result = tool.run(**tool_call.arguments)
        except AfgError as e:
            result = "工具执行失败：" + str(e)
            self._logger.warning(
                "tool.error", tool=tool_call.name, error=str(e), context=e.context
            )
        self._logger.info(
            "agent.observation",
            tool=tool_call.name,
            arguments=tool_call.arguments,
            result_length=len(result),
            latency_ms=round((time.perf_counter() - started) * 1000, 1),
        )
        return result

    def registry_names(self) -> list[str]:
        return self._registry.names()