"""Series remain browsable from the Pi when Jellyfin is unavailable."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import config
from app.tools import run_tool
from app.tools import jellyfin
from app.tools.base import ToolError


class LocalSeriesTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve() / "media"
        self.show = self.root / "serials" / "The Show (2025)"
        season = self.show / "Season 1"
        season.mkdir(parents=True)
        (season / "The.Show.S01E02.mkv").write_bytes(b"episode 2")
        (season / "The.Show.S01E01.mp4").write_bytes(b"episode 1")
        (season / "Extra Feature.mkv").write_bytes(b"extra")
        self.outside = Path(self.temp.name).resolve() / "outside.mkv"
        self.outside.write_bytes(b"private")
        (season / "Outside.mkv").symlink_to(self.outside)
        root_patch = patch.object(config, "FS_ROOT", str(self.root))
        root_patch.start()
        self.addCleanup(root_patch.stop)

    async def test_list_and_order_local_series_episodes(self):
        listing = await run_tool("local_series", {})
        self.assertTrue(listing["ok"])
        series = listing["data"]["items"]
        self.assertEqual([(item["name"], item["year"]) for item in series], [("The Show", 2025)])
        result = await run_tool("local_episodes", {"series_path": series[0]["path"]})
        self.assertTrue(result["ok"])
        episodes = result["data"]["episodes"]
        self.assertEqual([ep["episode"] for ep in episodes], [1, 2, 3])
        self.assertTrue(all(ep["season"] == 1 for ep in episodes))
        self.assertFalse(any(ep["path"] == str(self.outside) for ep in episodes))

    async def test_path_is_restricted_to_series_library(self):
        with self.assertRaises(ToolError):
            await jellyfin.local_episodes(str(self.outside))
        with self.assertRaises(ToolError):
            await jellyfin.local_episodes(str(self.root))


if __name__ == "__main__":
    unittest.main()
