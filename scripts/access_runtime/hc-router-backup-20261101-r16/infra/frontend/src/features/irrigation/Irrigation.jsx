import React, { useEffect, useMemo, useState } from "react";
import { Activity, BatteryCharging, CalendarDays, Clock, Droplets, Gauge, Play, Plus, RefreshCw, Save, Settings, Square, Trash2, Wrench } from "lucide-react";
import { api } from "../../apiClient";
import { ageText, dateText, numberText, shortValue, textValue, unitValue, valueText } from "../../formatters";
import { Card, IconButton, Table } from "../../uiPrimitives";
import { dayLabels } from "../scheduler/schedulerOptions";
import PilotDashboard, { PilotSummaryCards } from "./PilotDashboard";

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

const commandGroups = [
  {
    title: "Valve",
    commands: [
      ["valve_open", "Open", Play],
      ["valve_close", "Close", Square],
      ["valve_stop", "Stop", Square],
      ["valve_home", "Home", Wrench],
      ["valve_status", "Status", Activity],
      ["fault_reset", "Fault reset", RefreshCw],
      ["diag_now", "Diag now", Activity],
      ["nano_status_now", "Nano status", Activity],
    ],
  },
  {
    title: "Tank Fill / Mode",
    commands: [
      ["mode_manual", "Mode manual", Settings],
      ["mode_auto", "Mode auto", Settings],
      ["pump_on", "Pump ON", Play],
      ["pump_off", "Pump OFF", Square],
      ["ping", "Ping", Activity],
      ["valve_cal_zero", "Current zero", Gauge],
    ],
  },
  {
    title: "Nano Configuration",
    commands: [
      ["nano_get", "GET all", RefreshCw],
      ["nano_save", "SAVE EEPROM", Save],
      ["nano_load", "LOAD EEPROM", RefreshCw],
      ["nano_defaults", "DEFAULTS", Wrench],
    ],
  },
];

function firstValue(source, keys) {
  if (!source) return undefined;
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null && source[key] !== "") return source[key];
  }
  return undefined;
}

function nanoSerialText(value) {
  if (value === true) return "ok";
  if (value === false) return "fault";
  return textValue(value);
}

function nanoFaultText(value) {
  const text = textValue(value).trim();
  if (text === "-") return "";
  const normalized = text.toUpperCase();
  return ["0", "OK", "NONE", "NO_ERROR", "CLEAR", "CLEARED"].includes(normalized) ? "" : text;
}

