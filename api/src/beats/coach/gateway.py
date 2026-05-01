"""LLM Gateway — single entry point for all Anthropic calls.

Responsibilities:
  - Prompt-caching via cache_control breakpoints
  - Streaming and non-streaming completions
  - Usage tracking (input/output tokens, cache reads/writes, cost)
  - Per-user monthly cost ceiling enforcement
  - Retries with jitter on transient errors
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import anthropic
from anthropic.lib.streaming import MessageStreamEvent
from anthropic.types import ContentBlock, Message

from beats.coach.usage import UsageTracker
from beats.settings import settings

logger = logging.getLogger(__name__)

SONNET_INPUT_COST_PER_MTOK = 3.0
SONNET_OUTPUT_COST_PER_MTOK = 15.0
SONNET_CACHE_WRITE_PER_MTOK = 3.75
SONNET_CACHE_READ_PER_MTOK = 0.30

MAX_RETRIES = 3
BASE_DELAY_S = 1.0


@dataclass
class GatewayResponse:
    content: list[ContentBlock]
    model: str
    input_tokens: int
    output_tokens: int
    cache_creation_input_tokens: int
    cache_read_input_tokens: int
    cost_usd: float
    stop_reason: str | None = None


@dataclass
class CacheSpec:
    """Mark which message indices get cache_control breakpoints."""

    system_cached: bool = True
    cached_turn_indices: list[int] = field(default_factory=list)


def _estimate_cost(
    input_tokens: int,
    output_tokens: int,
    cache_creation: int,
    cache_read: int,
) -> float:
    base_input = max(0, input_tokens - cache_creation - cache_read)
    return (
        base_input * SONNET_INPUT_COST_PER_MTOK / 1_000_000
        + output_tokens * SONNET_OUTPUT_COST_PER_MTOK / 1_000_000
        + cache_creation * SONNET_CACHE_WRITE_PER_MTOK / 1_000_000
        + cache_read * SONNET_CACHE_READ_PER_MTOK / 1_000_000
    )


def _get_client() -> anthropic.AsyncAnthropic:
    if not settings.anthropic_api_key:
        raise RuntimeError("ANTHROPIC_API_KEY is not configured")
    return anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)


def _apply_cache_control(
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    spec: CacheSpec,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Inject cache_control breakpoints per the spec.

    Returns (system_blocks, messages) ready for the API call.
    """
    if isinstance(system, str):
        system_blocks: list[dict[str, Any]] = [{"type": "text", "text": system}]
    else:
        system_blocks = list(system)

    if spec.system_cached and system_blocks:
        system_blocks[-1] = {**system_blocks[-1], "cache_control": {"type": "ephemeral"}}

    msgs = [dict(m) for m in messages]
    for idx in spec.cached_turn_indices:
        if 0 <= idx < len(msgs):
            content = msgs[idx].get("content")
            if isinstance(content, str):
                msgs[idx]["content"] = [
                    {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                ]
            elif isinstance(content, list) and content:
                last = {**content[-1], "cache_control": {"type": "ephemeral"}}
                msgs[idx]["content"] = [*content[:-1], last]

    return system_blocks, msgs


async def complete(
    *,
    user_id: str,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    cache_spec: CacheSpec | None = None,
    temperature: float = 0.4,
    max_tokens: int = 4096,
    purpose: str = "coach",
) -> GatewayResponse:
    """Non-streaming completion with caching, usage tracking, and cost enforcement."""
    tracker = UsageTracker(user_id)
    await tracker.enforce_budget()

    spec = cache_spec or CacheSpec()
    system_blocks, cached_messages = _apply_cache_control(system, messages, spec)
    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": settings.coach_model,
        "system": system_blocks,
        "messages": cached_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools

    response: Message | None = None
    for attempt in range(MAX_RETRIES):
        try:
            response = await client.messages.create(**kwargs)
            break
        except anthropic.APIStatusError as exc:
            if exc.status_code in (429, 500, 502, 503, 529) and attempt < MAX_RETRIES - 1:
                delay = BASE_DELAY_S * (2**attempt) + random.uniform(0, 1)
                logger.warning("Anthropic %s, retrying in %.1fs", exc.status_code, delay)
                await asyncio.sleep(delay)
                continue
            raise

    if response is None:
        raise RuntimeError("Anthropic call failed after retries")

    usage = response.usage
    cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cost = _estimate_cost(usage.input_tokens, usage.output_tokens, cache_creation, cache_read)

    result = GatewayResponse(
        content=list(response.content),
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation_input_tokens=cache_creation,
        cache_read_input_tokens=cache_read,
        cost_usd=cost,
        stop_reason=response.stop_reason,
    )

    await tracker.record(
        model=response.model,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cache_creation=cache_creation,
        cache_read=cache_read,
        cost_usd=cost,
        purpose=purpose,
    )

    return result


async def stream(
    *,
    user_id: str,
    system: str | list[dict[str, Any]],
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]] | None = None,
    cache_spec: CacheSpec | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    purpose: str = "chat",
) -> AsyncIterator[MessageStreamEvent]:
    """Streaming completion. Yields the SDK's high-level stream events
    (TextEvent / CitationEvent / ThinkingEvent / etc.) from
    ``client.messages.stream``. The previous annotation said
    ``RawMessageStreamEvent`` but the stream manager iterator yields
    the parsed wrapper events, not the raw SSE protocol events —
    consumers expecting `.text` / `.delta` on the events would have
    found AttributeErrors had this ever been called.

    Usage is tracked at the end via the `message_stop` event which carries
    the final usage stats.
    """
    tracker = UsageTracker(user_id)
    await tracker.enforce_budget()

    spec = cache_spec or CacheSpec()
    system_blocks, cached_messages = _apply_cache_control(system, messages, spec)
    client = _get_client()

    kwargs: dict[str, Any] = {
        "model": settings.coach_model,
        "system": system_blocks,
        "messages": cached_messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if tools:
        kwargs["tools"] = tools

    async with client.messages.stream(**kwargs) as stream_mgr:
        async for event in stream_mgr:
            yield event

        final = await stream_mgr.get_final_message()
        usage = final.usage
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cost = _estimate_cost(usage.input_tokens, usage.output_tokens, cache_creation, cache_read)
        await tracker.record(
            model=final.model,
            input_tokens=usage.input_tokens,
            output_tokens=usage.output_tokens,
            cache_creation=cache_creation,
            cache_read=cache_read,
            cost_usd=cost,
            purpose=purpose,
        )
