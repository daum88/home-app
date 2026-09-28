"""HLS sessions are bounded, coalesced and cleaned without touching unrelated files."""
from __future__ import annotations

import asyncio
import unittest
from pathlib import Path
from unittest.mock import patch

from app import main
from tests.base import AsyncHomeTestCase


class FakeProcess:
    def __init__(self):
        self.running = True
        self.terminated = False

    def poll(self):
        return None if self.running else 0

    def terminate(self):
        self.terminated = True
        self.running = False

    def wait(self, timeout):
        return 0


class HLSSessionTests(AsyncHomeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.root = self.tmp / ".hls"
        root_patch = patch.object(main, "_HLS_DIR", str(self.root))
        root_patch.start()
        self.addCleanup(root_patch.stop)
        main._hls_sessions.clear()
        self.addAsyncCleanup(main._hls_shutdown)

    async def test_parallel_requests_share_one_process_and_shutdown_reaps_it(self):
        process = FakeProcess()
        with patch.object(main.subprocess, "Popen", return_value=process) as popen:
            first, second = await asyncio.gather(main._hls_start("/movie.mkv"), main._hls_start("/movie.mkv"))
            self.assertEqual(first["token"], second["token"])
            self.assertEqual(popen.call_count, 1)
            self.assertTrue((Path(first["dir"]) / "session.marker").exists())
            await main._hls_shutdown()
            self.assertTrue(process.terminated)
            self.assertFalse(Path(first["dir"]).exists())
            self.assertFalse(main._hls_sessions)

    async def test_recovery_prunes_only_owned_directories(self):
        session = self.root / ("a" * 32)
        unrelated = self.root / "user-media"
        no_marker = self.root / ("b" * 32)
        for folder in (session, unrelated, no_marker):
            folder.mkdir(parents=True)
        (session / "index.m3u8").write_text("#EXTM3U")
        (unrelated / "keep.txt").write_text("important")
        main._hls_prune_orphans()
        self.assertFalse(session.exists())
        self.assertTrue((unrelated / "keep.txt").exists())
        self.assertTrue(no_marker.exists())


if __name__ == "__main__":
    unittest.main()
