"""Offline regression tests for filesystem access through media endpoints."""
from __future__ import annotations

import threading
import unittest
from unittest.mock import AsyncMock, patch

from app import media_streaming
from app.tools.base import ToolError
from app.tools import jellyfin
from tests.base import AsyncHomeTestCase


class MediaPathTests(AsyncHomeTestCase):
    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.root = (self.tmp / "media").resolve()
        self.root.mkdir()
        self.outside = self.tmp.resolve() / "private.mp4"
        self.outside.write_bytes(b"private")
        self.movie = self.root / "filmid" / "Movie" / "movie.mp4"
        self.movie.parent.mkdir(parents=True)
        self.movie.write_bytes(b"movie")
        (self.movie.parent / "movie.srt").write_text("1\n00:00:01,000 --> 00:00:02,000\nHello\n")
        self.patch_config(FS_ROOT=str(self.root), JELLYFIN_SMB_PREFIX="/Volumes/Media")

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
        with patch.object(media_streaming, "_audio_codec", return_value="aac"):
            client = self.api_client()
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
        client = self.api_client()
        response = await client.get("/api/media/subtitles", params={"path": str(self.movie)})
        self.assertEqual(response.status_code, 200)
        self.assertIn("00:00:01.000 --> 00:00:02.000", response.text)
        self.assertIn("Tere", response.text)
        self.assertNotIn("Hello", response.text)

    async def test_media_stream_single_byte_ranges(self):
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
        with patch.object(media_streaming, "_audio_codec", return_value="aac"):
            client = self.api_client()
            for header, status, content, content_range in cases:
                with self.subTest(header=header):
                    response = await client.get(
                        "/api/media/stream", params={"path": str(self.movie)}, headers={"Range": header}
                    )
                    self.assertEqual(response.status_code, status)
                    self.assertEqual(response.headers["content-range"], content_range)
                    if content is not None:
                        self.assertEqual(response.content, content)

    async def test_download_keeps_original_filename_without_remux(self):
        source = self.movie.with_suffix(".mkv")
        source.write_bytes(b"movie")
        with patch.object(media_streaming, "_audio_codec", return_value="aac"), \
             patch.object(media_streaming, "_video_codec", return_value="h264"):
            response = await self.api_client().get(
                "/api/media/stream", params={"path": str(source), "download": 1}
            )
        self.assertEqual(response.status_code, 200)
        self.assertIn('filename="movie.mkv"', response.headers["content-disposition"])
        self.assertEqual(response.content, b"movie")

    async def test_download_uses_mp4_filename_for_remuxed_media(self):
        source = self.movie.with_suffix(".mkv")
        source.write_bytes(b"movie")
        prepared = self.tmp / "prepared.mp4"
        prepared.write_bytes(b"mp4")
        with patch.object(media_streaming, "_audio_codec", return_value="dts"), \
             patch.object(media_streaming, "_video_codec", return_value="h264"), \
             patch.object(media_streaming, "_download_mp4", return_value=str(prepared)) as remux:
            response = await self.api_client().get(
                "/api/media/stream", params={"path": str(source), "download": 1}
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["content-type"], "video/mp4")
        self.assertIn('filename="movie.mp4"', response.headers["content-disposition"])
        self.assertEqual(response.content, b"mp4")
        remux.assert_called_once_with(str(source), False)

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
