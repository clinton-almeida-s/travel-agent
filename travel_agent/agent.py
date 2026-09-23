"""The agentic loop: LLM -> tool calls -> results -> LLM, until a final answer.

Streams progress to the console. Caps at ``settings.max_tool_iterations``
tool rounds to avoid runaway loops.
"""
from __future__ import annotations

import json
import traceback

from . import llm
from .config import settings
from .prompts import SYSTEM_PROMPT
from .schemas import TOOLS
from .tools import TOOL_REGISTRY


def _truncate(text: str, limit: int = 6000) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + f"\n…[truncated {len(text) - limit} chars]"


def run_agent(trip_brief: str, verbose: bool = True) -> str:
    """Run the travel-planning agent on a trip brief. Returns the final plan text."""
    messages: list[dict] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": trip_brief},
    ]

    for iteration in range(1, settings.max_tool_iterations + 1):
        try:
            assistant = llm.chat(messages, TOOLS)
        except llm.LLMError as exc:
            return f"Sorry — I couldn't reach the language model: {exc}"

        messages.append(assistant)
        tool_calls = assistant.get("tool_calls") or []

        if assistant.get("content") and verbose:
            print(assistant["content"])

        if not tool_calls:
            return assistant.get("content") or "I couldn't produce a plan. Please try again."

        for tc in tool_calls:
            name, args = tc["name"], tc.get("arguments") or {}
            if verbose:
                print(f"\n  🔧 {name}({json.dumps(args)[:120]})")
            func = TOOL_REGISTRY.get(name)
            if func is None:
                result: dict = {"error": f"Unknown tool '{name}'.", "hint": "Use one of the provided tools."}
            else:
                try:
                    raw = func(**args)
                    result = raw if isinstance(raw, dict) else {"result": raw}
                except TypeError as exc:
                    result = {"error": f"Bad arguments for {name}: {exc}", "hint": "Check required parameters."}
                except Exception:
                    result = {"error": f"{name} crashed: {traceback.format_exc(limit=2)}", "hint": "Retry or skip."}
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "name": name,
                    "content": _truncate(json.dumps(result, default=str)),
                }
            )
        if verbose:
            print(f"  …round {iteration} done, thinking…")

    return (
        "I hit my tool-call limit before finishing. Here's what I have so far — "
        "please ask me to continue or narrow the request."
    )