function minutesFromTime(value) {
  const match = String(value || "").match(/^(\d{1,2}):(\d{2})$/);
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function timeFromMinutes(value) {
  const minutes = ((Number(value) % 1440) + 1440) % 1440;
  const hours = Math.floor(minutes / 60);
  const mins = minutes % 60;
  return `${String(hours).padStart(2, "0")}:${String(mins).padStart(2, "0")}`;
}

function nextWindowDefaults(schedule) {
  const start = minutesFromTime(schedule?.start_time);
  const fallbackStart = start !== null && start < 12 * 60 ? 18 * 60 : 5 * 60;
  return {
    start_time: timeFromMinutes(fallbackStart),
    stop_time: timeFromMinutes(fallbackStart + 45),
  };
}

function SchedulerPanel({ schedules = [], schedulerGuard = {}, reload, setToast }) {
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState("");
  const schedulesByDay = useMemo(() => dayLabels.map((label, dayIndex) => ({
    label,
    dayIndex,
    rows: schedules
      .filter((row) => Number(row.day_of_week) === dayIndex)
      .sort((a, b) => String(a.start_time || "").localeCompare(String(b.start_time || "")) || Number(a.id || 0) - Number(b.id || 0)),
  })), [schedules]);

  useEffect(() => {
    setDrafts((current) => {
      const next = { ...current };
      for (const schedule of schedules) {
        if (!next[schedule.id]) {
          next[schedule.id] = {
            start_time: schedule.start_time || "06:00",
            stop_time: schedule.stop_time || "06:20",
            is_active: Boolean(schedule.is_active),
          };
        }
      }
      return next;
    });
  }, [schedules]);

  function updateDraft(id, key, value) {
    setDrafts((current) => ({
      ...current,
      [id]: {
        ...(current[id] || {}),
        [key]: value,
      },
    }));
  }

  async function saveSchedule(schedule) {
    const draft = drafts[schedule.id] || schedule;
    setBusy(String(schedule.id));
    try {
      await api(`/api/irrigation/schedules/${schedule.id}`, {
        method: "PUT",
        body: JSON.stringify({
          start_time: draft.start_time,
          stop_time: draft.stop_time,
          is_active: Boolean(draft.is_active),
        }),
      });
      setToast("Schedule saved");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function addSchedule(dayIndex, rows = []) {
    const source = rows[rows.length - 1] || { day_of_week: dayIndex };
    const defaults = nextWindowDefaults(source);
    const dayLabel = dayLabels[dayIndex] || source.label || "Schedule";
    setBusy(`add-${dayIndex}`);
    try {
      await api("/api/irrigation/schedules", {
        method: "POST",
        body: JSON.stringify({
          day_of_week: dayIndex,
          label: dayLabel,
          start_time: defaults.start_time,
          stop_time: defaults.stop_time,
          is_active: false,
        }),
      });
      setToast("Schedule window added");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function deleteSchedule(schedule) {
    setBusy(`delete-${schedule.id}`);
    try {
      await api(`/api/irrigation/schedules/${schedule.id}`, { method: "DELETE" });
      setToast("Schedule window deleted");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <article className="panel scheduler-panel">
      <div className="panel-head">
        <h2 className="panel-title"><CalendarDays size={17} aria-hidden="true" /> Scheduler</h2>
        <span>{schedulerGuard.blocked ? `Blocked: manual valve ${schedulerGuard.state || "OPEN"}` : `${schedules.length} windows | Weekly DB config`}</span>
      </div>
      {schedulerGuard.blocked && (
        <div className="scheduler-blocked">
          Manual valve is open, scheduler start is disabled.
        </div>
      )}
      <div className="schedule-list">
        {schedulesByDay.map((day) => (
          <div className={`schedule-day ${day.rows.some((row) => row.is_today) ? "today" : ""}`} key={day.dayIndex}>
            <div className="schedule-day-head">
              <div>
                <strong>{day.label}</strong>
                <span>{day.rows.length} windows</span>
              </div>
              <IconButton icon={Plus} disabled={busy === `add-${day.dayIndex}`} onClick={() => addSchedule(day.dayIndex, day.rows)}>
                {busy === `add-${day.dayIndex}` ? "Adding" : "Add window"}
              </IconButton>
            </div>
            <div className="schedule-day-rows">
              {day.rows.map((schedule, index) => {
                const draft = drafts[schedule.id] || schedule;
                const active = Boolean(draft.is_active);
                const unsaved =
                  active !== Boolean(schedule.is_active) ||
                  draft.start_time !== schedule.start_time ||
                  draft.stop_time !== schedule.stop_time;
                const rowClass = [
                  "schedule-row",
                  active ? "active" : "",
                  schedule.is_today ? "today" : "",
                  schedule.should_run_now ? "due-now" : "",
                  schedulerGuard.blocked && schedule.should_run_now ? "blocked" : "",
                  unsaved ? "unsaved" : "",
                ].filter(Boolean).join(" ");
                return (
                  <div className={rowClass} key={schedule.id}>
                    <label className="schedule-active">
                      <input
                        type="checkbox"
                        checked={active}
                        onChange={(event) => updateDraft(schedule.id, "is_active", event.target.checked)}
                      />
                      <span>Window #{schedule.window_index || index + 1}</span>
                    </label>
                    <label>
                      <span>Start</span>
                      <input
                        className="time24-input"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-2][0-9]:[0-5][0-9]"
                        placeholder="06:00"
                        maxLength="5"
                        value={draft.start_time || "06:00"}
                        onChange={(event) => updateDraft(schedule.id, "start_time", event.target.value)}
                      />
                    </label>
                    <label>
                      <span>Stop</span>
                      <input
                        className="time24-input"
                        type="text"
                        inputMode="numeric"
                        pattern="[0-2][0-9]:[0-5][0-9]"
                        placeholder="06:20"
                        maxLength="5"
                        value={draft.stop_time || "06:20"}
                        onChange={(event) => updateDraft(schedule.id, "stop_time", event.target.value)}
                      />
                    </label>
                    <div className="schedule-meta">
                      <Clock size={14} aria-hidden="true" />
                      <span>{schedule.duration_minutes || "-"} min</span>
                    </div>
                    <div className="schedule-status">
                      {schedulerGuard.blocked && schedule.should_run_now ? "BLOCKED" : schedule.should_run_now ? "RUN WINDOW" : (schedule.schedule_status || (schedule.is_today ? "today" : "disabled")).replaceAll("_", " ").toUpperCase()}
                      {unsaved ? " | UNSAVED" : ""}
                    </div>
                    <div className="schedule-actions">
                      <IconButton icon={Save} disabled={busy === String(schedule.id)} onClick={() => saveSchedule(schedule)}>
                        {busy === String(schedule.id) ? "Saving" : "Save"}
                      </IconButton>
                      {schedule.can_delete && (
                        <IconButton icon={Trash2} disabled={busy === `delete-${schedule.id}`} onClick={() => deleteSchedule(schedule)}>
                          {busy === `delete-${schedule.id}` ? "Deleting" : "Delete"}
                        </IconButton>
                      )}
                    </div>
                  </div>
                );
              })}
              {!day.rows.length && (
                <IconButton icon={Plus} disabled={busy === `add-${day.dayIndex}`} onClick={() => addSchedule(day.dayIndex, [])}>
                  {busy === `add-${day.dayIndex}` ? "Adding" : "Add first window"}
                </IconButton>
              )}
            </div>
          </div>
        ))}
      </div>
    </article>
  );
}

function irrigationSessionType(row = {}) {
  if (row.started_by === "physical_manual" || row.source === "physical_manual_valve") return "Manual tap";
  if (row.started_by === "scheduler") return "Auto schedule";
  if (row.started_by === "pilot") return "Pilot";
  if (String(row.started_by || "").includes("dashboard") || String(row.started_by || "").includes("admin")) return "App manual";
  return row.started_by || row.source || "-";
}

function SolarPumpSchedulerPanel({ solarPump = {}, onSaved, setToast }) {
  const [draft, setDraft] = useState({});
  const [busy, setBusy] = useState("");
  const decision = solarPump.decision || {};
  const live = decision.live || {};
  const runs = solarPump.runs || [];

  useEffect(() => {
    const config = decision.config;
    if (config) setDraft(config);
  }, [decision.config?.updated_at]);

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function saveConfig() {
    setBusy("save");
    try {
      await api("/api/irrigation/solar-pump/config", {
        method: "PUT",
        body: JSON.stringify(draft),
      });
      setToast?.("Solar pump config saved");
      await onSaved?.();
    } catch (err) {
      setToast?.(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="grid two">
      <article className="panel">
        <div className="panel-head">
          <h2>Solar Pump Scheduler</h2>
          <span>{decision.reason || "Waiting for decision"}</span>
        </div>
        <div className="decision-grid">
          <div><span>State</span><strong>{decision.state || "-"}</strong></div>
          <div><span>Runtime today</span><strong>{unitValue(decision.completed_minutes_today, "min", 1)}</strong></div>
          <div><span>Next batch</span><strong>{unitValue(decision.next_batch_minutes, "min", 0)}</strong></div>
        </div>
        <div className="pilot-result">
          <span>Battery: {unitValue(live.battery_voltage_v, "V", 2)} | charge {unitValue(live.charge_current_a, "A", 2)}</span>
          <span>PV: {unitValue(live.pv_voltage_v, "V", 1)} | {unitValue(live.pv_current_a, "A", 2)}</span>
          <span>Tank L/H: {live.low_signal === true ? "1" : live.low_signal === false ? "0" : "-"} / {live.high_signal === true ? "1" : live.high_signal === false ? "0" : "-"} | full stop {live.tank_full_stop ? "YES" : "NO"}</span>
          <span>Mode: {live.mode || "-"} | remote {live.remote_mode ? "YES" : "NO"} | telemetry age {unitValue(live.telemetry_age_sec, "s", 0)}</span>
          <span>Active run: {decision.active_run ? `#${decision.active_run.id} until ${dateText(decision.active_run.planned_stop_at)}` : "-"}</span>
        </div>
        <div className="table-spacer" />
        <div className="panel-subhead">
          <h3>Recent solar pump runs</h3>
          <span>opportunistic batches</span>
        </div>
        <Table
          rows={runs}
          columns={[
            { key: "started_at", label: "Started", render: (row) => dateText(row.started_at) },
            { key: "duration_minutes", label: "Min" },
            { key: "status", label: "Status" },
            { key: "battery_voltage_v", label: "Bat V", render: (row) => unitValue(row.battery_voltage_v, "V", 2) },
            { key: "charge_current_a", label: "Chg A", render: (row) => unitValue(row.charge_current_a, "A", 2) },
            { key: "pv_voltage_v", label: "PV V", render: (row) => unitValue(row.pv_voltage_v, "V", 1) },
            { key: "tank_full_stop", label: "L/H", render: (row) => `${row.low_signal === true ? "1" : row.low_signal === false ? "0" : "-"} / ${row.high_signal === true ? "1" : row.high_signal === false ? "0" : "-"}` },
            { key: "decision_reason", label: "Reason", render: (row) => shortValue(row.decision_reason, 90) },
          ]}
        />
      </article>

      <article className="panel">
        <div className="panel-head">
          <h2>Solar Pump Settings</h2>
          <span>{draft.enabled ? "enabled" : "disabled"}</span>
        </div>
        <div className="pilot-form">
          <label>
            <span>Enabled</span>
            <input type="checkbox" checked={draft.enabled === true} onChange={(event) => updateDraft("enabled", event.target.checked)} />
          </label>
          {[
            ["batch_minutes", "Batch", "min", 1],
            ["cooldown_minutes", "Cooldown", "min", 1],
            ["max_charge_current_a", "Max charge current", "A", 0.1],
            ["min_pv_voltage_v", "Min PV voltage", "V", 0.1],
            ["min_battery_voltage_v", "Min battery start", "V", 0.1],
            ["stop_battery_voltage_v", "Stop battery", "V", 0.1],
            ["max_telemetry_age_seconds", "Telemetry max age", "s", 1],
          ].map(([key, label, unit, step]) => (
            <label key={key}>
              <span>{label} ({unit})</span>
              <input type="number" step={step} value={draft[key] ?? ""} onChange={(event) => updateDraft(key, event.target.value)} />
            </label>
          ))}
        </div>
        <div className="button-row">
          <IconButton icon={Save} onClick={saveConfig} disabled={Boolean(busy)}>{busy === "save" ? "Saving" : "Save solar pump"}</IconButton>
        </div>
      </article>
    </section>
  );
}

export default function Irrigation({ snapshot, reload, setToast }) {
  const [duration, setDuration] = useState(20);
  const [busy, setBusy] = useState("");
  const [configDraft, setConfigDraft] = useState({});
  const irrigation = snapshot.irrigation;
  const live = irrigation.live || {};
  const liveTopic = (name) => live.topics?.[name] || null;
  const liveJson = (name) => {
    const item = liveTopic(name);
    return item && typeof item.json === "object" && !Array.isArray(item.json) ? item.json : null;
  };
  const firstLatest = (entityName, key) =>
    irrigation.latest?.find((row) => row.entity_name === entityName && row.key === key) || null;
  const latestByKey = (key) => irrigation.latest?.find((row) => row.key === key) || null;

  const nano = liveJson("esp_nano_status");
  const metrics = liveJson("pump_metrics");
  const tankLive = liveJson("tank_level");
  const cfg = liveJson("nano_config") || {};
  const diag = liveJson("esp_diag");
  const solar = liveJson("solar");

  useEffect(() => {
    setConfigDraft((current) => {
      const next = { ...current };
      for (const [key] of nanoConfigFields) {
        if (next[key] === undefined && cfg[key] !== undefined) next[key] = cfg[key];
      }
      return next;
    });
  }, [cfg]);

  const summary = useMemo(() => {
    const running = irrigation.sessions.find((item) => item.status === "running");
    const valveLive = textValue(nano?.valve || metrics?.valve);
    const manualValveLive = textValue(nano?.manual_valve || metrics?.manual_valve);
    const valveDb = firstLatest("Irrigation controller", "valve_state");
    const valveText = valveLive !== "-" ? valveLive : valveDb ? valueText(valveDb) : "-";
    const manualValveText = manualValveLive;
    const valveLooksOpen = ["OPEN", "OPENING", "MOVING_OPEN", "BETWEEN"].some((part) => valveText.toUpperCase().includes(part));
    const manualValveLooksOpen = ["OPEN", "OPENING", "BETWEEN"].some((part) => manualValveText.toUpperCase().includes(part));
    const wateringSources = [
      valveLooksOpen ? "motorized valve" : "",
      manualValveLooksOpen ? "manual valve" : "",
    ].filter(Boolean);
    const manualState = wateringSources.length ? "Watering" : "Deactivated";
    const manualMeta = wateringSources.length
      ? `${wateringSources.join(" + ")} open | valve=${valveText} | manual=${manualValveText}`
      : running
        ? `Timer/session is running, but the valve appears closed | valve=${valveText} | manual=${manualValveText}`
        : `valve=${valveText} | manual=${manualValveText}`;

    const tank = firstLatest("Tank_level", "liquid_level_percent") || latestByKey("liquid_level_percent");
    const tankPercent = firstValue(tankLive, ["liquid_level_percent", "percent", "level_percent"]);
    const tankDepthM = firstValue(tankLive, ["liquid_depth"]);
    const tankDepthCm = tankDepthM !== undefined ? Number(tankDepthM) * 100 : undefined;
    const pumpValue = firstValue(metrics || nano, ["pump"]);
    const currentValue = firstValue(metrics || nano, ["current_a", "pump_metrics_current_a"]);
    const voltageValue = firstValue(metrics || nano, ["voltage_12v", "pump_metrics_voltage_12v"]);
    const pump = firstLatest("Irrigation controller", "pump_running");
    const energy = irrigation.energy_daily[0];
    const nanoSerialHealthy = firstValue(nano, ["serial_healthy"]);
    const healthValue = textValue(nano?.health ?? nano?.nano_health);
    const nanoFault = nanoFaultText(firstValue(nano, [
      "code_text",
      "nano_code_text",
      "fault_text",
      "last_fault",
      "last_error",
      "error_name",
      "pump_error",
      "error",
      "fault",
      "code",
      "nano_code",
    ]));
    const healthParts = [
      healthValue,
      `nano serial=${nanoSerialText(nanoSerialHealthy)}`,
      nanoFault,
    ].filter(Boolean);
    const soilSensors = [
      { label: "Garden", name: "Moisture_02", monitorOnly: false },
      { label: "Flower", name: "Moisture_03", monitorOnly: true },
    ].map((sensor) => {
      const moisture = firstLatest(sensor.name, "soil_moisture");
      const dry = firstLatest(sensor.name, "dry");
      const temperature = firstLatest(sensor.name, "temperature");
      return { ...sensor, moisture, dry, temperature };
    });
    const primarySoil = soilSensors.find((sensor) => sensor.moisture) || soilSensors[0];
    const soilMetaParts = soilSensors
      .filter((sensor) => sensor.moisture && sensor.monitorOnly)
      .map((sensor) => {
        const dryText = sensor.dry?.v_bool === true ? "dry" : sensor.dry?.v_bool === false ? "wet" : "n/a";
        return `${sensor.label} monitor only: ${valueText(sensor.moisture)}% ${dryText}`;
      });
    const soilMeta = primarySoil?.moisture
      ? [...soilMetaParts, dateText(primarySoil.moisture.ts)].filter(Boolean).join(" | ")
      : "Visible only, no automation";

    return {
      running,
      manualState,
      manualMeta,
      tankState: tankPercent !== undefined ? `${numberText(tankPercent, 0)}%${Number.isFinite(tankDepthCm) ? ` | ${numberText(tankDepthCm, 0)} cm` : ""}` : tank ? `${valueText(tank)}%` : "-",
      tankMeta: tankPercent !== undefined ? `L=${textValue(nano?.low)} | H=${textValue(nano?.high)} | MQTT age ${ageText(liveTopic("tank_level"))}` : tank ? `L=${textValue(nano?.low)} | H=${textValue(nano?.high)} | DB ${dateText(tank.ts)}` : "No data yet",
      pumpState: pumpValue !== undefined ? (Number(pumpValue) ? "Filling" : "Idle") : pump ? (pump.v_bool ? "Filling" : "Idle") : "-",
      pumpMeta: `${unitValue(currentValue, "A")} | ${unitValue(voltageValue, "V")}`,
      energyState: energy?.amp_hours !== null && energy?.amp_hours !== undefined ? `${numberText(energy.amp_hours, 2)} Ah` : "No data",
      energyMeta: energy?.amp_hours !== null && energy?.amp_hours !== undefined ? `${unitValue(energy.watt_hours, "Wh", 1)} | active ${numberText(energy.active_minutes, 0)} min | max ${unitValue(energy.max_current_a, "A", 1)} | ${energy.current_samples || 0} samples` : "Waiting for pump current samples",
      healthState: healthParts.join(" | "),
      healthMeta: nanoFault ? `Nano fault: ${nanoFault} | Age: ${ageText(liveTopic("esp_nano_status"))}` : `Age: ${ageText(liveTopic("esp_nano_status"))}`,
      healthBad: healthValue.includes("FAULT") || nanoSerialHealthy === false || Boolean(nanoFault),
      modeState: textValue(nano?.mode || nano?.current_mode),
      tempState: `${numberText(metrics?.temp_c ?? nano?.temp_c ?? liveJson("esp_diag")?.nano_temp_c, 2)} C`,
      espState: `wifi=${textValue(diag?.wifi_rssi)} | nano=${textValue(diag?.nano_online ?? nano?.online)}`,
      espMeta: `Age: ${ageText(liveTopic("esp_diag") || liveTopic("esp_nano_status"))}`,
      configState: `src=${textValue(cfg?.config_source)} | dirty=${textValue(cfg?.config_dirty)}`,
      solarState: `bat=${textValue(solar?.battery_voltage)} V | chg=${textValue(solar?.charge_current)} A`,
      solarMeta: `pv=${textValue(solar?.pv_voltage)} V / ${textValue(solar?.pv_current)} A | Age: ${ageText(liveTopic("solar"))}`,
      soilState: primarySoil?.moisture ? `${primarySoil.label}: ${valueText(primarySoil.moisture)}%` : "-",
      soilMeta,
    };
  }, [irrigation, live, nano, metrics, tankLive, cfg, diag, solar]);

  async function sendCommand(name) {
    setBusy(name);
    try {
      if (name === "valve_open") {
        await api("/api/irrigation/manual/start", {
          method: "POST",
          body: JSON.stringify({ duration_minutes: Number(duration || 20), started_by: "react-admin" }),
        });
        setToast("Valve opened, safety close scheduled");
      } else {
        await api("/api/irrigation/command", {
          method: "POST",
          body: JSON.stringify({ name }),
        });
        setToast("Command sent");
      }
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function stopManual() {
    setBusy("stop_manual");
    try {
      await api("/api/irrigation/manual/stop", { method: "POST", body: "{}" });
      setToast("Valve close command sent");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setNanoConfig(key) {
    setBusy(`cfg-${key}`);
    try {
      await api("/api/irrigation/nano-config", {
        method: "POST",
        body: JSON.stringify({ key, value: configDraft[key] ?? "" }),
      });
      setToast("Config value sent");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <>
      <section className="tile-grid">
        <Card title="Watering" value={summary.manualState} meta={summary.manualMeta} icon={Droplets} />
        <Card title="Tank" value={summary.tankState} meta={summary.tankMeta} icon={Droplets} />
        <Card title="Pump / Fill" value={summary.pumpState} meta={summary.pumpMeta} icon={Activity} />
        <Card title="Pump Use Today" value={summary.energyState} meta={summary.energyMeta} icon={BatteryCharging} />
        <Card title="Health" value={summary.healthState} meta={summary.healthMeta} tone={summary.healthBad ? "bad" : ""} icon={Activity} />
        <Card title="Temperature" value={summary.tempState} meta={`Age: ${ageText(liveTopic("pump_metrics") || liveTopic("esp_diag"))}`} icon={Gauge} />
        <Card title="ESP link" value={summary.espState} meta={summary.espMeta} icon={Activity} />
        <Card title="Solar" value={summary.solarState} meta={summary.solarMeta} icon={BatteryCharging} />
        <Card title="Soil Moisture" value={summary.soilState} meta={summary.soilMeta} icon={Droplets} />
        <PilotSummaryCards
          fallbackMode={summary.modeState}
          fallbackAge={ageText(liveTopic("esp_nano_status"))}
          seasonProfile={irrigation.season_profile?.profile === "winter" ? "Winter" : "Summer"}
        />
      </section>

      <SolarPumpSchedulerPanel solarPump={irrigation.solar_pump_scheduler || {}} onSaved={reload} setToast={setToast} />

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Manual Watering</h2>
            <span>Valve command and automatic close</span>
          </div>
          <div className="inline-form">
            <label>
              Duration, min
              <input type="number" min="1" max={irrigation.manual_max_minutes} value={duration} onChange={(event) => setDuration(event.target.value)} />
            </label>
            <IconButton icon={Play} disabled={Boolean(busy)} onClick={() => sendCommand("valve_open")}>Open Valve</IconButton>
            <IconButton icon={Square} disabled={Boolean(busy)} className="secondary" onClick={stopManual}>Close Valve</IconButton>
          </div>
          {commandGroups.slice(0, 2).map((group) => (
            <React.Fragment key={group.title}>
              <h3>{group.title}</h3>
              <div className="button-grid">
                {group.commands.map(([name, label, Icon]) => (
                  <IconButton key={name} icon={Icon} disabled={Boolean(busy)} onClick={() => sendCommand(name)}>
                    {busy === name ? "Sending" : label}
                  </IconButton>
                ))}
              </div>
            </React.Fragment>
          ))}
          {(irrigation.session_recovery?.unresolved || []).map((item) => (
            <p key={`recovery-${item.id}`} role="status">
              Session #{item.id}: {item.status} | Age: {numberText(item.age_sec, 0)} s
              {" | "}Automatic close attempts: {item.attempts ?? "unknown"}/{item.max_attempts}
              {item.requires_attention ? " | Operator action required; automatic attempts exhausted or invalid." : " | Start blocked until the valve state is confirmed."}
              {item.next_attempt_at ? ` | Next attempt: ${dateText(item.next_attempt_at)}` : ""}
              {item.error ? ` | ${item.error}` : ""}
            </p>
          ))}
          <Table
            rows={irrigation.sessions}
            columns={[
              { key: "id", label: "ID" },
              { key: "type", label: "Type", render: (row) => irrigationSessionType(row) },
              { key: "status", label: "Status" },
              { key: "started_at", label: "Start", render: (row) => dateText(row.started_at) },
              { key: "requested_stop_at", label: "Stop target", render: (row) => dateText(row.requested_stop_at) },
              { key: "stopped_at", label: "Stopped", render: (row) => dateText(row.stopped_at) },
              { key: "error", label: "Details" },
            ]}
          />
        </article>

        <SchedulerPanel
          schedules={irrigation.schedules || []}
          schedulerGuard={irrigation.scheduler_guard || {}}
          reload={reload}
          setToast={setToast}
        />
      </section>

      <PilotDashboard setToast={setToast} />

      <section className="panel">
        <div className="panel-head">
          <h2>Nano Configuration</h2>
          <span>MQTT nano_cfg | {summary.configState} | Age: {ageText(liveTopic("nano_config"))}</span>
        </div>
        <div className="config-grid">
          {nanoConfigFields.map(([key, label]) => (
            <React.Fragment key={key}>
              <label htmlFor={`cfg-${key}`}>{label}</label>
              <input id={`cfg-${key}`} value={configDraft[key] ?? cfg[key] ?? ""} onChange={(event) => setConfigDraft({ ...configDraft, [key]: event.target.value })} />
              <IconButton icon={Save} disabled={Boolean(busy)} onClick={() => setNanoConfig(key)}>SET</IconButton>
            </React.Fragment>
          ))}
        </div>
        <div className="button-row">
          {commandGroups[2].commands.map(([name, label, Icon]) => (
            <IconButton key={name} icon={Icon} disabled={Boolean(busy)} onClick={() => sendCommand(name)}>{label}</IconButton>
          ))}
        </div>
      </section>

    </>
  );
}
