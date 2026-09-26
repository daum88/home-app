"""Uniform tool interface.

Every tool handler is an ``async`` function that takes plain arguments and
returns a **sanitized** Python dict (never a raw API response). On any
user-facing problem it raises :class:`ToolError` with a friendly message; the
registry turns that into ``{"ok": False, "error": "..."}`` so the LLM can read
it and answer gracefully.
"""
from __future__ import annotations

import asyncio
from typing import Any, Callable


class ToolError(Exception):
    """A friendly, user-facing tool error. ``message`` is shown to the user."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def ok(data: Any = None) -> dict[str, Any]:
    """Wrap a successful tool result in a uniform envelope."""
    return {"ok": True, "data": data}


def fail(message: str) -> dict[str, Any]:
    """Wrap a tool failure in a uniform envelope."""
    return {"ok": False, "error": message}


async def run_sync(func: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Run a blocking call in a worker thread so the event loop never blocks.

    Used for the synchronous ``transmission-rpc`` client and for SQLite.
    """
    return await asyncio.to_thread(func, *args, **kwargs)
