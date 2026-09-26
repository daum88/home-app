"""Fridge inventory: barcode → Open Food Facts lookup → SQLite expiry tracking.

Expiry dates can be natural language ("friday", "in 5 days", "2026-10-01").
Photo-OCR of the printed date is a later enhancement (Phase 5+).
"""
from __future__ import annotations

import asyncio
import re
from datetime import date, timedelta
from typing import Any

import httpx
from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta

from .. import config, db
from .base import ToolError

OFF_PRODUCT = "https://world.openfoodfacts.org/api/v2/product/{barcode}.json"

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


async def _lookup(barcode: str) -> dict[str, str]:
    url = OFF_PRODUCT.format(barcode=barcode)
    headers = {"User-Agent": config.OFF_USER_AGENT}
    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            body = resp.json()
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach Open Food Facts ({err})") from err

    if body.get("status") != 1 or not body.get("product"):
        raise ToolError(f"I don't recognize barcode {barcode}")

    product = body["product"]
    category = ""
    tags = product.get("categories_tags") or []
    if tags:
        category = str(tags[0]).replace("en:", "").replace("-", " ")
    return {
        "name": (product.get("product_name") or product.get("generic_name") or "").strip(),
        "brands": (product.get("brands") or "").strip(),
        "category": category.strip(),
    }


def _parse_expiry(expires: str | None) -> str | None:
    """Parse natural-language expiry into an ISO date (YYYY-MM-DD)."""
    if not expires:
        return None
    text = expires.strip().lower()
    if not text or text in ("unknown", "none", "no", "n/a", "-", "na"):
        return None

    today = date.today()

    # Relative phrases first — dateutil's fuzzy mode would otherwise mis-parse
    # "in 5 days" as day 5 of the current month.
    # "in 5 days", "in 2 weeks", "in 3 months", "in 1 year".
    match = re.search(r"in\s+(\d+)\s+(day|week|month|year)s?", text)
    if match:
        n = int(match.group(1))
        unit = match.group(2)
        if unit == "day":
            return (today + timedelta(days=n)).isoformat()
        if unit == "week":
            return (today + timedelta(weeks=n)).isoformat()
        if unit == "month":
            return (today + relativedelta(months=n)).isoformat()
        if unit == "year":
            return (today + relativedelta(years=n)).isoformat()

    # "tomorrow" / "today".
    if "tomorrow" in text:
        return (today + timedelta(days=1)).isoformat()
    if text == "today":
        return today.isoformat()

    # "friday" → the next Friday (including today).
    for idx, name in enumerate(_WEEKDAYS):
        if name in text:
            target = today + timedelta(days=(idx - today.weekday()) % 7)
            return target.isoformat()

    # Plain date / datetime ("2026-10-01", "october 1", "1 oct 2026").
    try:
        parsed = dateparser.parse(text, fuzzy=True)
        if parsed is not None:
            return parsed.date().isoformat()
    except (ValueError, OverflowError, TypeError):
        pass

    raise ToolError(f"couldn't understand the expiry date '{expires}' — try 'in 5 days' or a date")


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def inventory_add(
    barcode: str, expires: str | None = None, name: str | None = None
) -> dict[str, Any]:
    """Look up a barcode and store the item with its expiry date."""
    barcode = (barcode or "").strip()
    if not barcode:
        raise ToolError("no barcode given")

    product: dict[str, str] = {}
    try:
        product = await _lookup(barcode)
    except ToolError:
        if not name:
            raise ToolError("I couldn't find that barcode online — tell me the product name")

    final_name = (name or "").strip() or product.get("name", "")
    if not final_name:
        raise ToolError("I couldn't work out a name for that product")

    expiry = _parse_expiry(expires)

    await asyncio.to_thread(
        db.inventory_add,
        name=final_name,
        barcode=barcode,
        brands=product.get("brands", ""),
        category=product.get("category", ""),
        expires_on=expiry,
    )
    return {
        "name": final_name,
        "brands": product.get("brands", ""),
        "category": product.get("category", ""),
        "expires_on": expiry,
    }


async def inventory_list() -> dict[str, Any]:
    """Everything in the inventory with expiry info."""
    items = await asyncio.to_thread(db.inventory_list)
    return {"items": items}


async def inventory_expiring(days: int = 3) -> dict[str, Any]:
    """Items expiring within the next N days."""
    try:
        days = int(days)
    except (TypeError, ValueError):
        days = 3
    items = await asyncio.to_thread(db.inventory_expiring, days)
    return {"days": days, "items": items}
