"""LLM client with a native tool-calling loop.

Supports OpenAI (function calling) and Anthropic (tool use) over plain httpx —
no SDK dependency. The loop runs at most ``MAX_TOOL_ROUNDS`` rounds, then forces
a final text answer so a chat never dead-ends.
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from . import config
from .prompts import FINAL_ANSWER_PROMPT
from .tools import get_schemas, run_tool

log = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 3

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class LLMError(Exception):
    """Raised when the LLM provider can't be reached or rejects the request."""


def _tools_payload(tools: list[dict]) -> Any:
    """Convert the unified {name, description, parameters} schema to provider format."""
    if config.LLM_PROVIDER == "anthropic":
        return [
            {"name": t["name"], "description": t["description"], "input_schema": t["parameters"]}
            for t in tools
        ]
    return [{"type": "function", "function": t} for t in tools]


async def chat(messages: list[dict[str, str]], tools: list[dict] | None = None) -> str:
    """Run the tool-calling conversation and return the final text answer."""
    if tools is None:
        tools = get_schemas()

    if config.LLM_PROVIDER == "anthropic":
        return await _anthropic_loop(messages, tools)
    return await _openai_loop(messages, tools)


# ---------------------------------------------------------------------------
# OpenAI
# ---------------------------------------------------------------------------

async def _openai_request(client: httpx.AsyncClient, messages: list[dict], tools: list[dict]) -> dict:
    if not config.OPENAI_API_KEY:
        raise LLMError("no OpenAI API key configured")
    body: dict[str, Any] = {"model": config.LLM_MODEL, "messages": messages}
    if tools:
        body["tools"] = _tools_payload(tools)
        body["tool_choice"] = "auto"
    try:
        resp = await client.post(
            config.LLM_BASE_URL.rstrip("/") + "/chat/completions",
            headers={"Authorization": f"Bearer {config.OPENAI_API_KEY}"},
            json=body,
        )
    except httpx.HTTPError as err:
        raise LLMError(f"can't reach OpenAI ({err})") from err
    if resp.status_code in (401, 403):
        raise LLMError("OpenAI rejected the API key")
    if resp.status_code >= 400:
        raise LLMError(f"OpenAI error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


async def _openai_loop(messages: list[dict], tools: list[dict]) -> str:
    msgs = [dict(m) for m in messages]
    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            body = await _openai_request(client, msgs, tools)
            choice = (body.get("choices") or [{}])[0]
            message = choice.get("message") or {}
            tool_calls = message.get("tool_calls")

            if not tool_calls:
                return message.get("content") or ""

            msgs.append(
                {
                    "role": "assistant",
                    "content": message.get("content") or "",
                    "tool_calls": tool_calls,
                }
            )
            async def run_one(call: dict) -> dict:
                fn = call.get("function") or {}
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    args = {}
                result = await run_tool(name, args)
                return {
                    "role": "tool",
                    "tool_call_id": call.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }

            # Run all requested tools concurrently — big win for multi-tool
            # requests like the morning briefing (weather + electricity + ...).
            msgs.extend(await asyncio.gather(*(run_one(c) for c in tool_calls)))

        # Tool round limit reached — force a spoken summary.
        msgs.append({"role": "user", "content": FINAL_ANSWER_PROMPT})
        body = await _openai_request(client, msgs, [])
        choice = (body.get("choices") or [{}])[0]
        return (choice.get("message") or {}).get("content") or ""


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

def _to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    converted: list[dict] = []
    for m in messages:
        role = m.get("role")
        if role in ("user", "assistant") and m.get("content"):
            converted.append({"role": role, "content": m["content"]})
    return system, converted


async def _anthropic_request(
    client: httpx.AsyncClient, system: str, messages: list[dict], tools: list[dict]
) -> dict:
    if not config.ANTHROPIC_API_KEY:
        raise LLMError("no Anthropic API key configured")
    body: dict[str, Any] = {
        "model": config.LLM_MODEL,
        "max_tokens": 1024,
        "system": system,
        "messages": messages,
    }
    if tools:
        body["tools"] = _tools_payload(tools)
    try:
        resp = await client.post(
            ANTHROPIC_URL,
            headers={
                "x-api-key": config.ANTHROPIC_API_KEY,
                "anthropic-version": "2023-06-01",
            },
            json=body,
        )
    except httpx.HTTPError as err:
        raise LLMError(f"can't reach Anthropic ({err})") from err
    if resp.status_code in (401, 403):
        raise LLMError("Anthropic rejected the API key")
    if resp.status_code >= 400:
        raise LLMError(f"Anthropic error {resp.status_code}: {resp.text[:200]}")
    return resp.json()


def _anthropic_text(body: dict) -> str:
    return "".join(b.get("text", "") for b in body.get("content", []) if b.get("type") == "text")


async def _anthropic_loop(messages: list[dict], tools: list[dict]) -> str:
    system, msgs = _to_anthropic(messages)
    async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
        for _ in range(MAX_TOOL_ROUNDS):
            body = await _anthropic_request(client, system, msgs, tools)

            if body.get("stop_reason") != "tool_use":
                return _anthropic_text(body)

            # Keep the assistant's tool_use blocks and answer with tool_result.
            msgs.append({"role": "assistant", "content": body.get("content", [])})

            async def run_one(block: dict) -> dict | None:
                if block.get("type") != "tool_use":
                    return None
                name = block.get("name", "")
                args = block.get("input") or {}
                result = await run_tool(name, args)
                return {
                    "type": "tool_result",
                    "tool_use_id": block.get("id", ""),
                    "content": json.dumps(result, ensure_ascii=False),
                }

            results = await asyncio.gather(*(run_one(b) for b in body.get("content", [])))
            msgs.append({"role": "user", "content": [r for r in results if r]})

        # Tool round limit reached — force a spoken summary.
        msgs.append({"role": "user", "content": FINAL_ANSWER_PROMPT})
        body = await _anthropic_request(client, system, msgs, [])
        return _anthropic_text(body)
