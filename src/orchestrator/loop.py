# src/orchestrator/loop.py
from __future__ import annotations

import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

from src.config import settings
from src.core.telemetry import (
    RunContext,
    TelemetryMode,
    TrajectoryErrorRecord,
    TrajectoryEventType,
    TrajectoryRecord,
    TrajectoryRecorder,
)
from src.core.telemetry.run_context import get_current_run_context
from src.llm.client import LLMClient
from src.orchestrator.context import MessageContext
from src.orchestrator.dispatcher import AsyncToolDispatcher
from src.orchestrator.types import AgentStepResult, ChatMessage, Role, ToolCallRequest
from src.schema.config import SchemaConfig
from src.schema.constraint import detect_ollama_schema_support, format_schema_for_ollama
from src.schema.models import ToolCallResponse
from src.schema.validator import build_retry_messages, validate_response
from src.tools.parser import ToolParser


class OrchestratorConfig(BaseModel):
    """Configuration for the AgentOrchestrator."""

    max_steps: int = Field(default=10, ge=1, le=50)
    model_selection: str = "qwen2.5-coder:latest"
    temperature: float = 0.0
    mode: Literal["light", "full"] = "light"
    schema_config: SchemaConfig = Field(default_factory=lambda: settings.schema_config)


@dataclass
class OrchestratorOptions:
    """Grouped options for orchestrator initialisation."""

    config: OrchestratorConfig = field(default_factory=OrchestratorConfig)
    recorder: TrajectoryRecorder | None = None
    run_context: RunContext | None = None


