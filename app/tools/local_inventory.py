"""SQLite-owned fridge inventory; hOn is an explicit, import-only source."""
from __future__ import annotations

import asyncio
import math
from datetime import date
from typing import Any

from .. import config, db
from . import hon_inventory
from .base import ToolError

POSITIONS = {"fridge", "freezer", "pantry"}


async def list_items() -> dict[str, Any]:
    return {"items": await asyncio.to_thread(db.inventory_list)}


async def add_item(
    name: str, qty: float = 1, expires_on: str | None = None,
    position: str = "fridge", note: str = "", unit: str | None = None,
    barcode: str = "", brands: str = "", category: str = "",
) -> dict[str, Any]:
    """Add a local item; note remains accepted for existing tool clients."""
    name = (name or "").strip()
    if not name:
        raise ToolError("enter an item name")
    try:
        quantity = float(qty)
    except (TypeError, ValueError):
        raise ToolError("quantity must be a positive number") from None
    if not math.isfinite(quantity) or quantity <= 0:
        raise ToolError("quantity must be a positive number")
    if position not in POSITIONS:
        raise ToolError("position must be fridge, freezer, or pantry")
    expires_on = expires_on or None
    if expires_on:
        try:
            expires_on = date.fromisoformat(expires_on).isoformat()
        except ValueError:
            raise ToolError("expiry must be a date in YYYY-MM-DD format") from None
    item_unit = (unit or ("kg" if quantity < 1 else "pz")).strip()
    if not item_unit or len(item_unit) > 12:
        raise ToolError("invalid quantity unit")
    item_id = await asyncio.to_thread(
        db.inventory_add, name=name, quantity=quantity, unit=item_unit,
        barcode=barcode, brands=brands, category=category,
        position=position, expires_on=expires_on,
    )
    return {"ok": True, "name": name, "item_id": item_id}


async def remove_item(item_id: int) -> dict[str, Any]:
    try:
        item_id = int(item_id)
    except (TypeError, ValueError):
        raise ToolError("invalid item id") from None
    if not await asyncio.to_thread(db.inventory_remove, item_id):
        raise ToolError("item not found in the local fridge")
    return {"removed": True, "item_id": item_id}


async def import_hon() -> dict[str, Any]:
    """Import hOn items without changing hOn or overwriting local items."""
    if not (config.HON_USER and config.HON_PASS):
        raise ToolError("hOn isn't configured; local fridge items are still available")
    snapshot = await hon_inventory.list_items()
    valid: list[dict[str, Any]] = []
    for raw in snapshot.get("items", []):
        try:
            hon_id = int(raw["id"])
            name = raw["name"]
            quantity = float(raw.get("quantity") or 1)
            if (hon_id <= 0 or not isinstance(name, str) or not name.strip()
                    or not math.isfinite(quantity) or quantity <= 0):
                continue
        except (KeyError, TypeError, ValueError):
            continue
        raw_expiry = str(raw.get("expires_on") or "").replace("/", "-")[:10]
        try:
            expiry = date.fromisoformat(raw_expiry).isoformat() if raw_expiry else None
        except ValueError:
            expiry = None
        position = raw.get("position")
        valid.append({
            "id": hon_id, "name": name.strip(), "quantity": quantity,
            "unit": str(raw.get("unit") or "pz")[:12],
            "position": position if position in POSITIONS else "fridge",
            "expires_on": expiry,
        })
    imported = await asyncio.to_thread(db.inventory_import_hon, valid)
    return {"imported": imported, "skipped": len(snapshot.get("items", [])) - imported}
