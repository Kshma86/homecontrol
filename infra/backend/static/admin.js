let snapshot = null;
let activeTab = "irrigation";

const nanoConfigFields = [
  ["heartbeat_timeout_ms", "Heartbeat timeout [ms]"],
  ["pump_min_off_ms", "Pump min off [ms]"],
  ["pump_start_debounce_ms", "Pump start debounce [ms]"],
  ["pump_max_runtime_ms", "Pump max runtime [ms]"],
  ["sensor_conflict_warn_ms", "Conflict warn [ms]"],
  ["sensor_conflict_fault_ms", "Conflict fault [ms]"],
  ["sensor_conflict_clear_ms", "Conflict clear [ms]"],
  ["current_zero_v", "Current zero [V]"],
  ["current_max_valid_a", "Current max [A]"],
  ["supply_divider_ratio", "12V divider ratio"],
  ["supply_offset_v", "12V offset [V]"],
  ["supply_min_voltage_v", "12V min fault [V]"],
];

const els = {
  statusLine: document.getElementById("statusLine"),
  manualState: document.getElementById("manualState"),
  manualMeta: document.getElementById("manualMeta"),
  valveState: document.getElementById("valveState"),
  valveMeta: document.getElementById("valveMeta"),
  manualValveState: document.getElementById("manualValveState"),
  manualValveMeta: document.getElementById("manualValveMeta"),
  tankState: document.getElementById("tankState"),
  tankMeta: document.getElementById("tankMeta"),
  soilState: document.getElementById("soilState"),
  soilMeta: document.getElementById("soilMeta"),
  pumpState: document.getElementById("pumpState"),
  pumpMeta: document.getElementById("pumpMeta"),
  energyState: document.getElementById("energyState"),
  energyMeta: document.getElementById("energyMeta"),
  sessionRows: document.getElementById("sessionRows"),
  topicRows: document.getElementById("topicRows"),
  rawRows: document.getElementById("rawRows"),
  rawCount: document.getElementById("rawCount"),
  nanoConfigFields: document.getElementById("nanoConfigFields"),
  nanoConfigMeta: document.getElementById("nanoConfigMeta"),
  latestRows: document.getElementById("latestRows"),
  entityRows: document.getElementById("entityRows"),
  metricRows: document.getElementById("metricRows"),
  entityCount: document.getElementById("entityCount"),
  metricCount: document.getElementById("metricCount"),
  mqttState: document.getElementById("mqttState"),
  mqttMeta: document.getElementById("mqttMeta"),
  toast: document.getElementById("toast"),
};

function valueText(row) {
  if (row.v_num !== null && row.v_num !== undefined) return Number(row.v_num).toLocaleString("hu-HU");
  if (row.v_bool !== null && row.v_bool !== undefined) return row.v_bool ? "true" : "false";
  if (row.v_text !== null && row.v_text !== undefined) return row.v_text;
  return "-";
}

function dateText(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("hu-HU", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function firstLatest(entityName, key) {
  return snapshot?.irrigation?.latest?.find((row) => row.entity_name === entityName && row.key === key) || null;
}

function latestByKey(key) {
  return snapshot?.irrigation?.latest?.find((row) => row.key === key) || null;
}

function liveTopic(name) {
  return snapshot?.irrigation?.live?.topics?.[name] || null;
}

function liveJson(name) {
  const item = liveTopic(name);
  return item && typeof item.json === "object" && !Array.isArray(item.json) ? item.json : null;
}

function firstValue(source, keys) {
  if (!source) return undefined;
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null && source[key] !== "") return source[key];
  }
  return undefined;
}

function textValue(value) {
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function numberText(value, digits = 1) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(digits);
}

function unitValue(value, unit, digits = 1) {
  const text = numberText(value, digits);
  return text === "-" ? "-" : `${text} ${unit}`;
}

function ageText(item) {
  return item ? `${item.age_sec} s` : "-";
}

function shortValue(value, max = 120) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "-";
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

function setCard(id, value, meta, tone = "") {
  const el = document.getElementById(id);
  if (!el) return;
  el.classList.remove("warn", "bad");
  if (tone) el.classList.add(tone);
  el.querySelector("strong").textContent = value || "-";
  el.querySelector("span").textContent = meta || "-";
}

