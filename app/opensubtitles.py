"""OpenSubtitles.com REST API client — auto-download subtitles for movies.

Finds the right subtitle by the OpenSubtitles *moviehash* (MD5 of the first +
last 64 KiB of the file) so the timings match the exact release, then falls
back to a filename search. Prefers Estonian, then English.

Disabled (no-op) until OPENSUBTITLES_API_KEY + USER + PASS are set in .env.
"""
from __future__ import annotations

import hashlib
import logging
import os
import time
from typing import Any

import httpx

from . import config

log = logging.getLogger("hva.subtitles")

_API = "https://api.opensubtitles.com/api/v1"
_token: str | None = None
_token_expires: float = 0.0


def enabled() -> bool:
    return bool(
        config.OPENSUBTITLES_API_KEY and config.OPENSUBTITLES_USER and config.OPENSUBTITLES_PASS
    )


def _headers() -> dict[str, str]:
    return {"Api-Key": config.OPENSUBTITLES_API_KEY, "User-Agent": config.OFF_USER_AGENT}


async def _login() -> str | None:
    """Log in and cache the bearer token (~20h)."""
    global _token, _token_expires
    if _token and time.time() < _token_expires - 60:
        return _token
    if not enabled():
        return None
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.post(
                f"{_API}/login",
                json={"username": config.OPENSUBTITLES_USER, "password": config.OPENSUBTITLES_PASS},
                headers=_headers(),
            )
            r.raise_for_status()
            _token = r.json().get("token")
            _token_expires = time.time() + 20 * 3600
            return _token
    except Exception as err:  # noqa: BLE001
        log.warning("opensubtitles login failed: %s", err)
        return None


def movie_hash(path: str) -> tuple[str, int] | None:
    """Return (moviehash, byte_size) for the OpenSubtitles hash scheme."""
    try:
        size = os.path.getsize(path)
        if size < 128 * 1024:
            return None
        with open(path, "rb") as f:
            head = f.read(64 * 1024)
            f.seek(-64 * 1024, os.SEEK_END)
            tail = f.read(64 * 1024)
        return hashlib.md5(head + tail).hexdigest(), size
    except OSError:
        return None


async def _search(params: dict[str, Any]) -> list[dict[str, Any]]:
    token = await _login()
    if not token:
        return []
    headers = _headers()
    headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(f"{_API}/subtitles", params=params, headers=headers)
            r.raise_for_status()
            return r.json().get("data", [])
    except Exception as err:  # noqa: BLE001
        log.warning("opensubtitles search failed: %s", err)
        return []


async def _download(file_id: int) -> str | None:
    token = await _login()
    if not token:
        return None
    headers = _headers()
    headers["Authorization"] = f"Bearer {token}"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(f"{_API}/download", json={"file_id": file_id}, headers=headers)
            r.raise_for_status()
            link = r.json().get("link")
            if not link:
                return None
            d = await client.get(link)
            d.raise_for_status()
            return d.text
    except Exception as err:  # noqa: BLE001
        log.warning("opensubtitles download failed: %s", err)
        return None


async def fetch_srt(path: str, languages: tuple[str, ...] = ("et", "en")) -> str | None:
    """Find + save a subtitle next to the file. Returns the .srt text, or None."""
    if not enabled():
        return None
    h = movie_hash(path)
    base = os.path.splitext(path)[0]
    for lang in languages:
        attempts: list[dict[str, Any]] = []
        if h:
            attempts.append({"moviehash": h[0], "moviebytesize": h[1], "languages": lang})
        attempts.append({"query": os.path.basename(base), "languages": lang})
        for params in attempts:
            params = {**params, "order_by": "download_count", "limit": "5"}
            for s in await _search(params):
                attrs = s.get("attributes", {}) or {}
                files = attrs.get("files", []) or []
                fid = files[0].get("file_id") if files else s.get("id")
                if not fid:
                    continue
                try:
                    fid = int(fid)
                except (TypeError, ValueError):
                    continue
                text = await _download(fid)
                if text and text.strip():
                    out = f"{base}.{lang}.srt"
                    try:
                        with open(out, "w", encoding="utf-8") as fh:
                            fh.write(text)
                        log.info("opensubtitles: saved %s", os.path.basename(out))
                    except OSError:
                        pass
                    return text
    return None
