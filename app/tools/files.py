"""Local filesystem tools — let the assistant answer questions about files.

The assistant can browse folders, read files and search by name/content within
the configured root (default: the home directory of the machine running the
server). Reads are size-capped and searches are bounded so a bad query can't
lock up the Pi.
"""
from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any

from .. import config
from .base import ToolError

FS_ROOT = config.FS_ROOT
READ_LIMIT = config.FILE_READ_LIMIT
MAX_DIR_ENTRIES = 200
MAX_SEARCH_FILES = 20000
MAX_SEARCH_HITS = 50

_EXCLUDED_DIRS = {".git", "node_modules", ".venv", "venv", ".cache", ".Trash", "Library", ".local", "__pycache__"}


def _resolve(path: str) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = Path(FS_ROOT) / p
    p = p.resolve()
    root = Path(FS_ROOT).resolve()
    if not (str(p) == str(root) or str(p).startswith(str(root) + os.sep)):
        raise ToolError("that path is outside the allowed area")
    return p


def _read_text(path: Path) -> tuple[str, bool]:
    with open(path, "rb") as f:
        data = f.read(READ_LIMIT + 1)
    truncated = len(data) > READ_LIMIT
    data = data[:READ_LIMIT]
    try:
        return data.decode("utf-8"), truncated
    except UnicodeDecodeError:
        return data.decode("utf-8", errors="replace"), truncated


def _name_search(root: Path, query: str) -> list[str]:
    q = query.lower()
    hits: list[str] = []
    count = 0
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _EXCLUDED_DIRS and not d.startswith(".")]
        for name in filenames:
            count += 1
            if count > MAX_SEARCH_FILES:
                return hits
            if q in name.lower():
                hits.append(str(Path(dirpath) / name))
                if len(hits) >= MAX_SEARCH_HITS:
                    return hits
    return hits


def _grep_search(root: Path, query: str) -> list[str]:
    cmd = [
        "grep", "-ril", "--exclude-dir=.git", "--exclude-dir=node_modules",
        "--exclude-dir=.venv", "--exclude-dir=Library", "--exclude-dir=.cache",
        query, str(root),
    ]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=8)
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return []
    return [line for line in proc.stdout.splitlines() if line][:MAX_SEARCH_HITS]


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

async def list_files(path: str = ".") -> dict[str, Any]:
    """List the contents of a directory."""
    p = await asyncio.to_thread(_resolve, path)
    if not p.exists():
        raise ToolError(f"no such path: {path}")
    if not p.is_dir():
        raise ToolError(f"that's a file, not a directory: {path}")
    entries: list[dict[str, Any]] = []
    for child in sorted(p.iterdir()):
        try:
            st = child.stat()
            entries.append({
                "name": child.name,
                "type": "dir" if child.is_dir() else "file",
                "size": st.st_size if child.is_file() else None,
            })
        except OSError:
            continue
    return {"path": str(p), "entries": entries[:MAX_DIR_ENTRIES]}


async def read_file(path: str) -> dict[str, Any]:
    """Read a text file (size-capped)."""
    p = await asyncio.to_thread(_resolve, path)
    if not p.exists():
        raise ToolError(f"no such file: {path}")
    if p.is_dir():
        raise ToolError(f"that's a directory, not a file: {path}")
    content, truncated = await asyncio.to_thread(_read_text, p)
    return {"path": str(p), "size": p.stat().st_size, "content": content, "truncated": truncated}


async def search_files(query: str, path: str = ".") -> dict[str, Any]:
    """Search for files by name or text content."""
    q = (query or "").strip()
    if not q:
        raise ToolError("what should I search for?")
    root = await asyncio.to_thread(_resolve, path)
    if not root.is_dir():
        root = root.parent
    name_matches = await asyncio.to_thread(_name_search, root, q)
    content_matches = await asyncio.to_thread(_grep_search, root, q)
    return {
        "query": q,
        "path": str(root),
        "name_matches": name_matches,
        "content_matches": content_matches,
    }


async def disk_usage() -> dict[str, Any]:
    """Free / used / total space on the media drive (in GB)."""
    total, used, free = await asyncio.to_thread(shutil.disk_usage, config.FS_ROOT)
    return {
        "root": config.FS_ROOT,
        "total_gb": round(total / 1e9, 1),
        "used_gb": round(used / 1e9, 1),
        "free_gb": round(free / 1e9, 1),
    }