function showToast(message) {
  els.toast.textContent = message;
  els.toast.classList.add("show");
  window.setTimeout(() => els.toast.classList.remove("show"), 2800);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await readJsonResponse(response);
  if (!response.ok || data.ok === false) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  return data;
}

async function readJsonResponse(response) {
  const text = await response.text();
  if (!text) {
    throw new Error(response.ok ? "Empty response from API" : `HTTP ${response.status}: empty response from API`);
  }
  try {
    return JSON.parse(text);
  } catch {
    const preview = text.replace(/\s+/g, " ").trim().slice(0, 120);
    throw new Error(response.ok ? "Invalid JSON response from API" : `HTTP ${response.status}: ${preview || "invalid API response"}`);
  }
}

function renderSummary() {
  const running = snapshot.irrigation.sessions.find((item) => item.status === "running");
  const nano = liveJson("esp_nano_status");
  const metrics = liveJson("pump_metrics");
  const tankLive = liveJson("tank_level");
  const nanoItem = liveTopic("esp_nano_status");
  const metricsItem = liveTopic("pump_metrics");
  const tankItem = liveTopic("tank_level");

  const valveLive = textValue(nano?.valve || metrics?.valve);
  const valveCurrentValue = firstValue(metrics || nano, ["valve_current_a"]);
  const manualValveLive = textValue(nano?.manual_valve || metrics?.manual_valve);
  const valveDb = firstLatest("Irrigation controller", "valve_state");
  els.valveState.textContent = valveLive !== "-" ? valveLive : valveDb ? valueText(valveDb) : "-";
  els.valveMeta.textContent =
    valveLive !== "-"
      ? `${unitValue(valveCurrentValue, "A", 3)} | MQTT age ${ageText(metricsItem || nanoItem)}`
      : valveDb
        ? `DB ${dateText(valveDb.ts)}`
        : "No valve data yet";
  els.manualValveState.textContent = manualValveLive;
  els.manualValveMeta.textContent =
    metrics || nano
      ? `open=${textValue(nano?.manual_valve_open ?? metrics?.manual_valve_open)} | closed=${textValue(nano?.manual_valve_close ?? metrics?.manual_valve_close)}`
      : "No manual valve data yet";

  const valveText = valveLive !== "-" ? valveLive : valveDb ? valueText(valveDb) : "-";
  const manualValveText = manualValveLive;
  const valveLooksOpen = ["OPEN", "OPENING", "MOVING_OPEN", "BETWEEN"].some((part) => valveText.toUpperCase().includes(part));
  const manualValveLooksOpen = ["OPEN", "OPENING", "BETWEEN"].some((part) => manualValveText.toUpperCase().includes(part));
  const valveLooksClosed = valveText.toUpperCase().includes("CLOSED");
  if (valveLooksOpen || manualValveLooksOpen) {
    els.manualState.textContent = "Watering";
  } else if (running && valveLooksClosed) {
    els.manualState.textContent = "Timer active";
  } else if (running) {
    els.manualState.textContent = "Pending";
  } else {
    els.manualState.textContent = "Idle";
  }
  els.manualMeta.textContent = running
    ? `Safety close: ${dateText(running.requested_stop_at)} | valve=${valveText} | manual=${manualValveText}`
    : `valve=${valveText} | manual=${manualValveText}`;

  const tank = firstLatest("Tank_level", "liquid_level_percent") || latestByKey("liquid_level_percent");
  const tankPercent = firstValue(tankLive, ["liquid_level_percent", "percent", "level_percent"]);
  const tankDepthM = firstValue(tankLive, ["liquid_depth"]);
  const tankDepthCm = tankDepthM !== undefined ? Number(tankDepthM) * 100 : undefined;
  els.tankState.textContent =
    tankPercent !== undefined
      ? `${numberText(tankPercent, 0)}%${Number.isFinite(tankDepthCm) ? ` | ${numberText(tankDepthCm, 0)} cm` : ""}`
      : tank
        ? `${valueText(tank)}%`
        : "-";
  els.tankMeta.textContent =
    tankPercent !== undefined
      ? `depth=${Number.isFinite(tankDepthCm) ? `${numberText(tankDepthCm, 0)} cm` : "-"} | MQTT age ${ageText(tankItem)}`
      : tank
        ? `DB ${dateText(tank.ts)}`
        : "No data yet";

  const soil = firstLatest("Moisture_03", "soil_moisture") || firstLatest("Moisture_02", "soil_moisture");
  els.soilState.textContent = soil ? `${valueText(soil)}%` : "-";
  els.soilMeta.textContent = soil ? `Monitor only: ${dateText(soil.ts)}` : "Visible only, no automation";

  const pumpValue = firstValue(metrics || nano, ["pump"]);
  const currentValue = firstValue(metrics || nano, ["current_a", "pump_metrics_current_a"]);
  const voltageValue = firstValue(metrics || nano, ["voltage_12v", "pump_metrics_voltage_12v"]);
  const pump = firstLatest("Irrigation controller", "pump_running");
  els.pumpState.textContent = pumpValue !== undefined ? (Number(pumpValue) ? "Filling" : "Idle") : pump ? (pump.v_bool ? "Filling" : "Idle") : "-";
  els.pumpMeta.textContent = `${unitValue(currentValue, "A")} | ${unitValue(voltageValue, "V")}`;

  const energy = snapshot.irrigation.energy_daily[0];
  if (energy?.amp_hours !== null && energy?.amp_hours !== undefined) {
    els.energyState.textContent = `${numberText(energy.amp_hours, 2)} Ah`;
    els.energyMeta.textContent =
      `${unitValue(energy.watt_hours, "Wh", 1)} | active ${numberText(energy.active_minutes, 0)} min | max ${unitValue(energy.max_current_a, "A", 1)} | ${energy.current_samples || 0} samples`;
  } else {
    els.energyState.textContent = "No data";
    els.energyMeta.textContent = "Waiting for pump current samples";
  }
}

