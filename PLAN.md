# Home Voice Assistant — Project Plan

Current work and deployment caveats are summarized in
[`docs/SESSION_SUMMARY.md`](docs/SESSION_SUMMARY.md). Older audit sections below
are historical snapshots; use the current delivery checklist for status.

The proposed UI direction and motion handoff for a future agent is in
[`docs/DESIGN_BRIEF.md`](docs/DESIGN_BRIEF.md). It is **design guidance only**;
review prototypes with the owner before redesigning the app.

## Current delivery — unified inventory, reliability and media

Decision: SQLite is the sole inventory used by the Fridge tab, widget, receipts,
barcode tools, recipes and voice. Keep legacy inventory rows as an archive and
migrate non-destructively into a package-level table. hOn remains an explicitly
triggered, idempotent, **import-only** source; do not delete or mutate cloud
items automatically. The app UI stays in English. Do not deploy without a DB
backup and live reconciliation review with the owner.

- [x] Add SQLite package-level migration, local tools, explicit hOn import,
      tombstones for removed cloud/legacy items and offline/mocked tests.
- [x] Switch iOS, widget, PWA, receipts, barcode and recipe readers/writers to
      the same inventory; cover offline hOn and duplicate/idempotency cases.
- [x] Add Python CI, Swift test target with deterministic resume tests, web DOM
      behavior tests, and a documented real-device acceptance checklist.
- [x] Fix Player resume race and HLS process/session recovery/shutdown with tests;
      add a Pi-local series/episodes fallback when Jellyfin is unavailable.
- [x] Pool Jellyfin HTTP connections, coalesce cold poster requests, and retain
      already-visited tab state; cover concurrency with mocked tests.
- [ ] Measure media/tab memory and bandwidth on a real Pi and iPhone.
- [ ] Keep UI labels and user-facing errors in English, improve integration
      recovery feedback, update docs, validate all affected targets and tests.
- [x] After adding tests, extract subtitle routes from `main.py` and the
      Continue Watching component from `MediaView.swift`.
- [ ] Split remaining Media view components after adding view-level tests; do
      not expand the refactor without equivalent coverage.
- [ ] Run the real-device checklist on the Pi and phone **only after owner approval**;
      compare local/hOn counts, back up SQLite, and review cloud duplicates.

---

## Full-project usage and performance audit (previous)

Scope verified against the complete tracked text/source/configuration tree (plus
untracked tests). The longest source at the audit was `ios/HomeApp/MediaView.swift` (1,015
lines at first review); read in four consecutive chunks (1–260, 261–520,
521–780, 781–end) and later split to 958 lines with continued view logic moved
into its own file.
The generated Xcode user-state file is binary IDE data, not application source.
First-party reachability is not proof of production usage: the LLM can call any
registered tool, and external clients may call public HTTP endpoints.

### Safe, bounded work
- [x] Remove confirmed app-local unused models/helpers only; retain optional
      services/tools until usage or owner preference is established.
- [x] Preserve Assistant conversation state across tab switches and reuse the
      last working iOS server to avoid repeated failed connection timeouts.
- [x] Avoid blocking the FastAPI event loop on chat history; handle truncated
      weather forecasts safely. Add regression tests and build the iOS scheme.
- [x] Stop sending unused client chat history; check download HTTP status,
      slow redundant Jellyfin polling, and show Media action errors with retry.
- [x] Offload direct media scans, codec probing and deletion from the event loop;
      skip background watchers for unconfigured integrations. Correct single-file
      HTTP Range handling (including suffix and unsatisfiable ranges).
- [x] Show loading/retry states for Fridge and Shopping, preserve the shopping
      input on a failed Add, and confirm destructive Clear.

### Findings / proposed next actions (ordered)
1. **P0 — Security:** implement API auth before exposing tools. Cap STT/PDF body
   size on the Pi; reject internal/redirect targets for recipe URL import; audit
   web PWA's remaining inline handlers and interpolated HTML for XSS.
