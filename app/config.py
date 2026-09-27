"""Central configuration.

Every secret lives in ``.env`` (see ``.env.example``) and is read here exactly
once at import time. Nothing in this module is ever committed to git.
"""
from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()

# ---------------------------------------------------------------------------
# LLM (cloud brain)
# ---------------------------------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "openai").strip().lower()  # openai | anthropic
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()
# OpenAI-compatible base URL (DeepSeek, OpenAI, etc.) — used by the "openai" provider.
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "https://api.openai.com/v1").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# Transmission (local torrent daemon)
# ---------------------------------------------------------------------------
TRANSMISSION_URL = os.getenv("TRANSMISSION_URL", "http://localhost:9091").strip()
TRANSMISSION_USER = os.getenv("TRANSMISSION_USER", "").strip()
TRANSMISSION_PASS = os.getenv("TRANSMISSION_PASS", "").strip()


def transmission_connection() -> tuple[str, int, str | None, str | None]:
    """Return (host, port, username_or_None, password_or_None)."""
    parsed = urlparse(TRANSMISSION_URL)
    host = parsed.hostname or "localhost"
    port = parsed.port or 9091
    return host, port, TRANSMISSION_USER or None, TRANSMISSION_PASS or None


# ---------------------------------------------------------------------------
# Samsung washer (SmartThings)
# ---------------------------------------------------------------------------
SMARTTHINGS_API = "https://api.smartthings.com/v1"
SMARTTHINGS_PAT = os.getenv("SMARTTHINGS_PAT", "").strip()
# OAuth 2.0 (permanent auth — replaces the 24h PAT). Create a SmartThings Cloud
# Connector at https://smartthings.developer.samsung.com/workspace/ to get these.
SMARTTHINGS_CLIENT_ID = os.getenv("SMARTTHINGS_CLIENT_ID", "").strip()
SMARTTHINGS_CLIENT_SECRET = os.getenv("SMARTTHINGS_CLIENT_SECRET", "").strip()
SMARTTHINGS_REDIRECT_URI = os.getenv(
    "SMARTTHINGS_REDIRECT_URI", "http://localhost:8080/callback"
).strip()
# Verified device id from RESEARCH.md.
WASHER_DEVICE_ID = os.getenv(
    "WASHER_DEVICE_ID", "b6d6a88b-8f08-919d-e51d-7f4799882d38"
).strip()

# ---------------------------------------------------------------------------
# Haier fridge (hOn — unofficial, fragile)
# ---------------------------------------------------------------------------
HON_USER = os.getenv("HON_USER", "").strip()
HON_PASS = os.getenv("HON_PASS", "").strip()

