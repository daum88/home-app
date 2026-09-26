# Home Voice Assistant

A personal AI voice assistant for the home, running on a **Raspberry Pi 3 B+
(1 GB RAM, DietPi)**. The phone is the microphone and speaker; the Pi runs a
small FastAPI service that orchestrates a cloud LLM (tool-calling) against real
devices: torrents, a Samsung washer, a Haier fridge, a Systemair ventilation
unit, and a fridge inventory.

Built as a portfolio piece for AI-integration roles — the interesting part is
the **reliability boundary**: the LLM never talks to devices, it only emits tool
calls that Python executes and sanitizes, so one broken integration can never
kill the agent.

## Architecture

```
PHONE (browser web app — served by the Pi)
  │  mic: Web Speech API (free STT)     speaker: speechSynthesis (free TTS)
  │  HTTP POST /api/chat  {text, history}
  ▼
Pi 3 B+ — Python 3 + FastAPI + uvicorn (systemd, ~50 MB RAM)
  │
  ├── LLM layer (cloud): GPT-4o-mini / Claude, native tool-calling
  │        system prompt + tool schemas → tool calls → execute → answer
  │
  ├── Tool: Transmission   → RPC localhost:9091 (transmission-rpc)
  ├── Tool: Torrent search → Prowlarr API (localhost:9696, X-Api-Key)
  ├── Tool: Washer         → SmartThings REST (api.smartthings.com, PAT)
  ├── Tool: Fridge         → hOn cloud (pyhOn, email+password)  [fragile — isolated]
  ├── Tool: Ventilation    → SaveConnect 2.0 local REST (/mread, /mwrite)
  ├── Tool: Inventory      → Open Food Facts v2 + local SQLite
  │
  └── State: SQLite (inventory, device-state cache, conversation history)
```

**Design rules**

1. Every integration is a self-contained tool module with a uniform interface.
   Each returns a sanitized dict; failures raise `ToolError` with friendly text.
2. The LLM never talks to devices directly — it emits tool calls, Python runs
   them, validates and returns structured results.
3. Async everywhere (FastAPI + httpx); blocking calls go through
   `asyncio.to_thread`.
4. Graceful degradation: a dead hOn/SmartThings/ventilation API produces a
   friendly sentence, never a crash.

## Project layout

```
app/
  main.py            FastAPI: /, /api/chat, /api/stt, /api/health
  config.py          env vars (.env)
  llm.py             LLM client + tool-calling loop (OpenAI / Anthropic)
  prompts.py         system prompt
  db.py              SQLite helpers
  speech.py          optional Groq STT (TTS is client-side)
  tools/
    base.py          ToolError + result envelope
    transmission.py  list/add/status/remove torrents
    search.py        Prowlarr search
    washer.py        SmartThings washer
    fridge.py        hOn fridge (lazy import — isolated)
    ventilation.py   SaveConnect 2.0 REST
    inventory.py     Open Food Facts + SQLite
    __init__.py      TOOLS registry (schemas + handlers)
web/index.html       phone UI (mic, TTS, barcode scanner)
scripts/
  install.sh         one-command Pi setup (venv + systemd)
  test_tools.py      CLI smoke test per tool (no LLM)
```

## Setup (on the Pi)

```bash
git clone <repo> /opt/home-voice-assistant   # or scp the folder
cd /opt/home-voice-assistant
cp .env.example .env                          # then edit .env with your keys
sudo bash scripts/install.sh                  # venv + deps + systemd
.venv/bin/python scripts/test_tools.py        # verify each integration
```

Then open `http://<pi-ip>:8000` on your phone (use Chrome/Edge for voice).

### Prereqs per integration