function renderLiveCards() {
  const live = snapshot.irrigation.live || {};
  const nano = liveJson("esp_nano_status");
  const nanoItem = liveTopic("esp_nano_status");
  const metrics = liveJson("pump_metrics");
  const metricsItem = liveTopic("pump_metrics");
  const diag = liveJson("esp_diag");
  const diagItem = liveTopic("esp_diag");
  const cfg = liveJson("nano_config");
  const cfgItem = liveTopic("nano_config");
  const solar = liveJson("solar");
  const solarItem = liveTopic("solar");

  const health = textValue(nano?.health || nano?.nano_health);
  const code = textValue(nano?.code_text || nano?.nano_code_text);
  setCard("cardHealth", `${health} | ${code}`, `Age: ${ageText(nanoItem)}`, health.includes("FAULT") ? "bad" : "");
  setCard("cardMode", textValue(nano?.mode || nano?.current_mode), `Age: ${ageText(nanoItem)}`);
  setCard("cardLevels", `L=${textValue(nano?.low)} | H=${textValue(nano?.high)}`, `Age: ${ageText(nanoItem)}`);
  setCard("cardTemp", `${numberText(metrics?.temp_c ?? nano?.temp_c ?? diag?.nano_temp_c, 2)} C`, `Age: ${ageText(metricsItem || diagItem)}`);
  setCard("cardEsp", `wifi=${textValue(diag?.wifi_rssi)} | nano=${textValue(diag?.nano_online ?? nano?.online)}`, `Age: ${ageText(diagItem)}`);
  setCard("cardConfig", `src=${textValue(cfg?.config_source)} | dirty=${textValue(cfg?.config_dirty)}`, `Age: ${ageText(cfgItem)}`);
  setCard("cardSolar", `bat=${textValue(solar?.battery_voltage)} V | chg=${textValue(solar?.charge_current)} A`, `pv=${textValue(solar?.pv_voltage)} V | Age: ${ageText(solarItem)}`);
  els.mqttState.textContent = live.mqtt_connected ? "online" : "offline";
  els.mqttMeta.textContent = live.last_error || `${live.broker?.host || "-"}:${live.broker?.port || "-"}`;
}

