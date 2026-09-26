# Home Voice Assistant — API & Integration Research

Status: verified 2026-09-12 via live sources (GitHub, PyPI, official docs, community).

---

## 1. Transmission (torrents) — ✅ EASY, LOCAL

**How it works:** Transmission exposes a JSON-RPC HTTP API on port **9091** (default).
Auth: HTTP Basic (username/password) OR just RPC whitelist. Sessions tracked with an
`X-Transmission-Session-Id` header (409 response tells you the new session id).

**Key methods:**
- `torrent-add` — add by magnet URI or file
- `torrent-get` — list with fields (id, name, status, percentDone, eta, downloadDir)
- `torrent-list` / `torrent-remove` / `torrent-start` / `torrent-stop`
- `session-get` / `session-set` — download dir, speed limits

**Important (verified):** Transmission **4.1.0+** added JSON-RPC 2.0 with **snake_case**
field names (`percent_done`, `download_dir`). The old camelCase protocol still works in 4.x
but is deprecated. DietPi's Transmission is 4.x → **use snake_case / JSON-RPC 2.0**.

**Library:** `transmission-rpc` (Python, maintained) or raw `requests` — raw is fine and lighter.

**Gotchas:** RPC auth can be disabled (localhost-only) or enabled; check DietPi settings
(`dietpi-software` → Transmission). If auth is on, the username/password live in
`/etc/transmission-daemon/settings.json` on the Pi.

---

## 2. SmartThings (Samsung washer WD90DG5G34BELE) — ✅ EASY, OFFICIAL API

**How it works:** REST API at `https://api.smartthings.com`. Auth = **Personal Access Token (PAT)**:
1. Create Samsung account → developer.smartthings.com → workspace
2. Generate PAT (menu → Personal Access Tokens)
3. `Authorization: Bearer <PAT>` header

**Key endpoints:**
- `GET /v1/devices` — list devices
- `GET /v1/devices/{id}` — device details (has `components`, `capabilities`)
- `GET /v1/devices/{id}/status` — current state of all components
- `POST /v1/devices/{id}/commands` — send command: `{"commands":[{"component":"main","capability":"...","command":"...","arguments":[...]}]}`

**✅ VERIFIED LIVE (2026-09-12) — the PAT works and the washer is reachable.**
- Device ID: `b6d6a88b-8f08-919d-e51d-7f4799882d38` ("washer", Samsung OCF Washer)
- Real state fields read today (component `main`):
  - `washerOperatingState.machineState` — `stop` / `run` / `pause`
  - `washerOperatingState.washerJobState` — `none` / ... / `complete`
  - `washerOperatingState.completionTime` — ISO timestamp when cycle ends ← **the key field for "washer done" notifications**
  - `samsungce.washerOperatingState.operatingState` — `ready` / `running` / `paused`
  - `samsungce.washerOperatingState.scheduledJobs` — `[{jobName: wash, timeInMin: 123}, {rinse, 26}, {spin, 13}]` ← remaining phase times
  - `switch.switch` — `on`/`off`
  - `samsungce.washerCycle` — current cycle + `supportedCycles` with full option tables (spin levels, water temps, drying levels)
  - `custom.washerWaterTemperature.washerWaterTemperature` — e.g. `40`
- Capability `remoteControlStatus` exists → the Smart Control session flag

