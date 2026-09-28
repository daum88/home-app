"""Media streaming routes, codec probing, and HLS/download session lifecycle."""
from __future__ import annotations

import asyncio
import hashlib
import mimetypes
import os
import re
import shutil
import subprocess
import time
import uuid
from contextlib import suppress
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, Response, StreamingResponse

from . import config
from .media_subtitles import resolve_media_path

router = APIRouter()


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


_UNSUPPORTED_VIDEO = {"mpeg4", "msmpeg4v3", "msmpeg4v2", "xvid", "divx", "div3",
                      "flv1", "wmv1", "wmv2", "wmv3", "vc1", "mpeg2video",
                      "vp8", "vp9", "rv40", "mjpeg"}
_video_codec_cache: dict[str, tuple[float, str]] = {}


def _video_codec(path: str) -> str:
    """Return the primary video codec of a file (cached for an hour)."""
    now = time.time()
    if path in _video_codec_cache and now - _video_codec_cache[path][0] < 3600:
        return _video_codec_cache[path][1]
    codec = ""
    try:
        out = subprocess.run(
            ["/usr/lib/jellyfin-ffmpeg/ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=codec_name", "-of", "csv=p=0", path],
            capture_output=True, text=True, timeout=12,
        )
        codec = out.stdout.strip().lower()
    except Exception:  # noqa: BLE001
        codec = ""
    _video_codec_cache[path] = (now, codec)
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


_DOWNLOAD_DIR = os.path.join(config.FS_ROOT, ".downloads")


def _download_mp4(path: str, transcode_video: bool = False) -> str:
    """Remux/transcode a file to a complete MP4 (video copied or H.264, audio → AAC),
    cached by source path + mtime + size, so downloads have a known size and
    the phone can show progress / download in the background."""
    os.makedirs(_DOWNLOAD_DIR, exist_ok=True)
    st = os.stat(path)
    key = hashlib.sha1(f"{path}:{st.st_mtime_ns}:{st.st_size}:{int(transcode_video)}".encode()).hexdigest()[:16]
    out = os.path.join(_DOWNLOAD_DIR, f"{key}.mp4")
    if os.path.isfile(out) and os.path.getsize(out) > 0:
        return out
    vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"] if transcode_video else ["-c:v", "copy"]
    cmd = [
        "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-i", path,
        "-map", "0:v:0", *vcodec,
        "-map", "0:a:0", "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-f", "mp4", out,
    ]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return out


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


async def _hls_start(path: str, transcode_video: bool = False) -> dict[str, Any]:
    """Start (or reuse) an ffmpeg HLS remux/transcode for a file. Returns its session."""
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
        vcodec = ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23"] if transcode_video else ["-c:v", "copy"]
        cmd = [
            "/usr/lib/jellyfin-ffmpeg/ffmpeg", "-hide_banner", "-loglevel", "error",
            "-i", path,
            "-map", "0:v:0", *vcodec,
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


async def _hls_playlist(request: Request, path: str, transcode_video: bool = False) -> Response:
    """Serve the growing HLS playlist with segment URLs rewritten to absolute."""
    sess = await _hls_start(path, transcode_video)
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


@router.get("/api/media/hls/{token}/{filename}")
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
    """Reap idle HLS sessions and old prepared-download files."""
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
        if os.path.isdir(_DOWNLOAD_DIR):
            for f in os.listdir(_DOWNLOAD_DIR):
                fp = os.path.join(_DOWNLOAD_DIR, f)
                if os.path.isfile(fp) and now - os.path.getmtime(fp) > 48 * 3600:
                    with suppress(OSError):
                        os.remove(fp)


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


@router.get("/api/media/stream")
async def media_stream(request: Request, path: str = "", download: int = 0) -> Response:
    """Stream a movie file straight from the Pi's disk (Range support for seeking)."""
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    local = resolve_media_path(path)
    if not os.path.isfile(local):
        raise HTTPException(status_code=404, detail="file not found on disk")

    audio = await asyncio.to_thread(_audio_codec, local)
    video = await asyncio.to_thread(_video_codec, local)
    transcode_video = video in _UNSUPPORTED_VIDEO

    # Offline save: serve the raw file when the iPhone can play its codecs
    # (instant, with a known size for progress + background), otherwise remux
    # to a complete MP4 file.
    if download:
        if transcode_video or audio in _UNSUPPORTED_AUDIO:
            out = await asyncio.to_thread(_download_mp4, local, transcode_video)
            return FileResponse(out, media_type="video/mp4",
                                filename=os.path.splitext(os.path.basename(local))[0] + ".mp4")
        # fall through to the raw-file serving below (Content-Length + Range)

    # iPhones can't decode XviD/DTS/TrueHD etc. — remux/transcode to HLS.
    if transcode_video or audio in _UNSUPPORTED_AUDIO:
        return await _hls_playlist(request, local, transcode_video)
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
