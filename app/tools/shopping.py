"""Shopping list (SQLite-backed)."""
from __future__ import annotations

import asyncio
from typing import Any

from .. import db
from .base import ToolError


async def shopping_add(name: str) -> dict[str, Any]:
    """Add an item to the shopping list."""
    name = (name or "").strip()
    if not name:
        raise ToolError("what should I add to the shopping list?")
    await asyncio.to_thread(db.shopping_add, name)
    return {"added": name}


async def shopping_list() -> dict[str, Any]:
    """List the shopping list."""
    items = await asyncio.to_thread(db.shopping_list)
    return {"items": items}


async def shopping_remove(item_id: int) -> dict[str, Any]:
    """Remove an item from the shopping list by id."""
    await asyncio.to_thread(db.shopping_remove, int(item_id))
    return {"removed": True}


async def shopping_clear() -> dict[str, Any]:
    """Clear the whole shopping list."""
    await asyncio.to_thread(db.shopping_clear)
    return {"cleared": True}
