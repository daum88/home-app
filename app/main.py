"""FastAPI app: serves the phone web UI and the chat endpoint.

Endpoints:
- GET  /            → web/index.html
- POST /api/chat    → {text, history} → {reply}
- POST /api/stt     → optional server-side STT (Groq), multipart file upload
- GET  /api/health  → liveness check
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import subprocess
import time
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, llm, speech
from . import letterboxd as letterboxd_sync
from .prompts import SYSTEM_PROMPT
from .tools import get_schemas, receipts as receipts_tool
from .tools import TOOLS, run_tool
from .tools import email_receipts as email_tool
from .tools import hon_inventory as hon_inv, fridge as fridge_tool
from .tools import jellyfin as jellyfin_tool
from .tools.base import ToolError


logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s"
)
log = logging.getLogger("hva")

# pyhOn (Haier fridge) logs a noisy, non-fatal 'intelligenceMode' KeyError on
# every device parse — silence it to keep logs clean and cut overhead.
logging.getLogger("pyhon").setLevel(logging.CRITICAL)
logging.getLogger("pyhOn").setLevel(logging.CRITICAL)

WEB_DIR = Path(__file__).resolve().parent.parent / "web"


async def _receipt_watcher() -> None:
    """Poll data/receipts/ (and, every 4th tick, email) for new receipts."""
    tick = 0
    while True:
        try:
            result = await receipts_tool.scan_receipts_folder()
            for entry in result.get("processed", []):
                if entry.get("error"):
                    log.warning("receipt import failed: %s", entry)
                else:
                    n = len(entry.get("items", []))
                    log.info("imported receipt %s (%d items)", entry.get("receipt_no"), n)
        except Exception:  # noqa: BLE001 — the watcher must survive anything
            log.exception("receipt watcher error")

        tick += 1
        if tick % 4 == 0:
            try:
                result = await email_tool.check_email_receipts()
                for entry in result.get("imported", []):
                    if entry.get("error"):
                        log.warning("email receipt import failed: %s", entry)
                    elif not entry.get("already_imported"):
                        log.info("imported email receipt %s (%d items)", entry.get("receipt_no"), len(entry.get("items", [])))
            except Exception:  # noqa: BLE001
                log.exception("email receipt watcher error")

        await asyncio.sleep(30)


async def _warm_up() -> None:
    """Pre-warm the hOn token + fridge caches so first calls are fast."""
    if config.HON_USER and config.HON_PASS:
        try:
            await hon_inv._authenticate()
            log.info("hOn tokens warmed")
        except Exception as err:  # noqa: BLE001
            log.info("hOn token warm-up skipped: %s", err)
        try:
            await fridge_tool.fridge_status()
            log.info("fridge status warmed")
        except Exception as err:  # noqa: BLE001
            log.info("fridge warm-up skipped: %s", err)
    try:
        from .tools import weather as weather_tool
        await weather_tool.weather_now()
        log.info("weather warmed")
    except Exception as err:  # noqa: BLE001
        log.info("weather warm-up skipped: %s", err)


async def _letterboxd_watcher() -> None:
    """Poll the Letterboxd watchlist every 30 min and add new movies to Radarr."""
    await asyncio.sleep(90)  # let Jellyfin/Radarr settle after boot
    while True:
        try:
            result = await letterboxd_sync.sync_watchlist()
            added = result.get("added", [])
            real = [a for a in added if a.get("added")]
            if real:
                log.info("letterboxd sync: added %s", [(a.get('title'), a.get('year')) for a in real])
            elif added:
                log.info("letterboxd sync: %d pending/skipped", len(added))
        except Exception:  # noqa: BLE001 — the watcher must survive anything
            log.exception("letterboxd sync error")
        await asyncio.sleep(1800)


async def _jellyfin_refresh_watcher() -> None:
    """Rescan Jellyfin every 10 min so new downloads/deletions show up automatically."""
    await asyncio.sleep(120)  # let services settle after boot
    while True:
        try:
            await jellyfin_tool.jellyfin_refresh()
        except Exception:  # noqa: BLE001
            log.exception("jellyfin refresh error")
        await asyncio.sleep(600)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db.init_db()
    watcher = asyncio.create_task(_receipt_watcher())
    warmup = asyncio.create_task(_warm_up())
    letterboxd_task = asyncio.create_task(_letterboxd_watcher())
    jellyfin_task = asyncio.create_task(_jellyfin_refresh_watcher())
    log.info("Home Voice Assistant started (LLM=%s/%s)", config.LLM_PROVIDER, config.LLM_MODEL)
    try:
        yield
    finally:
        watcher.cancel()
        warmup.cancel()
        letterboxd_task.cancel()
        jellyfin_task.cancel()
        with suppress(asyncio.CancelledError):
            await watcher
            await warmup
            await letterboxd_task
            await jellyfin_task


app = FastAPI(title="Home Voice Assistant", lifespan=lifespan)


class ChatRequest(BaseModel):
    text: str
    history: list[dict[str, str]] = Field(default_factory=list)


class ChatResponse(BaseModel):
    reply: str


class LogRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


@app.post("/api/log")
async def app_log(req: LogRequest) -> dict[str, Any]:
    """Receive an error/log line from the iOS app and record it."""
    log.info("APP: %s", req.message)
    return {"ok": True}


class ToolRequest(BaseModel):
    args: dict[str, Any] = Field(default_factory=dict)


@app.get("/api/tools")
async def list_tools() -> dict[str, Any]:
    """List all available tool names + descriptions (for the web UI)."""
    return {
        "tools": [
            {"name": name, "description": tool["description"]}
            for name, tool in TOOLS.items()
        ]
    }


@app.post("/api/tools/{name}")
async def run_tool_endpoint(name: str, req: ToolRequest) -> dict[str, Any]:
    """Run any tool directly (device controls, inventory, …)."""
    if name not in TOOLS:
        raise HTTPException(status_code=404, detail=f"unknown tool: {name}")
    return await run_tool(name, req.args)


@app.post("/api/chat")
async def chat(req: ChatRequest) -> ChatResponse:
    text = req.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="empty text")

    messages: list[dict[str, str]] = [{"role": "system", "content": SYSTEM_PROMPT}]
    # Persistent memory: recall recent conversations from SQLite (survives restarts).
    for m in db.history_recent(20):
        role = m.get("role")
        content = (m.get("content") or "").strip()
        if role in ("user", "assistant") and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": text})

    try:
        reply = await llm.chat(messages, tools=get_schemas())
    except llm.LLMError as err:
        log.exception("LLM error")
        reply = f"Sorry, I can't reach my brain right now — {err}"
    except Exception as err:  # noqa: BLE001 — always answer the user
        log.exception("chat error")
        reply = "Sorry, something went wrong on my end."

    reply = (reply or "").strip()
    db.history_append("user", text)
    db.history_append("assistant", reply)
    return ChatResponse(reply=reply)


@app.post("/api/stt")
async def stt(file: UploadFile = File(...)) -> dict[str, Any]:
    """Optional server-side transcription. Returns {"text": "..."}."""
    audio = await file.read()
    if not audio:
        raise HTTPException(status_code=400, detail="empty audio")
    try:
        text = await speech.transcribe(audio, filename=file.filename or "audio.webm")
    except speech.STTError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err
    return {"text": text}


@app.post("/api/receipts/import")
async def import_receipt(file: UploadFile = File(...)) -> dict[str, Any]:
    """Import a Coop e-receipt PDF directly (multipart upload)."""
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="expected a PDF file")
    pdf = await file.read()
    if not pdf:
        raise HTTPException(status_code=400, detail="empty file")
    try:
        return await receipts_tool.import_receipt(pdf, filename=file.filename or "")
    except ToolError as err:
        log.warning("receipt import failed (%s): %s", file.filename, err.message)
        raise HTTPException(status_code=400, detail=err.message) from err


@app.get("/api/jellyfin/image/{item_id}")
async def jellyfin_image(item_id: str) -> Response:
    """Proxy a Jellyfin poster image so it works from anywhere via Tailscale."""
    img = await jellyfin_tool.fetch_image(item_id)
    if img is None:
        raise HTTPException(status_code=404, detail="no image")
    data, content_type = img
    return Response(content=data, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})


def _srt_to_vtt(srt: str) -> str:
    """Convert SubRip (.srt) text to WebVTT."""
    out = ["WEBVTT", ""]
    lines = srt.replace("\r\n", "\n").split("\n")
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if line.isdigit() and i + 1 < len(lines) and "-->" in lines[i + 1]:
            i += 1
            continue
        if "-->" in line:
            out.append(line.replace(",", "."))
            i += 1
            while i < len(lines) and lines[i].strip():
                out.append(lines[i].strip())
                i += 1
            out.append("")
        else:
            i += 1
    return "\n".join(out)


@app.get("/api/media/subtitles")
async def media_subtitles(path: str = "") -> Response:
    """Return WebVTT subtitles for a movie (from a .srt next to the file)."""
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    local = jellyfin_tool.local_path(path)
    if not os.path.isfile(local):
        raise HTTPException(status_code=404, detail="file not found")
    folder = os.path.dirname(local)
    srt_files: list[str] = []
    for d in (folder, os.path.join(folder, "Subs"), os.path.join(folder, "subs")):
        if os.path.isdir(d):
            for f in os.listdir(d):
                if f.lower().endswith(".srt"):
                    srt_files.append(os.path.join(d, f))
    if not srt_files:
        raise HTTPException(status_code=404, detail="no subtitles")
    # prefer Estonian subtitles
    srt_files.sort(key=lambda f: 0 if ("est" in f.lower() or "eesti" in f.lower()) else 1)
    try:
        with open(srt_files[0], encoding="utf-8", errors="replace") as fh:
            srt = fh.read()
    except OSError as err:
        raise HTTPException(status_code=404, detail="subtitle unreadable") from err
    return Response(content=_srt_to_vtt(srt), media_type="text/vtt", headers={"Cache-Control": "no-cache"})


_UNSUPPORTED_AUDIO = {"dts", "dca", "truehd", "mlp", "vorbis", "flac", "pcm_s16le", "pcm_s24le"}
_audio_codec_cache: dict[str, tuple[float, str]] = {}


def _audio_codec(path: str) -> str:
    """Return the primary audio codec of a file (cached for an hour)."""
    now = time.time()
    if path in _audio_codec_cache and now - _audio_codec_cache[path][0] < 3600:
        return _audio_codec_cache[path][1]
    codec = ""
    try:
        out = subprocess.run(
            ["/usr/lib/jellyfin-ffmpeg/ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=12,
        )
        codec = out.stdout.strip().lower()
    except Exception:  # noqa: BLE001
        codec = ""
    _audio_codec_cache[path] = (now, codec)
    return codec


def _transcode_generator(path: str):
    """Stream the file with audio transcoded to AAC (video copied)."""
    cmd = [
        "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-hide_banner", "-loglevel", "error",
        "-i", path,
        "-map", "0:v:0", "-c:v", "copy",
        "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "frag_keyframe+empty_moov",
        "-f", "mp4", "pipe:1",
    ]
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, bufsize=0)
    try:
        while True:
            chunk = proc.stdout.read(1024 * 1024)
            if not chunk:
                break
            yield chunk
    finally:
        try:
            proc.stdout.close()
        except Exception:  # noqa: BLE001
            pass
        proc.terminate()


@app.get("/api/media/stream")
async def media_stream(request: Request, path: str = "") -> Response:
    """Stream a movie file straight from the Pi's disk (Range support for seeking)."""
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    local = jellyfin_tool.local_path(path)
    if not os.path.isfile(local):
        raise HTTPException(status_code=404, detail="file not found on disk")

    # iPhones can't decode DTS/TrueHD etc. — remux with AAC audio instead.
    if _audio_codec(local) in _UNSUPPORTED_AUDIO:
        return StreamingResponse(
            _transcode_generator(local),
            media_type="video/mp4",
            headers={"Content-Disposition": "inline", "Cache-Control": "no-store"},
        )
    size = os.path.getsize(local)
    filename = os.path.basename(local)
    content_type = mimetypes.guess_type(local)[0] or "application/octet-stream"
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if content_type == "application/octet-stream" and ext in ("mp4", "m4v", "mov"):
        content_type = "video/mp4"
    if content_type == "application/octet-stream" and ext == "mkv":
        content_type = "video/x-matroska"

    def _iter(start: int, end: int):
        with open(local, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                data = f.read(min(1024 * 1024, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    range_header = request.headers.get("range")
    if range_header:
        m = re.match(r"bytes=(\d*)-(\d*)", range_header)
        if m:
            start = int(m.group(1)) if m.group(1) else 0
            end = int(m.group(2)) if m.group(2) else size - 1
            end = min(end, size - 1)
            if start > end:
                start = 0
            headers = {
                "Content-Range": f"bytes {start}-{end}/{size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(end - start + 1),
                "Content-Disposition": f'inline; filename="{filename}"',
            }
            return StreamingResponse(_iter(start, end), status_code=206, media_type=content_type, headers=headers)

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(size),
        "Content-Disposition": f'inline; filename="{filename}"',
    }
    return StreamingResponse(_iter(0, size - 1), media_type=content_type, headers=headers)


if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
