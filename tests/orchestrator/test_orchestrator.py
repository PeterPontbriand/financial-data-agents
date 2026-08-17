from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.llm.client import LLMClient, LLMGenerateResult
from src.orchestrator.context import ContextConfig, MessageContext
from src.orchestrator.dispatcher import AsyncToolDispatcher
from src.orchestrator.loop import AgentOrchestrator, OrchestratorConfig, OrchestratorOptions
from src.orchestrator.prompts import SystemPromptBuilder
from src.orchestrator.types import (
    ChatMessage,
    Role,
    ToolCallRequest,
    ToolCallResult,
)
from src.schema.config import SchemaConfig
from src.tools.parser import ParsedToolCall, ToolParser, ToolParsingError

# ---------------------------------------------------------------------------
# Helper – canonical way to create a context with runtime rules injected
# ---------------------------------------------------------------------------


def make_context_with_runtime_rules(
    *,
    max_history_messages: int = 30,
    preserve_system_prompt: bool = True,
    tool_schemas_json: str | None = None,
    rules_path: Path | str | None = None,
) -> MessageContext:
    """
    Example factory that future application code should mirror.

    Builds the system prompt (including RUNTIME_AGENTS.md when present)
    and injects it into a fresh MessageContext.
    """
    builder = SystemPromptBuilder(
        tool_schemas_json=tool_schemas_json,
        rules_path=rules_path,
        inject_runtime_rules=True,
    )
    system_prompt = builder.build()

    config = ContextConfig(
        max_history_messages=max_history_messages,
        preserve_system_prompt=preserve_system_prompt,
    )
    context = MessageContext(config=config)
    context.set_system_prompt(system_prompt)
    return context


# ---------------------------------------------------------------------------
# 1. Prompt Builder Tests
# ---------------------------------------------------------------------------


def test_system_prompt_builder_default() -> None:
    builder = SystemPromptBuilder()
    prompt = builder.build()
    assert "You are a financial analysis assistant." in prompt
    assert "AVAILABLE TOOLS SCHEMA:" not in prompt


def test_system_prompt_builder_with_schema() -> None:
    builder = SystemPromptBuilder(tool_schemas_json='{"tools": [{"name": "get_stock_price"}]}')
    prompt = builder.build()
    assert "AVAILABLE TOOLS SCHEMA:" in prompt
    assert "get_stock_price" in prompt
    assert "Respond with JSON tool invocations" in prompt


def test_system_prompt_builder_injects_runtime_rules(tmp_path: Path) -> None:
    """RUNTIME_AGENTS.md content is appended under a clear heading when present."""
    rules_file = tmp_path / "RUNTIME_AGENTS.md"
    rules_file.write_text("# Agent Rules\n- Always be precise\n- Prefer tool results", encoding="utf-8")

    builder = SystemPromptBuilder(
        inject_runtime_rules=True,
        rules_path=rules_file,
    )
    prompt = builder.build()

    assert "# RUNTIME AGENT RULES" in prompt
    assert "Always be precise" in prompt
    assert "Prefer tool results" in prompt
    assert "You are a financial analysis assistant." in prompt


def test_system_prompt_builder_missing_rules_file_is_silent(tmp_path: Path) -> None:
    """Missing rules file must not raise; prompt remains valid."""
    missing = tmp_path / "does_not_exist.md"
    builder = SystemPromptBuilder(inject_runtime_rules=True, rules_path=missing)
    prompt = builder.build()
    assert "You are a financial analysis assistant." in prompt
    assert "# RUNTIME AGENT RULES" not in prompt


def test_system_prompt_builder_can_disable_injection() -> None:
    builder = SystemPromptBuilder(inject_runtime_rules=False)
    prompt = builder.build()
    assert "# RUNTIME AGENT RULES" not in prompt


# ---------------------------------------------------------------------------
# 2. Context Management Tests
# ---------------------------------------------------------------------------


def test_context_add_and_ollama_payload() -> None:
    # Use the recommended factory so the system prompt already contains rules
    context = make_context_with_runtime_rules()
    context.add_message(ChatMessage(role=Role.USER, content="Hello"))

    payload = context.to_ollama_payload()
    assert len(payload) >= 2
    assert payload[0]["role"] == "system"
    assert "You are a financial analysis assistant." in payload[0]["content"]
    assert payload[-1] == {"role": "user", "content": "Hello"}


