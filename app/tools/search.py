"""Torrent search via Prowlarr's search API (localhost:9696)."""
from __future__ import annotations

from typing import Any

import httpx

from .. import config
from .base import ToolError, format_size


async def search_torrents(query: str, limit: int = 5) -> dict[str, Any]:
    """Search Prowlarr indexers for a title and return the top releases."""
    query = (query or "").strip()
    if not query:
        raise ToolError("what would you like me to search for?")
    if not config.PROWLARR_API_KEY:
        raise ToolError("torrent search isn't configured — add PROWLARR_API_KEY to .env")

    url = f"{config.PROWLARR_URL}/api/v1/search"
    params = {"query": query, "type": "search", "categories": 2000}
    headers = {"X-Api-Key": config.PROWLARR_API_KEY}

    try:
        async with httpx.AsyncClient(timeout=config.REQUEST_TIMEOUT) as client:
            resp = await client.get(url, params=params, headers=headers)
    except httpx.HTTPError as err:
        raise ToolError(f"can't reach Prowlarr ({err})") from err
    if resp.status_code in (401, 403):
        raise ToolError("torrent search failed — Prowlarr rejected the API key")
    resp.raise_for_status()
    results = resp.json() or []

    results.sort(key=lambda r: (r.get("seeders") or 0, r.get("size") or 0), reverse=True)
    top = results[: max(1, min(int(limit), 10))]

    return {
        "query": query,
        "results": [
            {
                "title": r.get("title"),
                "size": format_size(r.get("size") or 0),
                "seeders": r.get("seeders") or 0,
                "leechers": r.get("leechers") or 0,
                "indexer": r.get("indexer"),
                # magnetUrl for public trackers; downloadUrl is a fallback (.torrent link)
                "magnet": r.get("magnetUrl") or r.get("downloadUrl"),
            }
            for r in top
        ],
    }
