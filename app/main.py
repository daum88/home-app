"""FastAPI app: serves the phone web UI and the chat endpoint.

Endpoints:
- GET  /            → web/index.html
- POST /api/chat    → {text} → {reply}
- POST /api/stt     → optional server-side STT (Groq), multipart file upload
- GET  /api/health  → liveness check
"""
from __future__ import annotations

import asyncio
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request, UploadFile, File
from fastapi.responses import FileResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, llm, speech
from . import letterboxd as letterboxd_sync
from .media_subtitles import resolve_media_path, router as subtitles_router
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
    await asyncio.to_thread(_hls_prune_orphans)
    jellyfin_tool.open_client()
    tasks = [
        asyncio.create_task(_receipt_watcher()),
        asyncio.create_task(_warm_up()),
        asyncio.create_task(_hls_cleanup()),
    ]
    if config.LETTERBOXD_USER and config.RADARR_API_KEY:
        tasks.append(asyncio.create_task(_letterboxd_watcher()))
    if config.JELLYFIN_URL and config.JELLYFIN_API_KEY:
        tasks.append(asyncio.create_task(_jellyfin_refresh_watcher()))
    log.info("Home Voice Assistant started (LLM=%s/%s)", config.LLM_PROVIDER, config.LLM_MODEL)
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        for task in tasks:
            with suppress(asyncio.CancelledError):
                await task
        await _hls_shutdown()
        await jellyfin_tool.close_client()


app = FastAPI(title="Home Voice Assistant", lifespan=lifespan)
app.include_router(subtitles_router)


class ChatRequest(BaseModel):
    text: str


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
    for m in await asyncio.to_thread(db.history_recent, 20):
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
    except Exception:  # noqa: BLE001 — always answer the user
        log.exception("chat error")
        reply = "Sorry, something went wrong on my end."

    reply = (reply or "").strip()
    await asyncio.to_thread(db.history_append_exchange, text, reply)
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


class PlaybackRequest(BaseModel):
    path: str
    position: float = 0.0
    duration: float = 0.0
    title: str = ""
    kind: str = ""
    image: str = ""
    series_id: str = ""
    season: int | None = None
    episode: int | None = None


class WatchedRequest(BaseModel):
    path: str
    watched: bool


@app.get("/api/playback")
async def playback_get(path: str = "") -> dict[str, Any]:
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    rec = await asyncio.to_thread(db.playback_get, path)
    if rec is None:
        return {"path": path, "position": 0.0, "duration": 0.0, "watched": False}
    rec["watched"] = bool(rec.get("watched"))
    return rec


@app.post("/api/playback")
async def playback_save(req: PlaybackRequest) -> dict[str, Any]:
    await asyncio.to_thread(
        db.playback_upsert, path=req.path, position=req.position, duration=req.duration,
        title=req.title, kind=req.kind, image=req.image, series_id=req.series_id,
        season=req.season, episode=req.episode,
    )
    return {"ok": True}


@app.post("/api/playback/watched")
async def playback_watched(req: WatchedRequest) -> dict[str, Any]:
    await asyncio.to_thread(db.playback_mark, req.path, req.watched)
    return {"ok": True}


@app.get("/api/playback/continue")
async def playback_continue() -> dict[str, Any]:
    items = await asyncio.to_thread(db.playback_continue, 20)
    for it in items:
        it["watched"] = bool(it.get("watched"))
    return {"items": items}


@app.get("/api/playback/status")
async def playback_status() -> dict[str, Any]:
    items = await asyncio.to_thread(db.playback_all)
    for it in items:
        it["watched"] = bool(it.get("watched"))
    return {"items": items}


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
    """Stream the file with audio transcoded to AAC (video copied) — used for offline downloads."""
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


_HLS_DIR = os.path.join(config.FS_ROOT, ".hls")
_hls_sessions: dict[str, dict[str, Any]] = {}
_hls_lock = asyncio.Lock()


def _hls_prune_orphans() -> None:
    root = Path(_HLS_DIR)
    if root.is_dir() and not root.is_symlink():
        for directory in root.iterdir():
            if (re.fullmatch(r"[a-f0-9]{32}", directory.name)
                    and directory.is_dir() and not directory.is_symlink()
                    and ((directory / "session.marker").exists() or (directory / "index.m3u8").exists())):
                shutil.rmtree(directory, ignore_errors=True)


def _hls_stop_session(session: dict[str, Any]) -> None:
    proc = session.get("proc")
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=2)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=2)
    shutil.rmtree(session["dir"], ignore_errors=True)


async def _hls_shutdown() -> None:
    async with _hls_lock:
        for session in list(_hls_sessions.values()):
            await asyncio.to_thread(_hls_stop_session, session)
        _hls_sessions.clear()