| Integration | What you need |
|---|---|
| Transmission | Runs locally on the Pi (dietpi-software). Set RPC user/pass in `.env` if auth is on. |
| Washer (SmartThings) | A Personal Access Token from developer.smartthings.com. Washer id is pre-filled. |
| Fridge (hOn) | Email+password hOn account. If Google-linked, use the hOn app password-reset for that Gmail. |
| Torrent search | Prowlarr installed on the Pi, with an indexer added, and its API key in `.env`. |
| Ventilation | SaveConnect **2.0** gateway IP in `SAVECONNECT_URL` (find it in the router's DHCP table). |
| Inventory | Nothing — Open Food Facts is free and keyless. |

## Env vars

See `.env.example`. The important ones: `LLM_PROVIDER`, `OPENAI_API_KEY` (or
`ANTHROPIC_API_KEY`), `SMARTTHINGS_PAT`, `HON_USER`/`HON_PASS`,
`PROWLARR_API_KEY`, `SAVECONNECT_URL`, `OFF_USER_AGENT`.

**Never commit `.env`.** The SmartThings PAT and all other secrets live only on
the Pi.

## Testing

```bash
.venv/bin/python scripts/test_tools.py --list           # all tools
.venv/bin/python scripts/test_tools.py                  # smoke-test everything
.venv/bin/python scripts/test_tools.py --tool washer_status
```

Each phase of the plan has its own acceptance test (see `PLAN.md` §5).

## Coop receipt auto-import

Drop a Coop **e-receipt PDF** into `data/receipts/` (or upload it via the 📄
button in the web UI) and it lands in the fridge inventory automatically. The
pipeline:

1. Extracts the item lines (name + **EAN barcode** + quantity + price) from the
   PDF with `pypdf` — Coop's digital receipts are text-based, so no OCR.
2. Humanises each name and uses the receipt's Estonian name as the **primary
   name** (more specific and correct than Open Food Facts, which is often
   generic or in another language).
3. Fills in **brand + category** from Open Food Facts where the barcode is known.
4. Estimates an **expiry date** from a category → shelf-life table (receipts
   never contain expiry dates), based on the receipt's purchase date.
5. Writes to SQLite, **deduped by receipt number** so re-importing is safe.

```bash
.venv/bin/python scripts/import_receipt.py /path/to/ost_nr_123.pdf   # one file
.venv/bin/python scripts/import_receipt.py                           # scan data/receipts/
```

The server also runs a watcher that polls `data/receipts/` every 30 s, and the
voice assistant can trigger it with *"import my receipts"* (the `import_receipts`
tool). Items moved to `data/receipts/processed/` (or `failed/` on error).

The pipeline also pushes every food item into the **hOn app's fridge inventory**
(Haier's "Smart Inventory" feature). That API is separate from the appliance
control API, so it isn't in pyhOn — we reverse-engineered it from the hOn iOS app:

- `GET/POST {API}/inventory/v1/smart-inventory/{mac}/item(s)`
- `DELETE {API}/inventory/v1/smart-inventory/item/{id}`
- positions: `fridge` 2024687, `freezer` 2024686, `pantry` 2024688
- item types: numeric category ids (e.g. MILK 493, EGGS 116, PASTA 218)

Implementation: `app/tools/hon_inventory.py`. Weighed produce is stored in grams
(hOn keeps integer quantities), packaged goods as pieces. Non-food items are
skipped. If hOn is down, the receipt still imports to SQLite — graceful
degradation.

## What broke and how we fixed it (portfolio notes)

- **hOn login backend retired (June 2026).** Haier's cloud is reverse-engineered
  and can break anytime. Mitigation: the fridge tool lazy-imports pyhOn and
  wraps every call, so a broken hOn degrades to a friendly "fridge offline"
  message instead of taking down the agent.
- **rargb.to is Cloudflare-walled.** Direct scraping returns 403. We route
  search through Prowlarr instead, and deliberately **do not** run FlareSolverr
  on the 1 GB Pi (it needs 500 MB+ of RAM). If a specific indexer still 403s,
  run FlareSolverr on-demand on another machine.
- **Samsung washer can't truly remote-start.** Samsung requires the physical
  Smart Control button press before an API start. We designed the UX to explain
  this instead of pretending; status/notifications are fully reliable.
- **Systemair had no public API** — until we found the SaveConnect 2.0 gateway's
  local REST interface (`/mread`, `/mwrite`, no auth). That removed an entire
  Modbus wiring phase. Fallback (Modbus RTU + EW11) is documented in
  `RESEARCH.md` if the gateway turns out to be 1.0.
- **Pi 3 B+ RAM pressure.** No Docker, no Home Assistant, no FlareSolverr. The
  stack is a ~50 MB venv + uvicorn + systemd, with all I/O async.

## Roadmap

See `PLAN.md` §5. Phase 6 adds an ESP32-S3 wake-word satellite, ntfy.sh push
notifications, a dashboard, and multi-user memory.