function renderNanoConfig() {
  const cfg = liveJson("nano_config") || {};
  const cfgItem = liveTopic("nano_config");
  els.nanoConfigMeta.textContent = `Age: ${ageText(cfgItem)} | src=${textValue(cfg.config_source)} | dirty=${textValue(cfg.config_dirty)}`;
  if (!els.nanoConfigFields.dataset.ready) {
    els.nanoConfigFields.innerHTML = "";
    for (const [key, labelText] of nanoConfigFields) {
      const label = document.createElement("label");
      label.htmlFor = `cfg-${key}`;
      label.textContent = labelText;

      const input = document.createElement("input");
      input.id = `cfg-${key}`;
      input.dataset.configKey = key;
      input.autocomplete = "off";

      const button = document.createElement("button");
      button.type = "button";
      button.textContent = "SET";
      button.dataset.configSet = key;

      els.nanoConfigFields.append(label, input, button);
    }
    els.nanoConfigFields.dataset.ready = "1";
  }
  for (const [key] of nanoConfigFields) {
    const input = els.nanoConfigFields.querySelector(`[data-config-key="${key}"]`);
    if (!input || document.activeElement === input) continue;
    input.value = cfg[key] ?? "";
  }
}

function renderTable(tbody, rows, columns) {
  tbody.innerHTML = "";
  if (!rows.length) {
    const tr = document.createElement("tr");
    const td = document.createElement("td");
    td.colSpan = columns.length;
    td.textContent = "No data";
    tr.appendChild(td);
    tbody.appendChild(tr);
    return;
  }
  for (const row of rows) {
    const tr = document.createElement("tr");
    for (const column of columns) {
      const td = document.createElement("td");
      td.textContent = column.render ? column.render(row) : row[column.key] ?? "-";
      tr.appendChild(td);
    }
    tbody.appendChild(tr);
  }
}

function render() {
  renderSummary();
  renderLiveCards();
  renderNanoConfig();
  renderTable(els.sessionRows, snapshot.irrigation.sessions, [
    { key: "id" },
    { key: "status" },
    { key: "started_at", render: (row) => dateText(row.started_at) },
    { key: "requested_stop_at", render: (row) => dateText(row.requested_stop_at) },
    { key: "stopped_at", render: (row) => dateText(row.stopped_at) },
  ]);
  renderTable(els.latestRows, snapshot.irrigation.latest, [
    { key: "entity_name" },
    { key: "key" },
    { key: "value", render: valueText },
    { key: "ts", render: (row) => dateText(row.ts) },
  ]);
  const topicRows = Object.entries(snapshot.irrigation.live?.topics || {}).map(([name, item]) => ({ name, item }));
  renderTable(els.topicRows, topicRows, [
    { key: "name" },
    { key: "age", render: (row) => ageText(row.item) },
    { key: "value", render: (row) => (row.item ? shortValue(row.item.json ?? row.item.payload) : "-") },
  ]);
  const raw = snapshot.irrigation.live?.raw || [];
  els.rawCount.textContent = `${raw.length} messages`;
  renderTable(els.rawRows, raw, [
    { key: "age", render: (row) => `${row.age_sec} s` },
    { key: "topic" },
    { key: "payload", render: (row) => shortValue(row.json ?? row.payload, 180) },
  ]);
  renderTable(els.entityRows, snapshot.entities, [
    { key: "id" },
    { key: "platform" },
    { key: "device_name" },
    { key: "name" },
    { key: "location" },
    { key: "topic_base" },
    { key: "status", render: (row) => row.status || "-" },
  ]);
  renderTable(els.metricRows, snapshot.metrics, [
    { key: "key" },
    { key: "value_type" },
    { key: "unit" },
    { key: "min_num" },
    { key: "max_num" },
    { key: "description" },
  ]);
  els.entityCount.textContent = `${snapshot.entities.length} entity`;
  els.metricCount.textContent = `${snapshot.metrics.length} metric`;
}

async function load() {
  els.statusLine.textContent = "Loading data...";
  snapshot = await api("/api/admin/bootstrap");
  els.statusLine.textContent = `DB online | ${snapshot.devices.length} device | ${snapshot.entities.length} entity`;
  render();
}

async function refreshIrrigation() {
  if (!snapshot || activeTab !== "irrigation") return;
  const data = await api("/api/irrigation/state");
  snapshot.irrigation = data;
  render();
}

