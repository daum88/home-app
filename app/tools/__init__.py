"""Tool registry package.

The registry maps a tool name to ``{name, description, parameters, handler}``.
The LLM only ever sees the schemas; Python executes handlers and validates the
boundary.

Tool submodules pull in heavy third-party integrations (transmission-rpc,
pyhOn, IMAP, ...), so the registry itself is imported lazily on first use —
importing a single leaf module such as ``app.tools.base`` stays cheap and does
not require the full dependency stack.
"""
from __future__ import annotations

import importlib
from typing import Any

from .base import ToolError, fail, ok

__all__ = ["ToolError", "fail", "ok", "TOOLS", "get_schemas", "run_tool"]


def _registry():
    return importlib.import_module(".registry", __package__)


def __getattr__(name: str) -> Any:
    if name == "TOOLS":
        return _registry().TOOLS
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def get_schemas() -> list[dict[str, Any]]:
    """Return the LLM-facing tool schemas (OpenAI-style)."""
    return _registry().get_schemas()


async def run_tool(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Execute a tool by name with the given arguments. Never raises."""
    return await _registry().run_tool(name, args)