2. **P1 — User-visible bugs:** `PlayerView` can miss the resume seek when the
   backend responds after AVPlayer is ready. The app's unsupported video/codec
   paths need clear playback feedback; a series context-menu Delete currently
   opens a movie-style detail sheet. `FridgeView.importReceipt` reads entire PDFs
   on the main actor; move file reading off-main. `PlayerView` scans every WebVTT
   cue every 250 ms; use indexed lookup and only publish changed subtitles.
   Add UI tests for loading/retry and optimistic shopping actions; decide whether
   chat should survive app restarts (tab-switch persistence is now fixed).
3. **P1 — Latency and background load:** the iOS app now prefers the last
   working server and polls the movie library every 5 min, while chat history,
   filesystem movie scans, codec probing and deletes run off the FastAPI event
   loop; SQLite enables WAL once on init. Disabled integrations no longer
   launch useless background watchers. Still outstanding: Jellyfin creates a
   client per request; poster fetches can
   stampede on a cold cache. HLS jobs need startup/shutdown cleanup. The custom
   tab switch still recreates Media/Fridge/Shopping views and reloads their data.
   Electricity chart bars repeatedly recompute the maximum and need explicit
   handling for zero/negative exchange prices.
4. **P1 — Data ownership:** local SQLite inventory and hOn inventory have
   different writers/readers (widget, voice, fridge tab). Specify whether to
   mirror, reconcile, or show two distinct lists before removing either.
5. **P2 — Verified unused in this tree:** `db.cache_get/cache_set` and
   `device_cache` have no in-repo readers/writers; `jellyfin.media_file_info`
   has no in-repo caller; `Server.washer()` is not used by any widget.
   Swift-only models for old Jellyfin/Kodi URL/status responses, the unused
   DownloadManager.isDownloaded helper, an unused hOn helper argument and the
   PWA's unused close/search icons were removed. Do not remove public backend
   endpoints just because iOS does
   not call them; record usage first.
6. **P2 — Product/UX decisions:** `/api/stt`/Groq has no in-repo caller (native
   and web speech both run on device). `jellyfin_stream_url/download_url` and
   Kodi tools are LLM-accessible even without direct UI callers. Keep or retire
   only after checking actual usage and owner intent. Consider unifying server
   URL configuration across app/widget/share extension and reducing redundant
   Devices/Media navigation. Test tab caching with real device memory limits.

### Removal decisions from first-party reachability

| Candidate | Evidence from the complete source tree | Decision |
|---|---|---|
| `app/speech.py`, `/api/stt`, `GROQ_API_KEY` | Neither iOS (`SFSpeechRecognizer`) nor the PWA (`SpeechRecognition`) calls `/api/stt`. | Optional, **do not delete yet**: public clients and deployed Groq config are unknown. |
| `app/tools/kodi.py` and Jellyfin URL tools | No direct iOS/web caller; all are registered in `TOOLS` and offered to the LLM. | Keep until voice-tool usage and owner preference are known. |
| SQLite `device_cache`, `db.cache_get/set`, `jellyfin.media_file_info` | Defined but no first-party call site. | Candidate for a future backend cleanup; leave existing DB data and check out-of-repo scripts first. |
| `ios/Home.xcodeproj/.../xcuserdata/...xcuserstate` | Tracked binary Xcode window state, not a build input. | Untrack and ignore in a dedicated repository-hygiene change (leave the generated project itself until XcodeGen generation is automated). |
| `web/app.css` `.hero` / `.toggle` and `Theme.icy` | No markup or Swift view uses these styles/token. | Remove after a PWA visual smoke test; they are not whole features. |
| Widget/share extension, web PWA, receipts, local inventory | Registered as targets/routes and reached by the OS or other clients even without direct Swift call sites. | Keep; static zero-call assumptions would remove working features. |

---

## Codebase audit and cleanup (previous passes)

The original project roadmap is retained below for historical context. The current
implementation includes many features beyond that roadmap; use this section for
prioritized maintenance work rather than treating the old milestones as pending.

