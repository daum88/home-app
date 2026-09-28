"""Only configured integrations should start periodic background polling."""
from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from app import config, main, media_streaming


class LifespanTests(unittest.IsolatedAsyncioTestCase):
    async def test_optional_watchers_only_start_when_configured(self):
        for configured in (False, True):
            with self.subTest(configured=configured), tempfile.TemporaryDirectory() as directory, \
                 patch.object(config, "DB_PATH", str(Path(directory) / "home.db")), \
                 patch.object(config, "LETTERBOXD_USER", "user" if configured else ""), \
                 patch.object(config, "RADARR_API_KEY", "key" if configured else ""), \
                 patch.object(config, "JELLYFIN_URL", "http://jellyfin" if configured else ""), \
                 patch.object(config, "JELLYFIN_API_KEY", "key" if configured else ""), \
                 patch.object(main, "_receipt_watcher", new_callable=AsyncMock), \
                 patch.object(main, "_warm_up", new_callable=AsyncMock), \
                 patch.object(media_streaming, "_hls_cleanup", new_callable=AsyncMock), \
                 patch.object(main, "_letterboxd_watcher", new_callable=AsyncMock) as letterboxd, \
                 patch.object(main, "_jellyfin_refresh_watcher", new_callable=AsyncMock) as jellyfin:
                async with main.lifespan(main.app):
                    await asyncio.sleep(0)
                    self.assertEqual(letterboxd.call_count, int(configured))
                    self.assertEqual(jellyfin.call_count, int(configured))


if __name__ == "__main__":
    unittest.main()
