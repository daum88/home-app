"""Shared fixtures for offline tests.

Importing this module quiets noisy HTTP client logging. The base classes give
each test a fresh temp directory, one-line config patching, an optional
isolated SQLite database and an ASGI test client for the FastAPI app.
"""
from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx

from app import config, db

logging.getLogger("httpx").setLevel(logging.WARNING)


class _Fixtures:
    temp: tempfile.TemporaryDirectory[str]
    tmp: Path

    def _setup_fixtures(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)

    def patch_config(self, **overrides: Any) -> None:
        """Override ``app.config`` attributes for the duration of the test."""
        for key, value in overrides.items():
            patcher = patch.object(config, key, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def use_temp_db(self) -> Path:
        """Point the app at a fresh SQLite database inside the temp dir."""
        path = self.tmp / "home.db"
        self.patch_config(DB_PATH=str(path))
        db.init_db()
        return path

    def api_client(self) -> httpx.AsyncClient:
        """Return an async client wired to the FastAPI app over ASGI."""
        from app.main import app

        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        self.addAsyncCleanup(client.aclose)
        return client


class HomeTestCase(_Fixtures, unittest.TestCase):
    def setUp(self) -> None:
        self._setup_fixtures()


class AsyncHomeTestCase(_Fixtures, unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self._setup_fixtures()
