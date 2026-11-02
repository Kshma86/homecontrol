import React, { useEffect, useMemo, useState } from "react";
import { AlertTriangle, ExternalLink, Pencil, RefreshCw, Save } from "lucide-react";
import { api } from "../../apiClient";
import { entitySelectLabel } from "../../entityHelpers";
import { displayEntityName } from "../../formatters";
import { roomDisplayName, roomKey } from "../../houseSensors";
import { IconButton, Table } from "../../uiPrimitives";
import { skinOptions } from "./adminOptions";

function localServiceUrl(port, path = "") {
  if (typeof window === "undefined") return `http://localhost:${port}${path}`;
  return `${window.location.protocol}//${window.location.hostname}:${port}${path}`;
}

const AI_NODE_HOST = "192.168.1.2";

const hcAdminLinks = [
  {
    name: "HomeControl UI",
    role: "React dashboard",
    address: () => localServiceUrl(3000),
    service: "homecontrol-frontend",
    access: "Web",
    note: "Main control surface",
  },
  {
    name: "Backend Health",
    role: "API status",
    address: () => localServiceUrl(5000, "/health"),
    service: "homecontrol-backend",
    access: "Web",
    note: "DB and MQTT health check",
  },
  {
    name: "AI Tab",
    role: "AI control surface",
    address: () => localServiceUrl(3000, "/#ai"),
    service: "homecontrol-frontend",
    access: "Web",
    note: "Remote AI PC, model and chat controls",
  },
  {
    name: "Backup Tab",
    role: "Backup and restore control",
    address: () => localServiceUrl(3000, "/#backup"),
    service: "homecontrol-frontend",
    access: "Web",
    note: "Archives, restic activity and staging restore",
  },
  {
    name: "AI Gateway Health",
    role: "AI server health",
    address: () => localServiceUrl(8095, "/health"),
    service: "homecontrol-ai-server",
    access: "Web",
    note: "Direct AI gateway readiness",
  },
  {
    name: "AI Gateway Config",
    role: "AI provider config",
    address: () => localServiceUrl(8095, "/config"),
    service: "homecontrol-ai-server",
    access: "Web",
    note: "Current provider, model and Ollama URL",
  },
  {
    name: "AI Backend Status",
    role: "AI API status",
    address: () => localServiceUrl(5000, "/api/ai/status"),
    service: "homecontrol-backend",
    access: "Web",
    note: "Backend view of AI gateway readiness",
  },
  {
    name: "AI Node Status",
    role: "Remote AI PC status",
    address: () => localServiceUrl(5000, "/api/ai/node/status"),
    service: "homecontrol-backend",
    access: "Web",
    note: "SSH, Ollama and remote node availability",
  },
  {
    name: "AI Models",
    role: "Ollama model list",
    address: () => localServiceUrl(5000, "/api/ai/models"),
    service: "homecontrol-backend",
    access: "Web",
    note: "Installed and recommended AI models",
  },
  {
    name: "Remote Ollama",
    role: "Remote model API",
    address: () => `http://${AI_NODE_HOST}:11434/api/tags`,
    service: "remote-ai-node",
    access: "Web",
    note: "Direct Ollama tags endpoint on AI PC",
  },
  {
    name: "Gitea Config Repo",
    role: "Versioned HC configuration",
    address: () => `http://${AI_NODE_HOST}:3002/homecontrol/config`,
    service: "homecontrol-ai-gitea",
    access: "Web",
    note: "Private repo: HA config, scripts, compose files",
  },
  {
    name: "Growatt Solar Dashboard",
    role: "Solar inverter page",
    address: () => "http://192.168.1.133:8123/",
    service: "homecontrol-ha-growatt-poller",
    access: "Web",
    note: "Home Assistant Growatt page",
  },
  {
    name: "Zigbee2MQTT",
    role: "Zigbee device console",
    address: () => localServiceUrl(8090),
    service: "zigbee2mqtt",
    access: "Web",
    note: "Pairing, device state, exposes",
  },
  {
    name: "PostgreSQL Adminer",
    role: "Database web admin",
    address: () => localServiceUrl(8080),
    service: "homecontrol-adminer",
    access: "Web",
    note: "Server: postgres, database: homecontrol",
  },
  {
    name: "PostgreSQL",
    role: "Database TCP endpoint",
    address: () => "postgres:5432 / host:5432",
    service: "homecontrol-postgres",
    access: "TCP",
    note: "Direct DB service inside compose",
  },
  {
    name: "PgBouncer",
    role: "Database pooler",
    address: () => "pgbouncer:5432 / host:6432",
    service: "homecontrol-pgbouncer",
    access: "TCP",
    note: "Backend uses this endpoint",
  },
  {
    name: "MQTT Broker",
    role: "Mosquitto broker",
    address: () => "mqtt:1883 / host:1883",
    service: "homecontrol-mqtt",
    access: "TCP",
    note: "Zigbee, X10, Climate and ingest bus",
  },
  {
    name: "HA Growatt Poller",
    role: "Home Assistant Growatt collector",
    address: () => "host network | HA:8123 | MQTT:1883",
    service: "homecontrol-ha-growatt-poller",
    access: "Worker",
    note: "Publishes Growatt cloud state into MQTT",
  },
  {
    name: "Growatt Grott Proxy",
    role: "Growatt inverter proxy",
    address: () => "growatt-grott:5279 / host:5279",
    service: "growatt-grott",
    access: "TCP",
    note: "Optional inverter proxy profile",
  },
];

