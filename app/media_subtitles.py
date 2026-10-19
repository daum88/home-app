"""Media subtitle lookup and SubRip-to-WebVTT conversion."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response

from . import opensubtitles
from .tools import jellyfin as jellyfin_tool
from .tools.base import ToolError

router = APIRouter()


def srt_to_vtt(srt: str) -> str:
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


def _read_srt(path: str) -> str:
    """Read a .srt, trying UTF-8 first, then common Windows/Baltic encodings
    so Estonian special characters (õ ä ö ü š ž) survive."""
    data = Path(path).read_bytes()
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    for enc in ("cp1252", "cp1257", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


def resolve_media_path(path: str) -> str:
    try:
        return jellyfin_tool.local_path(path)
    except ToolError as err:
        raise HTTPException(status_code=400, detail=err.message) from err


@router.get("/api/media/subtitles")
async def media_subtitles(path: str = "") -> Response:
    """Return WebVTT subtitles for a movie (from a .srt next to the file)."""
    if not path:
        raise HTTPException(status_code=400, detail="missing path")
    local = resolve_media_path(path)
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
        # Auto-download from OpenSubtitles (Estonian first, then English).
        fetched = await opensubtitles.fetch_srt(local)
        if fetched:
            return Response(content=srt_to_vtt(fetched), media_type="text/vtt",
                            headers={"Cache-Control": "no-cache"})
        raise HTTPException(status_code=404, detail="no subtitles")
    # Prefer English subtitles; treat unmarked files as English, push explicit
    # Estonian ("-est"/"eesti") to the end.
    def _lang_rank(f: str) -> int:
        fl = f.lower()
        if "est" in fl or "eesti" in fl:
            return 2
        if "eng" in fl or "english" in fl:
            return 0
        return 1
    srt_files.sort(key=_lang_rank)
    try:
        srt = await asyncio.to_thread(_read_srt, srt_files[0])
    except OSError as err:
        raise HTTPException(status_code=404, detail="subtitle unreadable") from err
    return Response(content=srt_to_vtt(srt), media_type="text/vtt", headers={"Cache-Control": "no-cache"})