def test_context_truncation_preserves_system_prompt() -> None:
    context = make_context_with_runtime_rules(
        max_history_messages=5,
        preserve_system_prompt=True,
    )

    # Add 10 messages (system already present + 10 more)
    for i in range(10):
        role = Role.USER if i % 2 == 0 else Role.ASSISTANT
        context.add_message(ChatMessage(role=role, content=f"Message {i}"))

    messages = context.get_messages()
    assert len(messages) == 5
    assert messages[0].role == Role.SYSTEM
    assert "You are a financial analysis assistant." in messages[0].content
    # Most recent non-system messages are retained
    assert messages[-1].content == "Message 9"


# ---------------------------------------------------------------------------
# 3. Async Tool Dispatcher Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dispatcher_sync_and_async_handlers() -> None:
    dispatcher = AsyncToolDispatcher()

    def sync_add(a: int, b: int) -> int:
        return a + b

    async def async_multiply(a: int, b: int) -> int:
        return a * b

    dispatcher.register_tool("add", sync_add)
    dispatcher.register_tool("multiply", async_multiply)

    res_add = await dispatcher.dispatch(ToolCallRequest(tool_name="add", arguments={"a": 2, "b": 3}))
    assert res_add.success is True
    assert res_add.result == 5

    res_mult = await dispatcher.dispatch(ToolCallRequest(tool_name="multiply", arguments={"a": 3, "b": 4}))
    assert res_mult.success is True
    assert res_mult.result == 12


@pytest.mark.asyncio
async def test_dispatcher_unregistered_and_exception_handling() -> None:
    dispatcher = AsyncToolDispatcher()

    def failing_tool() -> None:
        raise ValueError("Calculation failed")

    dispatcher.register_tool("fail", failing_tool)

    res_unreg = await dispatcher.dispatch(ToolCallRequest(tool_name="unknown", arguments={}))
    assert res_unreg.success is False
    assert "Unregistered tool" in (res_unreg.error_message or "")

    res_fail = await dispatcher.dispatch(ToolCallRequest(tool_name="fail", arguments={}))
    assert res_fail.success is False
    assert "Calculation failed" in (res_fail.error_message or "")


@pytest.mark.asyncio
async def test_dispatcher_duplicate_registration_raises() -> None:
    dispatcher = AsyncToolDispatcher()
    dispatcher.register_tool("test", lambda: None)
    with pytest.raises(ValueError, match="already registered"):
        dispatcher.register_tool("test", lambda: None)


# ---------------------------------------------------------------------------
# 4. Agent Orchestrator Loop Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_single_step_terminal() -> None:
    """Test orchestrator stopping when no tool calls are parsed (direct text response)."""
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct assistant answer"))

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    orchestrator = AgentOrchestrator(llm_client=llm_mock, dispatcher=dispatcher_mock, parser=parser_mock)

    # Canonical context creation with runtime rules
    context = make_context_with_runtime_rules()

    steps = []
    async for step in orchestrator.run_stream("Hello agent", context=context):
        steps.append(step)

    assert len(steps) == 1
    assert steps[0].step_number == 1
    assert steps[0].is_terminal is True
    assert steps[0].message.content == "Direct assistant answer"
    assert len(steps[0].executed_tools) == 0

    # System prompt (with rules) is still present after the run
    messages = context.get_messages()
    assert messages[0].role == Role.SYSTEM
    assert "You are a financial analysis assistant." in messages[0].content


@pytest.mark.asyncio
async def test_orchestrator_tool_execution_loop() -> None:
    """Test multi-step execution where a tool is called and then answered."""
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(
        side_effect=[
            LLMGenerateResult(text='{"name": "get_quote", "parameters": {"ticker": "AAPL"}}'),
            LLMGenerateResult(text="Apple is currently trading at $180."),
        ]
    )

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = [
        ParsedToolCall(tool_name="get_quote", arguments={"ticker": "AAPL"}),
        ToolParsingError("No tool call in final text"),
    ]

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-123",
            tool_name="get_quote",
            success=True,
            result={"price": 180.0},
        )
    )

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=True,
            max_validation_retries=0,
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )
    context = make_context_with_runtime_rules()

    steps = []
    async for step in orchestrator.run_stream("What is Apple price?", context=context):
        steps.append(step)

    assert len(steps) == 2

    assert steps[0].step_number == 1
    assert steps[0].is_terminal is False
    assert len(steps[0].executed_tools) == 1
    assert steps[0].executed_tools[0].result == {"price": 180.0}

    assert steps[1].step_number == 2
    assert steps[1].is_terminal is True
    assert steps[1].message.content == "Apple is currently trading at $180."

    # Rules remain in the system message after tool rounds
    assert context.get_messages()[0].role == Role.SYSTEM


