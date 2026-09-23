"""LLM backend abstraction with function-calling support.

``chat(messages, tools)`` returns an assistant message dict::

    {"role": "assistant", "content": str | None,
     "tool_calls": [{"id": str, "name": str, "arguments": dict}]}

Message roles: "system" | "user" | "assistant" | "tool".
Tool messages: {"role": "tool", "tool_call_id": str, "name": str, "content": str}.

SDK imports are lazy so the package imports without credentials or SDKs.
"""
from __future__ import annotations

import json
import time

from .config import settings
from .schemas import to_gemini_tools, to_groq_tools


class LLMError(RuntimeError):
    """Raised when the LLM backend cannot be used."""


def chat(messages: list[dict], tools: list[dict]) -> dict:
    """Send messages + tool schemas to the configured backend."""
    provider = settings.llm_provider
    if provider == "gemini":
        return _gemini_chat(messages, tools)
    if provider == "groq":
        return _groq_chat(messages, tools)
    raise LLMError(f"Unknown LLM_PROVIDER '{settings.llm_provider}' (use gemini|groq).")


# ── Gemini (google-genai) ──────────────────────────────────────────────────

def _function_call_part(name: str, args: dict, thought_signature=None):
    """Build a model FunctionCall part, preserving the thought signature.

    Thinking-capable Gemini models reject a request when a function call
    replayed from history lacks the thought_signature the model originally
    returned on that part (400 INVALID_ARGUMENT). The signature lives on
    the Part (not on FunctionCall), so we capture it from the response part
    and set it back on the rebuilt part here.
    """
    from google.genai import types

    part = types.Part(function_call=types.FunctionCall(name=name, args=args or {}))
    if thought_signature:
        try:
            part.thought_signature = thought_signature
        except Exception:
            pass  # older google-genai without the field
    return part


def _generate_with_retry(client, model: str, contents: list, config, attempts: int = 3):
    """Call generate_content, retrying transient 429/503 errors with backoff."""
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            return client.models.generate_content(model=model, contents=contents, config=config)
        except Exception as exc:
            last_exc = exc
            msg = str(exc)
            retryable = any(code in msg for code in ("503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"))
            if not retryable or attempt == attempts - 1:
                raise LLMError(f"Gemini request failed: {exc}") from exc
            time.sleep(2**attempt)
    raise LLMError(f"Gemini request failed: {last_exc}") from last_exc


def _gemini_chat(messages: list[dict], tools: list[dict]) -> dict:
    try:
        from google import genai
        from google.genai import types
    except ImportError as exc:
        raise LLMError("google-genai is not installed. Run: pip install google-genai") from exc
    if not settings.gemini_api_key:
        raise LLMError("GEMINI_API_KEY is not set.")

    system_instruction = None
    contents: list = []
    for m in messages:
        role = m["role"]
        if role == "system":
            system_instruction = m["content"]
        elif role == "user":
            contents.append(types.Content(role="user", parts=[types.Part.from_text(text=m["content"] or "")]))
        elif role == "assistant":
            parts = []
            if m.get("content"):
                parts.append(types.Part.from_text(text=m["content"]))
            for tc in m.get("tool_calls", []):
                parts.append(
                    _function_call_part(tc["name"], tc["arguments"], tc.get("thought_signature"))
                )
            contents.append(types.Content(role="model", parts=parts))
        elif role == "tool":
            try:
                payload = json.loads(m["content"]) if isinstance(m["content"], str) else m["content"]
            except json.JSONDecodeError:
                payload = {"result": m["content"]}
            contents.append(
                types.Content(
                    role="user",
                    parts=[types.Part.from_function_response(name=m["name"], response=payload)],
                )
            )

    client = genai.Client(api_key=settings.gemini_api_key)
    config = types.GenerateContentConfig(
        system_instruction=system_instruction,
        tools=to_gemini_tools(tools),
    )
    response = _generate_with_retry(client, settings.gemini_model, contents, config)

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    for cand in response.candidates or []:
        for part in (cand.content.parts or []):
            if part.text:
                text_parts.append(part.text)
            fc = getattr(part, "function_call", None)
            if fc:
                args = dict(fc.args) if fc.args else {}
                tool_calls.append(
                    {
                        "id": f"gemini-{fc.name}-{len(tool_calls)}",
                        "name": fc.name,
                        "arguments": args,
                        # Thought signature lives on the Part, not the FunctionCall.
                        "thought_signature": getattr(part, "thought_signature", None),
                    }
                )
    return {
        "role": "assistant",
        "content": "".join(text_parts) or None,
        "tool_calls": tool_calls,
    }


# ── Groq (OpenAI-compatible) ───────────────────────────────────────────────

def _groq_chat(messages: list[dict], tools: list[dict]) -> dict:
    try:
        from groq import Groq
    except ImportError as exc:
        raise LLMError("groq SDK is not installed. Run: pip install groq") from exc
    if not settings.groq_api_key:
        raise LLMError("GROQ_API_KEY is not set.")

    oai_messages: list[dict] = []
    for m in messages:
        role = m["role"]
        if role == "system":
            oai_messages.append({"role": "system", "content": m["content"]})
        elif role == "user":
            oai_messages.append({"role": "user", "content": m["content"]})
        elif role == "assistant":
            msg: dict = {"role": "assistant", "content": m.get("content")}
            if m.get("tool_calls"):
                msg["tool_calls"] = [
                    {
                        "id": tc["id"],
                        "type": "function",
                        "function": {"name": tc["name"], "arguments": json.dumps(tc["arguments"])},
                    }
                    for tc in m["tool_calls"]
                ]
            oai_messages.append(msg)
        elif role == "tool":
            oai_messages.append(
                {
                    "role": "tool",
                    "tool_call_id": m["tool_call_id"],
                    "content": m["content"] if isinstance(m["content"], str) else json.dumps(m["content"]),
                }
            )

    client = Groq(api_key=settings.groq_api_key)
    try:
        completion = client.chat.completions.create(
            model=settings.groq_model,
            messages=oai_messages,
            tools=to_groq_tools(tools),
        )
    except Exception as exc:
        raise LLMError(f"Groq request failed: {exc}") from exc

    choice = completion.choices[0].message
    tool_calls = []
    for tc in choice.tool_calls or []:
        try:
            args = json.loads(tc.function.arguments or "{}")
        except json.JSONDecodeError:
            args = {}
        tool_calls.append({"id": tc.id, "name": tc.function.name, "arguments": args})
    return {"role": "assistant", "content": choice.content, "tool_calls": tool_calls}
