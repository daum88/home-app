/* Home — iPhone web app for the Home Voice Assistant.
   Talks to the Pi over /api/chat and /api/tools/{name}. */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const $$ = (sel) => Array.from(document.querySelectorAll(sel));

  /* ------------------------------------------------------------------ icons */
  const svg = (p, extra) =>
    `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" ${extra || ""}>${p}</svg>`;

  const I = {
    chat: svg('<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5c-1.5 0-3-.4-4.2-1L3 21l2-5.3A8.5 8.5 0 1 1 21 11.5z"/>'),
    house: svg('<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V21h14V9.5"/>'),
    fridge: svg('<rect x="5" y="3" width="14" height="18" rx="2"/><path d="M5 9h14"/><path d="M9 6h.01"/>'),
    mic: svg('<path d="M12 15a3 3 0 0 0 3-3V6a3 3 0 1 0-6 0v6a3 3 0 0 0 3 3z"/><path d="M19 11a7 7 0 0 1-14 0"/><path d="M12 18v3"/>'),
    send: svg('<path d="M12 19V5"/><path d="m6 11 6-6 6 6"/>'),
    plus: svg('<path d="M12 5v14"/><path d="M5 12h14"/>'),
    scan: svg('<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><path d="M7 12h10"/>'),
    doc: svg('<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/><path d="M9 13h6M9 17h6"/>'),
    trash: svg('<path d="M4 7h16"/><path d="M9 7V4h6v3"/><path d="M6 7l1 13h10l1-13"/>'),
    chevron: svg('<path d="m9 6 6 6-6 6"/>'),
    refresh: svg('<path d="M20 12a8 8 0 1 1-2.3-5.7"/><path d="M20 3v4h-4"/>'),
    sparkle: svg('<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>'),
    washer: svg('<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/><path d="M12 8V6"/>'),
    fan: svg('<path d="M12 3v18"/><path d="M4 7h16"/><path d="M4 17h16"/><circle cx="12" cy="12" r="2"/>'),
    temp: svg('<path d="M14 14.8V5a2 2 0 0 0-4 0v9.8a4 4 0 1 0 4 0z"/>'),
    down: svg('<path d="M12 3v12"/><path d="m6 9 6 6 6-6"/><path d="M4 21h16"/>'),
  };

  /* ------------------------------------------------------------------ state */
  const state = {
    view: "assistant",
    chat: [],
    tts: true,
    speaking: false,
    recognising: false,
    devices: {},
  };

  /* ------------------------------------------------------------------ utils */
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function md(text) {
    let s = esc(text);
    s = s.replace(/\*\*(.+?)\*\*/g, "<b>$1</b>");
    s = s.replace(/^[-•]\s+/gm, "• ");
    s = s.replace(/\n/g, "<br>");
    return s;
  }

  let toastTimer;
  function toast(msg) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
  }

  async function api(path, opts) {
    const res = await fetch(path, opts);
    let data = {};
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
    return data;
  }

  function tool(name, args = {}) {
    return api("/api/tools/" + name, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ args }),
    });
  }

  /* theme */
  function applyTheme(t) {
    if (t === "dark") document.documentElement.setAttribute("data-theme", "dark");
    else document.documentElement.setAttribute("data-theme", "light");
    localStorage.setItem("theme", t);
    const b = $("#themeBtn");
    if (b) b.textContent = t === "dark" ? "🌙" : "☀️";
  }
  function toggleTheme() {
    applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark");
  }

  function daysLeft(iso) {
    if (!iso) return null;
    const d = new Date(iso.slice(0, 10) + "T00:00:00");
    const now = new Date(); now.setHours(0, 0, 0, 0);
    return Math.round((d - now) / 86400000);
  }

  function expiryBadge(iso) {
    const d = daysLeft(iso);
    if (d == null) return "";
    if (d < 0) return '<span class="badge red">expired</span>';
    if (d === 0) return '<span class="badge red">today</span>';
    if (d === 1) return '<span class="badge red">1 day</span>';
    if (d <= 3) return '<span class="badge orange">' + d + " days</span>";
    return '<span class="badge green">' + d + " days</span>";
  }

  function posLabel(p) {
    return { fridge: "🧊 Fridge", freezer: "❄️ Freezer", pantry: "🥫 Pantry" }[p] || p;
  }

  /* ------------------------------------------------------------------ tabs */
  const TABS = [
    { id: "assistant", label: "Assistant", icon: I.chat },
    { id: "devices", label: "Devices", icon: I.house },
    { id: "fridge", label: "Fridge", icon: I.fridge },
  ];

  function buildTabs() {
    $("#tabbar").innerHTML = TABS.map((t) =>
      `<button class="tab" data-view="${t.id}" role="tab">
         ${t.icon}<span>${t.label}</span>
       </button>`
    ).join("");
    $$("#tabbar .tab").forEach((b) =>
      b.addEventListener("click", () => setView(b.dataset.view))
    );
  }

  function setView(id) {
    state.view = id;
    $$("#tabbar .tab").forEach((b) => b.classList.toggle("on", b.dataset.view === id));
    const t = TABS.find((t) => t.id === id);
    $("#topbarTitle").textContent = t.label;
    $("#topbarActions").innerHTML = "";
    if (id === "assistant") renderAssistant();
    else if (id === "devices") loadDevices();
    else if (id === "fridge") loadFridge();
  }

  /* ------------------------------------------------------------------ assistant */
  function renderAssistant() {
    $("#topbarActions").innerHTML =
      `<button class="icon-btn" onclick="App.toggleTTS()" id="ttsBtn" title="Voice reply">🔊</button>`;
    $("#view").innerHTML = `
      <div class="quick">
        <button class="chip" onclick="App.quick('Is the washer done?')">Washer status</button>
        <button class="chip" onclick="App.quick('What is in my fridge?')">Fridge</button>
        <button class="chip" onclick="App.quick('Suggest 3 recipes using what is in my fridge')">🍳 Recipes</button>
        <button class="chip" onclick="App.quick('What expires this week?')">Expiring</button>
        <button class="chip" onclick="App.quick('Download The Matrix')">Torrents</button>
      </div>
      <div class="chat" id="chat"></div>
      <div class="composer">
        <button class="icon-btn" id="micBtn">${I.mic}</button>
        <div class="field"><input id="chatInput" type="text" placeholder="Ask anything…" autocomplete="off" /></div>
        <button class="icon-btn" id="sendBtn" style="background:var(--tint);color:#fff">${I.send}</button>
      </div>`;
    const chat = $("#chat");
    state.chat.forEach((m) => appendBubble(m.role, m.content, m.thinking));
    chat.scrollTop = chat.scrollHeight;

    $("#sendBtn").addEventListener("click", () => sendChat($("#chatInput").value));
    $("#chatInput").addEventListener("keydown", (e) => { if (e.key === "Enter") sendChat($("#chatInput").value); });
    $("#micBtn").addEventListener("click", toggleMic);
    updateTtsBtn();
  }

  function appendBubble(role, text, thinking) {
    const chat = $("#chat");
    if (!chat) return;
    const el = document.createElement("div");
    el.className = "bubble " + (thinking ? "thinking" : role);
    if (thinking || role === "user") el.textContent = text;
    else el.innerHTML = md(text);
    chat.appendChild(el);
    chat.scrollTop = chat.scrollHeight;
    return el;
  }

  async function sendChat(text) {
    text = (text || "").trim();
    if (!text) return;
    $("#chatInput").value = "";
    state.chat.push({ role: "user", content: text });
    appendBubble("user", text);
    const thinking = appendBubble("assistant", "…", true);
    try {
      const data = await api("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      thinking.remove();
      state.chat.push({ role: "assistant", content: data.reply });
      appendBubble("assistant", data.reply);
      if (state.tts) speak(data.reply);
    } catch (e) {
      thinking.remove();
      appendBubble("assistant", "⚠️ " + e.message, false);
    }
  }

  function quick(t) { sendChat(t); }

  function speak(text) {
    if (!("speechSynthesis" in window)) return;
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.0;
    const voices = speechSynthesis.getVoices();
    const v = voices.find((v) => /en(-|_)/i.test(v.lang)) || voices[0];
    if (v) u.voice = v;
    u.onend = () => { state.speaking = false; };
    state.speaking = true;
    speechSynthesis.speak(u);
  }

  function toggleTTS() {
    state.tts = !state.tts;
    if (!state.tts && state.speaking) speechSynthesis.cancel();
    updateTtsBtn();
  }
  function updateTtsBtn() {
    const b = $("#ttsBtn");
    if (b) { b.textContent = state.tts ? "🔊" : "🔇"; b.style.opacity = state.tts ? 1 : 0.5; }
  }

  /* ---- voice input ---- */
  let recognition = null;
  function toggleMic() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) { toast("Voice needs Chrome or Safari on iOS 14+"); return; }
    const btn = $("#micBtn");
    if (state.recognising) { recognition.stop(); return; }
    if (state.speaking) speechSynthesis.cancel();
    recognition = new SR();
    recognition.lang = "en-US";
    recognition.interimResults = false;
    state.recognising = true;
    btn.classList.add("recording");
    recognition.onresult = (e) => sendChat(e.results[0][0].transcript);
    recognition.onend = () => { state.recognising = false; btn.classList.remove("recording"); };
    recognition.onerror = (e) => { state.recognising = false; btn.classList.remove("recording"); toast("Voice: " + e.error); };
    recognition.start();
  }

  /* ------------------------------------------------------------------ devices */
  async function loadDevices() {
    $("#view").innerHTML = `<div class="empty"><h3>Loading…</h3></div>`;
    $("#topbarActions").innerHTML = `<button class="icon-btn" onclick="App.loadDevices()">${I.refresh}</button>`;

    const [w, f, v, t] = await Promise.allSettled([
      tool("washer_status"), tool("fridge_status"), tool("ventilation_status"), tool("list_torrents"),
    ]);
    state.devices = {
      washer: w.status === "fulfilled" ? w.value.data : null,
      fridge: f.status === "fulfilled" ? f.value.data : null,
      vent: v.status === "fulfilled" ? v.value.data : null,
      torrents: t.status === "fulfilled" ? (t.value.data || {}).torrents : [],
    };
    renderDevices();
  }

  function renderDevices() {
    const { washer, fridge, vent, torrents } = state.devices;
    const h = [];

    /* Washer */
    const ws = washer || {};
    const running = ["run", "running", "washing"].includes(ws.machine_state);
    h.push(`
      <div class="card">
        <div class="row">
          <div class="icon" style="background:linear-gradient(135deg,#0a84ff,#5856d6)">${I.washer}</div>
          <div class="body"><div class="label">Washer</div>
            <div class="sub">${esc(ws.machine_state || "unknown")}${ws.remaining_minutes != null ? " · " + ws.remaining_minutes + " min left" : ""}</div>
          </div>
          <span class="badge ${running ? "green" : "gray"}">${running ? "Running" : "Idle"}</span>
        </div>
        ${ws.progress != null ? `<div style="padding:0 16px 14px"><div class="progress"><span style="width:${Math.min(100, Number(ws.progress) || 0)}%"></span></div></div>` : ""}
        <div style="display:flex;gap:8px;padding:0 16px 16px">
          <button class="btn green small" onclick="App.washer('start')">Start</button>
          <button class="btn orange small" onclick="App.washer('pause')">Pause</button>
          <button class="btn red small" onclick="App.washer('stop')">Stop</button>
        </div>
      </div>`);

    /* Fridge */
    const fr = fridge || {};
    h.push(`
      <div class="card">
        <div class="row">
          <div class="icon" style="background:linear-gradient(135deg,#34c759,#30b0c7)">${I.temp}</div>
          <div class="body"><div class="label">Fridge</div>
            <div class="sub">${fr.fridge_door_open ? "door open" : "door closed"}</div></div>
          <span class="badge ${fr.fridge_door_open ? "red" : "green"}">${fr.fridge_door_open ? "Open" : "Closed"}</span>
        </div>
        <div class="row"><div class="body"><div class="label">Fridge temp</div></div><div class="value strong">${fr.fridge_temp != null ? fr.fridge_temp + "°" : "—"}</div></div>
        <div class="row"><div class="body"><div class="label">Freezer temp</div></div><div class="value strong">${fr.freezer_temp != null ? fr.freezer_temp + "°" : "—"}</div></div>
        <div class="row" style="border:none"><div class="body"><div class="label">Super cool / freeze</div></div>
          <div class="value">${fr.super_cool ? "❄️ cool" : ""} ${fr.super_freeze ? "🧊 freeze" : (fr.super_cool || fr.super_freeze ? "" : "off")}</div></div>
      </div>`);

    /* Ventilation */
    const ve = vent || {};
    h.push(`
      <div class="card">
        <div class="row">
          <div class="icon" style="background:linear-gradient(135deg,#ff9500,#ff375f)">${I.fan}</div>
          <div class="body"><div class="label">Ventilation</div>
            <div class="sub">${esc(ve.airflow || "—")} · CO₂ ${ve.co2 != null ? ve.co2 + " ppm" : "—"}</div></div>
          <button class="btn ghost small" onclick="App.openVentSheet()">Boost</button>
        </div>
        <div class="grid-2" style="margin:0 16px 16px;grid-template-columns:1fr 1fr">
          <div class="stat" style="background:var(--fill-2);box-shadow:none;border-radius:var(--r-inner)">
            <div class="k">Supply air</div><div class="v" style="font-size:22px">${ve.supply_temp != null ? ve.supply_temp + "°" : "—"}</div></div>
          <div class="stat" style="background:var(--fill-2);box-shadow:none;border-radius:var(--r-inner)">
            <div class="k">Filter</div><div class="v" style="font-size:22px">${ve.filter_days_left != null ? ve.filter_days_left + " d" : "—"}</div></div>
        </div>
      </div>`);

    /* Torrents */
    const trows = (torrents || []).map((t, index) => `
      <div class="row">
        <div class="icon" style="background:#5856d6">${I.down}</div>
        <div class="body"><div class="label" style="font-size:14px">${esc(t.name)}</div>
          <div class="sub">${esc(t.status)} · ${t.size}</div>
          <div class="progress" style="margin-top:6px"><span style="width:${Number(t.progress) || 0}%"></span></div></div>
        <button class="icon-btn torrent-remove" style="width:36px;height:36px;color:var(--red)" data-index="${index}">${I.trash}</button>
      </div>`).join("");
    h.push(`
      <div class="card">
        <div class="row">
          <div class="icon" style="background:#5856d6">${I.down}</div>
          <div class="body"><div class="label">Torrents</div><div class="sub">${(torrents || []).length} active</div></div>
        </div>
        ${trows || `<div class="row"><div class="body"><div class="sub">No torrents</div></div></div>`}
        <div style="display:flex;gap:8px;padding:0 16px 10px">
          <div class="field" style="flex:1"><input id="torrentSearch" type="text" placeholder="Search movies, shows…" /></div>
          <button class="btn small ghost" onclick="App.searchTorrents()">Search</button>
        </div>
        <div id="torrentResults" style="padding:0 16px"></div>
        <div style="display:flex;gap:8px;padding:0 16px 16px">
          <div class="field" style="flex:1"><input id="magnetInput" type="text" placeholder="Or paste a magnet link…" /></div>
          <button class="btn small" onclick="App.addTorrent()">Add</button>
        </div>
      </div>`);

    $("#view").innerHTML = h.join("");
    $$("#view .torrent-remove").forEach((button) => {
      button.addEventListener("click", () => removeTorrent(torrents[Number(button.dataset.index)].name));
    });
  }

  async function washer(action) {
    try {
      const r = await tool("washer_" + action);
      toast(r.ok ? "Washer: " + action : r.error);
      loadDevices();
    } catch (e) { toast(e.message); }
  }

  async function removeTorrent(name) {
    if (!confirm("Remove torrent?")) return;
    try {
      const r = await tool("torrent_remove", { name_substr: name });
      toast(r.ok ? "Removed" : r.error);
      loadDevices();
    } catch (e) { toast(e.message); }
  }

  async function addTorrent() {
    const v = $("#magnetInput").value.trim();
    if (!v) return;
    try {
      const r = await tool("add_torrent", { magnet_uri: v });
      toast(r.ok ? "Torrent added" : r.error);
      loadDevices();
    } catch (e) { toast(e.message); }
  }

  async function searchTorrents() {
    const q = $("#torrentSearch").value.trim();
    if (!q) return;
    const el = $("#torrentResults");
    el.innerHTML = '<div class="sub" style="padding:8px 0">Searching…</div>';
    try {
      const r = await tool("search_torrents", { query: q });
      const results = (r.data && r.data.results) || [];
      if (!results.length) { el.innerHTML = '<div class="sub" style="padding:8px 0">No results</div>'; return; }
      el.innerHTML = results.map((x, index) => `
        <div class="row" style="padding:10px 0">
          <div class="body">
            <div class="label" style="font-size:14px">${esc(x.title)}</div>
            <div class="sub">${esc(x.indexer || "")} · ${esc(x.seeders)} seeds · ${esc(x.size || "")}</div>
          </div>
          <button class="btn small green magnet-download" data-index="${index}">Download</button>
        </div>`).join("");
      $$("#torrentResults .magnet-download").forEach((button) => {
        button.addEventListener("click", () => downloadMagnet(results[Number(button.dataset.index)].magnet || ""));
      });
    } catch (e) { el.innerHTML = '<div class="sub" style="padding:8px 0">' + esc(e.message) + '</div>'; }
  }

  async function downloadMagnet(m) {
    try {
      const r = await tool("add_torrent", { magnet_uri: m });
      toast(r.ok ? "Downloading" : r.error);
      $("#torrentResults").innerHTML = "";
      loadDevices();
    } catch (e) { toast(e.message); }
  }

  function openVentSheet() {
    openSheet(`
      <div class="grabber"></div>
      <h2>Ventilation</h2>
      <p style="color:var(--text-2);font-size:14px;margin-bottom:14px">Fan speed</p>
      <div class="segmented" id="ventSeg">
        <button data-v="off">Off</button><button data-v="low">Low</button>
        <button data-v="normal">Normal</button><button data-v="high">High</button>
      </div>`);
    $$("#ventSeg button").forEach((b) => b.addEventListener("click", async () => {
      const r = await tool("ventilation_set", { level: b.dataset.v });
      toast(r.ok ? "Set to " + b.dataset.v : r.error);
      closeSheet();
    }));
  }

  /* ------------------------------------------------------------------ fridge */
  async function loadFridge() {
    $("#view").innerHTML = `<div class="empty"><h3>Loading…</h3></div>`;
    $("#topbarActions").innerHTML = `<button class="icon-btn" onclick="App.loadFridge()">${I.refresh}</button>`;

    try {
      const result = await tool("fridge_inventory_list");
      if (!result.ok) throw new Error(result.error || "Couldn't load fridge inventory");
      state.devices.fridgeItems = (result.data || {}).items || [];
      renderFridge();
    } catch (error) {
      $("#view").innerHTML = `<div class="empty"><h3>Couldn't load fridge</h3><p>${esc(error.message)}</p><button class="btn" onclick="App.loadFridge()">Retry</button></div>`;
    }
  }

  function renderFridge() {
    const items = state.devices.fridgeItems || [];
    const expiring = items.filter((item) => {
      const remaining = daysLeft(item.expires_on);
      return remaining !== null && remaining <= 7;
    });

    const actions = `
      <div class="card">
        <div class="row pressable" onclick="App.openAddItem()">
          <div class="icon" style="background:var(--tint)">${I.plus}</div>
          <div class="body"><div class="label">Add item</div></div><div class="value">${I.chevron}</div>
        </div>
        <div class="row pressable" onclick="App.openScan()">
          <div class="icon" style="background:var(--green)">${I.scan}</div>
          <div class="body"><div class="label">Scan barcode</div></div><div class="value">${I.chevron}</div>
        </div>
        <div class="row pressable" onclick="App.uploadReceipt()">
          <div class="icon" style="background:var(--orange)">${I.doc}</div>
          <div class="body"><div class="label">Import Coop receipt</div></div><div class="value">${I.chevron}</div>
        </div>
        <div class="row pressable" onclick="App.importHon()">
          <div class="icon" style="background:var(--tint)">${I.down}</div>
          <div class="body"><div class="label">Import hOn items</div><div class="sub">Copy cloud items once; hOn is unchanged</div></div><div class="value">${I.chevron}</div>
        </div>
        <div class="row pressable" onclick="App.recipes()">
          <div class="icon" style="background:var(--indigo)">🍳</div>
          <div class="body"><div class="label">Recipe ideas</div></div><div class="value">${I.chevron}</div>
        </div>
      </div>`;

    let expHtml = "";
    if (expiring.length) {
      expHtml = `<div class="section-h">Expiring soon</div>
        <div class="card">` + expiring.map((it) => `
          <div class="row"><div class="icon" style="background:var(--orange)">${I.sparkle}</div>
            <div class="body"><div class="label">${esc(it.name)}</div><div class="sub">${esc(it.expires_on || "")}</div></div>
            ${expiryBadge(it.expires_on)}</div>`).join("") + `</div>`;
    }

    const itemHtml = items.length
      ? items.map((it) => `
        <div class="row">
          <div class="icon" style="background:var(--fill);color:var(--text)">${it.position === "freezer" ? "❄️" : it.position === "pantry" ? "🥫" : "🧊"}</div>
          <div class="body"><div class="label">${esc(it.name)}</div>
            <div class="sub">${esc(it.quantity)} ${esc(it.unit)} · ${esc(posLabel(it.position))}</div></div>
          ${expiryBadge(it.expires_on)}
          <button class="icon-btn" style="width:36px;height:36px;color:var(--red)" onclick="App.removeFridgeItem(${it.id})">${I.trash}</button>
        </div>`).join("")
      : `<div class="empty"><div class="icon">🧊</div><h3>Fridge is empty</h3><p>Add items by scanning a barcode or importing a Coop receipt.</p></div>`;

    $("#view").innerHTML = actions + expHtml +
      `<div class="section-h">Fridge inventory</div><div class="card">${itemHtml}</div>`;
  }

  async function importHon() {
    if (!confirm("Copy hOn items to this app? Existing cloud items are not changed. Matching local items may appear twice.")) return;
    try {
      const result = await tool("fridge_inventory_import_hon");
      if (!result.ok) throw new Error(result.error || "Couldn't import hOn items");
      toast(`Imported ${result.data.imported} items; skipped ${result.data.skipped}`);
      loadFridge();
    } catch (error) { toast(error.message); }
  }

  async function removeFridgeItem(id) {
    if (!confirm("Remove this item?")) return;
    try {
      const r = await tool("fridge_inventory_remove", { item_id: id });
      toast(r.ok ? "Removed" : r.error);
      loadFridge();
    } catch (e) { toast(e.message); }
  }

  /* ---- add item sheet ---- */
  function openAddItem() {
    openSheet(`
      <div class="grabber"></div>
      <h2>Add to fridge</h2>
      <div class="field" style="margin:12px 0"><input id="addName" type="text" placeholder="Name (e.g. Milk 2.5%)" /></div>
      <div class="field" style="margin-bottom:12px"><input id="addExpiry" type="text" placeholder="Expires (e.g. in 5 days, 2026-10-01)" /></div>
      <div class="segmented" id="addPos">
        <button data-v="fridge" class="on">Fridge</button><button data-v="freezer">Freezer</button><button data-v="pantry">Pantry</button>
      </div>
      <button class="btn block big" style="margin-top:16px" onclick="App.submitAddItem()">Add item</button>`);
    $$("#addPos button").forEach((b) => b.addEventListener("click", () => {
      $$("#addPos button").forEach((x) => x.classList.remove("on"));
      b.classList.add("on");
    }));
  }

  function parseExpiry(str) {
    str = (str || "").trim();
    const iso = str.match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (iso) return iso[1] + "-" + iso[2] + "-" + iso[3];
    const dmy = str.match(/^(\d{1,2})[.\/](\d{1,2})[.\/](\d{4})$/);
    if (dmy) return dmy[3] + "-" + dmy[2].padStart(2, "0") + "-" + dmy[1].padStart(2, "0");
    const rel = str.match(/in\s+(\d+)\s+(day|week|month)s?/i);
    if (rel) {
      const d = new Date();
      const n = +rel[1];
      if (rel[2] === "day") d.setDate(d.getDate() + n);
      else if (rel[2] === "week") d.setDate(d.getDate() + n * 7);
      else if (rel[2] === "month") d.setMonth(d.getMonth() + n);
      return d.toISOString().slice(0, 10);
    }
    const d = new Date();
    d.setDate(d.getDate() + 7);
    return d.toISOString().slice(0, 10);
  }

  async function submitAddItem() {
    const name = $("#addName").value.trim();
    if (!name) { toast("Give it a name"); return; }
    const pos = ($("#addPos .on") || {}).dataset?.v || "fridge";
    const expires = parseExpiry($("#addExpiry").value);
    try {
      const r = await tool("fridge_inventory_add", { name, qty: 1, expires_on: expires, position: pos });
      toast(r.ok ? "Added to " + pos : (r.error || "Failed"));
      closeSheet();
      loadFridge();
    } catch (e) { toast(e.message); }
  }

  /* ---- barcode scan ---- */
  let scanStream = null;
  async function openScan() {
    if (!("BarcodeDetector" in window)) { toast("Scanning needs Chrome on Android"); return; }
    try {
      scanStream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" } });
      openSheet(`<div class="grabber"></div><h2>Scan barcode</h2>
        <video id="scanVideo" playsinline muted style="width:100%;border-radius:var(--r-inner);margin-top:10px"></video>`);
      const video = $("#scanVideo");
      video.srcObject = scanStream;
      const detector = new BarcodeDetector({ formats: ["ean_13", "ean_8", "upc_a", "upc_e", "code_128"] });
      let found = false;
      const tick = async () => {
        if (found) return;
        try {
          const codes = await detector.detect(video);
          if (codes.length) {
            found = true;
            stopScan();
            const barcode = codes[0].rawValue;
            closeSheet();
            sendChat("I scanned barcode " + barcode + ". Add it to the fridge inventory.");
            setTimeout(loadFridge, 2000);
          } else requestAnimationFrame(tick);
        } catch (_) { requestAnimationFrame(tick); }
      };
      requestAnimationFrame(tick);
    } catch (_) { toast("Camera access denied"); }
  }
  function stopScan() { if (scanStream) scanStream.getTracks().forEach((t) => t.stop()); scanStream = null; }

  /* ---- receipt upload ---- */
  function uploadReceipt() { $("#receiptFile").click(); }
  function handleReceipt(file) {
    const fd = new FormData();
    fd.append("file", file);
    toast("Importing receipt…");
    api("/api/receipts/import", { method: "POST", body: fd })
      .then((r) => {
        if (r.already_imported) toast("Already imported");
        else toast("Added " + (r.items || []).length + " items to fridge");
        loadFridge();
      })
      .catch((e) => toast(e.message));
  }

  async function recipes() {
    openSheet('<div class="grabber"></div><h2>Recipe ideas</h2><div id="recipesBody" style="padding:12px 0">Thinking…</div>');
    try {
      const r = await tool("suggest_recipes");
      if (!r.ok) { $("#recipesBody").innerHTML = esc(r.error); return; }
      const list = (r.data && r.data.recipes) || [];
      if (!list.length) { $("#recipesBody").innerHTML = '<div class="sub">No recipes found.</div>'; return; }
      $("#recipesBody").innerHTML = list.map((rec) => `
        <div class="recipe">
          <div class="recipe-name">${esc(rec.name)}</div>
          ${rec.category ? '<span class="badge gray">' + esc(rec.category) + '</span>' : ''}
          <div class="recipe-ing">${(rec.ingredients || []).map(esc).join(' · ')}</div>
          <div class="recipe-steps">${md(rec.instructions || '')}</div>
        </div>`).join('');
    } catch (e) { $("#recipesBody").innerHTML = esc(e.message); }
  }

  /* ------------------------------------------------------------------ sheet */
  function openSheet(html) {
    let mask = $("#sheetMask");
    if (!mask) {
      mask = document.createElement("div");
      mask.id = "sheetMask";
      mask.className = "sheet-mask";
      mask.innerHTML = `<div class="sheet" id="sheet"></div>`;
      document.body.appendChild(mask);
      mask.addEventListener("click", (e) => { if (e.target === mask) closeSheet(); });
    }
    $("#sheet").innerHTML = html;
    mask.classList.add("open");
  }
  function closeSheet() {
    stopScan();
    const mask = $("#sheetMask");
    if (mask) mask.classList.remove("open");
  }

  /* ------------------------------------------------------------------ boot */
  function init() {
    buildTabs();
    setView("assistant");
    applyTheme(localStorage.getItem("theme") || "light");
    $("#themeBtn").addEventListener("click", toggleTheme);
    $("#receiptFile").addEventListener("change", (e) => {
      const f = e.target.files && e.target.files[0];
      e.target.value = "";
      if (f) handleReceipt(f);
    });
    if ("speechSynthesis" in window) speechSynthesis.getVoices();
  }

  window.App = {
    setView, loadDevices, loadFridge, sendChat, quick, toggleTTS,
    washer, removeTorrent, addTorrent, searchTorrents, downloadMagnet, openVentSheet,
    removeFridgeItem, importHon, openAddItem, submitAddItem, openScan, uploadReceipt, recipes,
  };

  document.addEventListener("DOMContentLoaded", init);
})();