@pytest.mark.asyncio
async def test_orchestrator_max_steps_exceeded() -> None:
    """Test orchestrator stopping cleanly when max_steps threshold is hit."""
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text='{"name": "loop_forever"}'))

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.return_value = ParsedToolCall(tool_name="loop_forever", arguments={})

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-loop",
            tool_name="loop_forever",
            success=True,
            result="ok",
        )
    )

    config = OrchestratorConfig(max_steps=2)
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()

    steps = []
    async for step in orchestrator.run_stream("Start loop", context=context):
        steps.append(step)

    assert len(steps) == 3
    assert steps[-1].is_terminal is True
    assert "Exceeded maximum iteration steps." in steps[-1].message.content


# ---------------------------------------------------------------------------
# 5. Native schema constraint forwarding (Step 2.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_forwards_native_schema_format_to_llm() -> None:
    """When use_native_constraint is enabled, forward a top-level format kwarg.

    The orchestrator must forward a top-level ``format`` kwarg to
    LLMClient.generate carrying the ToolCallResponse JSON Schema. The call
    must succeed (no TypeError).
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=True, ollama_version="0.5.4"),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    llm_mock.generate.assert_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" in call_kwargs, "orchestrator must forward the format kwarg"
    fmt = call_kwargs["format"]
    assert isinstance(fmt, dict), "format must be a JSON Schema dict"
    assert fmt.get("type") == "object"
    # Schema for ToolCallResponse must include the required tool_name field.
    assert "tool_name" in fmt.get("properties", {})


@pytest.mark.asyncio
async def test_orchestrator_omits_format_when_native_constraint_disabled() -> None:
    """Omit the format kwarg when native constraint is disabled.

    When use_native_constraint is disabled, the orchestrator must not send a
    ``format`` kwarg to LLMClient.generate.
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=False),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    llm_mock.generate.assert_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" not in call_kwargs, "format must be omitted when native constraint is disabled"


# ---------------------------------------------------------------------------
# 5b. Capability resolution (runtime version-driven format decision)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_orchestrator_format_included_when_remote_server_supports() -> None:
    """Remote server reports a supported version → native format IS sent.

    The LLMClient's get_ollama_version() returns "0.6.1" (supported),
    so the orchestrator must include the format kwarg.
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))
    # Simulate the remote server reporting a supported version
    llm_mock.get_ollama_version = AsyncMock(return_value="0.6.1")

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=True),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    llm_mock.generate.assert_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" in call_kwargs, "format must be included when server capability is confirmed"
    assert call_kwargs["format"]["type"] == "object"


@pytest.mark.asyncio
async def test_orchestrator_format_omitted_when_remote_server_unsupported() -> None:
    """Remote server reports an unsupported version → native format NOT sent.

    The LLMClient's get_ollama_version() returns "0.3.0" (below 0.5.0),
    so the orchestrator must NOT include the format kwarg.
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))
    # Simulate the remote server reporting an old unsupported version
    llm_mock.get_ollama_version = AsyncMock(return_value="0.3.0")

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=True),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    llm_mock.generate.assert_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" not in call_kwargs, "format must be omitted when server is known-unsupported"


