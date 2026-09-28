"""Jellyfin requests reuse connections and cold poster fetches coalesce."""
from __future__ import annotations

import asyncio
import unittest
from unittest.mock import patch

import httpx

from app.tools import jellyfin
from tests.base import AsyncHomeTestCase


class JellyfinClientTests(AsyncHomeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.addCleanup(jellyfin._poster_locks.clear)
        # Poster file cache lives next to the DB; no database is needed here.
        self.patch_config(DB_PATH=str(self.tmp / "home.db"),
                          JELLYFIN_URL="http://jellyfin", JELLYFIN_API_KEY="test-key")

    async def test_poster_downloads_once_for_concurrent_requests_and_uses_cache(self):
        calls = []

        async def respond(request):
            calls.append(request)
            await asyncio.sleep(0.01)
            return httpx.Response(200, content=b"jpeg", headers={"content-type": "image/jpeg"})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch.object(jellyfin, "_client", client):
                first, second = await asyncio.gather(jellyfin.fetch_image("abc123"), jellyfin.fetch_image("abc123"))
                third = await jellyfin.fetch_image("abc123")
        self.assertEqual((first, second, third), ((b"jpeg", "image/jpeg"),) * 3)
        self.assertEqual(len(calls), 1)
        self.assertIsNone(await jellyfin.fetch_image("../private"))

    async def test_get_and_post_use_one_open_client(self):
        seen = []

        def respond(request):
            seen.append((request.method, request.url.path))
            return httpx.Response(200, json={"ok": True})

        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            with patch.object(jellyfin, "_client", client):
                await jellyfin._get("/Items")
                await jellyfin._post("/Library/Refresh")
        self.assertEqual(seen, [("GET", "/Items"), ("POST", "/Library/Refresh")])


if __name__ == "__main__":
    unittest.main()