### This pass
- [x] Restrict media file access to the configured media root (including symlink and
      SMB-prefix cases) and make rejected paths return client errors.
- [x] Guard media deletion from removing a whole media collection when a movie
      file lives directly in its collection folder.
- [x] Add offline regression tests for path handling and validate the backend.

### Previous full source review
- [x] Keep barcode-less receipt items distinct in SQLite; test both that case and
      normal barcode upserts, including the existing-database migration.
- [x] Consolidate identical torrent-size formatting and repeated iOS media URL
      construction; remove confirmed dead state/types without changing API contracts.
- [x] Correct the iOS Series fallback and fridge search filtering; replace
      dynamic inline JS handlers with event listeners. Constrain failed-receipt
      filenames to the receipts folder. Validate Python, JS and an unsigned
      iOS simulator build.

### Next (separate, coordinated changes)
1. **P0 — Authenticate the API.** `/api/tools/{name}`, `/api/chat`, media,
   playback and receipt routes currently have no authentication; any network peer
   reaching port 8000 can read files or invoke destructive tools. Select an
   authentication approach for the PWA, iOS app, widget, share extension, and
   streaming URLs; enforce it server-side, rate-limit sensitive routes, then
   rotate affected service credentials. Tailscale alone is not authorization.
   Make `FS_ROOT` explicit rather than defaulting to a credential-bearing home
   directory, with a migration check for existing installations. Remove the
   remaining inline handlers in the web PWA and adopt a restrictive CSP.
2. **P1 — Add automated backend and client tests/CI.** Cover tool input validation,
   media playlist behavior, SQLite migrations, receipts and key device
   workflows with mocks; run Python 3.11 checks and iOS simulator build in CI.
3. **P1 — Bound uploads and work per request.** Receipt/STT uploads read the
   entire body into memory on a 1 GB Pi. Add enforced size limits and move
   blocking disk/ffprobe/HLS operations off the event loop; cap concurrent
   transcodes and clean up processes on shutdown.
4. **P1 — Fix cross-client data consistency.** The expiring widget queries SQLite
   while the fridge tab edits hOn inventory; choose one source of truth or
   explicitly surface both. `/api/chat` now sends only text and uses global SQLite
   history; decide whether to support per-client sessions in a separate migration.
   Align the PWA's `en-US` speech settings
   with the Estonian assistant. Investigate receipt-email messages marked seen
   before successful import; short weather forecasts are now handled.
5. **P1 — Harden recipe URL import.** `import_recipe` fetches caller-supplied URLs
   and follows redirects; prevent SSRF to Pi/LAN/Tailscale services before
   exposing the API to untrusted callers.
6. **P2 — Improve module boundaries.** Split `app/main.py` by domain and
   `ios/HomeApp/MediaView.swift` into smaller views after test coverage exists;
   consolidate the three Open Food Facts lookups (which currently have different
   offline/fallback behavior), shared client configuration and hard-coded URLs.
   Audit unused public helpers such as `db.cache_get/set` and
   `jellyfin.media_file_info` before removal. Update `AGENT_GUIDELINES.md` as
   architecture changes.

---

An AI voice assistant for the home: torrents, washer, fridge, ventilation, fridge inventory.
Runs on a Raspberry Pi 3 B+ (DietPi, 1 GB RAM). Phone is mic + speaker. Cloud LLM/STT.
Doubles as a portfolio piece for AI-integration roles.

---

## 1. Architecture

```
PHONE (browser web app — served by the Pi)
  │  mic: Web Speech API (free STT)      speaker: speechSynthesis (free TTS)
  │  WebSocket: audio/text in, text/audio out
  ▼
Pi 3 B+ — Python 3 + FastAPI + uvicorn (systemd service, ~50 MB RAM)
  │
  ├── LLM layer (cloud): GPT-4o-mini / Claude, native tool-calling
  │        system prompt + tool definitions → decides tool calls → executes → answers
  │
  ├── Tool: Transmission        → RPC localhost:9091 (JSON-RPC 2.0, snake_case)
  ├── Tool: Torrent search      → Prowlarr API (localhost:9696, X-Api-Key)
  ├── Tool: Washer              → SmartThings REST (api.smartthings.com, PAT)
  ├── Tool: Fridge              → hOn cloud (pyhOn, email+password)  [fragile — isolated]
  ├── Tool: Ventilation         → SaveConnect 2.0 local REST API (/mread, /mwrite) [Phase 4]
  ├── Tool: Inventory           → Open Food Facts v2 + local SQLite (barcode → product)
  │
  └── State: SQLite (inventory, device state cache, conversation memory)
```