**Washer capabilities (samsungce.* vendor caps):**
- `samsungce.washerOperatingState` — wash/rinse/spin/finish states
- `samsungce.washerJobState` — none/weightSensing/readyToWash/washing/.../complete
- `samsungce.washerCycle` — current cycle (cotton, synthetics, etc.)
- `samsungce.dryerOperatingState` — dryer side (it's a washer-dryer)
- `remoteControlStatus` — whether "Smart Control" session is active

**⚠️ Verified limitation — REMOTE START IS NOT TRULY REMOTE:**
Samsung requires you to: load the machine → close door → **physically press the "Smart Control"
button** on the machine to authorize a remote session. Only then can the API start it.
Opening the door breaks the session. Community sources (Samsung docs + HA community) confirm
there is no way around this. **So: notifications/status are fully reliable; "remote start" works
only after manual pre-authorization.** Design the assistant accordingly.

**Reference:** HA custom integration `dineshrajaram/ha-samsung-washer` shows exactly which
states/attributes are useful: machine state, job state, progress %, remaining time, current
cycle, water temp, spin speed, rinse count, dry level, cycle type.

---

## 3. hOn / pyhOn (Haier fridge EHBQW5519ECM) — ⚠️ MEDIUM, UNOFFICIAL + FRAGILE

**Library:** `pyhOn` (PyPI, by Andre0512) — "Control your Haier, Candy and Hoover appliances".
Unofficial, reverse-engineered. `pip install pyhOn`.

**Usage:**
```python
from pyhon import Hon
async with Hon(USER_EMAIL, PASSWORD) as hon:
    for appliance in hon.appliances: print(appliance.nick_name)
```
Each appliance exposes `data` (attributes), `settings` (writable parameters, e.g.
`startProgram`, temperatures), and `commands`. Fridges expose climate-style entities
(fridge/freezer target temp, super cool/freeze) and door sensors in the HA integration.

**✅ GOOGLE LOGIN — SOLVED (verified from issue #272 + comments):**
pyhOn needs email+password. If your hOn account was created with "Sign in with Google":
1. **Simplest:** in the hOn app, use the password-reset flow for the SAME Gmail → define a
   password → now log into pyhOn with email+password. (Community-confirmed: "I use google
   log in but in the hOn app you can use the same gmail to log in, just define a password")
2. **Alternative:** create a fresh hOn account with normal email+password, then invite it to
   your family group in the hOn app — it gains access to the same appliances.

**Risks (verified from repo issues, 2026):**
- **Haier retired the Salesforce login backend in June 2026** → open issue #330
  "All devices unavailable / 0 appliances loaded after June 2026". Login can break at any time.
- pyhOn last release: **2024-08** (v0.17.5) — stale but still used.
- 2FA-protected accounts not supported (issue #13).
- Haier previously sent a **legal takedown** to the hOn HA integration (later resolved).
- Your exact model (EHBQW5519ECM) is not in the 134 confirmed models list, but fridges are a
  supported appliance type and most unlisted models still work.

**Design rule:** wrap hOn behind an interface with a health check + graceful degradation.
If hOn breaks, the rest of the assistant must keep working.

---

## 4. Systemair SAVE VTR 275 (ventilation, SaveConnect app) — ✅ SOLVED! LOCAL REST API, NO HARDWARE NEEDED

**🎉 NEW FINDING (verified 2026-09-12): the SaveConnect 2.0 gateway exposes a LOCAL REST API.**
No cloud, no wiring, no Modbus gateway, no auth:

- Base URL: `http://<saveconnect-ip>` (find the gateway's IP on the LAN — e.g. check your
  router's DHCP table or try hostname `saveconnect.home.arpa`)
- `GET /menu` — device info, no auth
- `GET /mread?{"12101":1,"12102":1}` — read registers (value is always 1)
- `GET /mwrite?{"1130":3}` — write register (value = data to write)
- Register numbers are **0-based** (from the device's own JS source, not the 1-based Modbus PDF)
- Exposes ~100 entities: temps, humidity, CO2, fan RPM + output %, IAQ level, seasonal mode,
  user mode + airflow selects, temp setpoint, ECO mode, free cooling, 33 alarm types,
  filter remaining time, alarm log (up to 200 entries)

**Sources:** `antikristian/ha-saveconnect` (HA integration, includes the register map in its
source), `tesharp/systemair` (SAVE Connect 2 over web). The register definitions in
`ha-saveconnect/custom_components/saveconnect/` are the reference for which register = what.

**⚠️ To verify on day 1:** the gateway must be **SaveConnect 2.0** (the newer gateway box).
If the unit talks to the app through an older SaveConnect 1.0 gateway, the REST API may not
exist → fall back to the Modbus path below.

**Fallback (Plan B) — Modbus:**

**What we know (verified):**
- Systemair SAVE units (VR/VTC/VSR/**VTR** families) expose **Modbus RTU over 3-wire RS485
  (A, B, GND)** on their connection board. Confirmed by Loxone library docs + multiple
  community integrations.
- The **SaveConnect app/cloud has no public API** — ignore it.
- **`maccan-tech/hass-systemair-save`** — full Home Assistant integration over **Modbus TCP**,
  verified on SAVE VSR 300; **VTR models share the register map** (detected via a system-type
  register). Vendored device library: **`systemair-save-modbus`** (can be used standalone,
  without HA). Exposes: climate entity (off/fan-only, fan speed off/low/normal/high/auto,
  supply-air setpoint), temps (supply/extract/exhaust/outdoor), fan RPMs, filter days,
  alarm sensors, filter-reset button. Registers: fan speed = REG 101, setpoint = REG 207.
- Alternative: `tuomaz/homeassistant-systemair-modbus-rs485` (direct RS485).
- Hardware path: **Elfin EW11** (~€20, RS485↔WiFi, exposes Modbus TCP) wired to the unit's
  A/B/GND, OR Systemair's own "Modbus Gateway" product.
- A ModbusCloud free template for SAVE VTR exists (VTR500L/300/700/250) — more register reference.

**Gotchas:**
- ⚠️ Opening the unit + wiring is invasive (warranty, safety). Do it carefully, or with an electrician.
- ⚠️ Check whether the existing SaveConnect module already occupies the RS485/comms port — if
  it does, there may be a conflict; research before wiring.
- ⚠️ Need the register map (from `systemair-save-modbus` source) for VTR-specific registers.

**Plan:** Python + `pymodbus` client against the EW11's Modbus TCP, using the register map
from `systemair-save-modbus` as reference. Phase 4.

---

## 5. Torrent SEARCH (rargb.to is Cloudflare-walled) — ⚠️ MEDIUM

**Verified:** `rargb.to` returns **403 Cloudflare challenge** to plain requests. Direct
scraping from the Pi is dead on arrival.

**Solution: Prowlarr** (or Jackett):
- Prowlarr = indexer manager. Add rargb.to (and other public trackers) as indexers.
- **Search API:** `GET /api/v1/search?query=<title>&categories=2000&type=search`
  (needs API key header `X-Api-Key`). Returns releases with `magnetUrl`, `title`, `size`,
  `seeders`, `indexer`.
- Jackett is the lighter/simpler alternative (Torznab: `/api/v2.0/indexers/all/results/torznab`).
- **FlareSolverr** may be needed for rargb.to's Cloudflare — BUT it runs headless Chrome:
  ~160 MB idle → 500 MB+ per search. **Do NOT run it on the 1 GB Pi 3 B+.** Options:
  (a) skip it and test if Prowlarr can use rargb.to directly, (b) run FlareSolverr on-demand
  only (start container → search → stop), (c) run it on another machine.

**Recommendation:** Prowlarr on the Pi (it's .NET but okay when idle; watch RAM),
FlareSolverr only on-demand or on the Mac.

---

## 6. Open Food Facts (fridge inventory) — ✅ EASY, FREE, NO AUTH — ESTONIAN COVERAGE CONFIRMED

**Verified live:**
- Product lookup: `GET https://world.openfoodfacts.org/api/v2/product/{barcode}.json`
  → fields: `product_name`, `brands`, `categories`, `expiration_date` (when known), `image_url`.
- Search: `GET https://world.openfoodfacts.org/cgi/search.pl?search_terms=<q>&search_simple=1&action=process&json=1&page_size=N`
- Tested with Estonian products: search "piim" → Alma, Valio, Farmi products. Coverage is real.
- Set a proper `User-Agent` header (identifying your app) — OFF asks for it.

**Expiration reality (verified):** barcodes do NOT encode expiry dates. Some OFF products
have a static `expiration_date` (rare). Real flow must be:
1. Phone camera scans barcode (browser `BarcodeDetector` API or `quagga2`/`zxing` JS lib)
2. OFF lookup → product name/category
3. User says/photos the expiry date (speech → parse "milk expires Friday" OR photo → OCR the
   printed date) → store in SQLite
4. Fallback when OFF doesn't know the product: manual name + category-based shelf-life
   defaults (e.g. milk 7 days, bread 4 days, etc.)

---

## 7. Voice pipeline — ✅ FREE OPTIONS FIRST

- **STT (Phase 1, free):** browser **Web Speech API** (`SpeechRecognition`) on the phone —
  zero cost, zero server. Caveat: uses Chrome's cloud STT; quality is good, requires Chrome/Edge.
- **STT (upgrade):** Groq `POST https://api.groq.com/openai/v1/audio/transcriptions`,
  model `whisper-large-v3-turbo`, multipart form. Fast + cheap (~$0.04/audio-hour). OpenAI
  Whisper API ($0.006/min = $0.36/hr) is the alternative.
- **TTS (all phases, free):** browser `speechSynthesis` API on the phone — no server TTS at all.
- **Wake word (Phase 6):** ESP32-S3 + `microWakeWord`, or later a USB mic on the Pi with
  openWakeWord (heavy for a Pi 3 B+ — prefer the ESP32 satellite).

---

## 8. LLM brain (tool-calling) — ✅ CLOUD

- **Recommended:** OpenAI GPT-4o-mini (cheap, reliable function-calling/JSON) or Anthropic
  Claude (Sonnet for stronger reasoning, Haiku for speed). Use **native tool-calling**
  (OpenAI `tools` param / Anthropic `tool_use`).
- **Avoid for the brain:** Groq's open models (Llama 3.x) — fast but flakier JSON/tool-call
  reliability (per community reports). Groq is fine for STT only.
- Approx cost: GPT-4o-mini ~$0.15/M input tokens — a voice command is fractions of a cent.

---

## 9. Platform: Raspberry Pi 3 B+ (1 GB) + DietPi — constraints

- **No Docker for heavy things** (FlareSolverr, Home Assistant) — RAM will thrash.
- Run: Python 3 + FastAPI + uvicorn (small footprint) directly via systemd.
- DietPi has `dietpi-software` for Transmission (already installed), Python, etc.
- Kodi is on the same box via HDMI — keep CPU headroom (Pi 3 B+ is already busy).
- The agent must be **async** (FastAPI/httpx) to stay responsive.

---

## Sources (key)

- Transmission RPC spec: github.com/transmission/transmission → docs/rpc-spec.md (4.1.0 = JSON-RPC 2.0, snake_case)
- SmartThings: developer.smartthings.com/docs + api.smartthings.com/v1 (PAT auth); Smart Control limitation per Samsung docs + HA community. **PAT verified live — washer device id `b6d6a88b-8f08-919d-e51d-7f4799882d38`**
- pyhOn: github.com/Andre0512/pyhOn (PyPI 0.17.5, 2024-08); hon integration repo issues #330 (Haier login backend retired June 2026); #272 (Google login → define a password for the same Gmail, or family-share a new account)
- Systemair SaveConnect 2.0: github.com/antikristian/ha-saveconnect (**local REST API**: /menu, /mread, /mwrite, no auth) + github.com/tesharp/systemair
- Systemair Modbus (fallback): github.com/maccan-tech/hass-systemair-save (Modbus TCP, register map, VTR-compatible); tuomaz/homeassistant-systemair-modbus-rs485; Loxone SAVE VTR library (3-wire RS485 on connection board)
- Prowlarr: prowlarr.com/docs/api-search; FlareSolverr RAM usage per community reports (160MB→500MB+)
- Open Food Facts: world.openfoodfacts.org/api/v2 (verified live; Estonian products present)
- Groq: console.groq.com/docs/speech-to-text (whisper-large-v3-turbo)
