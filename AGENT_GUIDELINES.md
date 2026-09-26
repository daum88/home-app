# Agent Guidelines — Build the Home Voice Assistant

You are an agent tasked with implementing this project. Follow this document exactly.
Read `RESEARCH.md` and `PLAN.md` in this folder first — they contain the verified
API research and the full plan. This file is your working instructions.

## Context

Build an AI voice assistant for a home, running on a **Raspberry Pi 3 B+ (1 GB RAM, DietPi)**.
The Pi is at `192.168.8.145` (SSH `root@192.168.8.145`, password in the user's notes — ask if
needed). Transmission (torrent client) already runs on it. Kodi also runs on it (be RAM-aware).

- Phone = mic + speaker (browser Web Speech API for STT, speechSynthesis for TTS — both free)
- LLM = cloud (OpenAI GPT-4o-mini or Anthropic Claude) with native tool-calling
- Devices: Samsung washer (SmartThings), Haier fridge (hOn), Systemair SAVE VTR 275
  ventilation (Modbus, Phase 4), torrents (Transmission + Prowlarr search)
- Fridge inventory feature (barcode → Open Food Facts → expiry tracking, Phase 5)

## Environment

- Python 3.9+ (Pi has 3.x via DietPi), FastAPI + uvicorn + httpx
- Env vars in `.env` (copy `.env.example`): `OPENAI_API_KEY` (or `ANTHROPIC_API_KEY`),
  `SMARTTHINGS_PAT`, `HON_USER`, `HON_PASS`, `TRANSMISSION_URL=http://localhost:9091`,
  `TRANSMISSION_USER/PASS` (may be empty), `PROWLARR_URL`, `PROWLARR_API_KEY`,
  `MODBUS_HOST` (Phase 4), `OFF_USER_AGENT` (identifying UA string)
- Run via systemd unit; no Docker on this Pi.

## Build order (do NOT skip ahead)

### Phase 0 — prereqs
1. Create the project structure from `PLAN.md` §2.
2. `requirements.txt`: fastapi, uvicorn[standard], httpx, pydantic, python-dotenv,
   transmission-rpc, pyhOn, requests (pymodbus added in Phase 4).
3. `scripts/install.sh`: create venv, pip install, copy .env.example, install systemd unit.
4. `scripts/test_tools.py`: CLI that prints, for each configured tool: transmission list,
   washer status, hOn appliances. Exit 0/1 per tool. This proves integrations BEFORE the LLM.

### Phase 1 — core agent + Transmission + washer
1. `app/tools/base.py`: define a uniform tool interface — every tool returns a sanitized
   Python dict (never raw API responses), raising typed errors that become friendly text.
2. `app/tools/transmission.py` — use `transmission-rpc`:
   - `list_torrents()`, `add_torrent(magnet)`, `torrent_status(name_substr)`
   - Note: Transmission 4.x → snake_case fields (`percent_done`, `download_dir`)
3. `app/tools/washer.py` — SmartThings REST (`https://api.smartthings.com`, Bearer PAT):
   - **VERIFIED: washer device id = `b6d6a88b-8f08-919d-e51d-7f4799882d38`** (component `main`)
   - `GET /v1/devices/{id}/status` → key fields: `washerOperatingState.machineState`
     (stop/run/pause), `washerOperatingState.washerJobState`, `washerOperatingState.completionTime`
     (ISO timestamp — use this for "washer done" notifications), `switch.switch`,
     `samsungce.washerOperatingState.scheduledJobs` (remaining phase minutes)
   - `POST /v1/devices/{id}/commands` → start (will fail unless Smart Control pressed —
     surface that as a friendly message, never a raw error)
4. `app/llm.py`: chat loop with OpenAI function calling (or Anthropic tool use):
   - system prompt: short, lists the user's devices and their real names ("your Samsung
     washer", "your Haier fridge"), instructs concise spoken-style answers
   - loop: model → tool calls → execute → append results → model → final answer
   - max 3 tool rounds; always return a text answer
5. `app/main.py`: FastAPI — `POST /api/chat` (JSON: text, optional history), `GET /` serves
   `web/index.html` statically.
6. `web/index.html`: minimal phone-friendly chat UI (text input, message list). No frameworks
   needed — plain JS + fetch. Dark theme.

**Acceptance:** from the phone browser, "is the washer done?" returns the real washer state.
"add this magnet <magnet>" starts a download in Transmission. `test_tools.py` passes.

### Phase 2 — voice
1. In `web/index.html`: mic button → `SpeechRecognition` (Web Speech API) → fill input →
   send → response spoken via `speechSynthesis`.
2. Handle unsupported browsers (Safari) with a fallback message ("use Chrome").

**Acceptance:** full hands-free voice loop from the couch.