Design principles:
1. **Every integration is a self-contained tool module** with a uniform interface:
   `status()` → dict, `act(...)` → result. One broken integration never kills the agent.
2. **LLM never talks to devices directly** — it only emits tool calls; Python executes,
   validates, returns structured results. This is the reliability boundary.
3. **Async everywhere** (FastAPI + httpx) — the Pi has one slow core.
4. **Graceful degradation**: if hOn/SmartThings is down, the assistant says so, not crash.

## 2. Code structure

```
home-voice-assistant/
├── app/
│   ├── main.py              # FastAPI app: /, /ws, /api/chat, static file serving
│   ├── config.py            # env vars: keys, tokens, IPs, ports, credentials
│   ├── llm.py               # LLM client: chat with tool-calling loop (OpenAI/Anthropic)
│   ├── prompts.py           # system prompt + tool descriptions (concise, strict)
│   ├── tools/
│   │   ├── __init__.py      # TOOLS registry: name → {schema, handler}
│   │   ├── base.py          # ToolResult, error conventions
│   │   ├── transmission.py  # torrent list/add/remove/status
│   │   ├── search.py        # Prowlarr search → magnet candidates
│   │   ├── washer.py        # SmartThings washer: status, start, notify
│   │   ├── fridge.py        # pyhOn fridge: temps, super-cool, door
│   │   ├── ventilation.py   # SaveConnect REST (/mread,/mwrite): fan speed, mode  (Phase 4)
│   │   └── inventory.py     # OFF lookup + SQLite add/list/expiring
│   ├── db.py                # SQLite helpers (inventory, state cache, history)
│   └── speech.py            # (optional) Groq STT endpoint; TTS is client-side
├── web/
│   └── index.html           # phone UI: mic button, Web Speech, speechSynthesis, WS client
├── scripts/
│   ├── install.sh           # Pi setup: python venv, deps, systemd unit
│   └── test_tools.py        # CLI smoke test per tool (no LLM needed)
├── data/                    # SQLite file lives here (gitignored)
├── requirements.txt
└── .env.example
```

## 3. The conversation loop (core)

```
user text (WS) → POST /api/chat {text, history}
  → llm.chat(messages, tools=TOOL_SCHEMAS)          # model picks tool or answers
  → if tool_calls: execute each handler → results appended as tool messages
  → llm.chat again with results (max 3 tool rounds) → final answer text
  → stream/return text → browser speaks it (speechSynthesis)
```

Safety: tool results are **sanitized dicts** (never raw API blobs). Hard limits on loop count.

## 4. Tool schemas (what the LLM can call)

| Tool | Arguments | Returns |
|---|---|---|
| `list_torrents` | — | name, % done, ETA, status |
| `add_torrent` | magnet_uri | added/duplicate/error |
| `torrent_status` | name substring | one torrent's details |
| `search_torrents` | query | top 5: title, size, seeders, magnet |
| `washer_status` | — | state, cycle, progress %, remaining |
| `washer_start` | — | ok / "Smart Control not enabled" |
| `fridge_status` | — | fridge+freezer temp, door |
| `fridge_set_temp` | zone, celsius | ok/error |
| `ventilation_status` | — | fan level, temps, filter days |
| `ventilation_set` | level (off/low/normal/high or user mode) | ok/error |
| `inventory_add` | barcode, expires ("friday"\|date) | product name + stored |
| `inventory_list` | — | items with expiry |
| `inventory_expiring` | days=3 | items expiring soon |

