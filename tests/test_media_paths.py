"""Offline regression tests for filesystem access through media endpoints."""
from __future__ import annotations

import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from app import config
from app.main import app
from app.tools.base import ToolError
from app.tools import jellyfin


class MediaPathTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addAsyncCleanup(self._cleanup_temp)
        self.root = Path(self.temp.name) / "media"
        self.root.mkdir()
        self.root = self.root.resolve()
        self.outside = Path(self.temp.name).resolve() / "private.mp4"
        self.outside.write_bytes(b"private")
        self.movie = self.root / "filmid" / "Movie" / "movie.mp4"
        self.movie.parent.mkdir(parents=True)
        self.movie.write_bytes(b"movie")
        (self.movie.parent / "movie.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        root_patch = patch.object(config, "FS_ROOT", str(self.root))
        smb_patch = patch.object(config, "JELLYFIN_SMB_PREFIX", "/Volumes/Media")
        root_patch.start()
        smb_patch.start()
        self.addCleanup(root_patch.stop)
        self.addCleanup(smb_patch.stop)

    def _cleanup_temp(self):
        self.temp.cleanup()

    async def test_local_paths_reject_escapes_and_accept_valid_smb_paths(self):
        self.assertEqual(jellyfin.local_path(str(self.movie)), str(self.movie))
        self.assertEqual(
            jellyfin.local_path("/Volumes/Media/filmid/Movie/movie.mp4"), str(self.movie)
        )
        (self.root / "shortcut.mp4").symlink_to(self.outside)
        for path in (
            str(self.outside),
            str(self.root / "shortcut.mp4"),
            str(self.root / ".." / "private.mp4"),
            "/Volumes/Media/../private.mp4",
            "/Volumes/Media2/filmid/Movie/movie.mp4",
            "filmid/Movie/movie.mp4",
            "",
        ):
            with self.subTest(path=path), self.assertRaises(ToolError):
                jellyfin.local_path(path)

    async def test_media_endpoints_reject_external_paths_and_serve_valid_files(self):
        transport = httpx.ASGITransport(app=app)
        with patch("app.main._audio_codec", return_value="aac"):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                for endpoint in ("/api/media/stream", "/api/media/subtitles"):
                    for path in (str(self.outside), "/Volumes/Media/../private.mp4"):
                        with self.subTest(endpoint=endpoint, path=path):
                            response = await client.get(endpoint, params={"path": path})
                            self.assertEqual(response.status_code, 400)
                    response = await client.get(endpoint, params={"path": str(self.movie)})
                    self.assertEqual(response.status_code, 200)
                    if endpoint.endswith("stream"):
                        self.assertEqual(response.content, b"movie")
                    else:
                        self.assertIn("WEBVTT", response.text)

    async def test_subtitles_prefer_estonian_and_convert_timestamps(self):
        (self.movie.parent / "movie.est.srt").write_text(
            "1\n00:00:01,000 --> 00:00:02,000\nTere\n", encoding="utf-8"
        )
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/media/subtitles", params={"path": str(self.movie)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("00:00:01.000 --> 00:00:02.000", response.text)
        self.assertIn("Tere", response.text)
        self.assertNotIn("Hello", response.text)

    async def test_media_stream_single_byte_ranges(self):
        transport = httpx.ASGITransport(app=app)
        cases = (
            ("bytes=0-1", 206, b"mo", "bytes 0-1/5"),
            ("bytes=2-", 206, b"vie", "bytes 2-4/5"),
            ("bytes=-2", 206, b"ie", "bytes 3-4/5"),
            ("bytes=1-99", 206, b"ovie", "bytes 1-4/5"),
            ("bytes=8-", 416, None, "bytes */5"),
            ("bytes=-0", 416, None, "bytes */5"),
            ("bytes=2-1", 416, None, "bytes */5"),
            ("bytes=0-1,3-4", 416, None, "bytes */5"),
        )
        with patch("app.main._audio_codec", return_value="aac"):
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                for header, status, content, content_range in cases:
                    with self.subTest(header=header):
                        response = await client.get(
                            "/api/media/stream", params={"path": str(self.movie)}, headers={"Range": header}
                        )
                        self.assertEqual(response.status_code, status)
                        self.assertEqual(response.headers["content-range"], content_range)
                        if content is not None:
                            self.assertEqual(response.content, content)

    async def test_local_movie_scan_runs_off_the_event_loop(self):
        worker_ids = []
        scan = jellyfin._scan_local_movies

        def trace_scan():
            worker_ids.append(threading.get_ident())
            return scan()

        with patch.object(jellyfin, "_scan_local_movies", side_effect=trace_scan):
            result = await jellyfin.local_movies()
        self.assertEqual(result["items"][0]["name"], "Movie")
        self.assertNotEqual(worker_ids[0], threading.get_ident())

    async def test_delete_refuses_collection_but_allows_movie_folder(self):
        collection_file = self.root / "filmid" / "single.mp4"
        collection_file.write_bytes(b"movie")
        with patch.object(jellyfin, "_get_item", new_callable=AsyncMock) as get_item, \
             patch.object(jellyfin, "_post", new_callable=AsyncMock) as post:
            get_item.return_value = {"Name": "Single", "Type": "Movie", "Path": str(collection_file)}
            with self.assertRaises(ToolError):
                await jellyfin.jellyfin_delete("id")
            self.assertTrue(collection_file.exists())
            post.assert_not_awaited()

            get_item.return_value = {"Name": "Private", "Type": "Movie", "Path": str(self.outside)}
            with self.assertRaises(ToolError):
                await jellyfin.jellyfin_delete("id")
            self.assertTrue(self.outside.exists())
            post.assert_not_awaited()

            get_item.return_value = {"Name": "Movie", "Type": "Movie", "Path": str(self.movie)}
            result = await jellyfin.jellyfin_delete("id")
            self.assertTrue(result["deleted"])
            self.assertFalse(self.movie.parent.exists())
            self.assertTrue((self.root / "filmid").exists())
            post.assert_awaited_once_with("/Library/Refresh")


if __name__ == "__main__":
    unittest.main()