class AgentOrchestrator:
    """Orchestrates the LLM, tool dispatcher, parser, and observational telemetry."""

    def __init__(
        self,
        llm_client: LLMClient,
        dispatcher: AsyncToolDispatcher,
        parser: ToolParser,
        options: OrchestratorOptions | None = None,
    ) -> None:
        """Initialize the orchestrator with explicit execution identity."""
        self.llm_client = llm_client
        self.dispatcher = dispatcher
        self.parser = parser
        self.options = options or OrchestratorOptions()
        self.config = self.options.config

        # Resolve run_context and recorder
        self.run_context = self.options.run_context
        if self.run_context is None and self.options.recorder is not None:
            self.run_context = self.options.recorder.run_context
        if self.run_context is None:
            self.run_context = get_current_run_context() or RunContext.new()

        # Ensure recorder is always set
        if self.options.recorder is not None:
            self.recorder = self.options.recorder
        else:
            self.recorder = TrajectoryRecorder.from_settings(
                self.run_context,
                mode=TelemetryMode(self.config.mode),
                model_tag=self.config.model_selection,
            )

        if self.recorder.run_context != self.run_context:
            raise ValueError("Orchestrator run_context must match the recorder run_context.")

        # Step 2.2 – Native schema capability (lazy-resolved, cached per-instance)
        # True=supported, False=unsupported, None=unknown/unresolved
        self._schema_capability: bool | None = None
        self._capability_resolved: bool = False

    async def run_stream(self, prompt: str, context: MessageContext) -> AsyncGenerator[AgentStepResult, None]:
        """Run the orchestration loop while recording an ordered causal trajectory."""
        run_started = False
        terminal_status = "aborted"
        final_step = 0
        started_at = time.perf_counter()
        run_span_id = self.recorder.start_span()

        try:
            self._record_run_start(run_span_id, prompt)
            run_started = True
            context.add_message(ChatMessage(role=Role.USER, content=prompt))

            for step in range(1, self.config.max_steps + 1):
                final_step = step
                step_span_id = self.recorder.start_span(parent_span_id=run_span_id)
                self._record_step_start(step, step_span_id, run_span_id)

                request_span_id = self.recorder.start_span(parent_span_id=step_span_id)

                tool_requests, assistant_msg = await self._handle_llm_response(
                    step, step_span_id, request_span_id, context
                )

                if not tool_requests:
                    terminal_status = "completed"
                    self._record_step_end(step, step_span_id, run_span_id, {"status": "completed", "tool_count": 0})
                    self.recorder.end_span(step_span_id)
                    yield AgentStepResult(step_number=step, message=assistant_msg, is_terminal=True)
                    return

                tool_results = await self._execute_tools(step, tool_requests, step_span_id, context)
                self._record_step_end(
                    step,
                    step_span_id,
                    run_span_id,
                    {"status": "continued", "tool_count": len(tool_requests)},
                )
                self.recorder.end_span(step_span_id)

                yield AgentStepResult(
                    step_number=step,
                    message=assistant_msg,
                    executed_tools=tool_results,
                    is_terminal=False,
                )

            terminal_status = "max_steps_exceeded"
            yield AgentStepResult(
                step_number=self.config.max_steps,
                message=ChatMessage(role=Role.ASSISTANT, content="Exceeded maximum iteration steps."),
                is_terminal=True,
            )
        except Exception:
            terminal_status = "failed"
            raise
        finally:
            if run_started:
                self._record_run_end(run_span_id, final_step, started_at, terminal_status)
            self.recorder.end_span(run_span_id)
            self.recorder.flush()
            self.recorder.close()

    def _record_run_start(self, span_id: UUID, prompt: str) -> None:
        """Emit RUN_START event."""
        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.RUN_START,
                component="orchestrator",
                span_id=span_id,
                model_tag=self.config.model_selection,
                payload={
                    "prompt": prompt,
                    "max_steps": self.config.max_steps,
                    "temperature": self.config.temperature,
                },
            )
        )

    def _record_step_start(self, step: int, span_id: UUID, parent_span_id: UUID) -> None:
        """Emit STEP_START event."""
        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.STEP_START,
                component="orchestrator",
                span_id=span_id,
                parent_span_id=parent_span_id,
                step_index=step,
            )
        )

    def _record_step_end(self, step: int, span_id: UUID, parent_span_id: UUID, payload: dict[str, Any]) -> None:
        """Emit STEP_END event."""
        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.STEP_END,
                component="orchestrator",
                span_id=span_id,
                parent_span_id=parent_span_id,
                step_index=step,
                payload=payload,
            )
        )

    def _record_run_end(self, span_id: UUID, final_step: int, started_at: float, terminal_status: str) -> None:
        """Emit RUN_END event."""
        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.RUN_END,
                component="orchestrator",
                span_id=span_id,
                step_index=final_step or None,
                latency_ms=(time.perf_counter() - started_at) * 1000,
                payload={"status": terminal_status, "final_step": final_step},
            )
        )

    async def _resolve_schema_capability(self) -> bool:
        """Determine whether to send the native JSON Schema constraint.

        Resolution order:
          1. If ``use_native_constraint`` is False → never send (explicit opt-out).
          2. If ``SchemaConfig.ollama_version`` is set → classify that static value.
          3. Otherwise → query the configured remote Ollama endpoint once, cache result.

        Policy for unknown capability (version unresolvable):
          Do NOT send the native constraint.  This is the safe default:
          an unsupported ``format`` key may cause the server to reject the
          entire request, whereas omitting it preserves existing behavior.

        Returns:
            True if the native ``format`` kwarg should be included in the LLM request.
        """
        if not self.config.schema_config.use_native_constraint:
            return False

        if self._capability_resolved:
            return self._schema_capability is True

        # Resolve: prefer static config override, then remote query
        if self.config.schema_config.ollama_version is not None:
            self._schema_capability = detect_ollama_schema_support(self.config.schema_config.ollama_version)
        else:
            version = await self.llm_client.get_ollama_version()
            self._schema_capability = detect_ollama_schema_support(version)

        self._capability_resolved = True
        return self._schema_capability is True

    async def _build_generate_kwargs(self, prompt_payload: Any) -> dict[str, Any]:
        """Build the kwargs for an LLM generate call, including schema constraints.

        The native schema ``format`` kwarg is only included when:
          * ``use_native_constraint`` is enabled AND
          * the remote Ollama server capability is confirmed (>= 0.5.0).

        When capability is unknown or unsupported, the request is constructed
        without the ``format`` key and the existing retry/fallback path handles
        schema validation.
        """
        kwargs: dict[str, Any] = {
            "prompt": prompt_payload,
            "model": self.config.model_selection,
            "temperature": self.config.temperature,
        }
        if await self._resolve_schema_capability():
            schema_params = format_schema_for_ollama(
                ToolCallResponse,
                strict=self.config.schema_config.strict_mode,
                additional_properties=self.config.schema_config.additional_properties,
            )
            kwargs.update(schema_params)
        return kwargs

    async def _call_llm(
        self,
        step: int,
        prompt_payload: Any,
        step_span_id: UUID,
        request_span_id: UUID,
    ) -> str:
        """Perform LLM call with telemetry and schema constraints."""
        request_started = time.perf_counter()
        generate_kwargs = await self._build_generate_kwargs(prompt_payload)

        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.PROMPT_SENT,
                component="llm",
                span_id=request_span_id,
                parent_span_id=step_span_id,
                model_tag=self.config.model_selection,
                step_index=step,
                payload={
                    "messages": prompt_payload,
                    "temperature": self.config.temperature,
                    "format_constrained": "format" in generate_kwargs,
                },
            )
        )

        try:
            result = await self.llm_client.generate(**generate_kwargs)
        except Exception as exc:
            self.recorder.record_error(
                TrajectoryErrorRecord(
                    component="llm",
                    message=str(exc),
                    step_index=step,
                    span_id=request_span_id,
                    parent_span_id=step_span_id,
                    error_type=type(exc).__name__,
                )
            )
            raise
        finally:
            self.recorder.end_span(request_span_id)

        latency_ms = (time.perf_counter() - request_started) * 1000
        self.recorder.record(
            TrajectoryRecord(
                event_type=TrajectoryEventType.LLM_RESPONSE,
                component="llm",
                span_id=request_span_id,
                parent_span_id=step_span_id,
                model_tag=self.config.model_selection,
                step_index=step,
                latency_ms=latency_ms,
                prompt_tokens=result.prompt_tokens,
                completion_tokens=result.completion_tokens,
                payload={"response": result.text},
            )
        )
        return result.text

    async def _handle_llm_response(
        self,
        step: int,
        step_span_id: UUID,
        request_span_id: UUID,
        context: MessageContext,
    ) -> tuple[list[ToolCallRequest], ChatMessage]:
        """Parse LLM response with schema validation and bounded retry on violation.

        Step 2.2: When the LLM is called with a native schema constraint and
        the response fails Pydantic validation, the failure is treated as a
        recoverable schema violation.  The orchestrator builds a retry prompt
        via ``build_retry_messages``, re-issues the LLM call, and repeats up
        to ``SchemaConfig.max_validation_retries`` times.

        Only after the retry budget is exhausted (or when native constraint
        is disabled) does the response fall through to the legacy
        ``self.parser.parse`` as a gated provider-compatibility fallback.
        """
        strict = self.config.schema_config.strict_mode
        max_retries = (
            self.config.schema_config.max_validation_retries if self.config.schema_config.use_native_constraint else 0
        )

        # --- initial attempt ------------------------------------------------
        payload = context.to_ollama_payload()
        raw = await self._call_llm(step, payload, step_span_id, request_span_id)
        val = validate_response(raw, ToolCallResponse, strict=strict)

        # --- bounded retry loop ---------------------------------------------
        attempts = 0
        while not val.valid and attempts < max_retries:
            self.recorder.record_error(
                TrajectoryErrorRecord(
                    component="schema_validator",
                    message=val.error_summary(),
                    step_index=step,
                    span_id=request_span_id,
                    parent_span_id=step_span_id,
                    error_type=val.error_type.value if val.error_type else "SchemaValidationError",
                )
            )
            retry_messages = build_retry_messages(payload, val, assistant_content=raw)
            delta = retry_messages[len(payload) :]
            context.append_raw_dicts(delta)
            payload = retry_messages
            raw = await self._call_llm(step, payload, step_span_id, request_span_id)
            val = validate_response(raw, ToolCallResponse, strict=strict)
            attempts += 1

        # Record final validation failure when the retry loop never ran (max_retries=0)
        if not val.valid and attempts == 0:
            self.recorder.record_error(
                TrajectoryErrorRecord(
                    component="schema_validator",
                    message=val.error_summary(),
                    step_index=step,
                    span_id=request_span_id,
                    parent_span_id=step_span_id,
                    error_type=val.error_type.value if val.error_type else "SchemaValidationError",
                )
            )

        # --- resolve tool requests -------------------------------------------
        tool_requests: list[ToolCallRequest] = []
        if val.valid and isinstance(val.data, ToolCallResponse):
            tool_requests.append(
                ToolCallRequest(
                    tool_name=val.data.tool_name,
                    arguments=val.data.tool_args,
                )
            )
        else:
            # Gated fallback: legacy parser as a provider-compatibility last
            # resort.  Reached only when:
            #   * use_native_constraint is False (provider-compat path), OR
            #   * the retry budget is exhausted on the native-constraint path.
            try:
                parsed = self.parser.parse(raw)
                tool_requests.append(
                    ToolCallRequest(
                        tool_name=parsed.tool_name,
                        arguments=parsed.arguments,
                    )
                )
            except Exception as exc:
                self.recorder.record_error(
                    TrajectoryErrorRecord(
                        component="tool_parser",
                        message=str(exc),
                        step_index=step,
                        span_id=request_span_id,
                        parent_span_id=step_span_id,
                        error_type=type(exc).__name__,
                    )
                )

        assistant_msg = ChatMessage(
            role=Role.ASSISTANT,
            content=raw,
            tool_calls=tool_requests if tool_requests else None,
        )
        context.add_message(assistant_msg)
        return tool_requests, assistant_msg

    async def _execute_tools(
        self,
        step: int,
        tool_requests: list[ToolCallRequest],
        step_span_id: UUID,
        context: MessageContext,
    ) -> list[Any]:
        """Dispatch and record all tool calls in this step."""
        results = []
        for request in tool_requests:
            tool_span_id = self.recorder.start_span(parent_span_id=step_span_id)
            self.recorder.record(
                TrajectoryRecord(
                    event_type=TrajectoryEventType.TOOL_CALL,
                    component="orchestrator",
                    span_id=tool_span_id,
                    parent_span_id=step_span_id,
                    step_index=step,
                    tool_name=request.tool_name,
                    tool_args=request.arguments,
                    payload={"call_id": request.call_id},
                )
            )

            tool_started = time.perf_counter()
            response = await self.dispatcher.dispatch(request)
            tool_latency_ms = (time.perf_counter() - tool_started) * 1000
            results.append(response)

            tool_msg_content = str(response.result) if response.success else f"Error: {response.error_message}"
            context.add_message(
                ChatMessage(
                    role=Role.TOOL,
                    name=response.tool_name,
                    content=tool_msg_content,
                    tool_call_id=response.call_id,
                )
            )

            if response.success:
                self.recorder.record(
                    TrajectoryRecord(
                        event_type=TrajectoryEventType.TOOL_RESULT,
                        component="tool_dispatcher",
                        span_id=tool_span_id,
                        parent_span_id=step_span_id,
                        step_index=step,
                        tool_name=response.tool_name,
                        latency_ms=tool_latency_ms,
                        tool_result_summary={"success": True, "result": response.result},
                        payload={"call_id": response.call_id},
                    )
                )
            else:
                self.recorder.record_error(
                    TrajectoryErrorRecord(
                        component="tool_dispatcher",
                        message=response.error_message or "Tool execution failed.",
                        step_index=step,
                        span_id=tool_span_id,
                        parent_span_id=step_span_id,
                        error_type="ToolExecutionError",
                    )
                )
                self.recorder.record(
                    TrajectoryRecord(
                        event_type=TrajectoryEventType.TOOL_RESULT,
                        component="tool_dispatcher",
                        span_id=tool_span_id,
                        parent_span_id=step_span_id,
                        step_index=step,
                        tool_name=response.tool_name,
                        latency_ms=tool_latency_ms,
                        tool_result_summary={"success": False, "error": response.error_message},
                        payload={"call_id": response.call_id},
                    )
                )
            self.recorder.end_span(tool_span_id)

        return results