## 5. Phases & milestones (each phase = working, testable increment)

**Phase 0 — Prereqs (½ day)**
- Pi: Python 3 venv, fastapi/uvicorn/httpx/transmission-rpc/pyhOn/requests installed
- Transmission RPC reachable from localhost:9091 (check auth in settings.json)
- SmartThings PAT created + verified (`GET /v1/devices` shows the washer)
- hOn login tested (`pyhOn` CLI lists the fridge)
- Env file created
- ✅ Test: `scripts/test_tools.py` prints torrent list + washer state

**Phase 1 — Text agent + Transmission + Washer (weekend)**
- FastAPI app + `/api/chat` + tool-calling loop with GPT-4o-mini
- Tools: transmission (list/add/status), washer (status/start), plus `search_torrents` stubbed
- Simple phone web UI (text box, chat log)
- ✅ Test: "is the washer done?" → real answer. "add this magnet" → download starts.

**Phase 2 — Voice (½ day)**
- Web UI: mic button → Web Speech API → text → agent → speechSynthesis speaks reply
- ✅ Test: full voice loop from the couch

**Phase 3 — Torrent search + Fridge basics**
- Prowlarr installed on Pi (bare, not Docker), rargb.to indexer added; test without
  FlareSolverr first; FlareSolverr only on-demand if needed
- `search_torrents` + `add_torrent` ("download movie X" end-to-end)
- pyhOn fridge tools (status, set temp) + graceful failure if hOn login breaks
- ✅ Test: "download The Matrix" → search → magnet → Transmission → "downloaded" later

**Phase 4 — Ventilation (now just HTTP — no hardware!)**
- Find the SaveConnect 2.0 gateway's IP on the LAN (router DHCP list / `saveconnect.home.arpa`)
- Verify: `curl http://<ip>/menu` returns JSON → confirm gateway is 2.0
- Use register map from `antikristian/ha-saveconnect` source (0-based registers)
- Tools: `ventilation_status` (/mread) + `ventilation_set` (/mwrite). Voice: "boost ventilation"
- ✅ Test: fan speed actually changes
- Fallback if gateway is SaveConnect 1.0: Modbus path (RS485 A/B/GND + Elfin EW11 + pymodbus)

**Phase 5 — Fridge inventory (own mini-project)**
- Barcode scan in phone UI (BarcodeDetector/zxing) → OFF lookup → "expires when?" (speech
  or photo-OCR) → SQLite
- `inventory_expiring` + proactive morning check ("3 things expire this week")
- ✅ Test: scan 5 real groceries, get correct expiry alerts

**Phase 6 — Hardware + polish**
- ESP32-S3 + microWakeWord satellite (wake word) or USB mic on Pi
- Proactive notifications (washer done → push via ntfy.sh)
- Conversation memory, multi-user, dashboard page

## 6. Risks & mitigations

| Risk | Mitigation |
|---|---|
| hOn breaks (Haier backend changes — happened June 2026) | isolated module, health check, graceful message |
| Prowlarr/rargb.to search fails (Cloudflare) | FlareSolverr on-demand on Mac; fallback: paste magnet manually |
| SmartThings PAT expires / washer not startable remotely | honest UX: assistant explains Smart Control step |
| Pi 3 B+ RAM pressure | no Docker for heavy apps; monitor with `free -h`; swap tuning via DietPi |
| SaveConnect gateway turns out to be 1.0 (no REST API) | fallback: Modbus wiring (researched, do last, electrician if unsure) |
| Cloud LLM cost | GPT-4o-mini ≈ fractions of a cent per command; cap with usage log |

## 7. Success criteria (what "done" means)

1. Voice command → real action on ≥3 device types (torrents, washer, fridge, ventilation)
2. Works from the phone, no keyboard, in normal room noise
3. Every integration degrades gracefully when its API is down
4. Config via .env only; one-command install on the Pi
5. Writeup: architecture diagram + what broke + how fixed (the portfolio artifact)
