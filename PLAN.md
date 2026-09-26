# Home Voice Assistant — Project Plan

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