function formDataObject(form) {
  return Object.fromEntries(new FormData(form).entries());
}

document.getElementById("refreshBtn").addEventListener("click", () => {
  load().catch((error) => showToast(error.message));
});

for (const button of document.querySelectorAll(".tab-btn")) {
  button.addEventListener("click", () => {
    const tab = button.dataset.tab;
    activeTab = tab;
    document.querySelectorAll(".tab-btn").forEach((item) => item.classList.toggle("active", item === button));
    document.querySelectorAll(".tab-panel").forEach((panel) => {
      panel.classList.toggle("active", panel.id === `tab-${tab}`);
    });
  });
}

document.getElementById("manualForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const button = event.submitter;
  button.disabled = true;
  try {
    const duration = Number(document.getElementById("durationMinutes").value || 20);
    await api("/api/irrigation/manual/start", {
      method: "POST",
      body: JSON.stringify({ duration_minutes: duration, started_by: "admin-ui" }),
    });
    showToast("Valve opened, safety close scheduled");
    await load();
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

window.setInterval(() => {
  refreshIrrigation().catch((error) => {
    els.statusLine.textContent = `Refresh error: ${error.message}`;
  });
}, 1000);

document.getElementById("stopManualBtn").addEventListener("click", async () => {
  try {
    await api("/api/irrigation/manual/stop", { method: "POST", body: "{}" });
    showToast("Valve close command sent");
    await load();
  } catch (error) {
    showToast(error.message);
  }
});

for (const button of document.querySelectorAll("[data-irrigation-command]")) {
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      if (button.dataset.irrigationCommand === "valve_open") {
        const duration = Number(document.getElementById("durationMinutes").value || 20);
        await api("/api/irrigation/manual/start", {
          method: "POST",
          body: JSON.stringify({ duration_minutes: duration, started_by: "admin-ui" }),
        });
        showToast("Valve opened, safety close scheduled");
      } else {
        await api("/api/irrigation/command", {
          method: "POST",
          body: JSON.stringify({ name: button.dataset.irrigationCommand }),
        });
        showToast("Command sent");
      }
      window.setTimeout(() => load().catch((error) => showToast(error.message)), 800);
    } catch (error) {
      showToast(error.message);
    } finally {
      button.disabled = false;
    }
  });
}

els.nanoConfigFields.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-config-set]");
  if (!button) return;
  const key = button.dataset.configSet;
  const input = els.nanoConfigFields.querySelector(`[data-config-key="${key}"]`);
  button.disabled = true;
  try {
    await api("/api/irrigation/nano-config", {
      method: "POST",
      body: JSON.stringify({ key, value: input?.value ?? "" }),
    });
    showToast("Config value sent");
    window.setTimeout(() => refreshIrrigation().catch((error) => showToast(error.message)), 800);
  } catch (error) {
    showToast(error.message);
  } finally {
    button.disabled = false;
  }
});

document.getElementById("deviceForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formDataObject(event.currentTarget);
  const metricRules = String(data.metric_keys || "")
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .map((metric_key) => ({
      metric_key,
      store_mode: "both",
      deadband_num: null,
      min_interval_sec: 30,
      max_interval_sec: 300,
      is_enabled: true,
    }));
  delete data.metric_keys;
  data.metric_rules = metricRules;
  try {
    await api("/api/admin/devices", { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset();
    showToast("Sensor saved");
    await load();
  } catch (error) {
    showToast(error.message);
  }
});

document.getElementById("metricForm").addEventListener("submit", async (event) => {
  event.preventDefault();
  const data = formDataObject(event.currentTarget);
  data.enforce_validation = Boolean(event.currentTarget.elements.enforce_validation.checked);
  for (const key of ["min_num", "max_num"]) {
    data[key] = data[key] === "" ? null : Number(data[key]);
  }
  try {
    await api("/api/admin/metrics", { method: "POST", body: JSON.stringify(data) });
    event.currentTarget.reset();
    event.currentTarget.elements.enforce_validation.checked = true;
    showToast("Metric saved");
    await load();
  } catch (error) {
    showToast(error.message);
  }
});

load().catch((error) => {
  els.statusLine.textContent = "Hiba";
  showToast(error.message);
});