async def _hls_start(path: str) -> dict[str, Any]:
    """Start (or reuse) an ffmpeg HLS remux for a file. Returns its session."""
    async with _hls_lock:
        now = time.time()
        if path in _hls_sessions:
            _hls_sessions[path]["last"] = now
            return _hls_sessions[path]
        # keep at most 4 concurrent sessions so the drive/RAM never fills up
        while len(_hls_sessions) >= 4:
            oldest = min(_hls_sessions.values(), key=lambda s: s["last"])
            await asyncio.to_thread(_hls_stop_session, oldest)
            _hls_sessions.pop(oldest["path"], None)
        token = uuid.uuid4().hex
        d = os.path.join(_HLS_DIR, token)
        await asyncio.to_thread(os.makedirs, d, exist_ok=True)
        await asyncio.to_thread(Path(d, "session.marker").touch)
        cmd = [
            "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", path,
            "-map", "0:v:0", "-c:v", "copy",
            "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k",
            "-hls_time", "6", "-hls_list_size", "0",
            "-hls_segment_filename", os.path.join(d, "seg%05d.ts"),
            "-f", "hls", os.path.join(d, "index.m3u8"),
        ]
        try:
            proc = await asyncio.to_thread(subprocess.Popen, cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError:
            await asyncio.to_thread(shutil.rmtree, d, ignore_errors=True)
            raise
        sess = {"path": path, "token": token, "dir": d, "proc": proc, "last": now}
        _hls_sessions[path] = sess
        return sess


async def _hls_playlist(request: Request, path: str) -> Response:
    """Serve the growing HLS playlist with segment URLs rewritten to absolute."""
    sess = await _hls_start(path)
    playlist = os.path.join(sess["dir"], "index.m3u8")
    deadline = time.time() + 15
    while time.time() < deadline:
        if os.path.isfile(playlist) and os.path.getsize(playlist) > 0:
            break
        await asyncio.sleep(0.3)
    try:
        with open(playlist, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError as err:
        raise HTTPException(status_code=503, detail="transcoder starting") from err
    sess["last"] = time.time()
    seg_base = f"{str(request.base_url).rstrip('/')}/api/media/hls/{sess['token']}/"
    lines = []
    for line in text.splitlines():
        if line and not line.startswith("#") and line.endswith(".ts"):
            lines.append(seg_base + line)
        else:
            lines.append(line)
    return Response(content="\n".join(lines) + "\n",
                    media_type="application/vnd.apple.mpegurl",
                    headers={"Cache-Control": "no-store"})


@app.get("/api/media/hls/{token}/{filename}")
async def media_hls_segment(token: str, filename: str) -> Response:
    sess = next((s for s in _hls_sessions.values() if s["token"] == token), None)
    if sess is None:
        raise HTTPException(status_code=404, detail="unknown session")
    sess["last"] = time.time()
    safe = os.path.basename(filename)
    fp = os.path.join(sess["dir"], safe)
    if not os.path.isfile(fp):
        raise HTTPException(status_code=404, detail="segment missing")
    media_type = "application/vnd.apple.mpegurl" if safe.endswith(".m3u8") else "video/mp2t"
    return FileResponse(fp, media_type=media_type, headers={"Cache-Control": "no-store"})


async def _hls_cleanup() -> None:
    """Reap idle HLS sessions so segments don't pile up on the drive."""
    while True:
        await asyncio.sleep(60)
        now = time.time()
        async with _hls_lock:
            for path, sess in list(_hls_sessions.items()):
                proc = sess.get("proc")
                done = proc is not None and proc.poll() is not None
                idle = now - sess.get("last", 0)
                if (done and idle > 300) or idle > 1800:
                    await asyncio.to_thread(_hls_stop_session, sess)
                    _hls_sessions.pop(path, None)


def _parse_byte_range(header: str, size: int) -> tuple[int, int]:
    match = re.fullmatch(r"bytes=(\d*)-(\d*)", header.strip())
    if match is not None and size > 0:
        first, last = match.groups()
        if first:
            start = int(first)
            end = min(int(last), size - 1) if last else size - 1
            if start < size and start <= end:
                return start, end
        elif last and int(last) > 0:
            return max(0, size - int(last)), size - 1
    raise HTTPException(status_code=416, headers={"Content-Range": f"bytes */{size}"})


@app.get("/api/media/stream")
async def media_stream(request: Request, path: str = "", download: int = 0) -> Response:
    """Stream a movie file straight from the Pi's disk (Range support for seeking)."""
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    local = resolve_media_path(path)
    if not os.path.isfile(local):
        raise HTTPException(status_code=404, detail="file not found on disk")

    # Offline save: a complete MP4 (video copied, audio → AAC) so the iPhone
    # can always play it, whatever the source container/audio codec is.
    if download:
        return StreamingResponse(
            _transcode_generator(local),
            media_type="video/mp4",
            headers={"Content-Disposition": f'inline; filename="{os.path.splitext(os.path.basename(local))[0]}.mp4"',
                     "Cache-Control": "no-store"},
        )

    # iPhones can't decode DTS/TrueHD etc. — remux to HLS (AAC audio, seekable).
    if await asyncio.to_thread(_audio_codec, local) in _UNSUPPORTED_AUDIO:
        return await _hls_playlist(request, local)
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
        start, end = _parse_byte_range(range_header, size)
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