const deviceTypePresets = {
  zigbee_plug: {
    label: "Zigbee plug",
    platform: "zigbee",
    model: "TS011F",
    manufacturer: "Zigbee",
    metrics: [
      ["switch_state", "both", null, 1, 300],
      ["power", "both", 1, 5, 300],
      ["current", "both", 0.02, 5, 300],
      ["energy_kwh", "both", 0.01, 30, 3600],
      ["mains_voltage_v", "both", 1, 30, 600],
      ["linkquality", "state", 1, 60, 600],
    ],
  },
  tuya_plug: {
    label: "Tuya plug",
    platform: "tuya",
    model: "Smart plug",
    manufacturer: "Tuya",
    metrics: [
      ["switch_state", "both", null, 1, 300],
      ["power_w", "both", 1, 5, 300],
      ["voltage_v", "both", 0.5, 30, 600],
      ["current_a", "both", 0.02, 5, 300],
      ["energy_kwh", "both", 0.01, 60, 3600],
      ["energy_calc_kwh", "state", 0.01, 60, 3600],
      ["lag_sec", "state", null, 30, 300],
      ["recv_ts", "state", null, 30, 300],
      ["src_ts", "state", null, 30, 300],
    ],
  },
  moisture_sensor: {
    label: "Moisture sensor",
    platform: "zigbee",
    model: "ZG-303Z",
    manufacturer: "HOBEIAN",
    metrics: [
      ["soil_moisture", "both", 1, 30, 300],
      ["dry", "both", null, 1, 300],
      ["temperature", "both", 0.1, 30, 600],
      ["humidity", "both", 1, 30, 600],
      ["battery", "both", 1, 300, 21600],
      ["linkquality", "both", null, 3600, 3600],
    ],
  },
  temp_humidity_sensor: {
    label: "Temp/humidity sensor",
    platform: "zigbee",
    model: "Temperature/humidity",
    manufacturer: "Zigbee",
    metrics: [
      ["temperature", "both", 0.1, 30, 600],
      ["humidity", "both", 1, 30, 600],
      ["battery", "both", 1, 300, 21600],
      ["linkquality", "state", 1, 60, 600],
    ],
  },
  temp_humidity_pressure_sensor: {
    label: "Temp/humidity/pressure sensor",
    platform: "zigbee",
    model: "Temperature/humidity/pressure",
    manufacturer: "Zigbee",
    metrics: [
      ["temperature", "both", 0.1, 30, 600],
      ["humidity", "both", 1, 30, 600],
      ["pressure_hpa", "both", 0.2, 30, 600],
      ["battery", "both", 1, 300, 21600],
      ["linkquality", "state", 1, 60, 600],
    ],
  },
  window_contact: {
    label: "Window contact",
    platform: "zigbee",
    model: "TS0203",
    manufacturer: "Tuya",
    openingType: "window",
    metrics: [
      ["contact", "both", null, 1, 86400],
      ["battery_low", "both", null, 1, 86400],
      ["battery", "both", 1, 3600, 86400],
      ["battery_voltage_mv", "both", 100, 3600, 86400],
      ["linkquality", "state", 1, 60, 600],
    ],
  },
  generic_sensor: {
    label: "Generic sensor",
    platform: "zigbee",
    model: "",
    manufacturer: "",
    metrics: [
      ["battery", "both", 1, 300, 21600],
      ["linkquality", "state", 1, 60, 600],
    ],
  },
};

function presetMetricRules(presetKey) {
  return (deviceTypePresets[presetKey]?.metrics || []).map(([metric_key, store_mode, deadband_num, min_interval_sec, max_interval_sec]) => ({
    metric_key,
    store_mode,
    deadband_num,
    min_interval_sec,
    max_interval_sec,
    is_enabled: true,
  }));
}

function rulesIncludeMetric(rules, metricKeys) {
  const keys = new Set(metricKeys);
  return rules.some((rule) => keys.has(rule.metric_key) && rule.is_enabled !== false);
}

function buildOpeningSensorRooms({ entities, entityMetrics }) {
  const rulesByEntity = new Map();
  entityMetrics.forEach((rule) => {
    if (!rulesByEntity.has(rule.entity_id)) rulesByEntity.set(rule.entity_id, []);
    rulesByEntity.get(rule.entity_id).push(rule);
  });

  const openingSensors = entities
    .map((entity) => {
      const rules = (rulesByEntity.get(entity.id) || []).slice().sort((a, b) => String(a.metric_key).localeCompare(String(b.metric_key)));
      if (!rules.some((rule) => rule.metric_key === "contact" && rule.is_enabled !== false)) return null;
      return {
        ...entity,
        entity_id: entity.id,
        entity_name: entity.name,
      };
    })
    .filter(Boolean);

  const grouped = openingSensors.reduce((acc, sensor) => {
    const label = roomDisplayName(sensor.location || "Unassigned");
    const key = roomKey(label) || "unassigned";
    if (!acc.has(key)) acc.set(key, { key, room: label, sensors: [] });
    acc.get(key).sensors.push(sensor);
    return acc;
  }, new Map());

  return [...grouped.values()]
    .map((group) => ({
      ...group,
      sensors: group.sensors.sort((a, b) => {
        const posA = Number.isFinite(Number(a.room_position)) ? Number(a.room_position) : Number.POSITIVE_INFINITY;
        const posB = Number.isFinite(Number(b.room_position)) ? Number(b.room_position) : Number.POSITIVE_INFINITY;
        if (posA !== posB) return posA - posB;
        return String(a.opening_label || a.entity_name).localeCompare(String(b.opening_label || b.entity_name), "hu");
      }),
    }))
    .sort((a, b) => {
      if (a.key === "unassigned") return 1;
      if (b.key === "unassigned") return -1;
      return a.room.localeCompare(b.room, "hu");
    });
}

