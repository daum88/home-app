# Home Voice Assistant

A personal **home automation + media platform** run by a Raspberry Pi 3 B+ and
controlled from a native iOS app (with a web PWA fallback). It ties together an
LLM (tool-calling) with real devices and self-hosted media, and adds a full
Netflix-style movie/TV experience that works from anywhere over Tailscale.

> **Portfolio angle:** the LLM never talks to devices directly — it only emits
> tool calls that Python executes through handlers. Input validation is currently
> handler-specific (centralized validation is planned); integrations return tool
> errors rather than crashing the agent.

## What it does

**Assistant (voice / chat, English by default)**
- Samsung washer (SmartThings), Haier fridge (hOn), Systemair ventilation
- Weather, electricity prices (Nord Pool via Elering), shopping list
- Recipes (TheMealDB + URL/text import + LLM parsing), spending, barcode scanning
- Persistent memory (SQLite chat history)
- One SQLite fridge inventory shared by the app, widget, web and voice tools;
  existing hOn items can be imported explicitly without changing hOn

**Media (Netflix-style)**
- Browse movies / series / cartoons with posters, ratings, cast
- **Play from anywhere** — the Pi streams files directly (no cloud, no Mac needed)
- Subtitles (auto `.srt` → overlay, Estonian preferred), downloads to the phone
- Episode picker for TV series, including a Pi-local fallback when Jellyfin is offline
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

- **[AGENTS.md](AGENTS.md)** — full technical reference for
  AI agents / future contributors: every service, IP, API, tool, workflow,
  build step, and gotcha.
- [Session handoff](docs/SESSION_SUMMARY.md) — what was implemented, tested and
  still needs real-device review.
- [Design and motion brief](docs/DESIGN_BRIEF.md) — proposal for the next UI agent;
  **not approval to implement** a redesign.
- `PLAN.md` — current maintenance priorities and original roadmap;
  `RESEARCH.md` — original research notes.

## Security and testing

The assistant is designed so the LLM never talks to devices directly — it only emits
tool calls that Python executes through handlers, and integrations return tool errors
instead of crashing the agent. Input validation is currently handler-specific
(centralized validation is planned).

The API is a personal, single-user deployment and intentionally has **no authentication
yet** — it is reachable only over Tailscale, never exposed to the public internet.
Authentication is tracked as roadmap work in `PLAN.md`.

Run offline backend regression tests with Python 3.11 after installing
`requirements.txt`:

```bash
python -m unittest discover -s tests -v
npm ci && npm test            # web behavior tests
swift test --package-path ios/Packages/HomeCore   # iOS logic tests (no simulator)
cd ios
xcodegen generate
xcodebuild -project Home.xcodeproj -scheme Home \
  -destination 'platform=iOS Simulator,name=iPhone 17 Pro' CODE_SIGNING_ALLOWED=NO build
```

iOS logic tests live in the `HomeCore` Swift package (`ios/Packages/HomeCore`)
so they run in seconds on macOS without booting a simulator or building the
app; the `xcodebuild` step is a compile smoke check of the full app.

See [the real-device checklist](docs/DEVICE_CHECKLIST.md) before deploying;
CI and simulator tests do not replace Pi/iPhone acceptance checks.

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

See **AGENTS.md** for the complete, current picture (IPs, credentials,
deploy commands, known issues).