# ---------------------------------------------------------------------------
# Torrent search (Prowlarr)
# ---------------------------------------------------------------------------
PROWLARR_URL = os.getenv("PROWLARR_URL", "http://localhost:9696").strip().rstrip("/")
PROWLARR_API_KEY = os.getenv("PROWLARR_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# Systemair SaveConnect 2.0 ventilation (local REST API)
# ---------------------------------------------------------------------------
SAVECONNECT_URL = os.getenv("SAVECONNECT_URL", "").strip().rstrip("/")

# ---------------------------------------------------------------------------
# Open Food Facts (fridge inventory)
# ---------------------------------------------------------------------------
OFF_USER_AGENT = os.getenv(
    "OFF_USER_AGENT", "HomeVoiceAssistant/0.1 (personal home project)"
).strip()

# ---------------------------------------------------------------------------
# Optional server-side STT (Groq). Browser Web Speech API is the default.
# ---------------------------------------------------------------------------
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# Email receipts (IMAP — auto-import Coop PDFs from your inbox)
# ---------------------------------------------------------------------------
EMAIL_HOST = os.getenv("EMAIL_HOST", "imap.gmail.com").strip()
EMAIL_PORT = int(os.getenv("EMAIL_PORT", "993"))
EMAIL_USER = os.getenv("EMAIL_USER", "").strip()
EMAIL_PASS = os.getenv("EMAIL_PASS", "").strip()  # Gmail: use an App Password
EMAIL_FOLDER = os.getenv("EMAIL_FOLDER", "INBOX").strip()

# ---------------------------------------------------------------------------
# Local filesystem access (let the assistant answer questions about files)
# ---------------------------------------------------------------------------
FS_ROOT = (os.getenv("FS_ROOT", "").strip() or str(Path.home()))
FILE_READ_LIMIT = int(os.getenv("FILE_READ_LIMIT", "100000"))

# ---------------------------------------------------------------------------
# Weather (Open-Meteo, free — no key)
# ---------------------------------------------------------------------------
WEATHER_LAT = float(os.getenv("WEATHER_LAT", "58.378"))  # Tartu
WEATHER_LON = float(os.getenv("WEATHER_LON", "26.729"))

# ---------------------------------------------------------------------------
# Kodi (JSON-RPC over TCP on the Android TV)
# ---------------------------------------------------------------------------
KODI_URL = os.getenv("KODI_URL", "http://192.168.8.137:8080").strip().rstrip("/")
KODI_USER = os.getenv("KODI_USER", "").strip()
KODI_PASS = os.getenv("KODI_PASS", "").strip()
KODI_PORT = int(os.getenv("KODI_PORT", "9090"))  # JSON-RPC over TCP

# ---------------------------------------------------------------------------
# Jellyfin (self-hosted media server)
# ---------------------------------------------------------------------------
JELLYFIN_URL = os.getenv("JELLYFIN_URL", "").strip().rstrip("/")
JELLYFIN_API_KEY = os.getenv("JELLYFIN_API_KEY", "").strip()
# Jellyfin runs on the Mac and sees the Pi's disk through this SMB mount. The
# backend runs on the Pi and sees the same files at FS_ROOT — used to translate
# Jellyfin paths into local paths when deleting media.
JELLYFIN_SMB_PREFIX = os.getenv("JELLYFIN_SMB_PREFIX", "/Users/mattiasdaum/PiMedia").strip().rstrip("/")

# ---------------------------------------------------------------------------
# Radarr (movie auto-download) + Letterboxd watchlist sync
# ---------------------------------------------------------------------------
RADARR_URL = os.getenv("RADARR_URL", "http://localhost:7878").strip().rstrip("/")
RADARR_API_KEY = os.getenv("RADARR_API_KEY", "").strip()
RADARR_QUALITY_PROFILE_ID = int(os.getenv("RADARR_QUALITY_PROFILE_ID", "4"))  # HD-1080p
LETTERBOXD_USER = os.getenv("LETTERBOXD_USER", "daum13").strip()

# ---------------------------------------------------------------------------
# TheMovieDB (TMDB) — poster art + metadata when Jellyfin/Mac is offline
# ---------------------------------------------------------------------------
TMDB_API_KEY = os.getenv("TMDB_API_KEY", "").strip()

# ---------------------------------------------------------------------------
# OpenSubtitles.com (auto-download subtitles for movies without .srt)
# ---------------------------------------------------------------------------
OPENSUBTITLES_API_KEY = os.getenv("OPENSUBTITLES_API_KEY", "").strip()
OPENSUBTITLES_USER = os.getenv("OPENSUBTITLES_USER", "daum13").strip()
OPENSUBTITLES_PASS = os.getenv("OPENSUBTITLES_PASS", "").strip()

# ---------------------------------------------------------------------------
# Storage & limits
# ---------------------------------------------------------------------------
DB_PATH = os.getenv("DB_PATH", "data/home.db").strip()
REQUEST_TIMEOUT = float(os.getenv("REQUEST_TIMEOUT", "10"))
LLM_TIMEOUT = float(os.getenv("LLM_TIMEOUT", "60"))