export default function HcAdmin({ snapshot, reload, setToast, skin, setSkin }) {
  const [deviceForm, setDeviceForm] = useState({ platform: "zigbee", preset: "zigbee_plug", device_id: "" });
  const [metricForm, setMetricForm] = useState({ value_type: "num", enforce_validation: true });
  const [processBindings, setProcessBindings] = useState({});
  const [bindingBusy, setBindingBusy] = useState("");
  const [safetyState, setSafetyState] = useState(null);
  const [safetyForm, setSafetyForm] = useState({});
  const [safetyBusy, setSafetyBusy] = useState(false);
  const [seasonProfiles, setSeasonProfiles] = useState(null);
  const [seasonForms, setSeasonForms] = useState({});
  const [seasonBusy, setSeasonBusy] = useState("");
  const devices = Array.isArray(snapshot?.devices) ? snapshot.devices : [];
  const entities = Array.isArray(snapshot?.entities) ? snapshot.entities : [];
  const metrics = Array.isArray(snapshot?.metrics) ? snapshot.metrics : [];
  const entityMetrics = Array.isArray(snapshot?.entity_metrics) ? snapshot.entity_metrics : [];
  const mqttFloodAlerts = Array.isArray(snapshot?.mqtt_flood_alerts) ? snapshot.mqtt_flood_alerts : [];
  const activeMqttFloodAlerts = mqttFloodAlerts.filter((item) => item.active);
  const mqttFloodConfig = snapshot?.mqtt_flood_config || {};
  const deviceEntities = useMemo(() => {
    const byDevice = new Map();
    entities.forEach((entity) => {
      if (!byDevice.has(entity.device_id)) byDevice.set(entity.device_id, entity);
    });
    return byDevice;
  }, [entities]);
  const selectedPreset = deviceTypePresets[deviceForm.preset] || deviceTypePresets.zigbee_plug;
  const selectedDevice = devices.find((device) => String(device.id) === String(deviceForm.device_id));
  const selectedEntity = selectedDevice ? deviceEntities.get(selectedDevice.id) : null;
  const selectedMetricRules = presetMetricRules(deviceForm.preset);
  const bindingRows = Object.values(processBindings).sort((a, b) => String(a.label || "").localeCompare(String(b.label || "")));
  const openingSensorRooms = useMemo(
    () => buildOpeningSensorRooms({ entities, entityMetrics }),
    [entities, entityMetrics],
  );
  const openingSensorCount = openingSensorRooms.reduce((sum, group) => sum + group.sensors.length, 0);
  const isOpeningPreset = deviceForm.preset === "window_contact" || rulesIncludeMetric(selectedMetricRules, ["contact"]);
  const isTemperaturePreset = rulesIncludeMetric(selectedMetricRules, ["temperature", "humidity"]);

  async function loadProcessBindings() {
    try {
      const data = await api("/api/process-bindings");
      setProcessBindings(data.bindings || {});
    } catch (err) {
      setToast(err.message);
    }
  }

  async function loadCombustionSafety() {
    try {
      const data = await api("/api/combustion-safety/state");
      setSafetyState(data);
      setSafetyForm(data.config || {});
    } catch (err) {
      setToast(err.message);
    }
  }

  async function loadSeasonProfiles() {
    try {
      const data = await api("/api/admin/season-profiles");
      setSeasonProfiles(data);
      const forms = {};
      Object.entries(data.domains || {}).forEach(([domain, item]) => {
        Object.entries(item.profiles || {}).forEach(([profile, row]) => {
          forms[`${domain}.${profile}`] = { ...(row.settings || {}) };
        });
      });
      setSeasonForms(forms);
    } catch (err) {
      setToast(err.message);
    }
  }

  useEffect(() => {
    loadProcessBindings();
    loadCombustionSafety();
    loadSeasonProfiles();
  }, []);

  async function saveSeasonProfile(domain, profile) {
    const key = `${domain}.${profile}`;
    setSeasonBusy(`save.${key}`);
    try {
      await api(`/api/admin/season-profiles/${domain}/${profile}`, {
        method: "PUT",
        body: JSON.stringify({ settings: seasonForms[key] || {} }),
      });
      await loadSeasonProfiles();
      setToast(`${domain} ${profile} profil mentve`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setSeasonBusy("");
    }
  }

  async function activateSeasonProfile(domain, profile) {
    setSeasonBusy(`activate.${domain}`);
    try {
      await api(`/api/admin/season-profiles/${domain}/activate`, {
        method: "POST",
        body: JSON.stringify({ profile }),
      });
      await loadSeasonProfiles();
      setToast(`${domain}: ${profile} profil aktiválva`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setSeasonBusy("");
    }
  }

  async function saveCombustionSafety(event) {
    event.preventDefault();
    setSafetyBusy(true);
    try {
      const data = await api("/api/combustion-safety/config", {
        method: "PUT",
        body: JSON.stringify({ ...safetyForm, updated_by: "react-admin" }),
      });
      setSafetyState(data.state);
      setSafetyForm(data.config || {});
      setToast("Elszívó-biztonsági paraméterek mentve");
    } catch (err) {
      setToast(err.message);
    } finally {
      setSafetyBusy(false);
    }
  }

  async function previewSafetyLight(pattern) {
    setSafetyBusy(true);
    try {
      await api("/api/combustion-safety/preview-light", { method: "POST", body: JSON.stringify({ pattern }) });
      setToast(`Villogási ritmuspróba elindítva: ${pattern}`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setSafetyBusy(false);
    }
  }

  async function acknowledgeSafety() {
    setSafetyBusy(true);
    try {
      const data = await api("/api/combustion-safety/acknowledge", { method: "POST", body: "{}" });
      setSafetyState(data);
      setToast("Biztonsági riasztás nyugtázva");
    } catch (err) {
      setToast(err.message);
    } finally {
      setSafetyBusy(false);
    }
  }

  function updateDevice(key, value) {
    setDeviceForm((current) => ({ ...current, [key]: value }));
  }

  function selectDevice(value) {
    if (!value) {
      setDeviceForm((current) => ({
        ...current,
        device_id: "",
        ext_id: "",
        name: "",
        location: "",
        entity_name: "",
        topic_base: "",
      }));
      return;
    }
    const device = devices.find((item) => String(item.id) === String(value));
    const entity = device ? deviceEntities.get(device.id) : null;
    const isOpeningEntity = entity
      ? entityMetrics.some((rule) => rule.entity_id === entity.id && rule.metric_key === "contact" && rule.is_enabled !== false)
      : false;
    const isTemperatureEntity = entity
      ? rulesIncludeMetric(entityMetrics.filter((rule) => rule.entity_id === entity.id), ["temperature", "humidity"])
      : false;
    const isPressureEntity = entity
      ? rulesIncludeMetric(entityMetrics.filter((rule) => rule.entity_id === entity.id), ["pressure_hpa"])
      : false;
    setDeviceForm((current) => ({
      ...current,
      device_id: value,
      preset: isOpeningEntity ? "window_contact" : isPressureEntity ? "temp_humidity_pressure_sensor" : isTemperatureEntity ? "temp_humidity_sensor" : current.preset,
      platform: device?.platform || current.platform || selectedPreset.platform,
      ext_id: device?.ext_id || "",
      name: device?.name || "",
      location: device?.location || "",
      model: device?.model || "",
      manufacturer: device?.manufacturer || "",
      entity_name: entity?.name || device?.name || "",
      topic_base: entity?.topic_base || "",
      opening_type: entity?.opening_type || current.opening_type || "window",
      room_position: entity?.room_position ?? "",
      opening_label: entity?.opening_label || "",
      has_mosquito_net: Boolean(entity?.has_mosquito_net),
      rain_alert_enabled: Boolean(entity?.rain_alert_enabled),
      climate_relevant: Boolean(entity?.climate_relevant),
      extractor_air_role: entity?.extractor_air_role || "none",
      is_outdoor: Boolean(entity?.is_outdoor),
    }));
  }

  function editOpeningSensor(sensor) {
    selectDevice(sensor.device_id);
    window.requestAnimationFrame(() => {
      document.getElementById("register-device-panel")?.scrollIntoView({ behavior: "smooth", block: "start" });
    });
    setToast(`Editing ${displayEntityName(sensor.opening_label || sensor.entity_name)}`);
  }

  function selectPreset(value) {
    const preset = deviceTypePresets[value] || deviceTypePresets.zigbee_plug;
    setDeviceForm((current) => ({
      ...current,
      preset: value,
      platform: preset.platform,
      model: current.model || preset.model,
      manufacturer: current.manufacturer || preset.manufacturer,
      opening_type: preset.openingType || current.opening_type,
      room_position: preset.openingType ? (current.room_position ?? "") : current.room_position,
      opening_label: preset.openingType ? (current.opening_label || "") : current.opening_label,
      has_mosquito_net: preset.openingType ? Boolean(current.has_mosquito_net) : current.has_mosquito_net,
      rain_alert_enabled: preset.openingType ? Boolean(current.rain_alert_enabled) : current.rain_alert_enabled,
      climate_relevant: preset.openingType ? Boolean(current.climate_relevant) : current.climate_relevant,
      extractor_air_role: preset.openingType ? (current.extractor_air_role || "none") : current.extractor_air_role,
      is_outdoor: rulesIncludeMetric(presetMetricRules(value), ["temperature", "humidity"]) ? Boolean(current.is_outdoor) : current.is_outdoor,
    }));
  }

  function fillTopicFromAddress() {
    setDeviceForm((current) => {
      const extId = String(current.ext_id || "").trim();
      const entityName = String(current.entity_name || current.name || "").trim();
      if (current.platform === "zigbee" && extId) {
        return { ...current, topic_base: `zigbee/${extId}` };
      }
      if (current.platform === "tuya" && entityName) {
        return { ...current, topic_base: `homecontrol/tele/tuya/${entityName}` };
      }
      return current;
    });
  }

  function updateMetric(key, value) {
    setMetricForm((current) => ({ ...current, [key]: value }));
  }

  function selectMetricDefinition(value) {
    if (!value) {
      setMetricForm({ value_type: "num", enforce_validation: true });
      return;
    }
    const metric = metrics.find((item) => item.key === value);
    setMetricForm({
      key: metric?.key || value,
      value_type: metric?.value_type || "num",
      unit: metric?.unit || "",
      min_num: metric?.min_num ?? "",
      max_num: metric?.max_num ?? "",
      description: metric?.description || "",
      enforce_validation: metric?.enforce_validation ?? true,
    });
  }

  async function saveDevice(event) {
    event.preventDefault();
    const metricRules = selectedMetricRules;
    const endpoint = deviceForm.device_id ? `/api/admin/devices/${deviceForm.device_id}` : "/api/admin/devices";
    try {
      const payload = {
        ...deviceForm,
        metric_rules: metricRules,
        room_position: deviceForm.room_position === "" || deviceForm.room_position === undefined ? null : Number(deviceForm.room_position),
      };
      await api(endpoint, {
        method: deviceForm.device_id ? "PUT" : "POST",
        body: JSON.stringify(payload),
      });
      setDeviceForm({ platform: selectedPreset.platform, preset: deviceForm.preset, opening_type: selectedPreset.openingType || "window", device_id: "", rain_alert_enabled: false, climate_relevant: false, extractor_air_role: "none", is_outdoor: false });
      setToast(deviceForm.device_id ? "Device updated" : "Device registered");
      await reload();
    } catch (err) {
      setToast(err.message);
    }
  }

  async function saveMetric(event) {
    event.preventDefault();
    const payload = {
      ...metricForm,
      min_num: metricForm.min_num === "" || metricForm.min_num === undefined ? null : Number(metricForm.min_num),
      max_num: metricForm.max_num === "" || metricForm.max_num === undefined ? null : Number(metricForm.max_num),
    };
    try {
      await api("/api/admin/metrics", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setMetricForm({ value_type: "num", enforce_validation: true });
      setToast("Metric saved");
      await reload();
    } catch (err) {
      setToast(err.message);
    }
  }

  async function saveProcessBinding(processKey, entityId) {
    if (!processKey || !entityId) return;
    setBindingBusy(processKey);
    try {
      const data = await api(`/api/process-bindings/${processKey}`, {
        method: "PUT",
        body: JSON.stringify({ entity_id: entityId }),
      });
      setProcessBindings((current) => ({ ...current, [processKey]: data.binding }));
      setToast("Function binding saved");
    } catch (err) {
      setToast(err.message);
      await loadProcessBindings();
    } finally {
      setBindingBusy("");
    }
  }

  return (
    <>
      <section className={`panel ${activeMqttFloodAlerts.length ? "mqtt-flood-panel active" : "mqtt-flood-panel"}`}>
        <div className="panel-head">
          <h2><AlertTriangle size={18} /> Zigbee MQTT flood védelem</h2>
          <span>{activeMqttFloodAlerts.length ? `${activeMqttFloodAlerts.length} aktív riasztás` : "nincs aktív riasztás"}</span>
        </div>
        <div className="replace-note">
          Figyelmeztetés {mqttFloodConfig.warning_per_minute ?? 60} üzenet/perc, kritikus riasztás {mqttFloodConfig.critical_per_minute ?? 180} üzenet/perc felett, {Number(mqttFloodConfig.sustain_seconds ?? 120) / 60} perc tartós terhelés után. A feloldás {Number(mqttFloodConfig.recovery_seconds ?? 120) / 60} perc nyugodt idő után automatikus.
        </div>
        <div className="table-wrap">
          <table>
            <thead><tr><th>Állapot</th><th>Eszköz</th><th>Topic</th><th>Üzenet/perc</th><th>Detektálva</th><th>Feloldva</th></tr></thead>
            <tbody>
              {mqttFloodAlerts.length ? mqttFloodAlerts.map((item) => (
                <tr key={`${item.topic_base}-${item.updated_at}`}>
                  <td><strong>{item.active ? item.severity.toUpperCase() : "FELOLDVA"}</strong></td>
                  <td>{item.entity_name || item.device_name || "Ismeretlen Zigbee eszköz"}<small>{item.location || ""}</small></td>
                  <td><code>{item.topic_base}</code></td>
                  <td>{Number(item.messages_per_minute || 0).toFixed(0)}</td>
                  <td>{item.detected_at ? new Date(item.detected_at).toLocaleString("hu-HU") : "-"}</td>
                  <td>{item.resolved_at ? new Date(item.resolved_at).toLocaleString("hu-HU") : "-"}</td>
                </tr>
              )) : <tr><td colSpan="6">Még nem történt Zigbee MQTT flood esemény.</td></tr>}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel admin-overview-panel">
        <div className="panel-head">
          <h2>Device Maintenance</h2>
          <span>{devices.length} device | {entities.length} entity | {metrics.length} metric</span>
        </div>
      </section>

      <section className="panel appearance-panel">
        <div className="panel-head">
          <h2>Appearance</h2>
          <span>Home dashboard skin</span>
        </div>
        <div className="skin-grid">
          {skinOptions.map((option) => (
            <button
              className={skin === option.value ? `skin-card ${option.value} active` : `skin-card ${option.value}`}
              type="button"
              onClick={() => {
                setSkin(option.value);
                setToast(`Skin selected: ${option.label}`);
              }}
              key={option.value}
            >
              <span className="skin-preview" aria-hidden="true"><i /><i /><i /></span>
              <span>
                <b>{option.label}</b>
                <small>{option.description}</small>
              </span>
            </button>
          ))}
        </div>
      </section>

      <section className="panel season-profile-panel">
        <div className="panel-head">
          <h2>Season Profiles</h2>
          <span>Profiles are activated independently for each area.</span>
        </div>
        <div className="form-grid">
          {Object.entries(seasonProfiles?.domains || {}).map(([domain, item]) => (
            <fieldset className="safety-settings-group" key={domain}>
              <legend>{domain === "irrigation" ? "Irrigation" : "Climate"}</legend>
              <label>Active profile
                <select
                  value={item.active_profile}
                  disabled={seasonBusy === `activate.${domain}`}
                  onChange={(event) => activateSeasonProfile(domain, event.target.value)}
                >
                  <option value="summer">Summer</option>
                  <option value="winter">Winter</option>
                </select>
              </label>
              {domain === "climate" ? (
                <div className="replace-note">
                  Summer and Winter climate profiles differ only in their scheduler configuration.
                </div>
              ) : (
                <div className="replace-note">
                  <strong>Irrigation control policy</strong>
                  <div className="table-wrap">
                    <table className="season-policy-table">
                      <thead>
                        <tr><th>Function</th><th>Summer</th><th>Winter</th></tr>
                      </thead>
                      <tbody>
                        {[
                          ["manual_watering", "Manual watering", "Starting a timed watering session from the Irrigation page."],
                          ["scheduled_watering", "Scheduled watering", "Watering starts triggered by the active irrigation schedule, including V2 execution."],
                          ["solar_pump_automation", "Solar pump automation", "Automatic pump batches started from solar and battery conditions."],
                          ["maintenance_controls", "Maintenance controls", "Valve homing, Auto/Manual mode changes, and manual pump start."],
                        ].map(([capability, label, description]) => (
                          <tr key={capability}>
                            <td><strong>{label}</strong><small>{description}</small></td>
                            {["summer", "winter"].map((profile) => {
                              const key = `${domain}.${profile}`;
                              return (
                                <td key={profile}>
                                  <input
                                    type="checkbox"
                                    aria-label={`${label} ${profile}`}
                                    checked={seasonForms[key]?.[capability] !== false}
                                    onChange={(event) => setSeasonForms((current) => ({
                                      ...current,
                                      [key]: { ...(current[key] || {}), [capability]: event.target.checked },
                                    }))}
                                  />
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                        <tr><td><strong>Measurements and logging</strong><small>Sensor collection, statistics, history, and event logging.</small></td><td>Always on</td><td>Always on</td></tr>
                        <tr><td><strong>Safety stop operations</strong><small>Safe stop, valve close/status, pump off, and diagnostics.</small></td><td>Always on</td><td>Always on</td></tr>
                      </tbody>
                    </table>
                  </div>
                  <div className="climate-schedule-actions">
                    {["summer", "winter"].map((profile) => (
                      <button type="button" key={profile} disabled={seasonBusy === `save.${domain}.${profile}`} onClick={() => saveSeasonProfile(domain, profile)}>
                        <Save size={15} /> Save {profile === "summer" ? "Summer" : "Winter"}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </fieldset>
          ))}
        </div>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Function Bindings</h2>
          <span>{bindingRows.length} process-device links</span>
        </div>
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>Function</th><th>Current Device</th><th>Device</th><th>Metrics</th></tr>
            </thead>
            <tbody>
              {bindingRows.length ? bindingRows.map((binding) => {
                const candidates = binding.candidates || [];
                const selectedId = binding.selected_entity_id || binding.selected_entity?.entity_id || "";
                return (
                  <tr key={binding.process_key}>
                    <td>
                      <strong>{binding.label}</strong>
                      <small>{binding.purpose}</small>
                    </td>
                    <td>
                      {entitySelectLabel(binding.selected_entity)}
                      {binding.uses_fallback && <small>fallback (not configured)</small>}
                      {binding.configuration_state === "invalid" && <small role="alert">Device unavailable or incompatible. Select a valid device.</small>}
                      {binding.configuration_state === "not_configured" && !binding.uses_fallback && <small>No usable device configured</small>}
                    </td>
                    <td>
                      <select
                        value={selectedId}
                        disabled={bindingBusy === binding.process_key}
                        onChange={(event) => saveProcessBinding(binding.process_key, event.target.value)}
                      >
                        {!selectedId && <option value="" disabled>{candidates.length ? "Select a device" : "No candidates"}</option>}
                        {candidates.map((candidate) => (
                          <option value={candidate.entity_id} key={candidate.entity_id}>{entitySelectLabel(candidate)}</option>
                        ))}
                      </select>
                    </td>
                    <td>{(binding.candidate_metric_keys || []).slice(0, 4).join(", ")}</td>
                  </tr>
                );
              }) : (
                <tr><td colSpan="4">No function bindings</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel combustion-safety-panel">
        <div className="panel-head">
          <h2>Elszívó / cserépkályha biztonság</h2>
          <span>
            állapot: {safetyState?.level || "-"} | számított: {safetyState?.would_level || "-"} | teljesítmény: {safetyState?.power_w ?? "-"} W
          </span>
        </div>
        <div className="replace-note">
          {safetyState?.reason || "Állapot betöltése…"} | primary ablak: {safetyState?.primary_open ? "nyitva" : "zárva/ismeretlen"} | secondary: {safetyState?.secondary_open ? "nyitva" : "nincs nyitva"} | CO: {safetyState?.co?.value_ppm ?? "-"} ppm / rádió {safetyState?.co?.radio_online === true ? "online" : safetyState?.co?.radio_online === false ? "offline" : "ismeretlen"} | füstérzékelő: {safetyState?.smoke?.configured ? "bekötve" : "még nincs bekötve"}
        </div>
        <div className="replace-note">
          Értékelés kora: {safetyState?.evaluation_age_seconds == null ? "még nincs értékelés" : `${Math.round(safetyState.evaluation_age_seconds)} s`}
          {safetyState?.stale ? " | Az értékelés elavult; nyugtázás nem engedélyezett." : ""}
          {safetyState?.persistence?.restored === false ? " | A retesz helyreállítása nem igazolt." : ""}
        </div>
        <div className="replace-note">
          A CO- és füstérzékelő csak változáskor küld jelzést. Az utolsó ismert jelzés a rádiós jelenléttel együtt érvényes; a régi jelzési idő önmagában nem hiba.
          {" | CO rádiós észlelés: "}{safetyState?.co?.radio_last_seen_ts ? new Date(safetyState.co.radio_last_seen_ts).toLocaleString("hu-HU") : "ismeretlen"}
          {" | Füst rádió: "}{safetyState?.smoke?.radio_online === true ? "online" : safetyState?.smoke?.radio_online === false ? "offline" : "ismeretlen"}
          {"; észlelés: "}{safetyState?.smoke?.radio_last_seen_ts ? new Date(safetyState.smoke.radio_last_seen_ts).toLocaleString("hu-HU") : "ismeretlen"}
          {safetyState?.input_health?.co === false || safetyState?.input_health?.smoke === false ? " | Nyugtázáshoz mindkét bekötött érzékelő ismert, hibamentes állapota és rádiós jelenléte szükséges." : ""}
        </div>
        <form className="form-grid" onSubmit={saveCombustionSafety}>
          <fieldset className="safety-settings-group wide">
            <legend>Működés és automatikus beavatkozás</legend>
            <div className="form-grid">
              <label className="check opening-check"><input type="checkbox" checked={Boolean(safetyForm.enabled)} onChange={(event) => setSafetyForm((current) => ({ ...current, enabled: event.target.checked }))} />Védelem engedélyezve</label>
              <label className="check opening-check"><input type="checkbox" checked={Boolean(safetyForm.auto_shutdown)} onChange={(event) => setSafetyForm((current) => ({ ...current, auto_shutdown: event.target.checked }))} />Elszívó automatikus lekapcsolása</label>
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide">
            <legend>Elszívó működésének felismerése</legend>
            <div className="form-grid">
              {[["fan_on_w", "Elszívó BE küszöb (W)"], ["fan_off_w", "Elszívó KI küszöb (W)"], ["fan_on_seconds", "Bekapcsolási késleltetés (s)"], ["fan_off_seconds", "Kikapcsolási késleltetés (s)"]].map(([key, label]) => (
                <label key={key}>{label}<input type="number" min="0" step={key.includes("_w") ? "0.1" : "1"} value={safetyForm[key] ?? ""} onChange={(event) => setSafetyForm((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>
              ))}
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide">
            <legend>CO-védelem</legend>
            <div className="form-grid">
              {[["co_warning_ppm", "CO figyelmeztetés (ppm)"], ["co_shutdown_ppm", "CO lekapcsolás (ppm)"], ["co_rise_ppm", "CO emelkedés (ppm)"]].map(([key, label]) => (
                <label key={key}>{label}<input type="number" min="0" step="0.1" value={safetyForm[key] ?? ""} onChange={(event) => setSafetyForm((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>
              ))}
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide">
            <legend>Villogási időzítések</legend>
            <div className="form-grid">
              {[["green_interval_seconds", "Zöld villanás időköz (s)"], ["secondary_interval_seconds", "Secondary narancs időköz (s)"], ["closed_interval_seconds", "Zárt lakás narancs időköz (s)"], ["pulse_seconds", "Villanás hossza (s)"]].map(([key, label]) => (
                <label key={key}>{label}<input type="number" min="0" step={key === "pulse_seconds" ? "0.1" : "1"} value={safetyForm[key] ?? ""} onChange={(event) => setSafetyForm((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>
              ))}
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide">
            <legend>Jelzőszínek</legend>
            <div className="form-grid safety-color-grid">
              {[["green_color", "Zöld jelzőszín"], ["orange_color", "Narancs jelzőszín"], ["red_color", "Piros jelzőszín"]].map(([key, label]) => (
                <label className="safety-color-field" key={key}>{label}
                  <span><input type="color" value={safetyForm[key] || "#000000"} onChange={(event) => setSafetyForm((current) => ({ ...current, [key]: event.target.value }))} /><code>{safetyForm[key] || "-"}</code></span>
                </label>
              ))}
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide">
            <legend>Színek fényereje</legend>
            <div className="form-grid safety-brightness-grid">
              {[["green_brightness", "Zöld fényerő"], ["orange_brightness", "Narancs fényerő"], ["red_brightness", "Piros fényerő"]].map(([key, label]) => (
                <label key={key}>{label} (1–254)<input type="number" min="1" max="254" step="1" value={safetyForm[key] ?? ""} onChange={(event) => setSafetyForm((current) => ({ ...current, [key]: Number(event.target.value) }))} /></label>
              ))}
            </div>
          </fieldset>

          <fieldset className="safety-settings-group wide safety-actions-group">
            <legend>Mentés és állapot</legend>
            <div className="actions"><IconButton icon={Save} type="submit" disabled={safetyBusy}>Paraméterek mentése</IconButton><button type="button" disabled={safetyBusy} onClick={() => loadCombustionSafety()}>Állapot frissítése</button><button type="button" disabled={safetyBusy || safetyState?.stale || safetyState?.danger || !safetyState?.persistence?.restored || !safetyState?.input_health?.co || !safetyState?.input_health?.smoke} onClick={acknowledgeSafety}>Riasztás nyugtázása</button></div>
          </fieldset>

          <fieldset className="safety-settings-group wide safety-actions-group">
            <legend>Lámpatesztek</legend>
            <div className="replace-note">A ritmuspróba három villanást mutat. A zöld egyperces szünete itt 5 másodpercre gyorsul, a két narancs a valódi időzítést használja, a piros 5 másodpercig folyamatos.</div>
            <div className="actions"><button type="button" disabled={safetyBusy} onClick={() => previewSafetyLight("green")}>Zöld ritmuspróba</button><button type="button" disabled={safetyBusy} onClick={() => previewSafetyLight("secondary")}>Narancs 20 s próba</button><button type="button" disabled={safetyBusy} onClick={() => previewSafetyLight("closed")}>Gyors narancs próba</button><button type="button" disabled={safetyBusy} onClick={() => previewSafetyLight("red")}>Folyamatos piros próba</button><button type="button" disabled={safetyBusy} onClick={() => previewSafetyLight("off")}>Lámpa kikapcsolása</button></div>
          </fieldset>
        </form>
      </section>

      <section className="grid two">
        <article className="panel" id="register-device-panel">
          <div className="panel-head">
            <h2>Register / Replace Device</h2>
            <span>{deviceForm.device_id ? `Editing #${deviceForm.device_id}` : "New device with metric preset"}</span>
          </div>
          <form className="form-grid" onSubmit={saveDevice}>
            <label className="wide">Existing device
              <select value={deviceForm.device_id || ""} onChange={(event) => selectDevice(event.target.value)}>
                <option value="">Register as new device</option>
                {devices.map((device) => {
                  const entity = deviceEntities.get(device.id);
                  return (
                    <option value={device.id} key={device.id}>
                      {displayEntityName(entity?.name || device.name)} | {device.platform} | {device.ext_id || "no address"}
                    </option>
                  );
                })}
              </select>
            </label>
            <label>Device type
              <select value={deviceForm.preset || "zigbee_plug"} onChange={(event) => selectPreset(event.target.value)}>
                {Object.entries(deviceTypePresets).map(([key, preset]) => <option value={key} key={key}>{preset.label}</option>)}
              </select>
            </label>
            {isOpeningPreset && (
              <label>Opening type
                <select value={deviceForm.opening_type || "window"} onChange={(event) => updateDevice("opening_type", event.target.value)}>
                  <option value="window">Window</option>
                  <option value="door">Door</option>
                </select>
              </label>
            )}
            {isOpeningPreset && (
              <>
                <label>Room position
                  <input
                    type="number"
                    step="1"
                    value={deviceForm.room_position ?? ""}
                    onChange={(event) => updateDevice("room_position", event.target.value)}
                    placeholder="10"
                  />
                </label>
                <label>Opening label
                  <input
                    value={deviceForm.opening_label || ""}
                    onChange={(event) => updateDevice("opening_label", event.target.value)}
                    placeholder="ajtótól 1 / szúnyoghálós"
                  />
                </label>
                <label className="check opening-check">
                  <input
                    type="checkbox"
                    checked={Boolean(deviceForm.has_mosquito_net)}
                    onChange={(event) => updateDevice("has_mosquito_net", event.target.checked)}
                  />
                  Mosquito net
                </label>
                <label className="check opening-check">
                  <input
                    type="checkbox"
                    checked={Boolean(deviceForm.rain_alert_enabled)}
                    onChange={(event) => updateDevice("rain_alert_enabled", event.target.checked)}
                  />
                  Rain alert
                </label>
                <label className="check opening-check">
                  <input
                    type="checkbox"
                    checked={Boolean(deviceForm.climate_relevant)}
                    onChange={(event) => updateDevice("climate_relevant", event.target.checked)}
                  />
                  Climate relevant
                </label>
                <label>Extractor air role
                  <select value={deviceForm.extractor_air_role || "none"} onChange={(event) => updateDevice("extractor_air_role", event.target.value)}>
                    <option value="none">Not relevant</option>
                    <option value="secondary">Secondary air path</option>
                    <option value="primary">Primary / kitchen</option>
                  </select>
                </label>
              </>
            )}
            {isTemperaturePreset && (
              <label className="check opening-check">
                <input
                  type="checkbox"
                  checked={Boolean(deviceForm.is_outdoor)}
                  onChange={(event) => updateDevice("is_outdoor", event.target.checked)}
                />
                Outdoor thermometer
              </label>
            )}
            <label>Platform
              <select value={deviceForm.platform || "zigbee"} onChange={(event) => updateDevice("platform", event.target.value)}>
                <option value="zigbee">zigbee</option>
                <option value="wifi">wifi</option>
                <option value="tuya">tuya</option>
                <option value="system">system</option>
                <option value="other">other</option>
              </select>
            </label>
            <label>Device address<input value={deviceForm.ext_id || ""} onChange={(event) => updateDevice("ext_id", event.target.value)} placeholder="0x... or Tuya id" /></label>
            <label>Device name<input required value={deviceForm.name || ""} onChange={(event) => updateDevice("name", event.target.value)} placeholder="Kitchen plug" /></label>
            <label>Location<input value={deviceForm.location || ""} onChange={(event) => updateDevice("location", event.target.value)} placeholder="Garden" /></label>
            <label>Entity name<input value={deviceForm.entity_name || ""} onChange={(event) => updateDevice("entity_name", event.target.value)} placeholder="Kitchen plug" /></label>
            <label>Model<input value={deviceForm.model || ""} onChange={(event) => updateDevice("model", event.target.value)} placeholder={selectedPreset.model || "Model"} /></label>
            <label>Manufacturer<input value={deviceForm.manufacturer || ""} onChange={(event) => updateDevice("manufacturer", event.target.value)} placeholder={selectedPreset.manufacturer || "Manufacturer"} /></label>
            <label className="wide">Topic base
              <div className="input-action-row">
                <input value={deviceForm.topic_base || ""} onChange={(event) => updateDevice("topic_base", event.target.value)} placeholder={deviceForm.platform === "tuya" ? "homecontrol/tele/tuya/Name" : "zigbee/0x..."} />
                <button type="button" onClick={fillTopicFromAddress}><RefreshCw size={16} aria-hidden="true" /><span>Auto</span></button>
              </div>
            </label>
            <div className="wide metric-preset-preview">
              <strong>{selectedPreset.label} metrics</strong>
              <div>
                {selectedMetricRules.map((rule) => <span className="metric-chip" key={rule.metric_key}>{rule.metric_key}</span>)}
              </div>
            </div>
            {deviceForm.device_id && selectedDevice && (
              <div className="wide replace-note">
                Replacing keeps entity ID {selectedEntity?.id || "-"} and updates only the device address/topic fields used by HC.
              </div>
            )}
            <div className="wide actions"><IconButton icon={Save} type="submit">{deviceForm.device_id ? "Update Device" : "Register Device"}</IconButton></div>
          </form>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Metric Definition</h2>
            <span>Advanced metadata editor</span>
          </div>
          <form className="form-grid" onSubmit={saveMetric}>
            <label className="wide">Existing metric
              <select value={metricForm.key || ""} onChange={(event) => selectMetricDefinition(event.target.value)}>
                <option value="">Create new metric</option>
                {metrics.map((metric) => <option value={metric.key} key={metric.key}>{metric.key}</option>)}
              </select>
            </label>
            <label>Key<input required value={metricForm.key || ""} onChange={(event) => updateMetric("key", event.target.value)} placeholder="liquid_level_percent" /></label>
            <label>Type
              <select value={metricForm.value_type || "num"} onChange={(event) => updateMetric("value_type", event.target.value)}>
                <option value="num">num</option>
                <option value="bool">bool</option>
                <option value="text">text</option>
                <option value="json">json</option>
              </select>
            </label>
            <label>Unit<input value={metricForm.unit || ""} onChange={(event) => updateMetric("unit", event.target.value)} placeholder="%" /></label>
            <label>Min<input type="number" step="any" value={metricForm.min_num || ""} onChange={(event) => updateMetric("min_num", event.target.value)} /></label>
            <label>Max<input type="number" step="any" value={metricForm.max_num || ""} onChange={(event) => updateMetric("max_num", event.target.value)} /></label>
            <label className="wide">Description<input value={metricForm.description || ""} onChange={(event) => updateMetric("description", event.target.value)} placeholder="Tank liquid level percent" /></label>
            <label className="check wide">
              <input type="checkbox" checked={Boolean(metricForm.enforce_validation)} onChange={(event) => updateMetric("enforce_validation", event.target.checked)} />
              Validation enabled
            </label>
            <div className="wide actions"><IconButton icon={Save} type="submit">Save Metric</IconButton></div>
          </form>
        </article>
      </section>

      <section className="panel opening-admin-panel">
        <div className="panel-head">
          <h2>Opening Sensors by Room</h2>
          <span>{openingSensorCount} sensor | registration parameters</span>
        </div>
        <div className="opening-room-list">
          {openingSensorRooms.length ? openingSensorRooms.map((group) => (
            <section className="opening-room-section" key={group.key}>
              <h3>{group.room}</h3>
              <div className="table-wrap opening-room-table">
                <table>
                  <thead>
                    <tr>
                      <th>Sensor</th>
                      <th>Address</th>
                      <th>Topic</th>
                      <th>Device</th>
                      <th>Opening</th>
                      <th>Flags</th>
                      <th>Action</th>
                    </tr>
                  </thead>
                  <tbody>
                    {group.sensors.map((sensor) => (
                      <tr key={sensor.entity_id}>
                        <td>
                          <strong>{displayEntityName(sensor.opening_label || sensor.entity_name)}</strong>
                          <small>entity #{sensor.entity_id}</small>
                        </td>
                        <td><code>{sensor.ext_id || "-"}</code></td>
                        <td><code>{sensor.topic_base || "-"}</code></td>
                        <td>
                          <strong>{displayEntityName(sensor.device_name)}</strong>
                          <small>{sensor.platform} | {sensor.model || "model -"} | {sensor.manufacturer || "maker -"}</small>
                        </td>
                        <td>{sensor.opening_type || "window"}{sensor.room_position == null ? "" : ` | pos ${sensor.room_position}`}</td>
                        <td>{[sensor.has_mosquito_net ? "net" : "", sensor.rain_alert_enabled ? "rain alert" : "", sensor.climate_relevant ? "climate" : "", sensor.extractor_air_role && sensor.extractor_air_role !== "none" ? `extractor ${sensor.extractor_air_role}` : ""].filter(Boolean).join(" | ") || "-"}</td>
                        <td>
                          <IconButton icon={Pencil} className="secondary opening-edit-button" type="button" onClick={() => editOpeningSensor(sensor)}>Edit</IconButton>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )) : (
            <div className="replace-note">No registered opening sensors yet. Use the Window contact preset above to register the new sensors.</div>
          )}
        </div>
      </section>

      <section className="panel admin-links-panel">
        <div className="panel-head">
          <h2>Service Links</h2>
          <span>HomeControl infrastructure shortcuts</span>
        </div>
        <Table
          rows={hcAdminLinks}
          columns={[
            { key: "name", label: "Service" },
            { key: "role", label: "Role" },
            {
              key: "address",
              label: "Address",
              render: (row) => {
                const address = row.address();
                const isLink = row.access === "Web" || /^https?:\/\//.test(address);
                return isLink ? (
                  <a className="admin-service-link" href={address} target="_blank" rel="noreferrer">
                    <span>{address}</span>
                    <ExternalLink size={14} aria-hidden="true" />
                  </a>
                ) : (
                  <code>{address}</code>
                );
              },
            },
            { key: "service", label: "Compose Service", render: (row) => <code>{row.service}</code> },
            { key: "access", label: "Access", render: (row) => <span className={`status-pill ${row.access === "Web" ? "ok" : "warn"}`}>{row.access}</span> },
            { key: "note", label: "Note" },
          ]}
        />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Entities</h2>
          <span>{entities.length} entity</span>
        </div>
        <Table
          rows={entities}
          columns={[
            { key: "id", label: "ID" },
            { key: "platform", label: "Platform" },
            { key: "device_name", label: "Device", render: (row) => displayEntityName(row.device_name) },
            { key: "name", label: "Entity", render: (row) => displayEntityName(row.name) },
            { key: "location", label: "Location" },
            {
              key: "opening",
              label: "Role",
              render: (row) => {
                if (row.opening_type) {
                  return `${row.opening_type}${row.room_position == null ? "" : ` #${row.room_position}`}${row.opening_label ? ` | ${row.opening_label}` : ""}${row.has_mosquito_net ? " | net" : ""}${row.rain_alert_enabled ? " | rain alert" : ""}${row.climate_relevant ? " | climate" : ""}${row.extractor_air_role && row.extractor_air_role !== "none" ? ` | extractor ${row.extractor_air_role}` : ""}`;
                }
                const rules = entityMetrics.filter((rule) => rule.entity_id === row.id);
                if (rulesIncludeMetric(rules, ["pressure_hpa"])) {
                  return row.is_outdoor ? "thermometer/barometer | outdoor" : "thermometer/barometer | indoor";
                }
                if (rulesIncludeMetric(rules, ["temperature", "humidity"])) {
                  return row.is_outdoor ? "thermometer | outdoor" : "thermometer | indoor";
                }
                return "-";
              },
            },
            { key: "topic_base", label: "Topic" },
            { key: "status", label: "Status", render: (row) => row.status || "-" },
          ]}
        />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Metrics</h2>
          <span>{metrics.length} metric</span>
        </div>
        <Table
          rows={metrics}
          columns={[
            { key: "key", label: "Key" },
            { key: "value_type", label: "Type" },
            { key: "unit", label: "Unit" },
            { key: "min_num", label: "Min" },
            { key: "max_num", label: "Max" },
            { key: "description", label: "Description" },
          ]}
        />
      </section>
    </>
  );
}
