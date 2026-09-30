"""Barcode lookup + add-to-fridge via Open Food Facts."""
from __future__ import annotations

import asyncio
from datetime import date, timedelta
from typing import Any

import httpx

from .. import config, db
from .base import ToolError
from .receipts import OFF_PRODUCT, _BARCODE_RE, _humanize, _off_category, _rule_for


async def _product(barcode: str) -> dict[str, Any] | None:
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(
                OFF_PRODUCT.format(barcode=barcode),
                headers={"User-Agent": config.OFF_USER_AGENT},
            )
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError:
        return None
    if body.get("status") != 1 or not body.get("product"):
        return None
    return body["product"]


async def lookup_barcode(barcode: str) -> dict[str, Any]:
    """Return product info (name, brand, category, shelf life) for a scanned EAN."""
    barcode = (barcode or "").strip()
    if not _BARCODE_RE.match(barcode):
        raise ToolError("not a valid EAN barcode")
    p = await _product(barcode)
    if not p:
        raise ToolError("barcode not found in Open Food Facts")
    name = p.get("product_name") or p.get("generic_name") or ""
    category, days = _off_category(p.get("categories_tags") or [])
    if category == "other":
        rule_cat, rule_days = _rule_for(name)
        if rule_cat != "other":
            category = rule_cat
            if days is None:
                days = rule_days
    return {
        "barcode": barcode,
        "name": _humanize(name),
        "brands": p.get("brands") or "",
        "category": category,
        "image": p.get("image_url") or p.get("image_front_url") or "",
        "shelf_life_days": days,
    }


async def add_barcode_item(barcode: str, position: str = "fridge") -> dict[str, Any]:
    """Look up a barcode and add the product to the fridge inventory with expiry."""
    info = await lookup_barcode(barcode)
    days = info.get("shelf_life_days")
    expires = (date.today() + timedelta(days=days)).isoformat() if days else None
    await asyncio.to_thread(
        db.inventory_add,
        name=info["name"],
        barcode=info["barcode"],
        brands=info["brands"],
        category=info["category"],
        expires_on=expires,
        position=position,
    )
    # Local SQLite is canonical; hOn inventory is import-only.
    return {
        "name": info["name"],
        "brands": info["brands"],
        "category": info["category"],
        "expires_on": expires,
        "position": position,
    }
