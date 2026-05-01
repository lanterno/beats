"""Chat with tool-use loop.

Implements the conversation flow:
  1. Build context (system + user + day) via build_coach_messages
  2. Load conversation history (last 20 turns)
  3. Append user message
  4. Call Anthropic; on tool_use blocks, execute tools, inject tool_result, loop
  5. Persist messages
  6. Yield SSE events for the UI

Note: v1 uses non-streaming `complete()` per round, not `stream()`. The SSE
transport to the client is real — events are yielded incrementally — but each
LLM round resolves fully before yielding. True token-by-token streaming with
tool-use is significantly more complex (partial tool_use blocks, incremental
JSON parsing) and is deferred to a follow-up.
"""

from __future__ import annotations

import logging
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

from anthropic.types import TextBlock, ToolUseBlock

from beats.coach.context import build_coach_messages
from beats.coach.gateway import complete
from beats.coach.repos import COACH_CONVERSATIONS_COLLECTION, build_repos
from beats.coach.tools import TOOL_SCHEMAS, execute_tool
from beats.infrastructure.database import Database

logger = logging.getLogger(__name__)

MAX_HISTORY_TURNS = 20
TOOL_RESULT_DISPLAY_LIMIT = 500


async def _load_history(user_id: str, conversation_id: str) -> list[dict[str, Any]]:
    db = Database.get_db()
    cursor = (
        db[COACH_CONVERSATIONS_COLLECTION]
        .find(
            {"user_id": user_id, "conversation_id": conversation_id},
            {"_id": 0, "role": 1, "content": 1},
        )
        .sort("created_at", -1)
        .limit(MAX_HISTORY_TURNS)
    )
    rows = await cursor.to_list(MAX_HISTORY_TURNS)
    rows.reverse()
    return [{"role": r["role"], "content": r["content"]} for r in rows]


async def _persist_message(
    user_id: str,
    conversation_id: str,
    role: str,
    content: str,
    tool_calls: list[dict] | None = None,
) -> None:
    db = Database.get_db()
    doc: dict[str, Any] = {
        "user_id": user_id,
        "conversation_id": conversation_id,
        "role": role,
        "content": content,
        "created_at": datetime.now(UTC),
    }
    if tool_calls:
        doc["tool_calls"] = tool_calls
    await db[COACH_CONVERSATIONS_COLLECTION].insert_one(doc)


async def handle_chat_turn(
    *,
    user_id: str,
    message: str,
    conversation_id: str | None = None,
) -> AsyncIterator[dict[str, Any]]:
    """Yields SSE-ready dicts: {type, ...payload}.

    Event types:
      - {"type": "text", "text": "..."}
      - {"type": "tool_use", "name": "...", "input": {...}}
      - {"type": "tool_result", "name": "...", "result": "..."}
      - {"type": "done", "conversation_id": "..."}
    """
    conv_id = conversation_id or str(uuid.uuid4())
    history = await _load_history(user_id, conv_id)

    system, all_messages, spec = await build_coach_messages(user_id, message, history=history)

    await _persist_message(user_id, conv_id, "user", message)

    # Build tool context once for the entire turn
    repos = await build_repos(user_id)
    projects = await repos.project.list()

    # Tool-use loop: keep calling until we get a non-tool response
    max_rounds = 5
    for _ in range(max_rounds):
        result = await complete(
            user_id=user_id,
            system=system,
            messages=all_messages,
            tools=TOOL_SCHEMAS,
            cache_spec=spec,
            temperature=0.7,
            max_tokens=4096,
            purpose="chat",
        )

        text_parts: list[str] = []
        tool_calls_made: list[dict] = []
        tool_use_blocks: list[dict[str, Any]] = []

        for block in result.content:
            if isinstance(block, TextBlock):
                text_parts.append(block.text)
                yield {"type": "text", "text": block.text}
            elif isinstance(block, ToolUseBlock):
                # isinstance narrows the union for the type checker —
                # the previous `block.type == "tool_use"` discriminator
                # was correct at runtime but ty couldn't see it, leaving
                # `.name` / `.input` / `.id` flagged as unresolved on
                # the broader content-block union.
                tool_calls_made.append({"name": block.name, "input": block.input})
                yield {
                    "type": "tool_use",
                    "name": block.name,
                    "input": block.input,
                }
                tool_use_blocks.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        if not tool_use_blocks:
            full_text = "".join(text_parts)
            if not full_text and not tool_calls_made:
                logger.warning("LLM returned empty content for user=%s", user_id)
            await _persist_message(
                user_id, conv_id, "assistant", full_text, tool_calls_made or None
            )
            yield {"type": "done", "conversation_id": conv_id}
            return

        # Execute tools and build tool_result messages
        assistant_content: list[dict[str, Any]] = []
        for block in result.content:
            if isinstance(block, TextBlock):
                assistant_content.append({"type": "text", "text": block.text})
            elif isinstance(block, ToolUseBlock):
                assistant_content.append(
                    {
                        "type": "tool_use",
                        "id": block.id,
                        "name": block.name,
                        "input": block.input,
                    }
                )

        all_messages.append({"role": "assistant", "content": assistant_content})

        tool_results: list[dict[str, Any]] = []
        for tb in tool_use_blocks:
            try:
                result_text = await execute_tool(
                    user_id, tb["name"], tb["input"], repos=repos, projects=projects
                )
            except Exception as exc:
                result_text = f"Error: {exc}"

            yield {
                "type": "tool_result",
                "name": tb["name"],
                "result": result_text[:TOOL_RESULT_DISPLAY_LIMIT],
            }
            tool_results.append(
                {
                    "type": "tool_result",
                    "tool_use_id": tb["id"],
                    "content": result_text,
                }
            )

        all_messages.append({"role": "user", "content": tool_results})

    # Exhausted tool rounds
    yield {"type": "text", "text": "I've reached the tool-call limit for this turn."}
    yield {"type": "done", "conversation_id": conv_id}
