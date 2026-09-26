"""Optional server-side STT via Groq (whisper-large-v3-turbo).

The default STT path is the browser Web Speech API (free, zero server cost).
This module is only used if GROQ_API_KEY is set and the client posts audio.
TTS stays fully client-side via the browser ``speechSynthesis`` API.
"""
from __future__ import annotations

import httpx

from . import config

GROQ_TRANSCRIBE_URL = "https://api.groq.com/openai/v1/audio/transcriptions"


class STTError(Exception):
    """Raised when server-side transcription fails."""


async def transcribe(audio: bytes, filename: str = "audio.webm") -> str:
    """Transcribe raw audio bytes to text using Groq's Whisper endpoint."""
    if not config.GROQ_API_KEY:
        raise STTError("server-side speech recognition isn't configured")
    try:
        async with httpx.AsyncClient(timeout=config.LLM_TIMEOUT) as client:
            resp = await client.post(
                GROQ_TRANSCRIBE_URL,
                headers={"Authorization": f"Bearer {config.GROQ_API_KEY}"},
                data={"model": "whisper-large-v3-turbo", "language": "et"},
                files={"file": (filename, audio, "audio/webm")},
            )
    except httpx.HTTPError as err:
        raise STTError(f"can't reach Groq ({err})") from err
    if resp.status_code >= 400:
        raise STTError(f"Groq transcription failed ({resp.status_code})")
    return (resp.json().get("text") or "").strip()