@pytest.mark.asyncio
async def test_orchestrator_format_omitted_when_capability_unknown() -> None:
    """Remote capability cannot be determined → safe default: NO format.

    The LLMClient's get_ollama_version() returns None (unreachable/malformed),
    so the orchestrator must NOT assume support and must omit the format kwarg.
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))
    # Simulate the remote server being unreachable
    llm_mock.get_ollama_version = AsyncMock(return_value=None)

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=True),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    llm_mock.generate.assert_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" not in call_kwargs, (
        "format must be omitted when capability is UNKNOWN (safe default: do not assume support)"
    )


@pytest.mark.asyncio
async def test_orchestrator_static_ollama_version_override_works() -> None:
    """Static ollama_version config bypasses remote query and classifies correctly."""
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))
    # get_ollama_version should NOT be called when static override is set
    llm_mock.get_ollama_version = AsyncMock(return_value="0.3.0")

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=True,
            ollama_version="1.0.0",  # static override: supported
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    # Static override used → remote query NOT made
    llm_mock.get_ollama_version.assert_not_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" in call_kwargs, "static override of supported version → format included"


@pytest.mark.asyncio
async def test_orchestrator_get_ollama_version_not_called_when_disabled() -> None:
    """When use_native_constraint=False, no version query is made at all."""
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(return_value=LLMGenerateResult(text="Direct answer"))
    llm_mock.get_ollama_version = AsyncMock(return_value="0.5.4")

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("No JSON found")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)

    config = OrchestratorConfig(
        schema_config=SchemaConfig(use_native_constraint=False),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    async for _step in orchestrator.run_stream("Hello", context=context):
        pass

    # Version query must NOT be made when native constraint is disabled
    llm_mock.get_ollama_version.assert_not_awaited()
    call_kwargs = llm_mock.generate.call_args.kwargs
    assert "format" not in call_kwargs


# ---------------------------------------------------------------------------
# 6. Schema-violation retry path (Step 2.2)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_schema_retry_recovers_after_one_invalid_response() -> None:
    """When the first response is schema-invalid and the second is valid.

    The orchestrator must re-issue the LLM call with the retry prompt and
    succeed without falling through to the legacy parser for step 1.
    """
    invalid_json = '{"name": "get_quote", "parameters": {"ticker": "AAPL"}}'
    valid_json = '{"tool_name": "get_quote", "tool_args": {"ticker": "AAPL"}}'
    terminal_text = "Apple is currently trading at $180."

    # Step 1: call1=invalid → retry → call2=valid → tool dispatched
    # Step 2: call3=text → retry → call4=text → parser(raises) → terminal
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(
        side_effect=[
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=valid_json),
            LLMGenerateResult(text=terminal_text),
            LLMGenerateResult(text=terminal_text),
        ]
    )

    # Parser raises: proves it was NOT used for step 1 recovery
    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = ToolParsingError("Parser must not be the recovery path")

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-retry",
            tool_name="get_quote",
            success=True,
            result={"price": 180.0},
        )
    )

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=True,
            max_validation_retries=1,
            ollama_version="0.5.4",
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    steps = []
    async for step in orchestrator.run_stream("What is Apple price?", context=context):
        steps.append(step)

    # Step 1: 2 calls (invalid + valid retry). Step 2: 2 calls (text + retry text).
    assert llm_mock.generate.await_count == 4
    # Tool was dispatched from the valid retry response in step 1
    assert len(steps) == 2
    assert steps[0].is_terminal is False
    assert steps[0].executed_tools[0].result == {"price": 180.0}
    assert steps[1].is_terminal is True
    # Parser was called (in step 2 after retries exhausted) but step 1 succeeded
    # via retry — the tool result proves recovery without parser.
    assert parser_mock.parse.call_count == 1


@pytest.mark.asyncio
async def test_schema_retry_exhaustion_falls_to_parser() -> None:
    """When all retry attempts return schema-invalid responses, the budget exhausts.

    The legacy parser fallback is then invoked as a last resort.
    """
    invalid_json = '{"name": "get_quote", "parameters": {"ticker": "AAPL"}}'
    terminal_text = "Apple is currently trading at $180."

    # Step 1: call1,2,3 all invalid → retries exhausted → parser succeeds → tool
    # Step 2: call4,5,6 all text → retries exhausted → parser fails → terminal
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(
        side_effect=[
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=terminal_text),
            LLMGenerateResult(text=terminal_text),
            LLMGenerateResult(text=terminal_text),
        ]
    )

    # Step 1: parser succeeds (fallback). Step 2: parser fails (terminal).
    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = [
        ParsedToolCall(tool_name="get_quote", arguments={"ticker": "AAPL"}),
        ToolParsingError("No JSON in final text"),
    ]

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-exhaust",
            tool_name="get_quote",
            success=True,
            result={"price": 180.0},
        )
    )

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=True,
            max_validation_retries=2,
            ollama_version="0.5.4",
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    steps = []
    async for step in orchestrator.run_stream("What is Apple price?", context=context):
        steps.append(step)

    # Step 1: 3 calls (initial + 2 retries). Step 2: 3 calls (initial + 2 retries).
    assert llm_mock.generate.await_count == 6
    # Parser called once per step (after exhaustion)
    assert parser_mock.parse.call_count == 2
    # Tool executed in step 1 via parser fallback
    assert len(steps) == 2
    assert steps[0].is_terminal is False
    assert steps[0].executed_tools[0].result == {"price": 180.0}
    assert steps[1].is_terminal is True


@pytest.mark.asyncio
async def test_schema_retry_does_not_use_parser_as_primary_recovery() -> None:
    """Even when the parser COULD handle the response, it must NOT be invoked.

    During the retry budget the retry prompt is the primary recovery mechanism.
    """
    invalid_json = '{"name": "get_quote", "parameters": {"ticker": "AAPL"}}'
    terminal_text = "Apple is currently trading at $180."

    # Step 1: call1=invalid → retry → call2=invalid → exhausted → parser(succeeds) → tool
    # Step 2: call3=text → retry → call4=text → exhausted → parser(fails) → terminal
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(
        side_effect=[
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=invalid_json),
            LLMGenerateResult(text=terminal_text),
            LLMGenerateResult(text=terminal_text),
        ]
    )

    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = [
        ParsedToolCall(tool_name="get_quote", arguments={"ticker": "AAPL"}),
        ToolParsingError("No JSON in final text"),
    ]

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-gate",
            tool_name="get_quote",
            success=True,
            result="ok",
        )
    )

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=True,
            max_validation_retries=1,
            ollama_version="0.5.4",
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    steps = []
    async for step in orchestrator.run_stream("What is Apple price?", context=context):
        steps.append(step)

    # Step 1: 2 calls (initial + 1 retry). Step 2: 2 calls (initial + 1 retry).
    assert llm_mock.generate.await_count == 4
    # Parser called exactly once per step — only AFTER budget exhausted
    assert parser_mock.parse.call_count == 2
    # Verify the retry feedback message was injected into context
    msgs = context.get_messages()
    user_msgs = [m for m in msgs if m.role == Role.USER]
    retry_feedback_msgs = [
        m for m in user_msgs if "schema" in m.content.lower() or "did not match" in m.content.lower()
    ]
    assert len(retry_feedback_msgs) >= 1, "retry feedback message must be present in context"


@pytest.mark.asyncio
async def test_provider_compat_parser_fallback_when_native_disabled() -> None:
    """When use_native_constraint is False, the legacy parser IS the recovery path.

    The provider-compatibility mode expects the parser for non-JSON responses.
    No retry loop should be triggered (max_retries is forced to 0).
    """
    llm_mock = MagicMock(spec=LLMClient)
    llm_mock.generate = AsyncMock(
        side_effect=[
            LLMGenerateResult(text='{"name": "get_quote", "parameters": {"ticker": "AAPL"}}'),
            LLMGenerateResult(text="Apple is currently trading at $180."),
        ]
    )

    # Step 1: parser succeeds → tool. Step 2: parser fails → terminal.
    parser_mock = MagicMock(spec=ToolParser)
    parser_mock.parse.side_effect = [
        ParsedToolCall(tool_name="get_quote", arguments={"ticker": "AAPL"}),
        ToolParsingError("No JSON in final text"),
    ]

    dispatcher_mock = MagicMock(spec=AsyncToolDispatcher)
    dispatcher_mock.dispatch = AsyncMock(
        return_value=ToolCallResult(
            call_id="call-compat",
            tool_name="get_quote",
            success=True,
            result={"price": 180.0},
        )
    )

    config = OrchestratorConfig(
        schema_config=SchemaConfig(
            use_native_constraint=False,
            max_validation_retries=3,  # must be ignored when native is off
        ),
    )
    orchestrator = AgentOrchestrator(
        llm_client=llm_mock,
        dispatcher=dispatcher_mock,
        parser=parser_mock,
        options=OrchestratorOptions(config=config),
    )

    context = make_context_with_runtime_rules()
    steps = []
    async for step in orchestrator.run_stream("What is Apple price?", context=context):
        steps.append(step)

    # Exactly one LLM call per step (no retries when native is disabled)
    assert llm_mock.generate.await_count == 2
    # Parser is the immediate fallback (one call per step)
    assert parser_mock.parse.call_count == 2
    # Tool executed in step 1
    assert len(steps) == 2
    assert steps[0].is_terminal is False
    assert steps[0].executed_tools[0].result == {"price": 180.0}
    assert steps[1].is_terminal is True
    # No retry feedback messages in context (retry loop was never entered)
    user_msgs = [m for m in context.get_messages() if m.role == Role.USER]
    retry_msgs = [m for m in user_msgs if "schema" in m.content.lower() or "did not match" in m.content.lower()]
    assert len(retry_msgs) == 0, "no retry feedback when native constraint is disabled"
