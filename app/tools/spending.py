"""Grocery spending stats from imported receipts."""
from __future__ import annotations

import asyncio
from typing import Any

from .. import db


async def spending_stats() -> dict[str, Any]:
    """Monthly totals, per-store totals and recent receipts."""
    return {
        "monthly": await asyncio.to_thread(db.spending_monthly, 6),
        "stores": await asyncio.to_thread(db.spending_by_store, 6),
        "recent": await asyncio.to_thread(db.recent_receipts, 20),
    }
