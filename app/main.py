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
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.responses import FileResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import config, db, llm, media_streaming, speech
from . import letterboxd as letterboxd_sync
from . import smartthings_oauth
from . import tmdb
from .media_subtitles import router as subtitles_router
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
    await asyncio.to_thread(media_streaming._hls_prune_orphans)
    jellyfin_tool.open_client()
    tasks = [
        asyncio.create_task(_receipt_watcher()),
        asyncio.create_task(_warm_up()),
        asyncio.create_task(media_streaming._hls_cleanup()),
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
        await media_streaming._hls_shutdown()
        await jellyfin_tool.close_client()


app = FastAPI(title="Home Voice Assistant", lifespan=lifespan)
app.include_router(subtitles_router)
app.include_router(media_streaming.router)


class ChatRequest(BaseModel):
    text: str


class ChatResponse(BaseModel):
    reply: str


class LogRequest(BaseModel):
    message: str


@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {"ok": True}


class OAuthExchangeRequest(BaseModel):
    code: str


@app.get("/api/tmdb/poster")
async def tmdb_poster(title: str = "", year: int = 0, kind: str = "movie") -> Response:
    """Proxy a TMDB poster image (cached on the drive) so posters work offline."""
    if not title:
        raise HTTPException(status_code=400, detail="missing title")
    data = await tmdb.poster_bytes(kind, title, year or None)
    if data is None:
        raise HTTPException(status_code=404, detail="no poster")
    return Response(content=data, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=86400"})


@app.get("/oauth/authorize")
async def oauth_authorize() -> Response:
    """Redirect to SmartThings' authorize page (open this once in a browser)."""
    if not smartthings_oauth.configured():
        raise HTTPException(status_code=400, detail="SmartThings OAuth not configured (set SMARTTHINGS_CLIENT_ID and SMARTTHINGS_CLIENT_SECRET)")
    return RedirectResponse(smartthings_oauth.authorize_url())


@app.post("/oauth/exchange")
async def oauth_exchange(req: OAuthExchangeRequest) -> dict[str, Any]:
    """Exchange an authorization code for tokens and store them."""
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="missing code")
    try:
        await smartthings_oauth.exchange_code(req.code.strip())
    except Exception as err:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"token exchange failed: {err}") from err
    return {"ok": True, "message": "SmartThings connected"}


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



if WEB_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(WEB_DIR)), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")
