"""SmartThings OAuth 2.0 — permanent washer auth via refresh tokens.

Flow: /oauth/authorize builds the SmartThings authorize URL, the user approves
in their browser and pastes the ``code`` from the redirect URL back to
``/oauth/exchange``. The refresh token is stored locally and auto-refreshed so
the washer never needs a hand-edited PAT again. A PAT remains a temporary
fallback until OAuth is configured.
"""
from __future__ import annotations

import asyncio
import time
from typing import Any
from urllib.parse import quote

import httpx

from . import config, db

AUTH_URL = "https://api.smartthings.com/v1/oauth/authorize"
TOKEN_URL = "https://api.smartthings.com/v1/oauth/token"
SCOPES = "r:locations:* r:devices:* x:devices:*"
_CACHE_KEY = "smartthings_oauth"

# In-memory access-token cache (avoids a DB read + refresh race per request).
_token: dict[str, Any] = {}
_lock = asyncio.Lock()


def configured() -> bool:
    return bool(config.SMARTTHINGS_CLIENT_ID and config.SMARTTHINGS_CLIENT_SECRET)


def authorize_url() -> str:
    return (
        f"{AUTH_URL}?client_id={quote(config.SMARTTHINGS_CLIENT_ID)}"
        f"&response_type=code&redirect_uri={quote(config.SMARTTHINGS_REDIRECT_URI)}"
        f"&scope={quote(SCOPES)}"
    )


def _store(tokens: dict[str, Any]) -> None:
    tokens = dict(tokens)
    tokens["expires_at"] = time.time() + int(tokens.get("expires_in", 3600)) - 60
    _token.clear()
    _token.update(tokens)
    db.cache_set(_CACHE_KEY, tokens)


def _load_stored() -> dict[str, Any] | None:
    return db.cache_get(_CACHE_KEY)


async def _token_request(payload: dict[str, Any]) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            TOKEN_URL,
            data=payload,
            auth=(config.SMARTTHINGS_CLIENT_ID, config.SMARTTHINGS_CLIENT_SECRET),
        )
    resp.raise_for_status()
    return resp.json()


async def exchange_code(code: str) -> None:
    """Exchange an authorization code for tokens and store them."""
    tokens = await _token_request({
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": config.SMARTTHINGS_REDIRECT_URI,
    })
    _store(tokens)


async def get_access_token() -> str:
    """Return a valid access token, refreshing via the refresh token if needed."""
    # Temporary fallback until OAuth is set up.
    if not configured():
        if config.SMARTTHINGS_PAT:
            return config.SMARTTHINGS_PAT
        raise RuntimeError("SmartThings OAuth not configured — open /oauth/authorize first")

    async with _lock:
        tokens = dict(_token) or _load_stored()
        if not tokens:
            raise RuntimeError("SmartThings OAuth not authorized yet — open /oauth/authorize")
        if time.time() >= tokens.get("expires_at", 0):
            tokens = await _token_request({
                "grant_type": "refresh_token",
                "refresh_token": tokens.get("refresh_token"),
            })
            _store(tokens)
        return tokens["access_token"]