### Phase 3 — torrent search + fridge basics
1. Install Prowlarr on the Pi (bare install, NOT Docker — RAM). Add rargb.to as indexer.
   Test WITHOUT FlareSolverr first. If rargb.to fails with 403/Cloudflare: try enabling
   FlareSolverr ON-DEMAND only (start process → search → stop) — never leave it running.
2. `app/tools/search.py`: `GET {PROWLARR_URL}/api/v1/search?query=...&type=search`
   header `X-Api-Key` → return top 5: title, size, seeders, magnetUrl, indexer.
3. Wire "download movie X" flow: LLM → search_torrents → present candidates → add chosen magnet.
4. `app/tools/fridge.py` with pyhOn: `fridge_status()` (temps, door), `fridge_set_temp(zone, c)`.
   Wrap ALL pyhOn calls in try/except; on auth failure return
   `{"error": "fridge offline (hOn login failed)"}` — agent must still answer gracefully.
   **hOn login note:** the user's hOn account is Google-linked. pyhOn needs email+password.
   Before this phase works, the user must define a password for that Gmail via the hOn app's
   password-reset flow (community-confirmed to work), OR the user creates a fresh
   email+password hOn account and invites it to the family group.

**Acceptance:** "download The Matrix" ends with a real download. Fridge status works.
Fridge failure does not break other tools.

### Phase 4 — ventilation (Systemair SAVE VTR 275) — HTTP, no hardware
1. **First verify the gateway type:** find the SaveConnect gateway's IP on the LAN (check the
   router's DHCP client list, or try `curl http://saveconnect.home.arpa/menu`). If `GET /menu`
   returns JSON → it's a SaveConnect **2.0** and has a local REST API. Use it:
   - `GET /menu` — device info (no auth)
   - `GET /mread?{"12101":1,...}` — read registers (0-based, value always 1)
   - `GET /mwrite?{"1130":3}` — write register
   - Register → meaning map: copy from `antikristian/ha-saveconnect` source
     (`custom_components/saveconnect/` — sensors/controls/alarms definitions)
2. `app/tools/ventilation.py`: `ventilation_status()` via /mread (temps, CO2, fan RPM/output %,
   mode, filter days); `ventilation_set(level)` via /mwrite (user mode / airflow / fan level).
3. If `/menu` is NOT reachable (SaveConnect 1.0, no REST API) → fall back to Plan B (Modbus):
   RS485 A/B/GND on the connection board + Elfin EW11 gateway + pymodbus, register map from
   `maccan-tech/hass-systemair-save` (REG 101 fan speed, REG 207 setpoint). Verify first that
   the SaveConnect module does not occupy the port.

**Acceptance:** voice command changes the real fan speed/mode.

### Phase 5 — fridge inventory
1. `web/index.html`: "scan item" button → camera → `BarcodeDetector` (fallback: zxing-js).
2. `app/tools/inventory.py`:
   - `inventory_add(barcode, expires)` → `GET https://world.openfoodfacts.org/api/v2/product/{barcode}.json`
     (send identifying User-Agent) → store in SQLite (`data/home.db`): name, brands, barcode,
     expiry date. If OFF unknown → user provides name manually + category shelf-life default.
   - `inventory_list()`, `inventory_expiring(days=3)`
3. Expiry input: accept natural language ("friday", "in 5 days", "2026-10-01") — parse with
   small dateutil logic; photo-OCR of printed date is a later enhancement.
4. Proactive: a scheduled (cron/systemd timer) check posts "3 items expire soon" into the
   chat/notifications (ntfy.sh).

**Acceptance:** scan 5 real groceries → correct products stored → correct expiry alerts.

### Phase 6 — polish
- ESP32-S3 + microWakeWord satellite (separate firmware) OR USB mic + openWakeWord if Pi
  copes; push notifications via ntfy.sh; simple dashboard; write-up.

## Hard rules

0. **Never commit the SmartThings PAT** (currently `56ea9a4e-...` in the user's notes) or any
   other secret — they live ONLY in `.env` on the Pi.

1. **Never** run FlareSolverr (headless Chrome) permanently on the Pi — 1 GB RAM.
2. **Never** install Home Assistant — this project is custom FastAPI by design.
3. Tool handlers must be **non-blocking** (httpx async) and **timeout-bounded** (≤10 s).
4. Every external API call gets try/except + friendly error dict. One dead API ≠ dead agent.
5. Secrets ONLY in `.env` (never committed). Ship `.env.example` with placeholders.
6. Keep answers short and spoken-style ("Your washer has 23 minutes left" not a data dump).
7. Test each tool standalone via `scripts/test_tools.py` before wiring it to the LLM.
8. Write no code for a phase until the previous phase passes its acceptance test.

## Definition of done (project)

1. Voice command → real action on torrents + washer + fridge + ventilation
2. Works from the phone in normal noise, no keyboard
3. Every integration degrades gracefully when its API is down
4. One-command install (`scripts/install.sh`) on a fresh Pi
5. `README.md`: architecture diagram, setup steps, what-broke-and-how-fixed write-up
