# Home Voice Assistant

A personal **home automation + media platform** run by a Raspberry Pi 3 B+ and
controlled from a native iOS app (with a web PWA fallback). It ties together an
LLM (tool-calling) with real devices and self-hosted media, and adds a full
Netflix-style movie/TV experience that works from anywhere over Tailscale.

> **Portfolio angle:** the LLM never talks to devices directly — it only emits
> tool calls that Python validates and executes. One broken integration can
> never crash the agent.

## What it does

**Assistant (voice / chat, Estonian)**
- Samsung washer (SmartThings), Haier fridge (hOn), Systemair ventilation
- Weather, electricity prices (Nord Pool via Elering), shopping list
- Recipes (TheMealDB + URL/text import + LLM parsing), spending, barcode scanning
- Persistent memory (SQLite chat history)

**Media (Netflix-style)**
- Browse movies / series / cartoons with posters, ratings, cast
- **Play from anywhere** — the Pi streams files directly (no cloud, no Mac needed)
- Subtitles (auto `.srt` → overlay, Estonian preferred), downloads to the phone
- Episode picker for TV series
- Delete movies, manage torrents, drive usage

**Automation**
- **Letterboxd watchlist → auto-download** (Radarr + Prowlarr + Transmission)
- H.264-only rule so downloads always play on the TV
- Jellyfin auto-rescan, receipts auto-import, washer notifications

## Architecture

```
iPhone (SwiftUI app) ──Tailscale──▶ Pi 3 B+ (FastAPI :8000)
                                     ├─ LLM (DeepSeek) ─ tool calls → devices
                                     ├─ /api/media/stream  (serves films directly)
                                     ├─ Radarr :7878 · Prowlarr :9696 · Transmission :9091
                                     └─ SQLite (data/home.db)

Mac (laptop) ── Jellyfin :8096 ── metadata/posters (reads Pi via SMB/Tailscale)
```

- **Pi** is the always-on brain (backend + downloads). Code: `/opt/home-voice-assistant`, systemd.
- **Mac** runs Jellyfin for metadata only (the Pi is too weak to run Jellyfin).
- **Tailscale** makes everything reachable from anywhere (no port-forwarding).

## Tech stack

| Layer | Tech |
|---|---|
| Backend | Python 3.11, FastAPI, uvicorn, httpx, SQLite |
| AI | DeepSeek (OpenAI-compatible), tool-calling |
| iOS | SwiftUI, AVKit, Liquid Glass design, widgets, share extension |
| Media | Jellyfin (Mac), Radarr, Prowlarr, Transmission, ffmpeg (Pi) |
| Remote | Tailscale (Pi + Mac + iPhone) |

## Repo layout

```
app/            FastAPI backend (tools, LLM, config, DB)
ios/            SwiftUI app + widget + share extension (xcodegen project)
web/            Web PWA (index.html + app.js + app.css)
scripts/        install.sh, test_tools.py, import_receipt.py
data/           SQLite DB + cache (git-ignored)
.env            secrets (git-ignored)
```

## Docs

- **[AGENT_GUIDELINES.md](AGENT_GUIDELINES.md)** — full technical reference for
  AI agents / future contributors: every service, IP, API, tool, workflow,
  build step, and gotcha.
- `PLAN.md`, `RESEARCH.md` — original planning/research notes.

## Quick start

```bash
# backend (on the Pi)
cd /opt/home-voice-assistant
cp .env.example .env      # fill in keys
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000

# iOS app (on the Mac)
cd ios && xcodegen generate
xcodebuild -project Home.xcodeproj -scheme Home -destination 'platform=iOS,name=…' build
```

See **AGENT_GUIDELINES.md** for the complete, current picture (IPs, credentials,
deploy commands, known issues).
