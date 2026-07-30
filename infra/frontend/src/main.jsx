import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  Archive,
  BarChart3,
  BatteryCharging,
  Bell,
  Bot,
  BookOpen,
  CalendarDays,
  Camera,
  ChevronLeft,
  ChevronRight,
  ClipboardList,
  Clock,
  CloudRain,
  Compass,
  Cpu,
  Database,
  Droplets,
  ExternalLink,
  Gauge,
  GitBranch,
  HardDrive,
  Home,
  Info,
  Lightbulb,
  Map as MapIcon,
  Menu,
  Play,
  Plus,
  Power,
  Radio,
  RefreshCw,
  Save,
  Settings,
  Server,
  Smartphone,
  Square,
  Thermometer,
  Trash2,
  Wind,
  Wrench,
  Zap,
} from "lucide-react";
import "./styles.css";

const UI_V2_STORAGE_KEY = "hc-ui-v2-tabs";
const MOBILE_DASHBOARD_MEDIA = "(max-width: 860px), (orientation: landscape) and (max-height: 560px) and (max-width: 940px)";
const TABLET_DASHBOARD_MEDIA = "(min-width: 861px) and (max-width: 1180px)";
const HOME_DASHBOARD_TABS = new Set(["home", "mobile-dashboard", "tablet-dashboard"]);
const navItems = [
  { id: "home", label: "Home", icon: Home, tone: "var(--tone-blue)", homeViewport: "desktop" },
  { id: "mobile-dashboard", label: "Mobile", icon: Smartphone, tone: "var(--tone-cyan)", homeViewport: "mobile" },
  { id: "tablet-dashboard", label: "Tablet", icon: Smartphone, tone: "var(--tone-sky)", homeViewport: "tablet" },
  { id: "irrigation", label: "Irrigation", icon: Droplets, tone: "var(--tone-green)" },
  { id: "solar", label: "Solar", icon: Zap, tone: "var(--tone-yellow)" },
  { id: "x10", label: "X10 Robot", icon: Home, tone: "var(--tone-orange)" },
  { id: "climate", label: "Climate", icon: Wind, tone: "var(--tone-sky)" },
  { id: "power-wall", label: "Power Wall", icon: Zap, tone: "var(--tone-amber)" },
  { id: "nyest-scheduler", label: "Marten Deterrent", icon: Bell, tone: "var(--tone-red)" },
  { id: "ai", label: "AI", icon: Bot, tone: "var(--tone-teal)" },
  { id: "scheduler", label: "Scheduler", icon: CalendarDays, tone: "var(--tone-purple)" },
  { id: "statistics", label: "Irrigation Stats", icon: BarChart3, tone: "var(--tone-green)" },
  { id: "hc-stat", label: "HC Stats", icon: Activity, tone: "var(--tone-indigo)" },
  { id: "performance", label: "Performance", icon: Cpu, tone: "var(--tone-rose)" },
  { id: "backup", label: "Backup", icon: Archive, tone: "var(--tone-cyan)" },
  { id: "hc-admin", label: "HC Admin", icon: Settings, tone: "var(--tone-violet)" },
  { id: "notes", label: "Notes", icon: ClipboardList, tone: "var(--tone-lime)" },
  { id: "documentation", label: "Docs", icon: BookOpen, tone: "var(--tone-teal)" },
  { id: "about", label: "About", icon: Info, tone: "var(--tone-blue)" },
];

function readUiV2Tabs() {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(UI_V2_STORAGE_KEY) || "{}");
    return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function dashboardTabForViewport() {
  if (typeof window === "undefined") return "home";
  if (window.matchMedia?.(MOBILE_DASHBOARD_MEDIA).matches) return "mobile-dashboard";
  if (window.matchMedia?.(TABLET_DASHBOARD_MEDIA).matches) return "tablet-dashboard";
  return "home";
}

function defaultTabForViewport() {
  if (typeof window === "undefined") return "home";
  const hash = window.location.hash.replace("#", "");
  const viewportHomeTab = dashboardTabForViewport();
  if (HOME_DASHBOARD_TABS.has(hash) && hash !== viewportHomeTab) return viewportHomeTab;
  if (hash) return hash;
  return viewportHomeTab;
}

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

const x10ModeOptions = [
  { value: "0", label: "Vacuum" },
  { value: "1", label: "Mop" },
  { value: "2", label: "Vacuum + Mop" },
];

const x10SuctionOptions = [
  { value: "0", label: "Silence" },
  { value: "1", label: "Standard" },
  { value: "2", label: "Strong" },
  { value: "3", label: "Turbo" },
];

const x10WaterOptions = [
  { value: "1", label: "Low" },
  { value: "2", label: "Medium" },
  { value: "3", label: "High" },
];

const x10DayOptions = [
  { index: 0, label: "Mon" },
  { index: 1, label: "Tue" },
  { index: 2, label: "Wed" },
  { index: 3, label: "Thu" },
  { index: 4, label: "Fri" },
  { index: 5, label: "Sat" },
  { index: 6, label: "Sun" },
];

const x10WeeklyTaskIds = [12, 13, 14, 17, 15, 16, 11];
const x10RobotDayMaskIndexByHcDay = [1, 2, 3, 4, 5, 6, 0];

const climateModeOptions = [
  { value: "auto", label: "Auto" },
  { value: "cool", label: "Cool" },
  { value: "dry", label: "Dry" },
  { value: "fan", label: "Fan" },
  { value: "heat", label: "Heat" },
];

const climateFanOptions = [
  { value: "auto", label: "Auto" },
  { value: "low", label: "Low" },
  { value: "mediumlow", label: "Medium Low" },
  { value: "medium", label: "Medium" },
  { value: "mediumhigh", label: "Medium High" },
  { value: "high", label: "High" },
];

const skinOptions = [
  { value: "premium", label: "Premium", description: "Commercial dark smart home dashboard" },
  { value: "jarvis", label: "Jarvis HUD", description: "Neon sci-fi control room interface" },
];

function textValue(value) {
  if (typeof value === "string" && ["none", "null", "undefined", "unknown_none", "unknown_null"].includes(value.trim().toLowerCase())) return "-";
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

function optionLabel(options, value) {
  const option = options.find((item) => String(item.value) === String(value));
  return option ? option.label : textValue(value);
}

function entitySelectLabel(entity) {
  if (!entity) return "-";
  const name = displayEntityName(entity.display_name || entity.entity_name || entity.device_name || "Entity");
  const location = entity.location ? ` | ${entity.location}` : "";
  const platform = entity.platform ? ` | ${entity.platform}` : "";
  return `${name}${location}${platform}`;
}

function processBinding(state, key) {
  return state?.process_bindings?.[key] || {};
}

function selectedProcessDevice(state, key, fallback) {
  const binding = processBinding(state, key);
  const selectedId = binding.selected_entity_id ?? binding.selected_entity?.entity_id;
  const devices = state?.devices || [];
  if (selectedId) {
    const selected = devices.find((item) => String(item.entity_id) === String(selectedId));
    if (selected) return selected;
  }
  if (binding.selected_entity) return binding.selected_entity;
  return typeof fallback === "function" ? fallback(devices) : null;
}

function normalizeDayMask(value) {
  const raw = String(value || "").padEnd(7, "0").slice(0, 7);
  return raw.replace(/[^1]/g, "0");
}

function parseSegmentList(value) {
  if (Array.isArray(value)) return value.map((item) => Number(item)).filter(Boolean);
  return String(value || "").split(",").map((item) => Number(item.trim())).filter(Boolean);
}

function dayMaskFor(index) {
  const chars = ["0", "0", "0", "0", "0", "0", "0"];
  const robotIndex = x10RobotDayMaskIndexByHcDay[index] ?? index;
  chars[robotIndex] = "1";
  return chars.join("");
}

function x10WeeklyDraftFromState(state) {
  const entries = Array.isArray(state?.scheduler_entries) ? state.scheduler_entries : [];
  return x10DayOptions.map((day) => {
    const taskId = x10WeeklyTaskIds[day.index];
    const entry = entries.find((item) => Number(item.task_id) === taskId);
    return {
      day_index: day.index,
      task_id: taskId,
      enabled: String(entry?.enabled ?? "0") === "1",
      start_time: entry?.time || "06:00",
      days: dayMaskFor(day.index),
      map_id: Number(entry?.map_id ?? state?.map?.current_id ?? 3),
      mode: textValue(entry?.clean_mode ?? entry?.flag ?? state?.clean_mode ?? 2),
      suction: textValue(entry?.suction ?? state?.suction ?? 3),
      water_level: textValue(entry?.water_level ?? entry?.clean_param ?? state?.water_level ?? 2),
      segments: parseSegmentList(entry?.segments),
    };
  });
}

function normalizeWeeklySchedules(rows = []) {
  return rows.map((item) => ({
    day_index: Number(item.day_index),
    task_id: Number(item.task_id),
    enabled: Boolean(item.enabled),
    start_time: item.start_time || "06:00",
    map_id: Number(item.map_id || 3),
    mode: String(item.mode ?? "2"),
    suction: String(item.suction ?? "3"),
    water_level: String(item.water_level ?? "2"),
    segments: parseSegmentList(item.segments).sort((a, b) => a - b),
  })).sort((a, b) => a.day_index - b.day_index);
}

function weeklyScheduleSignature(rows = []) {
  return JSON.stringify(normalizeWeeklySchedules(rows));
}

function valueText(row) {
  if (!row) return "-";
  if (row.v_num !== null && row.v_num !== undefined) return Number(row.v_num).toLocaleString("en-GB");
  if (row.v_bool !== null && row.v_bool !== undefined) return row.v_bool ? "true" : "false";
  if (row.v_text !== null && row.v_text !== undefined) return row.v_text;
  return "-";
}

function dateText(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("en-GB", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function timeText(value) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("en-GB", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
}

function shortTimeText(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function scheduleDateTime(schedule, base = new Date()) {
  if (!schedule?.start_time || schedule.day_of_week === undefined || schedule.day_of_week === null) return null;
  const [hours, minutes] = String(schedule.start_time).split(":").map(Number);
  if (!Number.isFinite(hours) || !Number.isFinite(minutes)) return null;
  const todayIndex = (base.getDay() + 6) % 7;
  let dayOffset = (Number(schedule.day_of_week) - todayIndex + 7) % 7;
  const target = new Date(base);
  target.setDate(base.getDate() + dayOffset);
  target.setHours(hours, minutes, 0, 0);
  if (target.getTime() < base.getTime() - 60_000) {
    target.setDate(target.getDate() + 7);
    dayOffset += 7;
  }
  return target;
}

function nextActiveSchedule(schedules = []) {
  const now = new Date();
  return schedules
    .filter((schedule) => schedule?.is_active)
    .map((schedule) => ({ schedule, at: schedule.should_run_now ? now : scheduleDateTime(schedule, now) }))
    .filter((item) => item.at)
    .sort((a, b) => a.at - b.at)[0] || null;
}

function firstTimestamp(row, keys = ["stopped_at", "ended_at", "started_at", "created_at", "updated_at", "ts"]) {
  for (const key of keys) {
    if (row?.[key]) return row[key];
  }
  return null;
}

function durationText(ms) {
  if (!Number.isFinite(ms)) return "-";
  const total = Math.max(0, Math.ceil(ms / 1000));
  const minutes = Math.floor(total / 60);
  const seconds = total % 60;
  return `${minutes}:${String(seconds).padStart(2, "0")}`;
}

function timeAfterMinutes(minutes = 2) {
  const target = new Date(Date.now() + Math.max(1, Number(minutes) || 2) * 60_000);
  return `${String(target.getHours()).padStart(2, "0")}:${String(target.getMinutes()).padStart(2, "0")}`;
}

function timeToMinutes(value) {
  const match = /^(\d{1,2}):(\d{2})$/.exec(String(value || ""));
  if (!match) return null;
  const hours = Number(match[1]);
  const minutes = Number(match[2]);
  if (hours < 0 || hours > 23 || minutes < 0 || minutes > 59) return null;
  return hours * 60 + minutes;
}

function dndMatch(windows = [], date = new Date()) {
  const nowMin = date.getHours() * 60 + date.getMinutes();
  return windows.find((item) => {
    if (!item.enabled) return false;
    const start = timeToMinutes(item.start);
    const end = timeToMinutes(item.end);
    if (start === null || end === null || start === end) return false;
    if (start < end) return nowMin >= start && nowMin < end;
    return nowMin >= start || nowMin < end;
  }) || null;
}

function roomCleanPlan(status, nowMs) {
  if (!status || typeof status !== "object") return null;
  const active = status.active || {};
  const task = status.task || {};
  const statusText = status.status || "";
  const isPending = ["scheduled", "active", "schedule_saved"].includes(statusText);
  if (!isPending) {
    return { status: statusText || "-", label: statusText || "-", meta: "no pending room clean" };
  }

  let targetMs = null;
  if (active.created_ts && active.delay_min !== undefined) {
    targetMs = (Number(active.created_ts) + Number(active.delay_min) * 60) * 1000;
  } else if (active.start_time) {
    const [hours, minutes] = String(active.start_time).split(":").map(Number);
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      const target = new Date(nowMs);
      target.setHours(hours, minutes, 0, 0);
      if (target.getTime() < nowMs - 60_000) target.setDate(target.getDate() + 1);
      targetMs = target.getTime();
    }
  } else if (task.time) {
    const [hours, minutes] = String(task.time).split(":").map(Number);
    if (Number.isFinite(hours) && Number.isFinite(minutes)) {
      const target = new Date(nowMs);
      target.setHours(hours, minutes, 0, 0);
      if (target.getTime() < nowMs - 60_000) target.setDate(target.getDate() + 1);
      targetMs = target.getTime();
    }
  }

  if (!targetMs) return { status: statusText || "-", label: statusText || "-", meta: "scheduled time unavailable" };
  const remaining = targetMs - nowMs;
  return {
    status: statusText,
    targetMs,
    label: remaining > 0 ? durationText(remaining) : "due",
    meta: `${timeText(targetMs)} start | ${statusText}`,
  };
}

function numberText(value, digits = 1) {
  if (typeof value === "string" && ["none", "null", "undefined", "unknown_none", "unknown_null"].includes(value.trim().toLowerCase())) return "-";
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(digits);
}

function unitValue(value, unit, digits = 1) {
  const text = numberText(value, digits);
  return text === "-" ? "-" : `${text} ${unit}`;
}

function signedNumberText(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const text = Math.abs(number) < 0.05 ? "0" : numberText(number, digits);
  return number > 0 ? `+${text}` : text;
}

function byteText(value) {
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  const units = ["B", "KB", "MB", "GB", "TB"];
  let size = number;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(index === 0 ? 0 : 1)} ${units[index]}`;
}

function uptimeText(seconds) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total < 0) return "-";
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

function ageText(item) {
  return item ? `${item.age_sec} s` : "-";
}

function shortValue(value, max = 140) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "-";
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

function jsonText(value) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function shortPath(value, max = 44) {
  const text = String(value || "");
  const name = text.split("/").filter(Boolean).pop() || text;
  return shortValue(name, max);
}

function firstValue(source, keys) {
  if (!source) return undefined;
  for (const key of keys) {
    if (source[key] !== undefined && source[key] !== null && source[key] !== "") return source[key];
  }
  return undefined;
}

async function api(path, options = {}) {
  const { allowOkFalse = false, skipContextRefresh = false, ...fetchOptions } = options;
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...fetchOptions,
  });
  const data = await readJsonResponse(response);
  if (!response.ok || (data.ok === false && !allowOkFalse)) {
    throw new Error(data.error || data.message || `HTTP ${response.status}`);
  }
  if (!skipContextRefresh) refreshContextReadAfter(data);
  return data;
}

const contextRefreshCache = new Map();
const contextRefreshSubscribers = new Map();

function contextReadAfterPaths(data) {
  const paths = Array.isArray(data?.context?.read_after) ? data.context.read_after : [];
  return [...new Set(paths.filter((path) => typeof path === "string" && path.startsWith("/api/context/")))];
}

function refreshContextReadAfter(data) {
  const paths = contextReadAfterPaths(data);
  if (!paths.length) return;
  paths.forEach((path) => {
    api(path, { allowOkFalse: true, skipContextRefresh: true })
      .then((payload) => {
        contextRefreshCache.set(path, payload);
        (contextRefreshSubscribers.get(path) || []).forEach((handler) => handler(payload, path));
      })
      .catch(() => {});
  });
}

function useContextRefresh(paths, handler) {
  const handlerRef = useRef(handler);
  useEffect(() => {
    handlerRef.current = handler;
  }, [handler]);
  const stablePaths = useMemo(() => paths, [paths.join("|")]);
  useEffect(() => {
    const wrapped = (payload, path) => handlerRef.current(payload, path);
    stablePaths.forEach((path) => {
      const current = contextRefreshSubscribers.get(path) || [];
      contextRefreshSubscribers.set(path, [...current, wrapped]);
      if (contextRefreshCache.has(path)) wrapped(contextRefreshCache.get(path), path);
    });
    return () => {
      stablePaths.forEach((path) => {
        const current = contextRefreshSubscribers.get(path) || [];
        contextRefreshSubscribers.set(path, current.filter((item) => item !== wrapped));
      });
    };
  }, [stablePaths]);
}

function aiFriendlyError(message) {
  const text = String(message || "");
  if (/ollama unavailable|no route to host|connection refused|timed out|ai provider error|urlopen/i.test(text)) {
    return "AI server unavailable";
  }
  return text || "AI server unavailable";
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

function Card({ title, value, meta, tone = "", icon: Icon = Activity, className = "" }) {
  const displayValue = value === 0 ? "0" : value || "-";
  return (
    <article className={`card ${tone} ${className}`.trim()}>
      <div className="card-title">
        <Icon size={16} aria-hidden="true" />
        <h2>{title}</h2>
      </div>
      <strong>{displayValue}</strong>
      <span>{meta || "-"}</span>
    </article>
  );
}

function tooltipTextFromChildren(children) {
  if (typeof children === "string" || typeof children === "number") return String(children).trim();
  if (Array.isArray(children)) return children.map(tooltipTextFromChildren).filter(Boolean).join(" ").trim();
  if (children && typeof children === "object" && "props" in children) return tooltipTextFromChildren(children.props.children);
  return "";
}

function IconButton({ children, icon: Icon = Activity, title, "aria-label": ariaLabel, ...props }) {
  const tooltip = title || ariaLabel || tooltipTextFromChildren(children);
  return (
    <button {...props} title={tooltip || undefined} aria-label={ariaLabel || tooltip || undefined}>
      <Icon size={16} aria-hidden="true" />
      <span>{children}</span>
    </button>
  );
}

function V2Page({ children, className = "" }) {
  return <section className={`v2-page ${className}`.trim()}>{children}</section>;
}

function V2AutoPage({ enabled, sectionId, children }) {
  if (!enabled) return children;
  return <V2Page className={`v2-auto v2-auto-${sectionId}`}>{children}</V2Page>;
}

function ensureButtonTooltip(button) {
  if (!button || button.title) return;
  const label = button.getAttribute("aria-label") || button.textContent || "";
  const tooltip = label.replace(/\s+/g, " ").trim();
  if (tooltip) button.title = tooltip;
}

function V2Toolbar({ children, className = "" }) {
  return <section className={`stats-head v2-toolbar ${className}`.trim()}>{children}</section>;
}

function V2KpiRow({ children, className = "" }) {
  return <section className={`v2-kpi-row ${className}`.trim()}>{children}</section>;
}

function V2SectionGrid({ children, className = "" }) {
  return <section className={`v2-section-grid ${className}`.trim()}>{children}</section>;
}

function VisualAuditButton({ activeTab, activeLabel, uiV2Tabs, setToast }) {
  const [busy, setBusy] = useState(false);

  async function capture() {
    const endpoint = `${window.location.protocol}//${window.location.hostname}:5015/capture`;
    setBusy(true);
    try {
      const response = await fetch(endpoint, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tab: activeTab,
          label: activeLabel,
          width: window.innerWidth,
          height: window.innerHeight,
          uiV2Tabs,
          url: `${window.location.origin}${window.location.pathname}#${activeTab}`,
        }),
      });
      const data = await readJsonResponse(response);
      if (!response.ok || data.ok === false) throw new Error(data.error || `HTTP ${response.status}`);
      setToast(`Screenshot saved: ${data.relative_path || data.path}`);
    } catch (err) {
      setToast(`Visual audit failed: ${err.message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="visual-audit-button" type="button" onClick={capture} disabled={busy} title="Save a visual audit screenshot">
      <Camera size={17} aria-hidden="true" />
      <span>{busy ? "Capturing" : "Screenshot"}</span>
    </button>
  );
}

function Table({ rows = [], columns }) {
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((column) => <th key={column.key}>{column.label || column.key}</th>)}</tr>
        </thead>
        <tbody>
          {rows.length ? (
            rows.map((row, index) => (
              <tr key={row.id ?? row.key ?? row.name ?? index}>
                {columns.map((column) => (
                  <td key={column.key}>{column.render ? column.render(row) : row[column.key] ?? "-"}</td>
                ))}
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan={columns.length}>No data</td>
            </tr>
          )}
        </tbody>
      </table>
    </div>
  );
}

class RenderErrorBoundary extends React.Component {
  constructor(props) {
    super(props);
    this.state = { error: null };
  }

  static getDerivedStateFromError(error) {
    return { error };
  }

  componentDidCatch(error) {
    console.error("HomeControl render error", error);
  }

  render() {
    if (this.state.error) {
      return (
        <section className="panel">
          <div className="panel-head">
            <h2>Render Error</h2>
            <span>Refresh or report this message</span>
          </div>
          <pre className="error-box">{this.state.error.message || String(this.state.error)}</pre>
        </section>
      );
    }
    return this.props.children;
  }
}

function timestampLabel(value) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function dayLabel(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-GB", { month: "2-digit", day: "2-digit" });
}

function metricNumber(row, key) {
  const value = row?.[key];
  if (value === undefined || value === null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function displayEntityName(name) {
  const labels = {
    "Nyestriasztó": "Marten Deterrent",
  };
  return labels[name] || name;
}

function roomDisplayName(name) {
  return name || "-";
}

function roomKey(name) {
  return String(name || "").trim().toLocaleLowerCase("hu-HU");
}

function statusTone(ok, warn = false) {
  if (ok) return "ok";
  return warn ? "warn" : "bad";
}

function boolText(value) {
  return value ? "Running" : "Stopped";
}

function svgPointerX(event, fallbackWidth) {
  const svg = event.currentTarget;
  const matrix = svg.getScreenCTM?.();
  if (matrix && svg.createSVGPoint) {
    const point = svg.createSVGPoint();
    point.x = event.clientX;
    point.y = event.clientY;
    return point.matrixTransform(matrix.inverse()).x;
  }
  const rect = svg.getBoundingClientRect();
  return ((event.clientX - rect.left) / Math.max(rect.width, 1)) * fallbackWidth;
}

function clampChartX(value, pad, width) {
  return Math.max(pad.left, Math.min(value, width - pad.right));
}

function smoothLinePath(points) {
  if (points.length < 3) return points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  return points.reduce((path, point, index) => {
    if (index === 0) return `M ${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    const previous = points[index - 1];
    const midX = (previous.x + point.x) / 2;
    const midY = (previous.y + point.y) / 2;
    return `${path} Q ${previous.x.toFixed(1)} ${previous.y.toFixed(1)} ${midX.toFixed(1)} ${midY.toFixed(1)}`;
  }, "") + ` T ${points[points.length - 1].x.toFixed(1)} ${points[points.length - 1].y.toFixed(1)}`;
}

function StatLineChart({ rows = [], yKey, unit = "", digits = 1, color = "accent", height = 250 }) {
  const [hover, setHover] = useState(null);
  const points = rows
    .map((row, index) => ({ index, ts: row.ts, value: metricNumber(row, yKey) }))
    .filter((point) => point.value !== null);
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!points.length) return <div className="chart-empty">No data</div>;
  const min = Math.min(...points.map((point) => point.value));
  const max = Math.max(...points.map((point) => point.value));
  const span = Math.max(max - min, 1);
  const xMax = Math.max(rows.length - 1, 1);
  const x = (index) => pad.left + (index / xMax) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((max - value) / span) * (height - pad.top - pad.bottom);
  const path = points.map((point, index) => `${index ? "L" : "M"} ${x(point.index).toFixed(1)} ${y(point.value).toFixed(1)}`).join(" ");
  const first = points[0];
  const last = points[points.length - 1];
  const active = hover || last;

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = points.reduce((best, point) => {
      const distance = Math.abs(x(point.index) - svgX);
      return !best || distance < best.distance ? { ...point, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`line-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(max, unit, digits)}</text>
        <text x={8} y={height - pad.bottom}>{unitValue(min, unit, digits)}</text>
        <text x={pad.left} y={height - 10}>{timestampLabel(first.ts)}</text>
        <text x={width - pad.right - 48} y={height - 10}>{timestampLabel(last.ts)}</text>
        <path d={path} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active.index)} y1={pad.top} x2={hover?.cursorX ?? x(active.index)} y2={height - pad.bottom} />
            <circle cx={x(active.index)} cy={y(active.value)} r="5" />
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(active.value, unit, digits)}</strong>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

function StatNormalizedMultiLineChart({ rows = [], series = [], height = 210 }) {
  const [hover, setHover] = useState(null);
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  const prepared = series.map((item) => {
    const points = rows
      .map((row, index) => ({ index, ts: row.ts || row.day, value: metricNumber(row, item.key) }))
      .filter((point) => point.value !== null);
    const values = points.map((point) => point.value);
    const min = values.length ? Math.min(...values) : 0;
    const max = values.length ? Math.max(...values) : 1;
    const span = Math.max(max - min, 1);
    return { ...item, points, min, max, span };
  });
  const activeSeries = prepared.filter((item) => item.points.length);
  if (!activeSeries.length) return <div className="chart-empty">No data</div>;

  const xMax = Math.max(rows.length - 1, 1);
  const x = (index) => pad.left + (index / xMax) * (width - pad.left - pad.right);
  const y = (item, value) => pad.top + ((item.max - value) / item.span) * (height - pad.top - pad.bottom);
  const pathFor = (item) => item.points.map((point, index) => `${index ? "L" : "M"} ${x(point.index).toFixed(1)} ${y(item, point.value).toFixed(1)}`).join(" ");
  const fallback = activeSeries[0].points[activeSeries[0].points.length - 1];
  const active = hover || fallback;

  function valueAt(item, index) {
    return item.points.find((point) => point.index === index) || null;
  }

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = activeSeries[0].points.reduce((best, point) => {
      const distance = Math.abs(x(point.index) - svgX);
      return !best || distance < best.distance ? { ...point, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box climate-chart-box">
      <div className="chart-legend">
        {activeSeries.map((item) => (
          <span className={`legend-item ${item.color}`} key={item.key}>{item.label}</span>
        ))}
      </div>
      <svg className="line-chart climate" viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>high</text>
        <text x={8} y={height - pad.bottom}>low</text>
        {activeSeries.map((item) => <path className={item.color} d={pathFor(item)} key={item.key} />)}
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active.index)} y1={pad.top} x2={hover?.cursorX ?? x(active.index)} y2={height - pad.bottom} />
            {activeSeries.map((item) => {
              const point = valueAt(item, active.index);
              return point ? <circle className={item.color} cx={x(active.index)} cy={y(item, point.value)} r="4.5" key={item.key} /> : null;
            })}
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip climate-tooltip pinned">
          {activeSeries.map((item) => {
            const point = valueAt(item, active.index);
            return <span className={`tooltip-line ${item.color}`} key={item.key}>{item.label}: {point ? unitValue(point.value, item.unit, item.digits) : "-"}</span>;
          })}
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

function StatBarChart({ rows = [], valueKey, unit = "", digits = 1, color = "accent" }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .slice()
    .reverse()
    .map((row) => ({ ...row, value: metricNumber(row, valueKey) }))
    .filter((row) => row.value !== null);
  const width = 720;
  const height = 250;
  const pad = { top: 18, right: 18, bottom: 34, left: 44 };
  if (!values.length) return <div className="chart-empty">No data</div>;
  const max = Math.max(...values.map((row) => row.value), 1);
  const slot = (width - pad.left - pad.right) / values.length;
  const barWidth = Math.max(8, Math.min(34, slot * 0.62));
  const barCenter = (index) => pad.left + index * slot + slot / 2;

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row, index) => {
      const distance = Math.abs(barCenter(index) - svgX);
      return !best || distance < best.distance ? { ...row, index, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`bar-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(max, unit, digits)}</text>
        {values.map((row, index) => {
          const barHeight = (row.value / max) * (height - pad.top - pad.bottom);
          const x = pad.left + index * slot + (slot - barWidth) / 2;
          const y = height - pad.bottom - barHeight;
          const isActive = hover?.index === index;
          return (
            <g key={`${row.day || index}-${valueKey}`}>
              <rect className={isActive ? "active" : ""} x={x.toFixed(1)} y={y.toFixed(1)} width={barWidth.toFixed(1)} height={barHeight.toFixed(1)} rx="3" />
              {index % Math.ceil(values.length / 7 || 1) === 0 && <text x={(x - 4).toFixed(1)} y={height - 10}>{dayLabel(row.day)}</text>}
            </g>
          );
        })}
        {hover && <line className="hover-line" x1={hover.cursorX} y1={pad.top} x2={hover.cursorX} y2={height - pad.bottom} />}
        {values.map((row, index) => (
          <rect
            className="bar-hitbox"
            key={`${row.day || index}-${valueKey}-hitbox`}
            x={(pad.left + index * slot).toFixed(1)}
            y={pad.top}
            width={slot.toFixed(1)}
            height={height - pad.top - pad.bottom}
          />
        ))}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(hover.value, unit, digits)}</strong>
          <span>{dayLabel(hover.day)}</span>
        </div>
      )}
    </div>
  );
}

function TimeLineChart({ rows = [], valueKey, unit = "", digits = 1, color = "blue", height = 250, yMin = null, yMax = null, smooth = false }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .map((row) => ({ ...row, value: metricNumber(row, valueKey), time: new Date(row.ts).getTime() }))
    .filter((row) => row.value !== null && Number.isFinite(row.time));
  const width = 720;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!values.length) return <div className="chart-empty">No data</div>;

  const minTime = Math.min(...values.map((row) => row.time));
  const maxTime = Math.max(...values.map((row) => row.time));
  const maxValue = yMax === null ? Math.max(...values.map((row) => row.value), 1) : yMax;
  const minValue = yMin === null ? Math.min(...values.map((row) => row.value), 0) : yMin;
  const spanValue = Math.max(maxValue - minValue, 1);
  const spanTime = Math.max(maxTime - minTime, 1);
  const x = (row) => pad.left + ((row.time - minTime) / spanTime) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((maxValue - value) / spanValue) * (height - pad.top - pad.bottom);
  const pathPoints = values.map((row) => ({ x: x(row), y: y(row.value) }));
  const path = smooth ? smoothLinePath(pathPoints) : pathPoints.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const active = hover || values[values.length - 1];

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row) => {
      const distance = Math.abs(x(row) - svgX);
      return !best || distance < best.distance ? { ...row, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box">
      <svg className={`line-chart ${color}`} viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>{unitValue(maxValue, unit, digits)}</text>
        <text x={8} y={height - pad.bottom}>{unitValue(minValue, unit, digits)}</text>
        <path d={path} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active)} y1={pad.top} x2={hover?.cursorX ?? x(active)} y2={height - pad.bottom} />
            <circle cx={x(active)} cy={y(active.value)} r="4.5" />
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip pinned">
          <strong>{unitValue(active.value, unit, digits)}</strong>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

function ResourceUsageChart({ rows = [] }) {
  const [hover, setHover] = useState(null);
  const values = rows
    .map((row) => ({
      ...row,
      time: new Date(row.ts).getTime(),
      cpu_percent: metricNumber(row, "cpu_percent"),
      memory_percent: metricNumber(row, "memory_percent"),
    }))
    .filter((row) => Number.isFinite(row.time) && (row.cpu_percent !== null || row.memory_percent !== null));
  const width = 720;
  const height = 250;
  const pad = { top: 18, right: 22, bottom: 34, left: 46 };
  if (!values.length) return <div className="chart-empty">No resource history yet</div>;

  const minTime = Math.min(...values.map((row) => row.time));
  const maxTime = Math.max(...values.map((row) => row.time));
  const spanTime = Math.max(maxTime - minTime, 1);
  const x = (row) => pad.left + ((row.time - minTime) / spanTime) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((100 - Math.max(0, Math.min(value, 100))) / 100) * (height - pad.top - pad.bottom);
  const pathFor = (key) => values
    .filter((row) => row[key] !== null)
    .map((row, index) => `${index ? "L" : "M"} ${x(row).toFixed(1)} ${y(row[key]).toFixed(1)}`)
    .join(" ");
  const active = hover || values[values.length - 1];

  function handleMove(event) {
    const svgX = svgPointerX(event, width);
    const cursorX = clampChartX(svgX, pad, width);
    const nearest = values.reduce((best, row) => {
      const distance = Math.abs(x(row) - svgX);
      return !best || distance < best.distance ? { ...row, distance } : best;
    }, null);
    setHover(nearest ? { ...nearest, cursorX } : null);
  }

  return (
    <div className="chart-box resource-chart-box">
      <div className="chart-legend">
        <span className="legend-item red">CPU</span>
        <span className="legend-item blue">RAM</span>
      </div>
      <svg className="line-chart resource" viewBox={`0 0 ${width} ${height}`} role="img" onMouseMove={handleMove} onMouseLeave={() => setHover(null)}>
        <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
        <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
        <text x={8} y={pad.top + 4}>100%</text>
        <text x={14} y={height - pad.bottom}>0%</text>
        <text x={pad.left} y={height - 10}>{timestampLabel(values[0].ts)}</text>
        <text x={width - pad.right - 48} y={height - 10}>{timestampLabel(values[values.length - 1].ts)}</text>
        <path className="red" d={pathFor("cpu_percent")} />
        <path className="blue" d={pathFor("memory_percent")} />
        {active && (
          <>
            <line className="hover-line" x1={hover?.cursorX ?? x(active)} y1={pad.top} x2={hover?.cursorX ?? x(active)} y2={height - pad.bottom} />
            {active.cpu_percent !== null && <circle className="red" cx={x(active)} cy={y(active.cpu_percent)} r="4.5" />}
            {active.memory_percent !== null && <circle className="blue" cx={x(active)} cy={y(active.memory_percent)} r="4.5" />}
          </>
        )}
      </svg>
      {hover && (
        <div className="chart-tooltip climate-tooltip pinned">
          <span className="tooltip-line red">CPU: {unitValue(active.cpu_percent, "%", 1)}</span>
          <span className="tooltip-line blue">RAM: {unitValue(active.memory_percent, "%", 1)}</span>
          <span>{dateText(active.ts)}</span>
        </div>
      )}
    </div>
  );
}

const dayLabels = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

function SchedulerPanel({ schedules = [], schedulerGuard = {}, reload, setToast }) {
  const [drafts, setDrafts] = useState({});
  const [busy, setBusy] = useState("");

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

  return (
    <article className="panel scheduler-panel">
      <div className="panel-head">
        <h2 className="panel-title"><CalendarDays size={17} aria-hidden="true" /> Scheduler</h2>
        <span>{schedulerGuard.blocked ? `Blocked: manual valve ${schedulerGuard.state || "OPEN"}` : "Weekly DB config, time based only"}</span>
      </div>
      {schedulerGuard.blocked && (
        <div className="scheduler-blocked">
          Manual valve is open, scheduler start is disabled.
        </div>
      )}
      <div className="schedule-list">
        {schedules.map((schedule) => {
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
                <span>{dayLabels[schedule.day_of_week] || schedule.label}</span>
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
              <IconButton icon={Save} disabled={busy === String(schedule.id)} onClick={() => saveSchedule(schedule)}>
                {busy === String(schedule.id) ? "Saving" : "Save"}
              </IconButton>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function useBootstrap() {
  const [snapshot, setSnapshot] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const snapshotRef = useRef(null);
  const irrigationRefreshInFlight = useRef(false);

  async function load() {
    setLoading(true);
    setError("");
    try {
      setSnapshot(await api("/api/admin/bootstrap"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function refreshIrrigation() {
    if (!snapshotRef.current || irrigationRefreshInFlight.current) return;
    irrigationRefreshInFlight.current = true;
    try {
      const irrigation = await api("/api/context/irrigation");
      setSnapshot((current) => current ? { ...current, irrigation } : current);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      irrigationRefreshInFlight.current = false;
    }
  }

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    snapshotRef.current = snapshot;
  }, [snapshot]);

  return { snapshot, error, loading, load, refreshIrrigation, setSnapshot };
}

function irrigationUserStatus(irrigation = {}) {
  const live = irrigation.live || {};
  const liveTopic = (name) => live.topics?.[name] || null;
  const liveJson = (name) => {
    const item = liveTopic(name);
    return item && typeof item.json === "object" && !Array.isArray(item.json) ? item.json : null;
  };
  const nano = liveJson("esp_nano_status");
  const metrics = liveJson("pump_metrics");
  const valveText = textValue(nano?.valve || metrics?.valve).toUpperCase();
  const manualValveText = textValue(nano?.manual_valve || metrics?.manual_valve).toUpperCase();
  const running = (irrigation.sessions || []).find((item) => item.status === "running");
  const openText = `${valveText} ${manualValveText}`;
  const active = Boolean(running) || ["OPEN", "OPENING", "MOVING_OPEN", "BETWEEN"].some((part) => openText.includes(part));
  return {
    active,
    value: active ? "ON" : "OFF",
    meta: running ? `timer running | stop ${dateText(running.requested_stop_at)}` : `valve ${valveText || "-"} | manual ${manualValveText || "-"}`,
  };
}

function x10UserStatus(state) {
  const stateText = String(state?.robot_state_text || state?.state?.state_text || "").toLowerCase();
  const roomStatus = state?.room_clean_status || {};
  const roomStatusText = String(roomStatus.status || "").toLowerCase();
  const active = ["cleaning", "room_cleaning", "working"].some((part) => stateText.includes(part)) || ["scheduled", "active"].includes(roomStatusText);
  return {
    active,
    value: active ? "ON" : "OFF",
    meta: active ? (roomStatusText ? `room clean ${roomStatusText}` : state?.robot_state_text || "active") : state?.robot_state_text || "idle",
  };
}

function climateUserStatus(state) {
  const active = state?.power === "on";
  const powerNow = metricNumber(state?.power_meter?.state || {}, "power_w");
  const currentTemperature = metricNumber(state || {}, "current_temperature");
  const targetTemperature = metricNumber(state || {}, "target_temperature");
  return {
    active,
    value: active ? "ON" : "OFF",
    description: `target ${unitValue(targetTemperature, "C", 0)}`,
    meta: `${unitValue(powerNow, "W", 0)} | current ${unitValue(currentTemperature, "C", 1)}`,
    compactMeta: `${unitValue(powerNow, "W", 0)} | target ${unitValue(targetTemperature, "C", 0)} | current ${unitValue(currentTemperature, "C", 1)}`,
  };
}

function homeSensorSnapshot(irrigation = {}) {
  const latest = irrigation.latest || [];
  const findByKey = (keys) => {
    for (const key of keys) {
      const row = latest.find((item) => String(item.key || "").toLowerCase() === key.toLowerCase());
      const value = metricNumber(row, "v_num");
      if (value !== null) return { value, row };
    }
    return { value: null, row: null };
  };
  return {
    temperature: findByKey(["temperature", "Temperature", "LocalTemperature"]),
    humidity: findByKey(["humidity", "Humidity", "LocalHumidity"]),
    pressure: findByKey(["pressure_hpa", "Pressure"]),
    rain: findByKey(["rain_mm", "Rain24h", "forecast_rain_24h_mm", "ForecastRain"]),
  };
}

function findYardSensor(localSensors = []) {
  return localSensors.find((sensor) => sensor.entity_name === "Udvar")
    || localSensors.find((sensor) => String(sensor.entity_name || sensor.device_name || "").toLowerCase().includes("udvar"));
}

function shortChartTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

function homeChartSeries(rows = [], valueKey, hours = 24, maxPoints = 96) {
  const averagePoints = (points, bucketCount) => {
    if (points.length <= bucketCount) return points;
    const step = Math.ceil(points.length / bucketCount);
    const averaged = [];
    for (let index = 0; index < points.length; index += step) {
      const bucket = points.slice(index, index + step);
      const value = bucket.reduce((sum, point) => sum + point.value, 0) / bucket.length;
      const middle = bucket[Math.floor(bucket.length / 2)];
      averaged.push({ ...middle, value, sampleCount: bucket.length });
    }
    return averaged;
  };
  const parsed = rows
    .map((row, index) => {
      const rawTime = row?.ts || row?.created_at || row?.day || null;
      const timeMs = rawTime ? new Date(rawTime).getTime() : NaN;
      return {
        value: metricNumber(row, valueKey),
        time: rawTime || index,
        timeMs,
        index,
      };
    })
    .filter((point) => point.value !== null)
    .sort((a, b) => {
      if (Number.isFinite(a.timeMs) && Number.isFinite(b.timeMs)) return a.timeMs - b.timeMs;
      return a.index - b.index;
    });
  const timed = parsed.filter((point) => Number.isFinite(point.timeMs));
  const latestMs = timed[timed.length - 1]?.timeMs;
  const windowed = latestMs
    ? parsed.filter((point) => !Number.isFinite(point.timeMs) || point.timeMs >= latestMs - hours * 60 * 60 * 1000)
    : parsed;
  if (windowed.length <= maxPoints) return windowed;
  const timedWindow = windowed.filter((point) => Number.isFinite(point.timeMs));
  if (!timedWindow.length) return averagePoints(windowed, maxPoints);
  const windowMs = hours * 60 * 60 * 1000;
  const bucketMs = Math.max(1, windowMs / maxPoints);
  const windowStart = latestMs - windowMs;
  const buckets = new Map();
  timedWindow.forEach((point) => {
    const bucketIndex = Math.min(maxPoints - 1, Math.max(0, Math.floor((point.timeMs - windowStart) / bucketMs)));
    const bucket = buckets.get(bucketIndex) || { valueSum: 0, timeMsSum: 0, count: 0, firstIndex: point.index };
    bucket.valueSum += point.value;
    bucket.timeMsSum += point.timeMs;
    bucket.count += 1;
    bucket.firstIndex = Math.min(bucket.firstIndex, point.index);
    buckets.set(bucketIndex, bucket);
  });
  return [...buckets.entries()]
    .sort(([leftIndex], [rightIndex]) => leftIndex - rightIndex)
    .map(([bucketIndex, bucket]) => {
      const timeMs = bucket.timeMsSum / bucket.count;
      return {
        value: bucket.valueSum / bucket.count,
        time: new Date(timeMs).toISOString(),
        timeMs,
        index: bucket.firstIndex,
        bucketIndex,
        sampleCount: bucket.count,
      };
    });
}

function HomeSparkline({ rows = [], valueKey, tone = "blue", type = "line", digits = 0 }) {
  const series = homeChartSeries(rows, valueKey);

  if (series.length < 2) return <div className={`home-sparkline-empty tone-${tone}`}>No trend</div>;

  const values = series.map((point) => point.value);
  const minRaw = Math.min(...values);
  const maxRaw = Math.max(...values);
  const padding = Math.max((maxRaw - minRaw) * 0.12, type === "bar" ? 0.4 : 0.2);
  const min = type === "bar" ? Math.min(0, minRaw) : minRaw - padding;
  const max = maxRaw + padding;
  const span = Math.max(max - min, 1);
  const ticks = [maxRaw, (minRaw + maxRaw) / 2, minRaw].map((value) => numberText(value, digits));
  const longestTick = ticks.reduce((maxLength, tick) => Math.max(maxLength, String(tick).length), 0);
  const left = longestTick <= 2 ? 13 : Math.min(34, 18 + (longestTick - 2) * 4);
  const right = 98;
  const top = 8;
  const bottom = 64;
  const width = right - left;
  const height = bottom - top;
  const timed = series.filter((point) => Number.isFinite(point.timeMs));
  const firstMs = timed[0]?.timeMs;
  const lastMs = timed[timed.length - 1]?.timeMs;
  const timeSpan = Number.isFinite(firstMs) && Number.isFinite(lastMs) ? Math.max(lastMs - firstMs, 1) : null;
  const points = series.map((point, index) => ({
    ...point,
    x: left + (timeSpan && Number.isFinite(point.timeMs) ? ((point.timeMs - firstMs) / timeSpan) : (index / Math.max(series.length - 1, 1))) * width,
    y: bottom - ((point.value - min) / span) * height,
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  const area = `${path} L ${right} ${bottom} L ${left} ${bottom} Z`;
  const firstTime = shortChartTime(series[0]?.time);
  const midTime = shortChartTime(series[Math.floor(series.length / 2)]?.time);
  const lastTime = shortChartTime(series[series.length - 1]?.time);
  const barWidth = Math.max(1.5, Math.min(5.5, width / series.length - 1));

  return (
    <div className={`home-sparkline tone-${tone}`}>
      <svg viewBox="0 0 100 72" aria-hidden="true" preserveAspectRatio="none">
        <line className="home-sparkline-grid" x1={left} y1={top} x2={right} y2={top} />
        <line className="home-sparkline-grid" x1={left} y1={(top + bottom) / 2} x2={right} y2={(top + bottom) / 2} />
        <line className="home-sparkline-grid" x1={left} y1={bottom} x2={right} y2={bottom} />
        <line className="home-sparkline-axis" x1={left} y1={top} x2={left} y2={bottom} />
        {type === "bar" ? points.map((point, index) => (
          <rect
            className="home-sparkline-bar"
            key={`${point.time}-${index}`}
            x={(point.x - barWidth / 2).toFixed(1)}
            y={point.y.toFixed(1)}
            width={barWidth.toFixed(1)}
            height={Math.max(2, bottom - point.y).toFixed(1)}
            rx="0.8"
          />
        )) : (
          <>
            <path className="home-sparkline-fill" d={area} />
            <path className="home-sparkline-line" d={path} />
          </>
        )}
      </svg>
      <div className="home-sparkline-y">
        {ticks.map((tick, index) => <span key={`${tick}-${index}`}>{tick}</span>)}
      </div>
      <div className="home-sparkline-x">
        <span>{firstTime}</span>
        <span>{midTime}</span>
        <span>{lastTime}</span>
      </div>
    </div>
  );
}

function HomeDualSparkline({ rows = [], primaryKey, secondaryKey, primaryDigits = 1, secondaryDigits = 0 }) {
  const buildSeries = (key) => homeChartSeries(rows, key);
  const primary = buildSeries(primaryKey);
  const secondary = buildSeries(secondaryKey);
  if (primary.length < 2 && secondary.length < 2) return <div className="home-sparkline-empty tone-blue">No trend</div>;

  const top = 8;
  const bottom = 64;
  const left = 16;
  const right = 86;
  const height = bottom - top;
  const width = right - left;
  const scale = (series, digits) => {
    const values = series.map((point) => point.value);
    if (!values.length) return null;
    const minRaw = Math.min(...values);
    const maxRaw = Math.max(...values);
    const padding = Math.max((maxRaw - minRaw) * 0.12, 0.2);
    const min = minRaw - padding;
    const max = maxRaw + padding;
    const span = Math.max(max - min, 1);
    const ticks = [maxRaw, (minRaw + maxRaw) / 2, minRaw].map((value) => numberText(value, digits));
    const timed = series.filter((point) => Number.isFinite(point.timeMs));
    const firstMs = timed[0]?.timeMs;
    const lastMs = timed[timed.length - 1]?.timeMs;
    const timeSpan = Number.isFinite(firstMs) && Number.isFinite(lastMs) ? Math.max(lastMs - firstMs, 1) : null;
    const points = series.map((point, index) => ({
      ...point,
      x: left + (timeSpan && Number.isFinite(point.timeMs) ? ((point.timeMs - firstMs) / timeSpan) : (index / Math.max(series.length - 1, 1))) * width,
      y: bottom - ((point.value - min) / span) * height,
    }));
    return {
      ticks,
      path: points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "),
    };
  };
  const primaryScale = scale(primary, primaryDigits);
  const secondaryScale = scale(secondary, secondaryDigits);
  const times = (primary.length >= secondary.length ? primary : secondary);
  const firstTime = shortChartTime(times[0]?.time);
  const midTime = shortChartTime(times[Math.floor(times.length / 2)]?.time);
  const lastTime = shortChartTime(times[times.length - 1]?.time);

  return (
    <div className="home-sparkline home-dual-sparkline">
      <svg viewBox="0 0 100 72" aria-hidden="true" preserveAspectRatio="none">
        <line className="home-sparkline-grid" x1={left} y1={top} x2={right} y2={top} />
        <line className="home-sparkline-grid" x1={left} y1={(top + bottom) / 2} x2={right} y2={(top + bottom) / 2} />
        <line className="home-sparkline-grid" x1={left} y1={bottom} x2={right} y2={bottom} />
        <line className="home-sparkline-axis humidity-axis" x1={left} y1={top} x2={left} y2={bottom} />
        <line className="home-sparkline-axis temperature-axis" x1={right} y1={top} x2={right} y2={bottom} />
        {secondaryScale?.path && <path className="home-sparkline-line humidity-line" d={secondaryScale.path} />}
        {primaryScale?.path && <path className="home-sparkline-line temperature-line" d={primaryScale.path} />}
      </svg>
      <div className="home-sparkline-y humidity-scale">
        {(secondaryScale?.ticks || []).map((tick, index) => <span key={`${tick}-${index}`}>{tick}</span>)}
      </div>
      <div className="home-sparkline-y temperature-scale">
        {(primaryScale?.ticks || []).map((tick, index) => <span key={`${tick}-${index}`}>{tick}</span>)}
      </div>
      <div className="home-sparkline-x">
        <span>{firstTime}</span>
        <span>{midTime}</span>
        <span>{lastTime}</span>
      </div>
    </div>
  );
}

function InlineTempSparkline({ rows = [] }) {
  const values = rows
    .map((row) => metricNumber(row, "temperature"))
    .filter((value) => value !== null)
    .slice(-18);
  if (values.length < 2) return <span className="home-inline-sparkline empty" aria-hidden="true" />;
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = Math.max(max - min, 0.5);
  const points = values.map((value, index) => ({
    x: 2 + (index / Math.max(values.length - 1, 1)) * 56,
    y: 20 - ((value - min) / span) * 16,
  }));
  const path = points.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" ");
  return (
    <svg className="home-inline-sparkline" viewBox="0 0 60 24" aria-hidden="true" preserveAspectRatio="none">
      <path d={path} />
    </svg>
  );
}

function windDirectionLabel(degrees) {
  const value = Number(degrees);
  if (!Number.isFinite(value)) return "-";
  const labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return labels[Math.round((((value % 360) + 360) % 360) / 45) % 8];
}

function weatherWindDegrees(row = {}) {
  const direct = metricNumber(row, "wind_deg");
  if (direct !== null) return direct;
  const raw = row.raw || {};
  return Number(raw?.current?.wind?.deg ?? raw?.payload?.current?.wind_deg ?? raw?.current?.wind_deg ?? raw?.wind?.deg ?? NaN);
}

function metersPerSecondToKmh(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number * 3.6 : null;
}

function weatherDescription(row = {}) {
  const raw = row.raw || {};
  const weather = raw?.current?.weather || raw?.payload?.current?.weather || raw?.weather || [];
  const first = Array.isArray(weather) ? weather[0] : weather;
  return first?.description || first?.main || (metricNumber(row, "rain_mm") > 0 ? "rain" : "clear");
}

function weatherDailyMin(row = {}) {
  const raw = row.raw || {};
  const value = raw?.daily?.[0]?.temp?.min
    ?? raw?.payload?.daily?.[0]?.temp?.min
    ?? raw?.forecast?.daily?.[0]?.temp?.min;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function pressureDeltaSummary(rows = []) {
  const series = rows
    .map((row) => ({
      value: metricNumber(row, "pressure_hpa"),
      time: new Date(row?.ts || row?.created_at || row?.day || "").getTime(),
    }))
    .filter((point) => point.value !== null && Number.isFinite(point.time))
    .sort((a, b) => a.time - b.time);
  const latest = series[series.length - 1];
  if (!latest) return "";
  const labels = [1, 3, 6].map((hours) => {
    const target = latest.time - hours * 60 * 60 * 1000;
    const previous = series.reduce((best, point) => {
      if (point.time > latest.time || point.time > target + 45 * 60 * 1000) return best;
      if (!best) return point;
      return Math.abs(point.time - target) < Math.abs(best.time - target) ? point : best;
    }, null);
    return previous ? `${hours}h ${signedNumberText(latest.value - previous.value, 1)}` : `${hours}h -`;
  });
  return `${labels.join(" | ")} hPa`;
}

function HomeStatusCard({ title, value, meta, description, icon: Icon = Activity, active = false, tone = "blue" }) {
  return (
    <article className={`home-status-card ${active ? "active" : ""} tone-${tone}`}>
      <div className="home-status-icon"><Icon size={20} aria-hidden="true" /></div>
      <div>
        <span>{title}</span>
        <strong>{value || "-"}</strong>
        <small>{description || meta || "-"}</small>
        <em>{meta || "-"}</em>
      </div>
    </article>
  );
}

function UserStatusTiles({ irrigation, weather, localSensors = [] }) {
  const [x10State, setX10State] = useState(null);
  const [climateState, setClimateState] = useState(null);
  const [error, setError] = useState("");

  async function loadStatuses() {
    try {
      const [x10, climate] = await Promise.all([
        api("/api/context/robot"),
        api("/api/context/climate"),
      ]);
      setX10State(x10);
      setClimateState(climate);
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadStatuses();
    const id = window.setInterval(loadStatuses, 5000);
    return () => window.clearInterval(id);
  }, []);

  const irrigationStatus = irrigationUserStatus(irrigation);
  const x10Status = x10UserStatus(x10State);
  const climateStatus = climateUserStatus(climateState);
  const irrigationSensors = homeSensorSnapshot(irrigation);
  const yardSensor = findYardSensor(localSensors);
  const yardTemperature = metricNumber(yardSensor, "latest_temperature");
  const latestWeather = weather?.latest || {};
  const owmTemp = metricNumber(latestWeather, "temperature_c");
  const owmRain = metricNumber(latestWeather, "rain_mm");
  const weatherText = yardTemperature !== null ? unitValue(yardTemperature, "C", 1) : irrigationSensors.temperature.value !== null ? unitValue(irrigationSensors.temperature.value, "C", 1) : owmTemp !== null ? unitValue(owmTemp, "C", 1) : "-";
  const rainText = irrigationSensors.rain.value !== null ? `${unitValue(irrigationSensors.rain.value, "mm", 1)} rain` : owmRain !== null ? `${unitValue(owmRain, "mm", 1)} OWM rain` : "weather data";
  const weatherMeta = yardTemperature !== null ? `yard ${dateText(yardSensor.latest_ts)}` : irrigationSensors.temperature.row ? `yard ${dateText(irrigationSensors.temperature.row.ts)}` : latestWeather.ts ? `OWM ${dateText(latestWeather.ts)}` : "waiting for sample";

  return (
    <section className="home-status-grid">
      <HomeStatusCard title="Irrigation" value={irrigationStatus.value} description="Timed garden valve" meta={irrigationStatus.meta} icon={Droplets} active={irrigationStatus.active} tone="green" />
      <HomeStatusCard title="Robot" value={x10Status.value} description="Xiaomi X10 cleaner" meta={error && !x10State ? error : x10Status.meta} icon={Home} active={x10Status.active} tone="orange" />
      <HomeStatusCard title="Climate" value={climateStatus.value} description={climateStatus.description} meta={error && !climateState ? error : climateStatus.meta} icon={Wind} active={climateStatus.active} tone="blue" />
      <HomeStatusCard title="Weather" value={weatherText} description={rainText} meta={weatherMeta} icon={CloudRain} active={(irrigationSensors.rain.value ?? owmRain ?? 0) > 0} tone="sky" />
    </section>
  );
}

function UserManualWatering({ irrigation, reload, setToast }) {
  const [duration, setDuration] = useState(20);
  const [busy, setBusy] = useState("");

  async function startManual() {
    setBusy("start");
    try {
      await api("/api/irrigation/manual/start", {
        method: "POST",
        body: JSON.stringify({ duration_minutes: Number(duration || 20), started_by: "user-dashboard" }),
      });
      setToast("Watering started");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function stopManual() {
    setBusy("stop");
    try {
      await api("/api/irrigation/manual/stop", { method: "POST", body: "{}" });
      setToast("Watering stop sent");
      await reload();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <article className="home-panel home-panel-water user-control-panel">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Droplets size={20} aria-hidden="true" /></div>
        <div>
          <h2>Irrigation</h2>
          <span>manual start with timed stop</span>
        </div>
      </div>
      <div className="home-action-row">
        <label className="home-field">
          Duration, min
          <input
            type="number"
            min="1"
            max={irrigation?.manual_max_minutes || 180}
            value={duration}
            onChange={(event) => setDuration(event.target.value)}
          />
        </label>
        <IconButton icon={Play} className="home-primary" disabled={Boolean(busy)} onClick={startManual}>{busy === "start" ? "Starting" : "Open Valve"}</IconButton>
        <IconButton icon={Square} disabled={Boolean(busy)} className="secondary home-secondary" onClick={stopManual}>{busy === "stop" ? "Stopping" : "Close Valve"}</IconButton>
      </div>
    </article>
  );
}

function UserX10QuickSchedule({ setToast }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [quickClean, setQuickClean] = useState({
    delay_min: 2,
    map_id: "",
    mode: "2",
    suction: "3",
    water_level: "2",
    segments: [],
  });

  async function loadX10(silent = false) {
    if (!silent) setLoading(true);
    try {
      setState(await api("/api/context/robot"));
    } catch (err) {
      setToast(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadX10();
    const id = window.setInterval(() => loadX10(true), 5000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/robot"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function publishX10(command, payload = "1") {
    return api("/api/xiaomi-x10/command", {
      method: "POST",
      body: JSON.stringify({ command, payload }),
    });
  }

  function updateQuickClean(key, value) {
    setQuickClean((current) => ({ ...current, [key]: value }));
  }

  function toggleQuickRoom(segmentId, checked) {
    const value = Number(segmentId);
    setQuickClean((current) => ({
      ...current,
      segments: checked
        ? [...new Set([...current.segments, value])]
        : current.segments.filter((roomId) => Number(roomId) !== value),
    }));
  }

  async function scheduleQuickCleaning() {
    const mapId = Number(quickClean.map_id || state?.map?.current_id || 3);
    const segments = [...new Set(parseSegmentList(quickClean.segments))];
    if (!segments.length) {
      setToast("Select room for quick clean");
      return;
    }
    const delayMin = Math.max(1, Number(quickClean.delay_min) || 2);
    setBusy("quick_clean");
    try {
      await publishX10("schedule_clean", {
        map_id: mapId,
        segments,
        start_time: timeAfterMinutes(delayMin),
        days: "0000000",
        enabled: 1,
        mode: Number(quickClean.mode || state?.clean_mode || 2),
        suction: Number(quickClean.suction || state?.suction || 3),
        clean_param: Number(quickClean.water_level || state?.water_level || 2),
      });
      setToast(`Quick clean scheduled in ${delayMin} min`);
      window.setTimeout(() => loadX10(true), 900);
      window.setTimeout(() => loadX10(true), 2500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  const rooms = (state?.map?.rooms || []).filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const x10Maps = state?.catalog?.maps?.length ? state.catalog.maps : [{ map_id: state?.map?.current_id || 3, name: state?.map?.current_name || "Current map", has_room_data: true }];
  const roomsByMap = state?.catalog?.rooms_by_map || {};
  const roomsForMap = (mapId) => (roomsByMap[String(mapId)] || (Number(mapId) === Number(state?.map?.current_id) ? rooms : []))
    .filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const quickMapId = Number(quickClean.map_id || state?.map?.current_id || 3);
  const quickRooms = roomsForMap(quickMapId);
  const quickSelectedSegments = [...new Set(parseSegmentList(quickClean.segments))];

  return (
    <article className="home-panel home-panel-x10 user-control-panel">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Home size={20} aria-hidden="true" /></div>
        <div>
          <h2>X10 Cleaning</h2>
          <span>{loading && !state ? "loading" : `starts ${timeAfterMinutes(quickClean.delay_min)}`}</span>
        </div>
      </div>
      <div className="home-x10-grid">
        <label className="home-field">
          Delay
          <input type="number" min="1" max="15" step="1" value={quickClean.delay_min} onChange={(event) => updateQuickClean("delay_min", event.target.value)} />
        </label>
        <label className="home-field">
          Map
          <select value={quickMapId} onChange={(event) => setQuickClean((current) => ({ ...current, map_id: Number(event.target.value), segments: [] }))}>
            {x10Maps.map((mapItem) => <option key={mapItem.map_id} value={mapItem.map_id}>{mapItem.name}</option>)}
          </select>
        </label>
        <IconButton icon={Clock} className="home-primary" disabled={Boolean(busy) || !quickSelectedSegments.length} onClick={scheduleQuickCleaning}>{busy === "quick_clean" ? "Scheduling" : "Schedule"}</IconButton>
      </div>
      <div className="home-room-picks">
        {quickRooms.length ? quickRooms.map((room) => (
          <label className="check" key={`user-quick-${quickMapId}-${room.segment_id}`}>
            <input
              type="checkbox"
              checked={quickClean.segments.map(Number).includes(Number(room.segment_id))}
              onChange={(event) => toggleQuickRoom(room.segment_id, event.target.checked)}
            />
            {room.name}
          </label>
        )) : <span className="muted-text">No room data</span>}
      </div>
      <details className="home-advanced">
        <summary>Cleaning settings</summary>
        <div className="home-advanced-grid">
          <label className="home-field">
            Mode
            <select value={quickClean.mode} onChange={(event) => updateQuickClean("mode", event.target.value)}>
              {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="home-field">
            Vacuum
            <select value={quickClean.suction} onChange={(event) => updateQuickClean("suction", event.target.value)}>
              {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
          <label className="home-field">
            Water
            <select value={quickClean.water_level} onChange={(event) => updateQuickClean("water_level", event.target.value)}>
              {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
            </select>
          </label>
        </div>
      </details>
    </article>
  );
}

function UserClimateQuickControl({ setToast }) {
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(() => climateDraftFromState(null));
  const [draftDirty, setDraftDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  async function loadClimate(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await api("/api/context/climate");
      setState(data);
    } catch (err) {
      setToast(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadClimate();
    const id = window.setInterval(() => loadClimate(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/climate"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  useEffect(() => {
    if (!state || draftDirty || busy) return;
    setDraft(climateDraftFromState(state));
  }, [state, draftDirty, busy]);

  function updateDraft(key, value) {
    setDraftDirty(true);
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function sendClimate(payload, busyKey = "command", message = "Climate command sent") {
    setBusy(busyKey);
    try {
      const data = await api("/api/climate/gree/command", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const nextState = data.state || data;
      setState(nextState);
      setDraft(climateDraftFromState(nextState));
      setDraftDirty(false);
      setToast(message);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function applyDraft() {
    await sendClimate({
      power: draft.power,
      mode: draft.mode,
      target_temperature: Number(draft.target_temperature),
      fan_speed: draft.fan_speed,
    }, "apply", "Climate settings applied");
  }

  return (
    <article className="home-panel home-panel-climate user-control-panel">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Wind size={20} aria-hidden="true" /></div>
        <div>
          <h2>Climate</h2>
          <span>{loading && !state ? "loading" : busy ? `sending ${busy}` : state?.power || "ready"}</span>
        </div>
      </div>
      <div className="home-climate-buttons">
        <IconButton icon={Power} className="home-primary" disabled={Boolean(busy)} onClick={() => sendClimate({ power: "on" }, "power_on", "Climate turned on")}>On</IconButton>
        <IconButton icon={Square} className="secondary home-secondary" disabled={Boolean(busy)} onClick={() => sendClimate({ power: "off" }, "power_off", "Climate turned off")}>Off</IconButton>
      </div>
      <div className="home-climate-form">
        <label className="home-field">
          Power
          <select value={draft.power} onChange={(event) => updateDraft("power", event.target.value)}>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
        <label className="home-field">
          Mode
          <select value={draft.mode} onChange={(event) => updateDraft("mode", event.target.value)}>
            {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <label className="home-field">
          Target
          <input type="number" min="8" max="30" step="1" value={draft.target_temperature} onChange={(event) => updateDraft("target_temperature", event.target.value)} />
        </label>
        <label className="home-field">
          Fan
          <select value={draft.fan_speed} onChange={(event) => updateDraft("fan_speed", event.target.value)}>
            {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
          </select>
        </label>
        <IconButton icon={Save} className="home-primary" disabled={Boolean(busy)} onClick={applyDraft}>{busy === "apply" ? "Applying" : "Apply"}</IconButton>
      </div>
    </article>
  );
}

function UserPowerWallDevice({ setToast }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [historyByEntity, setHistoryByEntity] = useState({});

  async function loadPowerWall(silent = false) {
    if (!silent) setLoading(true);
    try {
      setState(await api("/api/context/power_wall"));
    } catch (err) {
      setToast(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadPowerWall();
    const id = window.setInterval(() => loadPowerWall(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/power_wall"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function setPowerWallSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    try {
      await api("/api/power-wall/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      setToast(value ? "Marten deterrent turned on" : "Marten deterrent turned off");
      window.setTimeout(() => loadPowerWall(true), 1200);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setPowerWallAlwaysOn(device, alwaysOn) {
    const busyKey = `${device.entity_id}:always-on`;
    setPolicyBusy(busyKey);
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, always_on: alwaysOn }),
      });
      await loadPowerWall(true);
    } catch (err) {
      setToast(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  async function loadPowerWallHistory(entityId) {
    if (!entityId || historyByEntity[entityId]?.data || historyByEntity[entityId]?.loading) return;
    setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: true, error: "", data: null } }));
    try {
      const data = await api(`/api/power-wall/history?entity_id=${encodeURIComponent(entityId)}`);
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: "", data } }));
    } catch (err) {
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: err.message, data: null } }));
    }
  }

  const device = selectedProcessDevice(
    state,
    "marten_power_socket",
    (devices) => devices.find((item) => String(item.entity_name || "").toLowerCase().includes("nyestriaszt"))
  );
  const status = device?.status || "unknown";
  const isDegraded = status === "degraded";
  const isOffline = status === "offline";
  const switchState = powerWallValue(device, ["switch_state", "state"]);
  const switchStateOn = switchOn(switchState);
  const canCommand = device && ["zigbee", "tuya"].includes(device.platform) && status === "online";
  const powerValue = powerWallValue(device, ["power_w", "power"]);
  const currentValue = powerWallValue(device, ["current_a", "current"]);
  const voltageValue = powerWallValue(device, ["voltage_v", "mains_voltage_v"]);
  const energyValue = powerWallValue(device, ["energy_kwh"]);
  const lagValue = powerWallValue(device, ["lag_sec"]);
  const alwaysOn = Boolean(device?.always_on);

  if (loading && !device) {
    return (
      <article className="home-panel home-panel-guard user-control-panel home-power-wall-device">
        <div className="home-panel-head">
          <div className="home-panel-icon"><Power size={20} aria-hidden="true" /></div>
          <h2>Marten Deterrent</h2>
          <span>loading</span>
        </div>
      </article>
    );
  }

  if (!device) {
    return (
      <article className="home-panel home-panel-guard user-control-panel home-power-wall-device warn">
        <div className="home-panel-head">
          <div className="home-panel-icon"><Power size={20} aria-hidden="true" /></div>
          <h2>Marten Deterrent</h2>
          <span>device not found</span>
        </div>
      </article>
    );
  }

  return (
    <article className={`home-panel home-panel-guard user-control-panel home-power-wall-device ${alwaysOn ? "always-on" : ""} ${isOffline ? "bad" : isDegraded ? "warn" : ""}`}>
      <div className="home-panel-head">
        <div className="home-panel-icon"><Power size={20} aria-hidden="true" /></div>
        <div>
          <h2>{displayEntityName(device.entity_name)}</h2>
          <span>{device.platform} | {status}</span>
        </div>
      </div>
      <div className="home-device-state">
        <strong>{switchStateOn === null ? "-" : switchStateOn ? "ON" : "OFF"}</strong>
        <span>{powerWallMetricText(powerValue, " W", 1)} | seen {dateText(device.last_seen_ts)}</span>
      </div>
      <label className="home-check" title="Keep this socket switched on">
        <input
          type="checkbox"
          checked={alwaysOn}
          disabled={policyBusy === `${device.entity_id}:always-on`}
          onChange={(event) => setPowerWallAlwaysOn(device, event.target.checked)}
        />
        <span>Always on</span>
      </label>
      {["zigbee", "tuya"].includes(device.platform) && (
        <div className="home-split-actions">
          <IconButton
            icon={Power}
            className={switchStateOn === true ? "secondary home-secondary" : "home-primary"}
            disabled={!canCommand || Boolean(busy)}
            onClick={() => setPowerWallSwitch(device, true)}
          >
            {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
          </IconButton>
          <IconButton
            icon={Power}
            className={switchStateOn === false ? "secondary home-secondary" : "home-primary"}
            disabled={!canCommand || Boolean(busy)}
            onClick={() => setPowerWallSwitch(device, false)}
          >
            {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
          </IconButton>
        </div>
      )}
      <details className="home-advanced">
        <summary>Details</summary>
        <div className="tuya-metrics">
          <div><span>Switch</span><strong>{tuyaValueText(switchState)}</strong></div>
          <PowerWallPowerMetric
            device={device}
            value={powerValue}
            history={historyByEntity[device.entity_id]}
            loadHistory={loadPowerWallHistory}
          />
          <div><span>Voltage</span><strong>{powerWallMetricText(voltageValue, " V", 1)}</strong></div>
          <div><span>Current</span><strong>{powerWallMetricText(currentValue, " A", 3)}</strong></div>
          <div><span>Energy</span><strong>{powerWallMetricText(energyValue, " kWh", 2)}</strong></div>
          <div><span>Lag</span><strong>{powerWallMetricText(lagValue, " s", 0)}</strong></div>
        </div>
      </details>
    </article>
  );
}

function NyestriasztoScheduler({ setToast }) {
  const runSegmentLimit = 15;
  const [state, setState] = useState(null);
  const [sessions, setSessions] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [draft, setDraft] = useState({
    enabled: false,
    window_start: "20:00",
    window_end: "06:00",
    min_on_minutes: 12,
    max_on_minutes: 35,
    min_off_minutes: 20,
    max_off_minutes: 90,
    jitter_minutes: 5,
  });

  const device = selectedProcessDevice(
    state,
    "marten_power_socket",
    (devices) => devices.find((item) => String(item.entity_name || "").toLowerCase().includes("nyestriaszt"))
  );
  const switchState = powerWallValue(device, ["switch_state", "state"]);
  const switchStateOn = switchOn(switchState);
  const powerValue = powerWallValue(device, ["power_w", "power"]);
  const motion = state?.marten_motion || {};
  const motionSensor = motion.sensor;
  const motionState = motion.state || {};
  const motionCurrent = motionState.occupancy?.value ?? motionState.motion?.value ?? motionState.presence?.value;
  const motionActive = switchOn(motionCurrent);
  const motionEvents = motion.events || [];
  const motionSummary = motion.summary || {};
  const motionBattery = motionState.battery?.value;
  const motionLqi = motionState.linkquality?.value;

  function draftFromDevice(nextDevice) {
    if (!nextDevice) return;
    setDraft({
      enabled: Boolean(nextDevice.scheduler_enabled),
      window_start: nextDevice.scheduler_window_start || "20:00",
      window_end: nextDevice.scheduler_window_end || "06:00",
      min_on_minutes: nextDevice.scheduler_min_on_minutes ?? 12,
      max_on_minutes: nextDevice.scheduler_max_on_minutes ?? 35,
      min_off_minutes: nextDevice.scheduler_min_off_minutes ?? 20,
      max_off_minutes: nextDevice.scheduler_max_off_minutes ?? 90,
      jitter_minutes: nextDevice.scheduler_jitter_minutes ?? 5,
    });
  }

  async function loadSessions(entityId) {
    if (!entityId) return;
    const data = await api(`/api/power-wall/scheduler/sessions?entity_id=${encodeURIComponent(entityId)}&limit=${runSegmentLimit}`);
    setSessions((data.sessions || []).slice(0, runSegmentLimit));
  }

  async function loadScheduler(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      const data = await api("/api/context/power_wall");
      setState(data);
      const nextDevice = selectedProcessDevice(
        data,
        "marten_power_socket",
        (devices) => devices.find((item) => String(item.entity_name || "").toLowerCase().includes("nyestriaszt"))
      );
      draftFromDevice(nextDevice);
      await loadSessions(nextDevice?.entity_id);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadScheduler();
    const id = window.setInterval(() => loadScheduler(true), 15000);
    return () => window.clearInterval(id);
  }, []);

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function saveScheduler() {
    if (!device) return;
    setBusy("save");
    setError("");
    try {
      await api("/api/power-wall/scheduler", {
        method: "PUT",
        body: JSON.stringify({
          entity_id: device.entity_id,
          enabled: draft.enabled,
          window_start: draft.window_start,
          window_end: draft.window_end,
          min_on_minutes: draft.min_on_minutes,
          max_on_minutes: draft.max_on_minutes,
          min_off_minutes: draft.min_off_minutes,
          max_off_minutes: draft.max_off_minutes,
          jitter_minutes: draft.jitter_minutes,
        }),
      });
      setToast("Marten deterrent scheduler saved");
      await loadScheduler(true);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  if (loading && !state) {
    return <div className="chart-empty">Loading scheduler...</div>;
  }

  if (!device) {
    return (
      <section className="panel warn">
        <div className="panel-head">
          <h2 className="panel-title"><Bell size={17} aria-hidden="true" /> Marten Deterrent Scheduler</h2>
          <span>device not found</span>
        </div>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Marten Deterrent Scheduler</h2>
          <span>{error || `${device.platform} | ${device.status || "unknown"} | ${draft.enabled ? "enabled" : "disabled"}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadScheduler()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles">
        <Card title="State" value={switchStateOn === null ? "-" : switchStateOn ? "ON" : "OFF"} meta={`seen ${dateText(device.last_seen_ts)}`} icon={Power} tone={switchStateOn ? "warn" : ""} />
        <Card title="Power" value={powerWallMetricText(powerValue, " W", 1)} meta={displayEntityName(device.entity_name)} icon={Gauge} />
        <Card title="Window" value={`${draft.window_start}-${draft.window_end}`} meta={draft.enabled ? "scheduler active" : "scheduler disabled"} icon={Clock} tone={draft.enabled ? "warn" : ""} />
        <Card title="Run Time" value={`${draft.min_on_minutes}-${draft.max_on_minutes} min`} meta={`pause ${draft.min_off_minutes}-${draft.max_off_minutes} min`} icon={CalendarDays} />
      </section>

      <section className="tile-grid stats-tiles nyest-motion-summary">
        <Card
          title="PIR"
          value={motionActive === null ? "-" : motionActive ? "MOTION" : "Clear"}
          meta={motionSensor ? `seen ${dateText(motionSensor.last_seen_ts)}` : motion.error || "sensor not configured"}
          icon={Radio}
          tone={motionActive ? "warn" : ""}
        />
        <Card title="Motion 24h" value={String(motionSummary.motion_24h || 0)} meta={`last ${dateText(motionSummary.last_motion_at)}`} icon={Activity} />
        <Card title="Battery" value={motionBattery === undefined || motionBattery === null ? "-" : unitValue(motionBattery, "%", 0)} meta={motionState.battery_low?.value === true ? "low battery" : "sensor battery"} icon={BatteryCharging} tone={motionState.battery_low?.value === true ? "warn" : ""} />
        <Card title="Signal" value={motionLqi === undefined || motionLqi === null ? "-" : numberText(motionLqi, 0)} meta={motionSensor?.topic_base || "zigbee/0xa4c1386aa4a76dd5"} icon={Radio} />
      </section>

      <section className="panel nyest-scheduler-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Bell size={17} aria-hidden="true" /> Settings</h2>
          <span>{displayEntityName(device.entity_name)}</span>
        </div>
        <div className="nyest-scheduler-grid">
          <label className="check nyest-scheduler-enable">
            <input type="checkbox" checked={draft.enabled} onChange={(event) => updateDraft("enabled", event.target.checked)} />
            Enabled
          </label>
          <label>From<input type="time" value={draft.window_start} onChange={(event) => updateDraft("window_start", event.target.value)} /></label>
          <label>To<input type="time" value={draft.window_end} onChange={(event) => updateDraft("window_end", event.target.value)} /></label>
          <label>Min run<input type="number" min="1" max="1440" value={draft.min_on_minutes} onChange={(event) => updateDraft("min_on_minutes", event.target.value)} /></label>
          <label>Max run<input type="number" min="1" max="1440" value={draft.max_on_minutes} onChange={(event) => updateDraft("max_on_minutes", event.target.value)} /></label>
          <label>Min pause<input type="number" min="1" max="1440" value={draft.min_off_minutes} onChange={(event) => updateDraft("min_off_minutes", event.target.value)} /></label>
          <label>Max pause<input type="number" min="1" max="1440" value={draft.max_off_minutes} onChange={(event) => updateDraft("max_off_minutes", event.target.value)} /></label>
          <label>Jitter<input type="number" min="0" max="240" value={draft.jitter_minutes} onChange={(event) => updateDraft("jitter_minutes", event.target.value)} /></label>
          <IconButton icon={Save} disabled={Boolean(busy)} onClick={saveScheduler}>{busy ? "Saving" : "Save"}</IconButton>
        </div>
      </section>

      <section className="panel nyest-log-panel">
        <div className="panel-head">
          <h2 className="panel-title"><CalendarDays size={17} aria-hidden="true" /> Active Run Segments</h2>
          <span>{sessions.length}/{runSegmentLimit} row</span>
        </div>
        <div className="nyest-scheduler-table-wrap">
          <table className="nyest-scheduler-table">
            <thead>
              <tr>
                <th>Status</th>
                <th>Start</th>
                <th>End</th>
                <th>Run</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {sessions.length ? sessions.map((row) => (
                <tr key={row.id}>
                  <td>{row.status}</td>
                  <td>{dateText(row.actual_start_at || row.planned_start_at)}</td>
                  <td>{dateText(row.actual_end_at || row.planned_end_at)}</td>
                  <td>{row.duration_minutes ? `${row.duration_minutes} min` : "-"}</td>
                  <td>{row.error || "-"}</td>
                </tr>
              )) : (
                <tr><td colSpan="5">No scheduled runs yet</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section className="panel nyest-log-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Radio size={17} aria-hidden="true" /> Motion Log</h2>
          <span>{motionEvents.length} row</span>
        </div>
        <Table
          rows={motionEvents.map((row, index) => ({ ...row, id: `${row.ts}-${index}` }))}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "key", label: "Metric" },
            { key: "motion", label: "State", render: (row) => row.motion ? <span className="status-pill warn">motion</span> : <span className="status-pill ok">clear</span> },
            { key: "source", label: "Source", render: () => displayEntityName(motionSensor?.entity_name || "Nyestriasztó PIR") },
          ]}
        />
      </section>
    </>
  );
}

function HomeSensorCard({ title, value, meta, unit, digits = 1, icon: Icon = Activity, tone = "blue", rows = [], valueKey, chartType = "line", secondary = null }) {
  const number = value === null || value === undefined ? null : Number(value);
  const secondaryNumber = secondary?.value === null || secondary?.value === undefined ? null : Number(secondary?.value);
  const SecondaryIcon = secondary?.icon || Activity;
  return (
    <article className={`home-sensor-card tone-${tone}`}>
      <div className="home-sensor-top">
        <div className="home-panel-icon"><Icon size={18} aria-hidden="true" /></div>
        <span>{title}</span>
      </div>
      <div className="home-sensor-values">
        <strong>{number === null || !Number.isFinite(number) ? "-" : unitValue(number, unit, digits)}</strong>
        {secondary && (
          <span>
            <SecondaryIcon size={14} aria-hidden="true" />
            {secondaryNumber === null || !Number.isFinite(secondaryNumber) ? "-" : unitValue(secondaryNumber, secondary.unit, secondary.digits ?? 0)}
          </span>
        )}
      </div>
      {secondary?.overlayChart ? (
        <HomeDualSparkline rows={secondary.rows || rows} primaryKey={valueKey} secondaryKey={secondary.valueKey} primaryDigits={digits} secondaryDigits={secondary.digits ?? 0} />
      ) : (
        <HomeSparkline rows={rows} valueKey={valueKey} tone={tone} type={chartType} digits={digits} />
      )}
      {secondary && !secondary.overlayChart && (
        <div className="home-sensor-secondary-chart">
          <span>{secondary.label}</span>
          <HomeSparkline rows={secondary.rows || rows} valueKey={secondary.valueKey} tone={secondary.tone || "green"} type={secondary.chartType || "line"} digits={secondary.digits ?? 0} />
        </div>
      )}
      <small>{meta || "last update pending"}</small>
    </article>
  );
}

function HomeIrrigationFeedbackCard({ pilotState, pilotError = "", irrigation }) {
  const latest = irrigation?.latest || [];
  const recommendation = pilotState?.recommendation || {};
  const inputs = recommendation.details?.inputs || {};
  const rainSensorWet = inputs.RainSensorWet === true ? "WET" : inputs.RainSensorWet === false ? "DRY" : "-";
  const soilRows = irrigation?.soil_moisture_24h || [];
  const soilSensors = latest
    .filter((row) => String(row.key || "").toLowerCase() === "soil_moisture")
    .sort((a, b) => String(a.entity_name || "").localeCompare(String(b.entity_name || ""), "en"));
  const primarySoil = soilSensors.find((row) => String(row.entity_name || "").toLowerCase().includes("02")) || soilSensors[0] || null;
  const primarySoilName = primarySoil?.entity_name || "Soil";
  const primaryRows = soilRows.filter((row) => row.entity_name === primarySoilName);
  const soilValue = metricNumber(primarySoil, "v_num");
  const forecastMinutes = metricNumber(recommendation, "final_duration");
  const footerMeta = pilotError || (primarySoil?.ts ? `soil ${dateText(primarySoil.ts)}` : "soil trend");

  return (
    <article className="home-sensor-card home-irrigation-feedback-card tone-green">
      <div className="home-sensor-top">
        <div className="home-panel-icon"><Droplets size={18} aria-hidden="true" /></div>
        <span>Irrigation Feedback</span>
      </div>
      <div className="home-irrigation-feedback-values">
        <div>
          <span>Forecast</span>
          <strong>{forecastMinutes === null ? "-" : unitValue(forecastMinutes, "min", 0)}</strong>
        </div>
        <div>
          <span>Rain</span>
          <strong>{rainSensorWet}</strong>
        </div>
        <div>
          <span>Soil</span>
          <strong>{soilValue === null ? "-" : unitValue(soilValue, "%", 0)}</strong>
        </div>
      </div>
      <HomeSparkline rows={primaryRows} valueKey="soil_moisture" tone="green" digits={0} />
      <small>{footerMeta}</small>
    </article>
  );
}

function HomeSensorGrid({ irrigation, weather, localSensors = [] }) {
  const [pilotState, setPilotState] = useState(null);
  const [pilotError, setPilotError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadPilotState() {
      try {
        const data = await api("/api/context/irrigation_pilot");
        if (!cancelled) {
          setPilotState(data);
          setPilotError("");
        }
      } catch (err) {
        if (!cancelled) setPilotError(err.message);
      }
    }
    loadPilotState();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") loadPilotState();
    }, 60000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const irrigationSensors = homeSensorSnapshot(irrigation);
  const latestWeather = weather?.latest || {};
  const weatherRows = weather?.history_24h || [];
  const weatherRowsKmh = weatherRows.map((row) => ({
    ...row,
    wind_speed_kmh: metersPerSecondToKmh(row?.wind_speed_mps),
  }));
  const yardSensor = findYardSensor(localSensors);
  const yardRows = yardSensor?.samples || [];
  const yardTemperature = metricNumber(yardSensor, "latest_temperature");
  const yardHumidity = metricNumber(yardSensor, "latest_humidity");
  const yardTs = yardSensor?.latest_ts;
  const pressure = metricNumber(latestWeather, "pressure_hpa");
  const pressureMeta = pressureDeltaSummary(weatherRows) || (latestWeather.ts ? `OpenWeather | ${dateText(latestWeather.ts)}` : "no OWM pressure sample");
  const wind = metersPerSecondToKmh(metricNumber(latestWeather, "wind_speed_mps"));
  const windDeg = weatherWindDegrees(latestWeather);
  const windDirection = windDirectionLabel(windDeg);
  const windMeta = Number.isFinite(windDeg) ? `OWM direction ${windDirection} ${numberText(windDeg, 0)} deg` : latestWeather.ts ? `OpenWeather | ${dateText(latestWeather.ts)}` : "no wind sample";
  return (
    <section className="home-sensor-grid">
      <HomeSensorCard
        title="Yard Temperature"
        value={yardTemperature ?? irrigationSensors.temperature.value}
        unit="C"
        digits={1}
        icon={Thermometer}
        tone="blue"
        meta={yardTemperature !== null ? `local sensor | ${dateText(yardTs)}` : irrigationSensors.temperature.row ? `fallback | ${dateText(irrigationSensors.temperature.row.ts)}` : "no yard temperature sample"}
        rows={yardRows}
        valueKey="temperature"
        secondary={{
          label: "Humidity",
          value: yardHumidity ?? irrigationSensors.humidity.value,
          unit: "%",
          digits: 0,
          icon: Droplets,
          tone: "green",
          rows: yardRows,
          valueKey: "humidity",
          overlayChart: true,
        }}
      />
      <HomeIrrigationFeedbackCard pilotState={pilotState} pilotError={pilotError} irrigation={irrigation} />
      <HomeSensorCard title="OWM Pressure" value={pressure} unit="hPa" digits={0} icon={Gauge} tone="purple" meta={pressureMeta} rows={weatherRows} valueKey="pressure_hpa" />
      <HomeSensorCard title={`Wind ${windDirection}`} value={wind} unit="km/h" digits={1} icon={Compass} tone="sky" meta={windMeta} rows={weatherRowsKmh} valueKey="wind_speed_kmh" chartType="bar" />
    </section>
  );
}

function OpeningSensorIcons({ sensors = [] }) {
  if (!sensors.length) return <span className="home-window-icons empty" aria-label="Nincs ablakérzékelő">-</span>;
  const orderedSensors = sensors.slice().sort((a, b) => {
    const posA = Number.isFinite(Number(a.room_position)) ? Number(a.room_position) : Number.POSITIVE_INFINITY;
    const posB = Number.isFinite(Number(b.room_position)) ? Number(b.room_position) : Number.POSITIVE_INFINITY;
    if (posA !== posB) return posA - posB;
    return String(a.opening_label || a.entity_name || "").localeCompare(String(b.opening_label || b.entity_name || ""), "hu");
  });
  return (
    <span className="home-window-icons" aria-label={`${orderedSensors.length} ablakérzékelő`}>
      {orderedSensors.map((sensor) => {
        const closed = sensor.contact === true;
        const alert = sensor.battery_low === true || sensor.contact == null || sensor.rain_alert_active === true;
        const openingType = sensor.opening_type === "door" ? "door" : "window";
        const label = openingType === "door" ? "Ajtó" : "Ablak";
        const name = sensor.opening_label || sensor.entity_name || label;
        const mosquito = sensor.has_mosquito_net ? " | szúnyogháló" : "";
        const rainAlert = sensor.rain_alert_enabled ? " | eső riasztás előkészítve" : "";
        const alertText = alert ? ` | ${sensor.rain_alert_active ? "eső riasztás" : sensor.battery_low ? "szenzor gond: alacsony elem" : "szenzor gond: nincs kontakt adat"}` : "";
        const position = sensor.room_position == null ? "" : ` | #${sensor.room_position}`;
        const title = `${name}: ${closed ? "csukva" : "nyitva"}${position}${mosquito}${rainAlert}${alertText} | ${sensor.battery == null ? "elem -" : `elem ${numberText(sensor.battery, 0)}%`} | ${dateText(sensor.latest_ts || sensor.contact_ts)}`;
        return (
          <span className={`home-opening-icon ${openingType} ${alert ? "alert" : closed ? "closed" : "open"}`} title={title} key={sensor.entity_id || sensor.entity_name} aria-label={title}>
            <span className="opening-cross" aria-hidden="true" />
            <span className="opening-door-window" aria-hidden="true" />
            <span className="opening-handle" aria-hidden="true" />
          </span>
        );
      })}
    </span>
  );
}

function HomeWeatherPanel({ localSensors = [], openingSensors = [] }) {
  const indoorSensors = localSensors
    .filter((sensor) => {
      const name = String(sensor.entity_name || sensor.device_name || "").toLowerCase();
      return !name.includes("udvar")
        && !name.includes("yard")
        && !name.includes("moisture")
        && metricNumber(sensor, "latest_temperature") !== null;
    })
    .sort((a, b) => String(a.location || a.entity_name || a.device_name || "").localeCompare(String(b.location || b.entity_name || b.device_name || ""), "hu"));
  const openingByRoom = openingSensorsByRoom(openingSensors);
  const avgTempValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_temperature")).filter((value) => value !== null);
  const avgTemp = avgTempValues.length ? avgTempValues.reduce((sum, value) => sum + value, 0) / avgTempValues.length : null;
  return (
    <article className="home-side-card home-weather-card home-thermo-card tone-blue">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Thermometer size={20} aria-hidden="true" /></div>
        <div>
          <h2>Indoor Thermometers</h2>
          <span>{indoorSensors.length ? `${indoorSensors.length} indoor sensors | average ${unitValue(avgTemp, "C", 1)}` : "no indoor thermometer data"}</span>
        </div>
      </div>
      <div className="home-thermo-list">
        {indoorSensors.length ? indoorSensors.map((sensor) => {
          const name = roomDisplayName(sensor.location || sensor.entity_name || sensor.device_name || "Szenzor");
          const roomOpenings = openingByRoom.get(roomKey(sensor.location || sensor.entity_name || sensor.device_name)) || [];
          const temp = metricNumber(sensor, "latest_temperature");
          const humidity = metricNumber(sensor, "latest_humidity");
          return (
            <div className="home-thermo-row" key={sensor.entity_id || name}>
              <Thermometer size={16} aria-hidden="true" />
              <strong>{name}</strong>
              <OpeningSensorIcons sensors={roomOpenings} />
              <InlineTempSparkline rows={sensor.samples || []} />
              <span>{unitValue(temp, "C", 1)}</span>
              <small>{humidity === null ? dateText(sensor.latest_ts) : `${unitValue(humidity, "%", 0)} | ${dateText(sensor.latest_ts)}`}</small>
            </div>
          );
        }) : (
          <div className="home-thermo-empty">No indoor thermometer data available.</div>
        )}
      </div>
    </article>
  );
}

function HomeRecentEvents({ irrigation }) {
  const [x10State, setX10State] = useState(null);
  const [climateState, setClimateState] = useState(null);
  const irrigationStatus = irrigationUserStatus(irrigation);
  const latest = irrigation.latest || [];
  const newest = latest.slice().sort((a, b) => new Date(b.ts || 0) - new Date(a.ts || 0))[0];
  const nextSchedule = nextActiveSchedule(irrigation.schedules || []);
  const latestSession = (irrigation.session_stats || irrigation.sessions || [])[0] || null;
  const sessionTime = firstTimestamp(latestSession);
  const x10Plan = roomCleanPlan(x10State?.room_clean_status, Date.now());
  const climateUpdatedAt = climateState?.updated_at || climateState?.power_meter?.updated_at || climateState?.power_meter?.last_seen_ts;
  useEffect(() => {
    let cancelled = false;
    async function loadEventSources() {
      try {
        const [x10, climate] = await Promise.all([
          api("/api/context/robot"),
          api("/api/context/climate"),
        ]);
        if (!cancelled) {
          setX10State(x10);
          setClimateState(climate);
        }
      } catch {
        if (!cancelled) {
          setX10State(null);
          setClimateState(null);
        }
      }
    }
    loadEventSources();
    const id = window.setInterval(loadEventSources, 30000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const upcomingEvents = [
    {
      icon: Droplets,
      title: irrigationStatus.active ? "Watering stop scheduled" : "Next irrigation",
      tone: "green",
      time: irrigationStatus.active ? "soon" : shortTimeText(nextSchedule?.at),
    },
    {
      icon: Home,
      title: x10Plan?.targetMs ? "Robot cleaning scheduled" : "Robot schedule watch",
      tone: "orange",
      time: x10Plan?.targetMs ? shortTimeText(x10Plan.targetMs) : "--:--",
    },
  ];
  const pastEvents = [
    { icon: Droplets, title: latestSession ? "Irrigation session" : irrigationStatus.active ? "Irrigation started" : "Irrigation standby", tone: "green", time: shortTimeText(sessionTime || newest?.ts) },
    { icon: Home, title: "Robot finished", tone: "orange", time: shortTimeText(x10State?.bridge_last_seen) },
    { icon: Wind, title: "Climate changed", tone: "blue", time: shortTimeText(climateUpdatedAt) },
  ];
  function renderEvent(event, compact = false) {
    const Icon = event.icon;
    return (
      <div className={`home-event-row tone-${event.tone} ${compact ? "upcoming" : ""}`} key={event.title}>
        <div className="home-event-icon"><Icon size={16} aria-hidden="true" /></div>
        <div className="home-event-name">
          <strong>{event.title}</strong>
        </div>
        <time>{event.time}</time>
      </div>
    );
  }
  return (
    <article className="home-side-card home-events-card">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Bell size={20} aria-hidden="true" /></div>
        <div>
          <h2>Recent Events</h2>
          <span>automation timeline</span>
        </div>
      </div>
      <div className="home-event-list">
        <div className="home-event-section-label">Next</div>
        {upcomingEvents.map((event) => renderEvent(event, true))}
        <div className="home-event-divider" />
        <div className="home-event-section-label">Done</div>
        {pastEvents.map((event) => renderEvent(event))}
      </div>
    </article>
  );
}

function HomeSolarPanel() {
  const [solar, setSolar] = useState(null);
  const [error, setError] = useState("");

  async function loadSolar() {
    try {
      const data = await api("/api/context/solar");
      setSolar(data);
      setError("");
    } catch (err) {
      setError(err.message);
      setSolar(null);
    }
  }

  useEffect(() => {
    loadSolar();
    const id = window.setInterval(loadSolar, 30000);
    return () => window.clearInterval(id);
  }, []);

  const values = solar?.state || {};
  const charts = solar?.charts || {};
  const productionRows = charts.production_power_24h || [];
  const dailyRows = charts.production_daily_30d || [];
  const powerNow = solarStateValue(values, "system_power_w") ?? solarStateValue(values, "output_power_w") ?? solarStateValue(values, "plant_output_power_w");
  const todayEnergy = solarStateValue(values, "energy_today_kwh") ?? solarStateValue(values, "plant_energy_today_kwh");
  const todayRow = dailyRows[dailyRows.length - 1] || {};
  const todayKwh = todayEnergy ?? metricNumber(todayRow, "production_kwh");
  const monthValues = dailyRows.map((row) => metricNumber(row, "production_kwh")).filter((value) => value !== null && value > 0);
  const monthAvg = monthValues.length ? monthValues.reduce((sum, value) => sum + value, 0) / monthValues.length : null;
  const monthProduction = solar?.summary?.production_month_kwh ?? null;
  const updatedAt = solar?.summary?.updated_at || solar?.entity?.last_seen_ts;

  return (
    <article className="home-side-card home-solar-card tone-yellow">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Zap size={20} aria-hidden="true" /></div>
        <div>
          <h2>Solar</h2>
          <span>{error || `updated ${dateText(updatedAt)}`}</span>
        </div>
      </div>
      <div className="home-solar-now">
        <strong>{solarMetricText(powerNow, "system_power_w")}</strong>
        <span>current production</span>
      </div>
      <HomeSparkline rows={productionRows} valueKey="avg_production_power_w" tone="yellow" type="line" digits={0} />
      <div className="home-solar-stats">
        <div>
          <span>Today</span>
          <strong>{solarMetricText(todayKwh, "energy_today_kwh")}</strong>
        </div>
        <div>
          <span>30d avg</span>
          <strong>{solarMetricText(monthAvg, "energy_today_kwh")}</strong>
        </div>
        <div>
          <span>Month</span>
          <strong>{solarMetricText(monthProduction, "energy_today_kwh")}</strong>
        </div>
      </div>
    </article>
  );
}

function useHomeWeather() {
  const [weather, setWeather] = useState(null);
  const [localSensors, setLocalSensors] = useState([]);
  const [openingSensors, setOpeningSensors] = useState([]);

  async function loadWeather() {
    try {
      const [pilot, stats] = await Promise.all([
        api("/api/context/irrigation_pilot"),
        api("/api/context/home_statistics?force=1"),
      ]);
      setWeather(pilot.weather || null);
      setLocalSensors(stats.temp_humidity_sensors || []);
      setOpeningSensors(stats.opening_sensors || []);
    } catch {
      setWeather(null);
      setLocalSensors([]);
      setOpeningSensors([]);
    }
  }

  useEffect(() => {
    loadWeather();
    const id = window.setInterval(loadWeather, 5000);
    return () => window.clearInterval(id);
  }, []);

  return { weather, localSensors, openingSensors };
}

function UserDashboard({ snapshot, reload, setToast, variant = "v1" }) {
  const { weather, localSensors, openingSensors } = useHomeWeather();
  const isV2 = variant === "v2";

  if (isV2) {
    return (
      <V2Page className="home-v2">
        <section className="home-hero-band home-v2-hero">
          <div>
            <span>HomeControl OS</span>
            <h2>Daily smart home control</h2>
          </div>
          <div className="home-hero-metrics">
            <b>{snapshot?.devices?.length || 0}</b>
            <span>devices</span>
            <b>{snapshot?.entities?.length || 0}</b>
            <span>entities</span>
          </div>
        </section>
        <UserStatusTiles irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />
        <V2SectionGrid className="home-v2-layout">
          <div className="home-v2-main v2-span-8">
            <section className="user-dashboard home-v2-controls">
              <UserManualWatering irrigation={snapshot?.irrigation || {}} reload={reload} setToast={setToast} />
              <UserX10QuickSchedule setToast={setToast} />
              <UserClimateQuickControl setToast={setToast} />
              <UserPowerWallDevice setToast={setToast} />
            </section>
            <HomeSensorGrid irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />
          </div>
          <aside className="home-v2-side v2-span-4">
            <HomeWeatherPanel localSensors={localSensors} openingSensors={openingSensors} />
            <HomeSolarPanel />
          </aside>
        </V2SectionGrid>
      </V2Page>
    );
  }

  return (
    <section className="home-shell">
      <section className="home-hero-band">
        <div>
          <span>HomeControl OS</span>
          <h2>Premium smart home operations</h2>
        </div>
        <div className="home-hero-metrics">
          <b>{snapshot?.devices?.length || 0}</b>
          <span>devices</span>
          <b>{snapshot?.entities?.length || 0}</b>
          <span>entities</span>
        </div>
      </section>
      <UserStatusTiles irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />
      <section className="home-dashboard-layout">
        <div className="home-main-stack">
          <section className="user-dashboard">
            <UserManualWatering irrigation={snapshot?.irrigation || {}} reload={reload} setToast={setToast} />
            <UserX10QuickSchedule setToast={setToast} />
            <UserClimateQuickControl setToast={setToast} />
            <UserPowerWallDevice setToast={setToast} />
          </section>
          <HomeSensorGrid irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />
        </div>
        <aside className="home-right-panel">
          <HomeWeatherPanel localSensors={localSensors} openingSensors={openingSensors} />
          <HomeSolarPanel />
        </aside>
      </section>
    </section>
  );
}

function MobileStatusButton({ id, title, value, meta, icon: Icon, tone, active, expanded, onClick }) {
  return (
    <button className={`mobile-status-card tone-${tone} ${active ? "active" : ""} ${expanded ? "expanded" : ""}`.trim()} type="button" onClick={() => onClick(id)}>
      <span className="mobile-status-icon"><Icon size={17} aria-hidden="true" /></span>
      <span className="mobile-status-copy">
        <span>{title}</span>
        <strong>{value || "-"}</strong>
        <small>{meta || "-"}</small>
      </span>
      <ChevronRight size={15} aria-hidden="true" />
    </button>
  );
}

function TabletStatusButton({ id, title, value, meta, icon: Icon, tone, active, expanded, onClick }) {
  function handleClick(event) {
    onClick(id);
    event.currentTarget.blur();
  }

  return (
    <button className={`tablet-status-card tone-${tone} ${active ? "active" : ""} ${expanded ? "expanded" : ""}`.trim()} type="button" onClick={handleClick}>
      <span className="tablet-status-icon"><Icon size={19} aria-hidden="true" /></span>
      <span className="tablet-status-copy">
        <span>{title}</span>
        <strong>{value || "-"}</strong>
        <small>{meta || "-"}</small>
      </span>
      <ChevronRight size={16} aria-hidden="true" />
    </button>
  );
}

function TabletClock({ menuOpen, onToggleMenu }) {
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(id);
  }, []);

  async function handleClockPress() {
    try {
      if (!document.fullscreenElement && document.documentElement.requestFullscreen) {
        await document.documentElement.requestFullscreen();
      }
    } catch {
      // Browsers may deny fullscreen outside supported tablet/PWA contexts.
    }
    onToggleMenu();
  }

  return (
    <button
      className={`tablet-clock-card ${menuOpen ? "menu-open" : ""}`.trim()}
      type="button"
      aria-label="Tablet menu"
      aria-expanded={menuOpen}
      onClick={handleClockPress}
    >
      <span className="tablet-clock-date">
        {now.toLocaleDateString("hu-HU", { weekday: "long", month: "long", day: "numeric" })}
      </span>
      <strong>{now.toLocaleTimeString("hu-HU", { hour: "2-digit", minute: "2-digit" })}</strong>
      <small>{now.toLocaleDateString("hu-HU", { year: "numeric" })}</small>
    </button>
  );
}

function useDashboardUnitStatuses(snapshot) {
  const [x10State, setX10State] = useState(null);
  const [climateState, setClimateState] = useState(null);
  const [powerWallState, setPowerWallState] = useState(null);
  const [statusError, setStatusError] = useState("");

  useEffect(() => {
    let cancelled = false;
    async function loadMobileStatuses() {
      try {
        const [x10, climate, powerWall] = await Promise.all([
          api("/api/context/robot"),
          api("/api/context/climate"),
          api("/api/context/power_wall"),
        ]);
        if (!cancelled) {
          setX10State(x10);
          setClimateState(climate);
          setPowerWallState(powerWall);
          setStatusError("");
        }
      } catch (err) {
        if (!cancelled) setStatusError(err.message);
      }
    }
    loadMobileStatuses();
    const id = window.setInterval(loadMobileStatuses, 10000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const irrigationStatus = irrigationUserStatus(snapshot?.irrigation || {});
  const x10Status = x10UserStatus(x10State);
  const climateStatus = climateUserStatus(climateState);
  const martenDevice = selectedProcessDevice(
    powerWallState,
    "marten_power_socket",
    (devices) => devices.find((item) => String(item.entity_name || "").toLowerCase().includes("nyestriaszt"))
  );
  const martenSwitchOn = switchOn(powerWallValue(martenDevice, ["switch_state", "state"]));
  const martenPower = powerWallValue(martenDevice, ["power_w", "power"]);
  const martenStatus = {
    active: Boolean(martenSwitchOn),
    value: martenSwitchOn === null ? "?" : martenSwitchOn ? "ON" : "OFF",
    meta: martenDevice ? `${powerWallMetricText(martenPower, " W", 1)} | ${dateText(martenDevice.last_seen_ts)}` : statusError || "device not found",
  };
  const statusCards = [
    { id: "irrigation", title: "Irrigation", ...irrigationStatus, icon: Droplets, tone: "green" },
    { id: "x10", title: "Robot", ...x10Status, meta: statusError && !x10State ? statusError : x10Status.meta, icon: Home, tone: "orange" },
    { id: "climate", title: "Climate", ...climateStatus, meta: statusError && !climateState ? statusError : climateStatus.compactMeta, icon: Wind, tone: "blue" },
    { id: "marten", title: "Marten", ...martenStatus, icon: Bell, tone: "red" },
  ];
  return { statusCards, statusError, x10State, climateState, powerWallState };
}

function DashboardStatusGrid({ statusCards, expandedUnit = "", onToggle }) {
  return (
    <section className="mobile-status-grid">
      {statusCards.map((card) => (
        <MobileStatusButton
          key={card.id}
          id={card.id}
          title={card.title}
          value={card.value}
          meta={card.meta}
          icon={card.icon}
          tone={card.tone}
          active={card.active}
          expanded={expandedUnit === card.id}
          onClick={onToggle}
        />
      ))}
    </section>
  );
}

function MobileDashboard({ snapshot, reload, setToast }) {
  const { weather, localSensors, openingSensors } = useHomeWeather();
  const [expandedUnit, setExpandedUnit] = useState("");
  const { statusCards } = useDashboardUnitStatuses(snapshot);

  function toggleUnit(unitId) {
    setExpandedUnit((current) => current === unitId ? "" : unitId);
  }

  return (
    <section className="mobile-dashboard">
      <DashboardStatusGrid statusCards={statusCards} expandedUnit={expandedUnit} onToggle={toggleUnit} />

      {expandedUnit && (
        <section className="mobile-dash-control-panel">
          {expandedUnit === "irrigation" && <UserManualWatering irrigation={snapshot?.irrigation || {}} reload={reload} setToast={setToast} />}
          {expandedUnit === "marten" && <UserPowerWallDevice setToast={setToast} />}
          {expandedUnit === "climate" && <UserClimateQuickControl setToast={setToast} />}
          {expandedUnit === "x10" && <UserX10QuickSchedule setToast={setToast} />}
        </section>
      )}

      <HomeSensorGrid irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />

      <section className="mobile-dash-side">
        <HomeSolarPanel />
        <HomeWeatherPanel localSensors={localSensors} openingSensors={openingSensors} />
      </section>
    </section>
  );
}

function TabletDashboard({ snapshot, reload, setToast, activeTab, setActiveTab, menuItems = navItems }) {
  const { weather, localSensors, openingSensors } = useHomeWeather();
  const [expandedUnit, setExpandedUnit] = useState("");
  const [menuOpen, setMenuOpen] = useState(false);
  const { statusCards } = useDashboardUnitStatuses(snapshot);

  function toggleUnit(unitId) {
    setExpandedUnit((current) => current === unitId ? "" : unitId);
  }

  function openTabletNav(id) {
    setActiveTab(id);
    window.location.hash = id;
    setMenuOpen(false);
  }

  return (
    <section className="tablet-dashboard">
      <section className="tablet-dashboard-top">
        <div className="tablet-clock-menu-wrap">
          <TabletClock menuOpen={menuOpen} onToggleMenu={() => setMenuOpen((open) => !open)} />
          {menuOpen && (
            <nav className="tablet-hidden-menu" aria-label="Tablet menu">
              {menuItems.map(({ id, label, icon: Icon, tone }) => (
                <button
                  className={activeTab === id ? "active" : ""}
                  style={{ "--tone": tone }}
                  type="button"
                  onClick={() => openTabletNav(id)}
                  key={id}
                >
                  <Icon size={17} aria-hidden="true" />
                  <span>{label}</span>
                </button>
              ))}
            </nav>
          )}
        </div>
        <section className="tablet-status-grid">
          {statusCards.map((card) => (
            <TabletStatusButton
              key={card.id}
              id={card.id}
              title={card.title}
              value={card.value}
              meta={card.meta}
              icon={card.icon}
              tone={card.tone}
              active={card.active}
              expanded={false}
              onClick={toggleUnit}
            />
          ))}
        </section>
      </section>

      {expandedUnit && (
        <section className="tablet-dash-control-panel">
          {expandedUnit === "irrigation" && <UserManualWatering irrigation={snapshot?.irrigation || {}} reload={reload} setToast={setToast} />}
          {expandedUnit === "marten" && <UserPowerWallDevice setToast={setToast} />}
          {expandedUnit === "climate" && <UserClimateQuickControl setToast={setToast} />}
          {expandedUnit === "x10" && <UserX10QuickSchedule setToast={setToast} />}
        </section>
      )}

      <section className="tablet-dashboard-main">
        <div className="tablet-sensor-stack">
          <HomeSensorGrid irrigation={snapshot?.irrigation || {}} weather={weather} localSensors={localSensors} />
          <HomeSolarPanel />
        </div>
        <aside className="tablet-thermo-stack">
          <HomeWeatherPanel localSensors={localSensors} openingSensors={openingSensors} />
        </aside>
      </section>
    </section>
  );
}

function Irrigation({ snapshot, reload, setToast }) {
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
      healthState: `${healthValue} | nano serial=${textValue(nanoSerialHealthy)}`,
      healthMeta: `Age: ${ageText(liveTopic("esp_nano_status"))}`,
      healthBad: healthValue.includes("FAULT") || nanoSerialHealthy === false,
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
        <PilotSummaryCards fallbackMode={summary.modeState} fallbackAge={ageText(liveTopic("esp_nano_status"))} />
      </section>

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
          <Table
            rows={irrigation.sessions}
            columns={[
              { key: "id", label: "ID" },
              { key: "status", label: "Status" },
              { key: "started_at", label: "Start", render: (row) => dateText(row.started_at) },
              { key: "requested_stop_at", label: "Stop target", render: (row) => dateText(row.requested_stop_at) },
              { key: "stopped_at", label: "Stopped", render: (row) => dateText(row.stopped_at) },
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

function XiaomiX10({ setToast }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const [cleanMode, setCleanMode] = useState("");
  const [suction, setSuction] = useState("");
  const [waterLevel, setWaterLevel] = useState("");
  const [captureLabel, setCaptureLabel] = useState("");
  const [selectedMapId, setSelectedMapId] = useState("");
  const [weeklySchedules, setWeeklySchedules] = useState(() => x10WeeklyDraftFromState(null));
  const [quickClean, setQuickClean] = useState({
    delay_min: 2,
    map_id: "",
    mode: "2",
    suction: "3",
    water_level: "2",
    segments: [],
    segment_text: "",
  });
  const [scheduleDirty, setScheduleDirty] = useState(false);
  const [scheduleSyncHoldUntil, setScheduleSyncHoldUntil] = useState(0);
  const [pendingScheduleSignature, setPendingScheduleSignature] = useState("");
  const [nowMs, setNowMs] = useState(Date.now());
  const [dndWindows, setDndWindows] = useState(() => {
    try {
      const saved = JSON.parse(window.localStorage.getItem("x10-dnd-windows") || "[]");
      if (Array.isArray(saved) && saved.length) return saved;
    } catch (err) {
      // Ignore invalid local storage and fall back to one editable window.
    }
    return [{ enabled: false, start: "22:00", end: "07:00" }];
  });

  async function loadX10(silent = false) {
    if (!silent) setLoading(true);
    try {
      setState(await api("/api/context/robot"));
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadX10();
    const id = window.setInterval(() => loadX10(true), 3000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/robot"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  useEffect(() => {
    if (!state) return;
    setCleanMode((current) => current || textValue(state.clean_mode));
    setSuction((current) => current || textValue(state.suction));
    setWaterLevel((current) => current || textValue(state.water_level));
    setSelectedMapId((current) => current || textValue(state?.map?.current_id));
    if (scheduleDirty) return;
    const serverDraft = x10WeeklyDraftFromState(state);
    const serverSignature = weeklyScheduleSignature(serverDraft);
    if (pendingScheduleSignature && serverSignature === pendingScheduleSignature) {
      setPendingScheduleSignature("");
      setScheduleSyncHoldUntil(0);
      setWeeklySchedules(serverDraft);
      return;
    }
    if (scheduleSyncHoldUntil && Date.now() < scheduleSyncHoldUntil) return;
    setPendingScheduleSignature("");
    setScheduleSyncHoldUntil(0);
    setWeeklySchedules(serverDraft);
  }, [state, scheduleDirty, scheduleSyncHoldUntil, pendingScheduleSignature]);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    window.localStorage.setItem("x10-dnd-windows", JSON.stringify(dndWindows));
  }, [dndWindows]);

  async function publishX10(command, payload = "1") {
    return api("/api/xiaomi-x10/command", {
      method: "POST",
      body: JSON.stringify({ command, payload }),
    });
  }

  async function sendX10(command, payload = "1", message = "Command sent") {
    setBusy(command);
    try {
      await publishX10(command, payload);
      setToast(message);
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function applyCleaningSettings() {
    setBusy("settings");
    try {
      await publishX10("set_clean_mode", { value: Number(cleanMode || state?.clean_mode || 0) });
      await publishX10("set_suction", { value: Number(suction || state?.suction || 3) });
      await publishX10("set_water_level", { value: Number(waterLevel || state?.water_level || 1) });
      setToast("Cleaning settings sent");
      window.setTimeout(() => loadX10(true), 1200);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function startCapture() {
    setBusy("capture_start");
    try {
      await publishX10("capture_start", {
        label: captureLabel || state?.map?.current_name || "x10_capture",
        map_id: state?.map?.current_id || null,
      });
      setToast("X10 data capture started");
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function stopCapture() {
    setBusy("capture_stop");
    try {
      await publishX10("capture_stop", {});
      setToast("X10 data capture stopped");
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function activateSelectedMap() {
    const mapId = Number(selectedMapId || state?.map?.current_id);
    if (!mapId) {
      setToast("Select map first");
      return;
    }
    setBusy("select_map");
    try {
      await publishX10("select_map", { map_id: mapId });
      setToast("Map activation sent");
      window.setTimeout(() => loadX10(true), 1500);
      window.setTimeout(() => loadX10(true), 5000);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function selectX10Map(mapId) {
    const nextMapId = textValue(mapId);
    setSelectedMapId(nextMapId);
    setQuickClean((current) => {
      if (textValue(current.map_id) === nextMapId) return current;
      return { ...current, map_id: nextMapId, segments: [], segment_text: "" };
    });
  }

  async function roomClean(room) {
    const activeDnd = dndMatch(dndWindows, new Date(nowMs));
    if (activeDnd) {
      setToast(`DND active: ${activeDnd.start}-${activeDnd.end}`);
      return;
    }
    const mapId = state?.map?.current_id;
    const segmentId = room.segment_id;
    if (!mapId || !segmentId) return;
    setBusy("room_clean");
    try {
      if (cleanMode !== "") {
        await publishX10("set_clean_mode", { value: Number(cleanMode) });
      }
      if (waterLevel !== "") {
        await publishX10("set_water_level", { value: Number(waterLevel) });
      }
      await publishX10("room_clean", {
        map_id: mapId,
        segments: [segmentId],
        delay_min: 2,
        suction: Number(suction || state?.suction || 3),
        clean_param: Number(waterLevel || state?.water_level || 3),
      });
      setToast(`${room.name || segmentId} scheduled`);
      window.setTimeout(() => loadX10(true), 900);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateWeeklySchedule(dayIndex, key, value) {
    setScheduleDirty(true);
    setWeeklySchedules((current) => current.map((item) => (
      item.day_index === dayIndex ? { ...item, [key]: value, ...(key === "map_id" ? { segments: [] } : {}) } : item
    )));
  }

  function toggleWeeklyRoom(dayIndex, segmentId, checked) {
    setScheduleDirty(true);
    setWeeklySchedules((current) => current.map((item) => {
      if (item.day_index !== dayIndex) return item;
      const value = Number(segmentId);
      const next = checked
        ? [...new Set([...item.segments, value])]
        : item.segments.filter((roomId) => Number(roomId) !== value);
      return { ...item, segments: next };
    }));
  }

  function updateQuickClean(key, value) {
    setQuickClean((current) => ({ ...current, [key]: value }));
  }

  function toggleQuickRoom(segmentId, checked) {
    const value = Number(segmentId);
    setQuickClean((current) => {
      const next = checked
        ? [...new Set([...current.segments, value])]
        : current.segments.filter((roomId) => Number(roomId) !== value);
      return { ...current, segments: next };
    });
  }

  async function scheduleQuickCleaning() {
    const activeDnd = dndMatch(dndWindows, new Date(nowMs));
    if (activeDnd) {
      setToast(`DND active: ${activeDnd.start}-${activeDnd.end}`);
      return;
    }
    const mapId = Number(quickClean.map_id || state?.map?.current_id || 3);
    const segments = [...new Set([
      ...parseSegmentList(quickClean.segments),
      ...parseSegmentList(quickClean.segment_text),
    ])];
    if (!segments.length) {
      setToast("Select room or enter segment for quick clean");
      return;
    }
    const delayMin = Math.max(1, Number(quickClean.delay_min) || 2);
    setBusy("quick_clean");
    try {
      await publishX10("schedule_clean", {
        map_id: mapId,
        segments,
        start_time: timeAfterMinutes(delayMin),
        days: "0000000",
        enabled: 1,
        mode: Number(quickClean.mode || state?.clean_mode || 2),
        suction: Number(quickClean.suction || state?.suction || 3),
        clean_param: Number(quickClean.water_level || state?.water_level || 2),
      });
      setToast(`Quick clean scheduled in ${delayMin} min`);
      window.setTimeout(() => loadX10(true), 900);
      window.setTimeout(() => loadX10(true), 2500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function saveWeeklyCleaningSchedule() {
    const mapId = state?.map?.current_id;
    const enabledWithoutRooms = weeklySchedules.find((item) => item.enabled && !item.segments.length);
    if (!mapId) return;
    if (enabledWithoutRooms) {
      setToast(`Select room for ${x10DayOptions[enabledWithoutRooms.day_index]?.label || "day"}`);
      return;
    }
    setBusy("schedule_clean");
    const schedulePayload = weeklySchedules
      .map((item) => ({
        day_index: item.day_index,
        task_id: item.task_id,
            enabled: item.enabled && item.segments.length ? 1 : 0,
            start_time: item.start_time || "06:00",
            days: dayMaskFor(item.day_index),
            map_id: Number(item.map_id || mapId),
            mode: Number(item.mode || state?.clean_mode || 0),
        suction: Number(item.suction || state?.suction || 3),
        clean_param: Number(item.water_level || state?.water_level || 3),
        segments: item.segments.map((roomId) => Number(roomId)).filter(Boolean),
      }));
    try {
      await publishX10("schedule_clean_week", {
        map_id: mapId,
        schedules: schedulePayload,
      });
      setPendingScheduleSignature(weeklyScheduleSignature(weeklySchedules));
      setScheduleSyncHoldUntil(Date.now() + 10000);
      setScheduleDirty(false);
      setToast("Weekly cleaning schedule saved");
      window.setTimeout(() => loadX10(true), 2500);
      window.setTimeout(() => loadX10(true), 6500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function disableWeeklyCleaningSchedule() {
    const mapId = state?.map?.current_id;
    if (!mapId) return;
    const disabledSchedules = weeklySchedules.map((item) => ({ ...item, enabled: false }));
    setWeeklySchedules(disabledSchedules);
    setScheduleDirty(true);
    setBusy("schedule_clean");
    try {
      await publishX10("schedule_clean_week", {
        map_id: mapId,
        schedules: disabledSchedules
          .map((item) => ({
            day_index: item.day_index,
            task_id: item.task_id,
            enabled: 0,
            start_time: item.start_time || "06:00",
            days: dayMaskFor(item.day_index),
            map_id: Number(item.map_id || mapId),
            mode: Number(item.mode || state?.clean_mode || 0),
            suction: Number(item.suction || state?.suction || 3),
            clean_param: Number(item.water_level || state?.water_level || 3),
            segments: item.segments.map((roomId) => Number(roomId)).filter(Boolean),
          })),
      });
      setPendingScheduleSignature(weeklyScheduleSignature(disabledSchedules));
      setScheduleSyncHoldUntil(Date.now() + 10000);
      setScheduleDirty(false);
      setToast("Weekly cleaning schedule disabled");
      window.setTimeout(() => loadX10(true), 2500);
      window.setTimeout(() => loadX10(true), 6500);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateDnd(index, key, value) {
    setDndWindows((current) => current.map((item, itemIndex) => (
      itemIndex === index ? { ...item, [key]: value } : item
    )));
  }

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading Xiaomi X10...</span>
      </section>
    );
  }

  const rooms = (state?.map?.rooms || []).filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const x10Maps = state?.catalog?.maps?.length ? state.catalog.maps : [{ map_id: state?.map?.current_id || 3, name: state?.map?.current_name || "Current map", has_room_data: true }];
  const roomsByMap = state?.catalog?.rooms_by_map || {};
  const roomsForMap = (mapId) => (roomsByMap[String(mapId)] || (Number(mapId) === Number(state?.map?.current_id) ? rooms : []))
    .filter((room) => room.segment_id && room.name && !String(room.name).startsWith("room_"));
  const catalogCurrentMap = x10Maps.find((mapItem) => mapItem.is_current);
  const robotMapId = state?.map?.current_id || catalogCurrentMap?.map_id;
  const selectedMap = x10Maps.find((mapItem) => Number(mapItem.map_id) === Number(selectedMapId || robotMapId)) || x10Maps[0] || {};
  const selectedMapRooms = roomsForMap(selectedMap.map_id || robotMapId);
  const robotMap = x10Maps.find((mapItem) => Number(mapItem.map_id) === Number(robotMapId)) || catalogCurrentMap || {};
  const robotMapName = state?.map?.current_name || robotMap.name || "unknown";
  const selectedMapName = selectedMap.name || robotMapName;
  const mapSyncPending = Boolean(selectedMap.map_id && robotMapId && Number(selectedMap.map_id) !== Number(robotMapId));
  const mapCardMeta = mapSyncPending
    ? `waiting for robot ${robotMapName}`
    : `${selectedMapRooms.length} room | robot synced`;
  const bridgeOnline = String(state?.bridge_online) === "1" || state?.bridge_online === 1;
  const topics = Object.values(state?.topics || {}).sort((a, b) => String(a.rel_topic).localeCompare(String(b.rel_topic)));
  const cleanPlan = roomCleanPlan(state?.room_clean_status, nowMs);
  const activeDnd = dndMatch(dndWindows, new Date(nowMs));
  const cleanModeLabel = optionLabel(x10ModeOptions, state?.clean_mode);
  const suctionLabel = optionLabel(x10SuctionOptions, state?.suction);
  const waterLabel = optionLabel(x10WaterOptions, state?.water_level);
  const captureStatus = state?.capture_status || {};
  const captureActive = Boolean(captureStatus?.active);
  const robotStateText = textValue(state?.robot_state_text || state?.state?.state_text);
  const telemetryMissing = state?.telemetry_available === false;
  const telemetrySource = textValue(state?.telemetry_source);
  const quickMapId = Number(quickClean.map_id || selectedMapId || state?.map?.current_id || 3);
  const quickRooms = roomsForMap(quickMapId);
  const quickSelectedSegments = [...new Set([
    ...parseSegmentList(quickClean.segments),
    ...parseSegmentList(quickClean.segment_text),
  ])];

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Xiaomi X10</h2>
          <span>{error || `${state?.base_topic || "homecontrol/xiaomi_x10"} | ${bridgeOnline ? "bridge online" : "bridge offline"} | ${selectedMapName || "map unknown"}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadX10()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles x10-tiles">
        <Card title="Robot State" value={robotStateText} meta={telemetryMissing ? "telemetry missing | map data available" : `source=${telemetrySource} | raw=${textValue(state?.robot_state)} | task=${textValue(state?.task_state)}`} icon={Activity} tone={bridgeOnline && !telemetryMissing ? "" : "warn"} />
        <Card title="Battery" value={unitValue(state?.battery, "%", 0)} meta={`source=${telemetrySource} | bridge ${textValue(state?.bridge_status)} | seen ${textValue(state?.bridge_last_seen)}`} icon={BatteryCharging} tone={telemetryMissing ? "warn" : ""} />
        <Card title="Cleaning" value={cleanModeLabel} meta={`vacuum=${suctionLabel} | water=${waterLabel} | mop=${textValue(state?.mop_attached)}`} icon={Gauge} />
        <Card title="Map" value={selectedMapName || "-"} meta={mapCardMeta} icon={MapIcon} tone={mapSyncPending ? "warn" : ""} className={`x10-map-card ${mapSyncPending ? "map-sync-pending" : ""}`} />
        <Card title="Room Clean" value={cleanPlan?.label || "-"} meta={cleanPlan?.meta || (activeDnd ? `DND ${activeDnd.start}-${activeDnd.end}` : "no pending schedule")} icon={Clock} tone={activeDnd ? "warn" : ""} />
      </section>

      <section className="grid">
        <article className="panel">
          <div className="panel-head">
            <h2>Active Map</h2>
            <span>{selectedMapName || "unknown"} | selected ID {selectedMap.map_id || "-"}</span>
          </div>
          <div className="inline-form x10-map-select">
            <label>
              Map
              <select value={selectedMapId || robotMapId || ""} onChange={(event) => selectX10Map(event.target.value)}>
                {x10Maps.map((mapItem) => (
                  <option key={mapItem.map_id} value={mapItem.map_id}>
                    {mapItem.name || `Map ${mapItem.map_id}`} #{mapItem.map_id}{mapItem.is_current ? " current" : ""}
                  </option>
                ))}
              </select>
            </label>
            <IconButton icon={MapIcon} disabled={Boolean(busy) || !selectedMapId} onClick={activateSelectedMap}>
              {busy === "select_map" ? "Activating" : "Activate Map"}
            </IconButton>
            <IconButton icon={RefreshCw} className="secondary" disabled={Boolean(busy)} onClick={() => sendX10("refresh_map", "1", "Map list refreshed")}>
              Refresh Map List
            </IconButton>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Control</h2>
            <span>{busy ? `sending ${busy}` : "MQTT command proxy"}</span>
          </div>
          <div className="button-grid">
            <IconButton icon={Play} disabled={Boolean(busy)} onClick={() => sendX10("start")}>Start</IconButton>
            <IconButton icon={Square} disabled={Boolean(busy)} className="secondary" onClick={() => sendX10("stop")}>Stop</IconButton>
            <IconButton icon={Home} disabled={Boolean(busy)} onClick={() => sendX10("home")}>Dock</IconButton>
            <IconButton icon={RefreshCw} disabled={Boolean(busy)} onClick={() => sendX10("status")}>Status</IconButton>
            <IconButton icon={CalendarDays} disabled={Boolean(busy)} onClick={() => sendX10("read_scheduler")}>Scheduler</IconButton>
          </div>
          <div className="x10-capture-box">
            <label>
              Capture Label
              <input
                type="text"
                value={captureLabel}
                placeholder={state?.map?.current_name || "x10_capture"}
                onChange={(event) => setCaptureLabel(event.target.value)}
              />
            </label>
            <div className="x10-capture-status">
              <strong>{captureActive ? "Capture active" : "Capture idle"}</strong>
              <span>{captureActive ? `${captureStatus.sample_count || 0} samples | ${shortPath(captureStatus.file)}` : "saves map/status samples to x10_maps/captures"}</span>
            </div>
            {captureActive ? (
              <IconButton icon={Square} className="secondary" disabled={Boolean(busy)} onClick={stopCapture}>{busy === "capture_stop" ? "Stopping" : "Stop Capture"}</IconButton>
            ) : (
              <IconButton icon={Database} disabled={Boolean(busy)} onClick={startCapture}>{busy === "capture_start" ? "Starting" : "Start Capture"}</IconButton>
            )}
          </div>
        </article>

        <article className="panel x10-scheduler-panel">
          <div className="panel-subhead">
            <h3>Weekly Cleaning Schedule</h3>
            <span>{scheduleDirty ? "unsaved changes" : "one task per day"}</span>
          </div>
          <div className="x10-weekly-list">
            {weeklySchedules.map((row) => {
              const day = x10DayOptions[row.day_index];
              return (
                <div className={`x10-weekly-row ${row.enabled ? "active" : ""}`} key={row.task_id}>
                  <label className="check x10-weekly-day">
                    <input
                      type="checkbox"
                      checked={Boolean(row.enabled)}
                      onChange={(event) => updateWeeklySchedule(row.day_index, "enabled", event.target.checked)}
                    />
                    {day?.label || row.day_index}
                  </label>
                  <label>
                    Start
                    <input type="time" value={row.start_time || "06:00"} onChange={(event) => updateWeeklySchedule(row.day_index, "start_time", event.target.value)} />
                  </label>
                  <label>
                    Map
                    <select value={row.map_id || state?.map?.current_id || 3} onChange={(event) => updateWeeklySchedule(row.day_index, "map_id", Number(event.target.value))}>
                      {x10Maps.map((mapItem) => <option key={mapItem.map_id} value={mapItem.map_id}>{mapItem.name}</option>)}
                    </select>
                  </label>
                  <label>
                    Mode
                    <select value={row.mode} onChange={(event) => updateWeeklySchedule(row.day_index, "mode", event.target.value)}>
                      {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Vacuum
                    <select value={row.suction} onChange={(event) => updateWeeklySchedule(row.day_index, "suction", event.target.value)}>
                      {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Water
                    <select value={row.water_level} onChange={(event) => updateWeeklySchedule(row.day_index, "water_level", event.target.value)}>
                      {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <div className="x10-weekly-rooms">
                    {roomsForMap(row.map_id || state?.map?.current_id || 3).length ? roomsForMap(row.map_id || state?.map?.current_id || 3).map((room) => (
                      <label className="check" key={`${row.task_id}-${room.segment_id}`}>
                        <input
                          type="checkbox"
                          checked={row.segments.map(Number).includes(Number(room.segment_id))}
                          onChange={(event) => toggleWeeklyRoom(row.day_index, room.segment_id, event.target.checked)}
                        />
                        {room.name}
                      </label>
                    )) : <span className="muted-text">No room data</span>}
                  </div>
                </div>
              );
            })}
          </div>

          <div className="x10-schedule-box">
            <strong>{cleanPlan?.targetMs ? `Scheduled start: ${timeText(cleanPlan.targetMs)}` : "No pending scheduled room clean"}</strong>
            <span>{cleanPlan?.targetMs ? `Countdown ${cleanPlan.label} | ${cleanPlan.status}` : "Room cleaning is started through the vacuum scheduler"}</span>
          </div>
          <div className="button-row compact">
            <IconButton icon={Save} disabled={Boolean(busy)} onClick={saveWeeklyCleaningSchedule}>{busy === "schedule_clean" ? "Saving" : "Save Schedule"}</IconButton>
            <button type="button" className="secondary" disabled={Boolean(busy)} onClick={disableWeeklyCleaningSchedule}>Disable & Save</button>
          </div>

          <div className="panel-subhead">
            <h3>Quick Scheduled Clean</h3>
            <span>{activeDnd ? `DND ${activeDnd.start}-${activeDnd.end}` : `starts ${timeAfterMinutes(quickClean.delay_min)}`}</span>
          </div>
          <div className="x10-quick-grid">
            <label>
              Delay
              <input
                type="number"
                min="1"
                max="15"
                step="1"
                value={quickClean.delay_min}
                onChange={(event) => updateQuickClean("delay_min", event.target.value)}
              />
            </label>
            <label>
              Map
              <select
                value={quickMapId}
                onChange={(event) => setQuickClean((current) => ({ ...current, map_id: Number(event.target.value), segments: [], segment_text: "" }))}
              >
                {x10Maps.map((mapItem) => <option key={mapItem.map_id} value={mapItem.map_id}>{mapItem.name}</option>)}
              </select>
            </label>
            <label>
              Mode
              <select value={quickClean.mode} onChange={(event) => updateQuickClean("mode", event.target.value)}>
                {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Vacuum
              <select value={quickClean.suction} onChange={(event) => updateQuickClean("suction", event.target.value)}>
                {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Water
              <select value={quickClean.water_level} onChange={(event) => updateQuickClean("water_level", event.target.value)}>
                {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Segments
              <input
                type="text"
                value={quickClean.segment_text}
                placeholder="4,7"
                onChange={(event) => updateQuickClean("segment_text", event.target.value)}
              />
            </label>
            <IconButton icon={Clock} disabled={Boolean(busy) || Boolean(activeDnd) || !quickSelectedSegments.length} onClick={scheduleQuickCleaning}>{busy === "quick_clean" ? "Scheduling" : "Schedule"}</IconButton>
          </div>
          <div className="x10-weekly-rooms x10-quick-rooms">
            {quickRooms.length ? quickRooms.map((room) => (
              <label className="check" key={`quick-${quickMapId}-${room.segment_id}`}>
                <input
                  type="checkbox"
                  checked={quickClean.segments.map(Number).includes(Number(room.segment_id))}
                  onChange={(event) => toggleQuickRoom(room.segment_id, event.target.checked)}
                />
                {room.name}
              </label>
            )) : <span className="muted-text">No room data</span>}
          </div>

          <div className="panel-subhead">
            <h3>Cleaning Settings</h3>
            <span>{cleanModeLabel} | vacuum={suctionLabel} | water={waterLabel}</span>
          </div>
          <div className="x10-settings-grid">
            <label>
              Mode
              <select value={cleanMode} onChange={(event) => setCleanMode(event.target.value)}>
                <option value="">Current</option>
                {x10ModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Vacuum
              <select value={suction} onChange={(event) => setSuction(event.target.value)}>
                <option value="">Current</option>
                {x10SuctionOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <label>
              Water
              <select value={waterLevel} onChange={(event) => setWaterLevel(event.target.value)}>
                <option value="">Current</option>
                {x10WaterOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
              </select>
            </label>
            <IconButton icon={Save} disabled={Boolean(busy)} onClick={applyCleaningSettings}>{busy === "settings" ? "Sending" : "Apply Now"}</IconButton>
          </div>

          <div className="panel-subhead">
            <h3>DND</h3>
            <span>{activeDnd ? `active ${activeDnd.start}-${activeDnd.end}` : "dashboard guard"}</span>
          </div>
          <div className="x10-dnd-list">
            {dndWindows.map((item, index) => (
              <div className="x10-dnd-row" key={index}>
                <label className="check">
                  <input type="checkbox" checked={Boolean(item.enabled)} onChange={(event) => updateDnd(index, "enabled", event.target.checked)} />
                  Enabled
                </label>
                <label>
                  From
                  <input type="time" value={item.start || "22:00"} onChange={(event) => updateDnd(index, "start", event.target.value)} />
                </label>
                <label>
                  To
                  <input type="time" value={item.end || "07:00"} onChange={(event) => updateDnd(index, "end", event.target.value)} />
                </label>
              </div>
            ))}
          </div>
          <div className="button-row compact">
            <button type="button" className="secondary" onClick={() => setDndWindows([...dndWindows, { enabled: true, start: "22:00", end: "07:00" }])}>Add DND</button>
            <button type="button" className="secondary" onClick={() => setDndWindows(dndWindows.length > 1 ? dndWindows.slice(0, -1) : dndWindows)}>Remove Last</button>
          </div>

          <div className="panel-subhead">
            <h3>Last Result</h3>
            <span>{dateText(state?.topics?.command_result?.timestamp ? new Date(state.topics.command_result.timestamp * 1000).toISOString() : null)}</span>
          </div>
          <pre className="json-box">{shortValue(state?.command_result || state?.error || {}, 900)}</pre>
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Live X10 MQTT</h2>
          <span>{topics.length} retained/current topics</span>
        </div>
        <Table
          rows={topics}
          columns={[
            { key: "rel_topic", label: "Topic" },
            { key: "json", label: "Value", render: (row) => shortValue(row.json, 150) },
            { key: "age_sec", label: "Age", render: (row) => `${row.age_sec}s` },
          ]}
        />
      </section>
    </>
  );
}

function climateDraftFromState(state) {
  return {
    power: state?.power || "off",
    mode: state?.mode && state.mode !== "unknown" ? state.mode : "auto",
    target_temperature: state?.target_temperature ?? 23,
    fan_speed: state?.fan_speed && state.fan_speed !== "unknown" ? state.fan_speed : "auto",
    light: state?.light || "off",
  };
}

function ClimateControl({ setToast }) {
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState(() => climateDraftFromState(null));
  const [draftDirty, setDraftDirty] = useState(false);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function loadClimate(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await api("/api/context/climate");
      setState(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadClimate();
    const id = window.setInterval(() => loadClimate(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/climate"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  useEffect(() => {
    if (!state) return;
    if (draftDirty || busy) return;
    setDraft(climateDraftFromState(state));
  }, [state, draftDirty, busy]);

  function updateDraft(key, value) {
    setDraftDirty(true);
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function sendClimate(payload, busyKey = "command", message = "Climate command sent") {
    setBusy(busyKey);
    try {
      const data = await api("/api/climate/gree/command", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      const nextState = data.state || data;
      setState(nextState);
      setDraft(climateDraftFromState(nextState));
      setDraftDirty(false);
      setError("");
      setToast(message);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function applyDraft() {
    await sendClimate({
      power: draft.power,
      mode: draft.mode,
      target_temperature: Number(draft.target_temperature),
      fan_speed: draft.fan_speed,
    }, "apply", "Climate settings applied");
  }

  const online = state?.bridge_online && !error;
  const modeLabel = optionLabel(climateModeOptions, state?.mode);
  const fanLabel = optionLabel(climateFanOptions, state?.fan_speed);
  const powerMeter = state?.power_meter || {};
  const powerMeterState = powerMeter.state || {};
  const powerMeterDaily = powerMeter.daily || {};

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading climate...</span>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>{state?.name || "Gree Climate"}</h2>
          <span>{error || `${state?.ip || "192.168.1.72"}:${state?.port || 7000} | bridge ${online ? "online" : "offline"} | ${state?.base_topic || "homecontrol/gree_climate"}`}</span>
        </div>
        <IconButton
          icon={RefreshCw}
          onClick={async () => {
            setDraftDirty(false);
            await loadClimate();
          }}
          disabled={loading}
        >
          {loading ? "Refreshing" : "Refresh"}
        </IconButton>
      </section>

      <section className="tile-grid stats-tiles climate-tiles">
        <Card
          title="Power"
          value={String(state?.power || "-").toUpperCase()}
          meta={`${unitValue(powerMeterState.power_w, "W", 0)} | target ${unitValue(state?.target_temperature, "C", 0)} | current ${unitValue(state?.current_temperature, "C", 1)}`}
          icon={Power}
          tone={state?.power === "off" ? "warn" : ""}
        />
        <Card title="Target" value={unitValue(state?.target_temperature, "C", 0)} meta={state?.power || "-"} icon={Thermometer} tone={state?.power === "off" ? "warn" : ""} />
        <Card title="Current Temp" value={unitValue(state?.current_temperature, "C", 1)} meta={state?.updated_at ? dateText(state.updated_at) : "-"} icon={Thermometer} />
        <Card title="Mode" value={modeLabel} meta={`fan ${fanLabel}`} icon={Wind} />
        <Card title="Today Use" value={unitValue(powerMeterDaily.energy_kwh, "kWh", 2)} meta={`${powerMeterDaily.sample_count || 0} samples | ${powerMeter.status || "unknown"}`} icon={BatteryCharging} tone={powerMeter.ok ? "" : "warn"} />
        <Card title="Total Energy" value={unitValue(powerMeterState.energy_kwh, "kWh", 2)} meta={unitValue(powerMeterState.voltage_v, "V", 1)} icon={BatteryCharging} />
      </section>

      <section className="grid two climate-grid">
        <div className="climate-stack">
          <article className="panel">
            <div className="panel-head">
              <h2>Quick Control</h2>
              <span>{busy ? `sending ${busy}` : "direct Gree API"}</span>
            </div>
            <div className="button-grid climate-power-grid">
              <IconButton icon={Power} disabled={Boolean(busy)} onClick={() => sendClimate({ power: "on" }, "power_on", "Climate turned on")}>On</IconButton>
              <IconButton icon={Square} className="secondary" disabled={Boolean(busy)} onClick={() => sendClimate({ power: "off" }, "power_off", "Climate turned off")}>Off</IconButton>
              <IconButton icon={Lightbulb} disabled={Boolean(busy)} onClick={() => sendClimate({ light: state?.light === "on" ? "off" : "on" }, "light", "Light toggled")}>Light</IconButton>
              <IconButton
                icon={RefreshCw}
                className="secondary"
                disabled={Boolean(busy)}
                onClick={async () => {
                  setDraftDirty(false);
                  await loadClimate();
                }}
              >
                Refresh
              </IconButton>
            </div>

            <div className="climate-form">
              <label>
                Power
                <select value={draft.power} onChange={(event) => updateDraft("power", event.target.value)}>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <label>
                Mode
                <select value={draft.mode} onChange={(event) => updateDraft("mode", event.target.value)}>
                  {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Target
                <input
                  type="number"
                  min="8"
                  max="30"
                  step="1"
                  value={draft.target_temperature}
                  onChange={(event) => updateDraft("target_temperature", event.target.value)}
                />
              </label>
              <label>
                Fan
                <select value={draft.fan_speed} onChange={(event) => updateDraft("fan_speed", event.target.value)}>
                  {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <IconButton icon={Save} disabled={Boolean(busy)} onClick={applyDraft}>{busy === "apply" ? "Applying" : "Apply"}</IconButton>
            </div>
          </article>
          <ClimatePowerWallPlug setToast={setToast} />
        </div>

        <article className="panel">
          <div className="panel-head">
            <h2>Device State</h2>
            <span>{state?.updated_at || "-"}</span>
          </div>
          <div className="meter-list">
            <div className="meter-row">
              <strong>Endpoint</strong>
              <span>{state?.ip || "-"}:{state?.port || "-"}</span>
              <b>{state?.mac || "-"}</b>
            </div>
            <div className="meter-row">
              <strong>Current</strong>
              <span>{unitValue(state?.current_temperature, "C", 1)} | power {state?.power || "-"}</span>
              <b>{state?.power || "-"}</b>
            </div>
            <div className="meter-row">
              <strong>Target</strong>
              <span>{unitValue(state?.target_temperature, "C", 0)} | mode {modeLabel}</span>
              <b>{fanLabel}</b>
            </div>
            <div className="meter-row">
              <strong>Current Use</strong>
              <span>{powerMeter.ok ? unitValue(powerMeterState.voltage_v, "V", 1) : powerMeter.error || "-"}</span>
              <b>{unitValue(powerMeterState.power_w, "W", 0)}</b>
            </div>
            <div className="meter-row">
              <strong>Today Use</strong>
              <span>{powerMeterDaily.sample_count || 0} samples</span>
              <b>{unitValue(powerMeterDaily.energy_kwh, "kWh", 2)}</b>
            </div>
            <div className="meter-row">
              <strong>Total Energy</strong>
              <span>{powerMeter.entity_name || "-"} | {unitValue(powerMeterState.voltage_v, "V", 1)}</span>
              <b>{unitValue(powerMeterState.energy_kwh, "kWh", 2)}</b>
            </div>
          </div>
          <div className="panel-subhead">
            <h3>Raw Properties</h3>
            <span>{Object.keys(state?.raw_properties || {}).length} values</span>
          </div>
          <pre className="json-box climate-raw">{shortValue(state?.raw_properties || {}, 1200)}</pre>
        </article>
      </section>

      <ClimatePowerCharts />
      <ClimateScheduleRules setToast={setToast} />
      <ClimateSensorSnapshot />
    </>
  );
}

function ClimatePowerWallPlug({ setToast }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [historyByEntity, setHistoryByEntity] = useState({});
  const [error, setError] = useState("");

  async function loadPlug(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      setState(await api("/api/context/power_wall"));
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadPlug();
    const id = window.setInterval(() => loadPlug(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/power_wall"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function setPlugSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      setToast(value ? "Climate plug turned on" : "Climate plug turned off");
      window.setTimeout(() => loadPlug(true), 1200);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setPlugAlwaysOn(device, alwaysOn) {
    const busyKey = `${device.entity_id}:always-on`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, always_on: alwaysOn }),
      });
      setToast(alwaysOn ? "Climate plug always-on enabled" : "Climate plug always-on disabled");
      await loadPlug(true);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  async function setPlugAutoClimate(device, autoClimate) {
    const busyKey = `${device.entity_id}:auto-climate`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, auto_climate: autoClimate }),
      });
      setToast(autoClimate ? "Climate plug auto mode enabled" : "Climate plug auto mode disabled");
      await loadPlug(true);
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  async function loadPowerWallHistory(entityId) {
    if (!entityId || historyByEntity[entityId]?.data || historyByEntity[entityId]?.loading) return;
    setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: true, error: "", data: null } }));
    try {
      const data = await api(`/api/power-wall/history?entity_id=${encodeURIComponent(entityId)}`);
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: "", data } }));
    } catch (err) {
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: err.message, data: null } }));
    }
  }

  const device = (state?.devices || []).find((item) => String(item.entity_name || "").toLowerCase() === "felső előszoba konnektor");
  if (loading && !state) {
    return (
      <article className="panel tuya-device">
        <div className="panel-head">
          <h2 className="panel-title"><Power size={17} aria-hidden="true" /> Upstairs Hallway Plug</h2>
          <span className="status-pill warn">loading</span>
        </div>
        <div className="chart-empty diff-empty">Loading plug...</div>
      </article>
    );
  }
  if (!device) {
    return (
      <article className="panel tuya-device warn">
        <div className="panel-head">
          <h2 className="panel-title"><Power size={17} aria-hidden="true" /> Upstairs Hallway Plug</h2>
          <span className="status-pill warn">missing</span>
        </div>
        <div className="muted-text">{error || "Plug not found in Power Wall state"}</div>
      </article>
    );
  }

  const status = device.status || "unknown";
  const isDegraded = status === "degraded";
  const isOffline = status === "offline";
  const switchState = powerWallValue(device, ["switch_state", "state"]);
  const switchStateOn = switchOn(switchState);
  const canCommand = ["zigbee", "tuya"].includes(device.platform) && status === "online";
  const powerValue = powerWallValue(device, ["power_w", "power"]);
  const currentValue = powerWallValue(device, ["current_a", "current"]);
  const voltageValue = powerWallValue(device, ["voltage_v", "mains_voltage_v"]);
  const energyValue = powerWallValue(device, ["energy_kwh"]);
  const lagValue = powerWallValue(device, ["lag_sec"]);
  const alwaysOn = Boolean(device.always_on);
  const autoClimate = Boolean(device.auto_climate);

  return (
    <article className={`panel tuya-device climate-plug-device ${alwaysOn ? "always-on" : ""} ${isOffline ? "bad" : isDegraded ? "warn" : ""}`}>
      <div className="panel-head">
        <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {displayEntityName(device.entity_name)}</h2>
        <div className="climate-plug-toggles">
          <label className="always-on-toggle" title="Keep this socket switched on">
            <input
              type="checkbox"
              checked={alwaysOn}
              disabled={policyBusy === `${device.entity_id}:always-on`}
              onChange={(event) => setPlugAlwaysOn(device, event.target.checked)}
            />
            <span>Always on</span>
          </label>
          <label className="always-on-toggle" title="Follow climate power on/off commands">
            <input
              type="checkbox"
              checked={autoClimate}
              disabled={policyBusy === `${device.entity_id}:auto-climate`}
              onChange={(event) => setPlugAutoClimate(device, event.target.checked)}
            />
            <span>Auto</span>
          </label>
        </div>
        <div className="power-wall-badges">
          <span className={`platform-pill ${device.platform}`}>{device.platform}</span>
          <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
        </div>
      </div>
      <div className="tuya-device-meta">
        <span>{error || device.topic_base}</span>
        <span>{device.ext_id || "-"}</span>
        <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
      </div>
      <div className="tuya-metrics">
        <div><span>Switch</span><strong>{tuyaValueText(switchState)}</strong></div>
        <PowerWallPowerMetric
          device={device}
          value={powerValue}
          history={historyByEntity[device.entity_id]}
          loadHistory={loadPowerWallHistory}
        />
        <div><span>Voltage</span><strong>{powerWallMetricText(voltageValue, " V", 1)}</strong></div>
        <div><span>Current</span><strong>{powerWallMetricText(currentValue, " A", 3)}</strong></div>
        <div><span>Energy</span><strong>{powerWallMetricText(energyValue, " kWh", 2)}</strong></div>
        <div><span>Lag</span><strong>{powerWallMetricText(lagValue, " s", 0)}</strong></div>
      </div>
      <div className="tuya-actions">
        <IconButton
          icon={Power}
          className={switchStateOn === true ? "secondary" : ""}
          disabled={!canCommand || Boolean(busy)}
          onClick={() => setPlugSwitch(device, true)}
        >
          {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
        </IconButton>
        <IconButton
          icon={Power}
          className={switchStateOn === false ? "secondary" : ""}
          disabled={!canCommand || Boolean(busy)}
          onClick={() => setPlugSwitch(device, false)}
        >
          {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
        </IconButton>
      </div>
    </article>
  );
}

function ClimatePowerCharts() {
  const [history, setHistory] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadHistory(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      setHistory(await api("/api/context/climate_power_history"));
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadHistory();
    const id = window.setInterval(() => loadHistory(true), 30000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/climate_power_history"], (payload) => {
    setHistory(payload);
    setLoading(false);
  });

  const powerRows = history?.power_24h || [];
  const dailyRows = history?.daily_30d || [];
  const summary = history?.summary || {};

  return (
    <section className="grid two climate-grid">
      <article className="panel">
        <div className="panel-head">
          <h2>Climate Power / 24h</h2>
          <span>{error || `${summary.power_samples || powerRows.length} samples`}</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <TimeLineChart rows={powerRows} valueKey="power_w" unit="W" digits={0} color="blue" />}
      </article>

      <article className="panel">
        <div className="panel-head">
          <h2>Daily Climate Use / 30d</h2>
          <span>{unitValue(summary.today_energy_kwh, "kWh", 2)} today</span>
        </div>
        {loading && !history ? <div className="chart-empty">Loading...</div> : <StatBarChart rows={dailyRows} valueKey="energy_kwh" unit="kWh" digits={2} color="green" />}
      </article>
    </section>
  );
}

function ClimateScheduleRules({ setToast }) {
  const [schedules, setSchedules] = useState([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");
  const schedulesByDay = useMemo(() => dayLabels.map((label, dayIndex) => ({
    label,
    dayIndex,
    rows: schedules
      .filter((row) => Number(row.day_of_week) === dayIndex)
      .sort((a, b) => String(a.start_time || "").localeCompare(String(b.start_time || ""))),
  })), [schedules]);

  async function loadSchedules(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await api("/api/context/climate_schedules");
      setSchedules(data.schedules || []);
      setError("");
    } catch (err) {
      setError(err.message);
      setToast(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadSchedules();
  }, []);
  useContextRefresh(["/api/context/climate_schedules"], (payload) => {
    setSchedules(payload.schedules || []);
    setLoading(false);
  });

  function updateSchedule(id, key, value) {
    setSchedules((current) => current.map((item) => (
      item.id === id ? { ...item, [key]: value } : item
    )));
  }

  async function saveSchedule(row) {
    setBusy(String(row.id));
    try {
      const { light, ...payload } = row;
      const data = await api(`/api/climate/gree/schedules/${row.id}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setSchedules(data.schedules || []);
      setToast("Climate schedule saved");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function addSchedule(dayIndex) {
    setBusy(`new-${dayIndex}`);
    try {
      const data = await api("/api/climate/gree/schedules", {
        method: "POST",
        body: JSON.stringify({
          label: "Climate event",
          day_of_week: dayIndex,
          start_time: "06:30",
          is_enabled: false,
          power: "on",
          mode: "heat",
          target_temperature: 23,
          fan_speed: "auto",
          rule_engine: { rule_engine: "manual_schedule" },
        }),
      });
      setSchedules(data.schedules || []);
      setToast("Climate event added");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function deleteSchedule(row) {
    setBusy(`delete-${row.id}`);
    try {
      const data = await api(`/api/climate/gree/schedules/${row.id}`, {
        method: "DELETE",
      });
      setSchedules(data.schedules || []);
      setToast("Climate event deleted");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel climate-schedule-panel">
      <div className="panel-head">
        <div>
          <h2>Climate Schedule</h2>
          <span>{error || `${schedules.length} events | scheduler`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadSchedules()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </div>
      <div className="climate-schedule-list">
        {schedulesByDay.map((day) => (
          <div className="climate-schedule-day" key={day.dayIndex}>
            <div className="climate-schedule-day-head">
              <div>
                <strong>{day.label}</strong>
                <span>{day.rows.length} events</span>
              </div>
              <IconButton icon={Plus} onClick={() => addSchedule(day.dayIndex)} disabled={busy === `new-${day.dayIndex}`}>
                {busy === `new-${day.dayIndex}` ? "Adding" : "Add event"}
              </IconButton>
            </div>
            <div className="climate-schedule-day-rows">
              {day.rows.map((row) => (
                <div className={`climate-schedule-row ${row.is_enabled ? "active" : ""}`} key={row.id}>
                  <label className="check">
                    <input
                      type="checkbox"
                      checked={Boolean(row.is_enabled)}
                      onChange={(event) => updateSchedule(row.id, "is_enabled", event.target.checked)}
                    />
                    Enabled
                  </label>
                  <label>
                    Label
                    <input type="text" value={row.label || ""} onChange={(event) => updateSchedule(row.id, "label", event.target.value)} />
                  </label>
                  <label>
                    Time
                    <input type="time" value={row.start_time || "06:30"} onChange={(event) => updateSchedule(row.id, "start_time", event.target.value)} />
                  </label>
                  <label>
                    Power
                    <select value={row.power || "on"} onChange={(event) => updateSchedule(row.id, "power", event.target.value)}>
                      <option value="on">On</option>
                      <option value="off">Off</option>
                    </select>
                  </label>
                  <label>
                    Mode
                    <select value={row.mode || "heat"} onChange={(event) => updateSchedule(row.id, "mode", event.target.value)}>
                      {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <label>
                    Target
                    <input type="number" min="8" max="30" value={row.target_temperature ?? 23} onChange={(event) => updateSchedule(row.id, "target_temperature", event.target.value)} />
                  </label>
                  <label>
                    Fan
                    <select value={row.fan_speed || "auto"} onChange={(event) => updateSchedule(row.id, "fan_speed", event.target.value)}>
                      {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                    </select>
                  </label>
                  <div className="climate-schedule-actions">
                    <IconButton icon={Save} disabled={busy === String(row.id)} onClick={() => saveSchedule(row)}>{busy === String(row.id) ? "Saving" : "Save"}</IconButton>
                    <IconButton icon={Trash2} disabled={busy === `delete-${row.id}`} onClick={() => deleteSchedule(row)}>{busy === `delete-${row.id}` ? "Deleting" : "Delete"}</IconButton>
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function openingSensorsByRoom(openingSensors = []) {
  return openingSensors.reduce((acc, sensor) => {
    const key = roomKey(sensor.location);
    if (!key || key === "unassigned") return acc;
    if (!acc.has(key)) acc.set(key, []);
    acc.get(key).push(sensor);
    return acc;
  }, new Map());
}

function openingSensorsForSensor(sensor, byRoom) {
  return byRoom.get(roomKey(sensor.location || sensor.entity_name || sensor.device_name)) || [];
}

function SensorSnapshotTable({ sensors = [], openingSensors = [] }) {
  const byRoom = openingSensorsByRoom(openingSensors);
  return (
    <Table
      rows={sensors}
      columns={[
        { key: "entity_name", label: "Sensor", render: (row) => roomDisplayName(row.location || row.entity_name) },
        { key: "window", label: "Window", render: (row) => <OpeningSensorIcons sensors={openingSensorsForSensor(row, byRoom)} /> },
        { key: "latest_temperature", label: "Temp", render: (row) => unitValue(row.latest_temperature, "C", 1) },
        { key: "latest_humidity", label: "RH", render: (row) => unitValue(row.latest_humidity, "%", 0) },
        { key: "latest_absolute_humidity_g_m3", label: "Abs", render: (row) => unitValue(row.latest_absolute_humidity_g_m3, "g/m3", 1) },
        { key: "latest_ts", label: "Updated", render: (row) => dateText(row.latest_ts) },
      ]}
    />
  );
}

function ClimateSensorSnapshot() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadStats(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      setStats(await api("/api/context/home_statistics?force=1"));
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
    const id = window.setInterval(() => loadStats(true), 30000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/home_statistics"], (payload) => {
    setStats(payload);
    setLoading(false);
  });

  const sensors = stats?.temp_humidity_sensors || [];
  const openingSensors = stats?.opening_sensors || [];

  return (
    <section className="panel">
      <div className="panel-head">
        <div>
          <h2>Sensor Snapshot</h2>
          <span>{error || `${sensors.length} temp/humidity sensors`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadStats()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </div>
      <SensorSnapshotTable sensors={sensors} openingSensors={openingSensors} />
    </section>
  );
}

const pilotFields = [
  ["rain_24h_threshold_mm", "Rain threshold", "mm", 0.1],
  ["forecast_rain_threshold_mm", "Forecast rain threshold", "mm", 0.1],
  ["pop_threshold_percent", "POP threshold", "%", 1],
  ["heat_threshold_c", "Heat threshold", "C", 0.1],
  ["heat_correction_percent", "Heat correction", "%", 1],
  ["cold_threshold_c", "Cool weather threshold", "C", 0.1],
  ["cold_correction_percent", "Cool weather correction", "%", 1],
  ["soil_wet_skip_threshold_percent", "Wet soil skip", "%", 1],
  ["soil_dry_threshold_percent", "Dry soil threshold", "%", 1],
  ["soil_dry_correction_percent", "Dry soil correction", "%", 1],
  ["soil_sample_max_age_hours", "Soil max age", "h", 1],
];

function ruleText(rules = []) {
  if (!Array.isArray(rules) || !rules.length) return "-";
  return rules.join(", ");
}

function decisionStatusText(row = {}) {
  const status = row.execution_status || (row.executed ? "completed" : "not_executed");
  const labels = {
    completed: "completed",
    command_sent: "command sent",
    no_physical_watering: "no physical watering",
    navigator_only: "recommendation only",
    skipped: "skipped",
    failed: "failed",
    manual_evaluation: "test log",
    not_executed: "not executed",
  };
  return labels[status] || status;
}

function PilotSummaryCards({ fallbackMode = "-", fallbackAge = "-" }) {
  const [state, setState] = useState(null);
  const [error, setError] = useState("");

  async function loadPilot() {
    try {
      setState(await api("/api/context/irrigation_pilot"));
      setError("");
    } catch (err) {
      setError(err.message);
    }
  }

  useEffect(() => {
    loadPilot();
  }, []);
  useContextRefresh(["/api/context/irrigation_pilot"], (payload) => {
    setState(payload);
  });

  const forecastDecision = state?.recommendation || {};
  const inputs = forecastDecision.details?.inputs || {};
  const rules = forecastDecision.triggered_rules || [];
  const mode = state?.config?.mode;
  const pilotModeText = mode === "pilot" ? "Pilot" : mode === "navigator" ? "Navigator" : "Pilot";
  const fallbackText = fallbackMode && fallbackMode !== "-" ? fallbackMode : "Fallback";
  const rainSensorWet = inputs.RainSensorWet === true ? "WET" : inputs.RainSensorWet === false ? "DRY" : "-";
  const rainSensorMeta = inputs.RainSensorLastWet ? `last wet: ${dateText(inputs.RainSensorLastWet)}` : `battery ${unitValue(inputs.RainSensorBattery, "%", 0)} | lqi ${numberText(inputs.RainSensorLinkquality, 0)}`;

  return (
    <>
      <Card title="Mode" value={`${pilotModeText} | ${fallbackText}`} meta={error || `Fallback age ${fallbackAge}`} icon={Settings} />
      <Card title="Current forecast" value={unitValue(forecastDecision.final_duration, "min", 0)} meta={error || ruleText(rules)} icon={Droplets} />
      <Card title="Rain sensor" value={rainSensorWet} meta={error || rainSensorMeta} icon={CloudRain} />
    </>
  );
}

function PilotDashboard({ setToast }) {
  const [state, setState] = useState(null);
  const [draft, setDraft] = useState({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function loadPilot() {
    setLoading(true);
    setError("");
    try {
      const data = await api("/api/context/irrigation_pilot");
      setState(data);
      setDraft(data.config || {});
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPilot();
  }, []);
  useContextRefresh(["/api/context/irrigation_pilot"], (payload) => {
    setState(payload);
    setDraft(payload.config || {});
    setLoading(false);
  });

  function updateDraft(key, value) {
    setDraft((current) => ({ ...current, [key]: value }));
  }

  async function saveConfig() {
    setBusy("save");
    try {
      const payload = Object.fromEntries(Object.entries(draft).filter(([key]) => key !== "base_duration_minutes"));
      await api("/api/irrigation/pilot/config", {
        method: "PUT",
        body: JSON.stringify(payload),
      });
      setToast("Pilot config saved");
      await loadPilot();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function fetchWeather() {
    setBusy("weather");
    try {
      await api("/api/irrigation/weather/fetch", { method: "POST", body: "{}" });
      setToast("Weather refreshed");
      await loadPilot();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function createDecision() {
    setBusy("decision");
    try {
      await api("/api/irrigation/pilot/evaluate", { method: "POST", body: "{}" });
      setToast("Decision logged");
      await loadPilot();
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading pilot...</span>
      </section>
    );
  }

  const recommendation = state?.recommendation || {};
  const todayDecision = state?.today_decision || null;
  const forecastDecision = recommendation;
  const weather = state?.weather || {};
  const latestWeather = weather.latest || {};
  const forecastDetails = forecastDecision.details || {};
  const inputs = forecastDetails.inputs || {};
  const ruleState = forecastDetails.rules || {};
  const result = forecastDetails.result || {};
  const rules = forecastDecision.triggered_rules || [];
  const baseSchedule = forecastDecision.base_schedule || forecastDetails.result?.base_schedule || null;
  const baseMeta = baseSchedule
    ? `${baseSchedule.label || "Scheduler"} ${baseSchedule.start_time || ""}-${baseSchedule.stop_time || ""}`
    : ["config_fallback", "legacy_config_fallback"].includes(forecastDecision.base_source)
      ? "no active scheduler, config fallback"
      : "scheduler duration";
  const rainSensorWet = inputs.RainSensorWet === true ? "WET" : inputs.RainSensorWet === false ? "DRY" : "-";
  const soilEnabled = draft.soil_moisture_enabled !== false && draft.soil_moisture_enabled !== "false";
  const soilBinding = processBinding(state, "irrigation_soil_moisture");
  const selectedSoilSensor = entitySelectLabel(soilBinding.selected_entity);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Pilot</h2>
          <span>{error || (weather.openweather_configured ? `OpenWeather OK | last ${dateText(latestWeather.ts)}` : "OpenWeather config missing")}</span>
        </div>
        <div className="button-row compact pilot-actions">
          <IconButton icon={CloudRain} title="Fetch and store OpenWeather data now" onClick={fetchWeather} disabled={Boolean(busy)}>{busy === "weather" ? "Refreshing" : "Refresh weather"}</IconButton>
          <IconButton icon={Save} title="Store the current calculation in the decision log without sending a control command" onClick={createDecision} disabled={Boolean(busy)}>{busy === "decision" ? "Logging" : "Test log"}</IconButton>
          <IconButton icon={RefreshCw} title="Reload pilot page data" onClick={loadPilot} disabled={loading}>{loading ? "Refreshing" : "Refresh page"}</IconButton>
        </div>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Status</h2>
            <span>Navigator / Pilot</span>
          </div>
          <div className="mode-toggle">
            <button className={draft.mode !== "pilot" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => updateDraft("mode", "navigator")}>Navigator</button>
            <button className={draft.mode === "pilot" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => updateDraft("mode", "pilot")}>Pilot</button>
          </div>
          <div className="pilot-reason">
            <strong>{forecastDecision.reason || "-"}</strong>
          </div>
          <div className="button-row">
            <IconButton icon={Save} onClick={saveConfig} disabled={Boolean(busy)}>{busy === "save" ? "Saving" : "Save config"}</IconButton>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Parameters</h2>
            <span>{selectedSoilSensor === "-" ? "rule engine thresholds" : `sensor ${selectedSoilSensor}`}</span>
          </div>
          <div className="pilot-form">
            <label>
              <span>Soil moisture enabled</span>
              <input
                type="checkbox"
                checked={soilEnabled}
                onChange={(event) => updateDraft("soil_moisture_enabled", event.target.checked)}
              />
            </label>
            {pilotFields.map(([key, label, unit, step]) => (
              <label key={key}>
                <span>{label} ({unit})</span>
                <input
                  type="number"
                  step={step}
                  value={draft[key] ?? ""}
                  onChange={(event) => updateDraft(key, event.target.value)}
                />
              </label>
            ))}
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current prediction</h2>
            <span>what would happen if watering started now</span>
          </div>
          <div className="decision-grid">
            <div><span>Scheduler base</span><strong>{unitValue(forecastDecision.base_duration, "min", 0)}</strong></div>
            <div><span>Pilot recommendation</span><strong>{unitValue(forecastDecision.final_duration, "min", 0)}</strong></div>
            <div><span>Executed</span><strong>NO</strong></div>
            <div><span>Active rules</span><strong>{ruleText(rules)}</strong></div>
          </div>
          <div className="pilot-reason muted-block">{forecastDecision.reason || "-"}</div>
          {todayDecision && (
            <div className="pilot-reason muted-block">
              Last final decision: {unitValue(todayDecision.final_duration, "min", 0)} | {decisionStatusText(todayDecision)} | {dateText(todayDecision.timestamp)}
            </div>
          )}
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Detailed decision info</h2>
            <span>inputs and result</span>
          </div>
          <Table
            rows={[
              { key: "Rain24h", value: unitValue(inputs.Rain24h, "mm", 1) },
              { key: "ForecastRain", value: unitValue(inputs.ForecastRain, "mm", 1) },
              { key: "POP", value: unitValue(inputs.POP, "%", 0) },
              { key: "Temperature", value: unitValue(inputs.Temperature, "C", 1) },
              { key: "Humidity", value: unitValue(inputs.Humidity, "%", 0) },
              { key: "Wind", value: unitValue(inputs.Wind, "m/s", 1) },
              { key: "Yard temperature", value: unitValue(inputs.LocalTemperature, "C", 1) },
              { key: "Yard humidity", value: unitValue(inputs.LocalHumidity, "%", 0) },
              { key: "Yard absolute humidity", value: unitValue(inputs.LocalAbsoluteHumidity, "g/m3", 1) },
              { key: "Rain sensor wet", value: rainSensorWet },
              { key: "Rain sensor last wet", value: inputs.RainSensorLastWet ? dateText(inputs.RainSensorLastWet) : "-" },
              { key: "Rain sensor battery", value: unitValue(inputs.RainSensorBattery, "%", 0) },
              { key: "Rain sensor linkquality", value: numberText(inputs.RainSensorLinkquality, 0) },
              { key: "Garden soil sensor", value: inputs.SoilSensor || "-" },
              { key: "Garden soil moisture", value: unitValue(inputs.SoilMoisture, "%", 0) },
              { key: "Garden soil sample age", value: unitValue(inputs.SoilMoistureAgeHours, "h", 1) },
              { key: "Garden soil samples 24h", value: numberText(inputs.SoilMoistureSampleCount24h, 0) },
              { key: "Garden soil avg 24h", value: unitValue(inputs.SoilMoistureAvg24h, "%", 0) },
              { key: "Garden soil usable", value: inputs.SoilMoistureUsable ? "YES" : "NO" },
            ]}
            columns={[
              { key: "key", label: "Input" },
              { key: "value", label: "Value" },
            ]}
          />
          <div className="rule-list">
            {["rain_skip", "forecast_skip", "soil_wet_skip", "soil_dry_increase", "heat_increase", "cold_decrease"].map((name) => (
              <span className={ruleState[name] ? "active" : ""} key={name}>{name}</span>
            ))}
          </div>
          <div className="pilot-result">
            <span>Base duration: {unitValue(result.base_duration, "min", 0)} ({baseMeta})</span>
            <span>Corrections: {shortValue(result.corrections || [])}</span>
            <span>Final duration: {unitValue(result.final_duration, "min", 0)}</span>
          </div>
        </article>
      </section>

    </>
  );
}

function PilotHistory() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadPilot() {
    setLoading(true);
    setError("");
    try {
      setState(await api("/api/context/irrigation_pilot"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPilot();
  }, []);

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading pilot history...</span>
      </section>
    );
  }

  const weather = state?.weather || {};
  const latestWeather = weather.latest || {};
  const weatherEndpoint = latestWeather.raw?.endpoint || latestWeather.raw?.payload?.endpoint || latestWeather.raw?.source;
  const uvText = latestWeather.uv_index === null || latestWeather.uv_index === undefined ? "Not available" : numberText(latestWeather.uv_index, 1);
  const uvMeta = weatherEndpoint ? `${uvText} (${weatherEndpoint})` : uvText;

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Pilot History</h2>
          <span>{error || `${state?.decisions?.length || 0} decisions | weather ${latestWeather.ts ? dateText(latestWeather.ts) : "not available"}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadPilot} disabled={loading}>{loading ? "Refreshing" : "Refresh pilot history"}</IconButton>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Weather snapshot</h2>
          <span>stored OpenWeatherMap data</span>
        </div>
        <Table
          rows={[latestWeather].filter((row) => row && row.id)}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "temperature_c", label: "Temp C" },
            { key: "humidity_percent", label: "RH %" },
            { key: "wind_speed_mps", label: "Wind" },
            { key: "rain_mm", label: "Rain" },
            { key: "forecast_rain_24h_mm", label: "Forecast rain" },
            { key: "forecast_pop_max_percent", label: "POP" },
            { key: "uv_index", label: "UV", render: () => uvMeta },
            { key: "cloudiness_percent", label: "Cloud" },
            { key: "pressure_hpa", label: "Pressure" },
            { key: "sunrise", label: "Sunrise", render: (row) => dateText(row.sunrise) },
            { key: "sunset", label: "Sunset", render: (row) => dateText(row.sunset) },
          ]}
        />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Decision log</h2>
          <span>{state?.decisions?.length || 0} entries</span>
        </div>
        <Table
          rows={state?.decisions || []}
          columns={[
            { key: "timestamp", label: "Time", render: (row) => dateText(row.timestamp) },
            { key: "mode", label: "Mode" },
            { key: "base_duration", label: "Base" },
            { key: "final_duration", label: "Final" },
            { key: "execution_status", label: "Status", render: (row) => decisionStatusText(row) },
            { key: "triggered_rules", label: "Rules", render: (row) => ruleText(row.triggered_rules) },
            { key: "reason", label: "Reason" },
          ]}
        />
      </section>
    </>
  );
}

function IrrigationDiagnostics() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadDiagnostics() {
    setLoading(true);
    setError("");
    try {
      setState(await api("/api/context/irrigation"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDiagnostics();
  }, []);
  useContextRefresh(["/api/context/irrigation"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  const live = state?.live || {};
  const topicRows = Object.entries(live.topics || {}).map(([name, item]) => ({ name, item }));
  const rawRows = live.raw || [];

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Diagnostics</h2>
          <span>{error || `${topicRows.length} live topics | ${rawRows.length} raw messages`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadDiagnostics} disabled={loading}>{loading ? "Refreshing" : "Refresh diagnostics"}</IconButton>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>DB Current State</h2>
          <span>entity_state</span>
        </div>
        <Table
          rows={state?.latest || []}
          columns={[
            { key: "entity_name", label: "Entity", render: (row) => displayEntityName(row.entity_name) },
            { key: "key", label: "Key" },
            { key: "value", label: "Value", render: valueText },
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Live MQTT Topics</h2>
            <span>MQTT snapshot</span>
          </div>
          <Table
            rows={topicRows}
            columns={[
              { key: "name", label: "Name" },
              { key: "age", label: "Age", render: (row) => ageText(row.item) },
              { key: "value", label: "Last value", render: (row) => row.item ? shortValue(row.item.json ?? row.item.payload) : "-" },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Raw MQTT Monitor</h2>
            <span>{rawRows.length} messages</span>
          </div>
          <Table
            rows={rawRows}
            columns={[
              { key: "age", label: "Age", render: (row) => `${row.age_sec} s` },
              { key: "topic", label: "Topic" },
              { key: "payload", label: "Payload", render: (row) => shortValue(row.json ?? row.payload, 180) },
            ]}
          />
        </article>
      </section>
    </>
  );
}

function IrrigationStatistics() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [moistureWindow, setMoistureWindow] = useState("24h");

  async function loadStats() {
    setLoading(true);
    setError("");
    try {
      setStats(await api("/api/context/irrigation_statistics"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
  }, []);
  useContextRefresh(["/api/context/irrigation_statistics"], (payload) => {
    setStats(payload);
    setLoading(false);
  });

  if (loading && !stats) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading statistics...</span>
      </section>
    );
  }

  const tank24 = stats?.tank_24h || [];
  const tankDaily = stats?.tank_daily || [];
  const soilMoisture24h = (stats?.soil_moisture_24h || []).slice(0, 2);
  const soilMoisture7d = (stats?.soil_moisture_7d || []).slice(0, 2);
  const soilMoistureSensors = moistureWindow === "7d" ? soilMoisture7d : soilMoisture24h;
  const moistureWindowLabel = moistureWindow === "7d" ? "7d" : "24h";
  const pumpDaily = stats?.pump_daily || [];
  const solarDaily = stats?.solar_daily || [];
  const tempDaily = stats?.temp_daily || [];
  const sessions = stats?.sessions || [];
  const latestTank = [...tank24].reverse().find((row) => metricNumber(row, "level_percent") !== null);
  const todayPump = pumpDaily[0] || {};
  const todaySolar = solarDaily[0] || {};
  const latestSession = sessions[0] || null;
  const latestTankDepth = metricNumber(latestTank, "depth_m");
  const latestTankDepthText = latestTankDepth === null ? "-" : unitValue(latestTankDepth * 100, "cm", 0);
  const soilMoistureMeta = (sensor) => {
    if (!sensor) return "No soil moisture sensor";
    if (!sensor.sample_count) {
      return sensor.latest_ts
        ? `No ${moistureWindowLabel} samples | last ${unitValue(sensor.latest_soil_moisture, "%", 0)} at ${timestampLabel(sensor.latest_ts)}`
        : `No ${moistureWindowLabel} samples`;
    }
    return `Latest ${unitValue(sensor.latest_soil_moisture, "%", 0)} | min ${unitValue(sensor.min_soil_moisture, "%", 0)} | max ${unitValue(sensor.max_soil_moisture, "%", 0)}`;
  };
  const renderMoistureWindowSwitch = () => (
    <div className="mode-switch moisture-range-switch" aria-label="Moisture chart range">
      <button className={moistureWindow === "24h" ? "active" : ""} type="button" onClick={() => setMoistureWindow("24h")}>24h</button>
      <button className={moistureWindow === "7d" ? "active" : ""} type="button" onClick={() => setMoistureWindow("7d")}>7d</button>
    </div>
  );

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Irrigation Statistics</h2>
          <span>{error || `${tank24.length} tank samples | ${soilMoistureSensors.reduce((sum, sensor) => sum + (sensor.sample_count || 0), 0)} soil samples | ${pumpDaily.length} pump days`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadStats} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles">
        <Card title="Tank Now" value={unitValue(latestTank?.level_percent, "%", 0)} meta={latestTank ? `${latestTankDepthText} | ${timestampLabel(latestTank.ts)}` : "No 24h tank sample"} icon={Droplets} />
        <Card title="Pump Today" value={unitValue(todayPump.pump_running_minutes, "min", 0)} meta={`${unitValue(todayPump.watt_hours, "Wh", 1)} | ${unitValue(todayPump.amp_hours, "Ah", 2)}`} icon={Activity} />
        <Card title="Solar Today" value={unitValue(todaySolar.charge_amp_hours, "Ah", 2)} meta={`${unitValue(todaySolar.avg_battery_voltage_v, "V", 2)} avg bat | max ${unitValue(todaySolar.max_charge_current_a, "A", 1)}`} icon={BatteryCharging} />
        <Card title="Last Cycle" value={latestSession ? unitValue(latestSession.duration_minutes, "min", 1) : "-"} meta={latestSession ? `${latestSession.started_by || "-"} | ${dateText(latestSession.started_at)}` : "No sessions"} icon={Clock} />
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Tank Level, 24h</h2>
            <span>{latestTank ? `Latest ${unitValue(latestTank.level_percent, "%", 0)} at ${timestampLabel(latestTank.ts)}` : "No data"}</span>
          </div>
          <StatLineChart rows={tank24} yKey="level_percent" unit="%" digits={0} color="accent" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Pump Runtime / Day</h2>
            <span>{unitValue(todayPump.amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={pumpDaily} valueKey="pump_running_minutes" unit="min" digits={0} color="accent" />
        </article>
      </section>

      <section className="grid two stats-grid">
        {[0, 1].map((index) => {
          const sensor = soilMoistureSensors[index];
          const label = sensor?.entity_name || sensor?.device_name || `Soil Moisture ${index + 1}`;
          return (
            <article className="panel chart-panel" key={sensor?.entity_id || `soil-moisture-${index}`}>
              <div className="panel-head">
                <h2>{label}, {moistureWindowLabel}</h2>
                <span>{soilMoistureMeta(sensor)}</span>
                {renderMoistureWindowSwitch()}
              </div>
              <TimeLineChart rows={sensor?.samples || []} valueKey="soil_moisture" unit="%" digits={0} color={index === 0 ? "green" : "blue"} yMin={0} yMax={100} smooth />
            </article>
          );
        })}
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Pump Consumption / Day</h2>
            <span>{unitValue(todayPump.amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={pumpDaily} valueKey="amp_hours" unit="Ah" digits={2} color="blue" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Solar Charge / Day</h2>
            <span>{unitValue(todaySolar.charge_amp_hours, "Ah", 2)} today</span>
          </div>
          <StatBarChart rows={solarDaily} valueKey="charge_amp_hours" unit="Ah" digits={2} color="yellow" />
        </article>
      </section>

      <section className="grid two stats-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Battery Voltage / Day</h2>
            <span>{unitValue(todaySolar.min_battery_voltage_v, "V", 2)} min | {unitValue(todaySolar.avg_battery_voltage_v, "V", 2)} avg | {unitValue(todaySolar.max_battery_voltage_v, "V", 2)} max today</span>
          </div>
          <StatNormalizedMultiLineChart
            rows={solarDaily.slice().reverse()}
            height={250}
            series={[
              { key: "min_battery_voltage_v", label: "Min", unit: "V", digits: 2, color: "blue" },
              { key: "avg_battery_voltage_v", label: "Avg", unit: "V", digits: 2, color: "green" },
              { key: "max_battery_voltage_v", label: "Max", unit: "V", digits: 2, color: "red" },
            ]}
          />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Controller Max Temp / Day</h2>
            <span>Daily electronics temperature peak</span>
          </div>
          <StatBarChart rows={tempDaily} valueKey="max_controller_temp_c" unit="C" digits={1} color="red" />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Daily Pump</h2>
            <span>Runtime and consumption</span>
          </div>
          <Table
            rows={pumpDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "pump_running_minutes", label: "Run min" },
              { key: "watt_hours", label: "Wh" },
              { key: "amp_hours", label: "Ah" },
              { key: "max_current_a", label: "Max A" },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Daily Solar</h2>
            <span>Charge current and battery voltage</span>
          </div>
          <Table
            rows={solarDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "charge_amp_hours", label: "Solar Ah" },
              { key: "avg_battery_voltage_v", label: "Avg bat V" },
              { key: "min_battery_voltage_v", label: "Min bat V" },
              { key: "max_charge_current_a", label: "Max chg A" },
            ]}
          />
          <div className="table-spacer" />
          <div className="panel-subhead">
            <h3>Daily Tank</h3>
            <span>Ultrasonic level summary</span>
          </div>
          <Table
            rows={tankDaily}
            columns={[
              { key: "day", label: "Day", render: (row) => dayLabel(row.day) },
              { key: "avg_level_percent", label: "Avg %" },
              { key: "min_level_percent", label: "Min %" },
              { key: "max_level_percent", label: "Max %" },
              { key: "avg_depth_m", label: "Avg depth m" },
            ]}
          />
        </article>
      </section>

      <PilotHistory />
      <IrrigationDiagnostics />
    </>
  );
}

function tuyaStateValue(device, key) {
  const item = device?.state?.[key];
  return item ? item.value : undefined;
}

function tuyaValueText(value, digits = 1) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "boolean") return value ? "on" : "off";
  const number = Number(value);
  if (Number.isFinite(number)) return number.toLocaleString("en-GB", { maximumFractionDigits: digits });
  return String(value);
}

function tuyaMetric(device, key, suffix = "", digits = 1) {
  const value = tuyaStateValue(device, key);
  const text = tuyaValueText(value, digits);
  return text === "-" ? text : `${text}${suffix}`;
}

function TuyaPlayground() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [error, setError] = useState("");

  async function loadTuya(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      setState(await api("/api/context/tuya"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadTuya();
    const id = window.setInterval(() => loadTuya(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/tuya"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function setTuyaSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/tuya/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      window.setTimeout(() => loadTuya(true), 1200);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  const devices = state?.devices || [];
  const batteryDevices = state?.battery_devices || [];
  const summary = state?.summary || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const totalPower = devices.reduce((sum, device) => sum + (Number(tuyaStateValue(device, "power_w")) || 0), 0);
  const onlineCount = Number(summary.online || 0);
  const degradedCount = Number(summary.degraded || 0);

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Tuya</h2>
          <span>{error || `${devices.length} active device | ${onlineCount} online | ${degradedCount} degraded`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadTuya} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles tuya-summary">
        <Card title="Devices" value={String(summary.total ?? devices.length)} meta={`${onlineCount} online`} icon={Power} />
        <Card title="Degraded" value={String(degradedCount)} meta="poller availability" tone={degradedCount ? "warn" : ""} icon={Activity} />
        <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power_w" icon={Gauge} />
        <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
      </section>

      <section className="tuya-device-grid">
        {devices.map((device) => {
          const status = device.status || "unknown";
          const isDegraded = status === "degraded";
          const isOffline = status === "offline";
          const switchState = tuyaStateValue(device, "switch_state");
          const canCommand = status === "online";
          return (
            <article className={`panel tuya-device ${isOffline ? "bad" : isDegraded ? "warn" : ""}`} key={device.entity_id}>
              <div className="panel-head">
                <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {displayEntityName(device.entity_name)}</h2>
                <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
              </div>
              <div className="tuya-device-meta">
                <span>{device.topic_base}</span>
                <span>{device.ext_id || "-"}</span>
                <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
              </div>
              <div className="tuya-metrics">
                <div><span>Switch</span><strong>{tuyaMetric(device, "switch_state")}</strong></div>
                <div><span>Power</span><strong>{tuyaMetric(device, "power_w", " W", 1)}</strong></div>
                <div><span>Voltage</span><strong>{tuyaMetric(device, "voltage_v", " V", 1)}</strong></div>
                <div><span>Current</span><strong>{tuyaMetric(device, "current_a", " A", 3)}</strong></div>
                <div><span>Energy</span><strong>{tuyaMetric(device, "energy_kwh", " kWh", 2)}</strong></div>
                <div><span>Lag</span><strong>{tuyaMetric(device, "lag_sec", " s", 0)}</strong></div>
              </div>
              <div className="tuya-actions">
                <IconButton
                  icon={Power}
                  className={switchState === true ? "secondary" : ""}
                  disabled={!canCommand || Boolean(busy)}
                  onClick={() => setTuyaSwitch(device, true)}
                >
                  {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
                </IconButton>
                <IconButton
                  icon={Power}
                  className={switchState === false ? "secondary" : ""}
                  disabled={!canCommand || Boolean(busy)}
                  onClick={() => setTuyaSwitch(device, false)}
                >
                  {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
                </IconButton>
              </div>
            </article>
          );
        })}
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current State Rows</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "value", label: "Value", render: valueText },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Measurements</h2>
            <span>last 6 hours</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
              { key: "min_num", label: "Min", render: (row) => tuyaValueText(row.min_num, 2) },
              { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>
    </>
  );
}

function powerWallValue(device, keys) {
  for (const key of keys) {
    const value = tuyaStateValue(device, key);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

function powerWallMetricText(value, suffix = "", digits = 1) {
  const text = tuyaValueText(value, digits);
  return text === "-" ? text : `${text}${suffix}`;
}

function PowerWallMiniChart({ rows = [] }) {
  const points = rows
    .map((row) => ({ ts: row.ts, value: metricNumber(row, "power_w") }))
    .filter((point) => point.value !== null)
    .map((point, index) => ({ ...point, index }));
  const width = 360;
  const height = 150;
  const pad = { top: 18, right: 14, bottom: 26, left: 38 };
  if (!points.length) return <div className="power-wall-popover-empty">No 24h power samples</div>;

  const max = Math.max(...points.map((point) => point.value), 1);
  const min = Math.min(...points.map((point) => point.value), 0);
  const span = Math.max(max - min, 1);
  const xMax = Math.max(points.length - 1, 1);
  const x = (index) => pad.left + (index / xMax) * (width - pad.left - pad.right);
  const y = (value) => pad.top + ((max - value) / span) * (height - pad.top - pad.bottom);
  const path = points.map((point, index) => `${index ? "L" : "M"} ${x(index).toFixed(1)} ${y(point.value).toFixed(1)}`).join(" ");
  const latest = points[points.length - 1];
  const first = points[0];

  return (
    <svg className="power-wall-mini-chart" viewBox={`0 0 ${width} ${height}`} role="img" aria-label="Power use in the last 24 hours">
      <line x1={pad.left} y1={pad.top} x2={pad.left} y2={height - pad.bottom} />
      <line x1={pad.left} y1={height - pad.bottom} x2={width - pad.right} y2={height - pad.bottom} />
      <text x={6} y={pad.top + 4}>{unitValue(max, "W", 0)}</text>
      <text x={6} y={height - pad.bottom}>{unitValue(min, "W", 0)}</text>
      <text x={pad.left} y={height - 8}>{timestampLabel(first.ts)}</text>
      <text x={width - pad.right - 42} y={height - 8}>{timestampLabel(latest.ts)}</text>
      <path d={path} />
      <circle cx={x(latest.index)} cy={y(latest.value)} r="4" />
    </svg>
  );
}

function PowerWallPowerMetric({ device, value, history, loadHistory }) {
  const rows = history?.data?.power_24h || [];
  const summary = history?.data?.summary || {};

  function requestHistory() {
    loadHistory(device.entity_id);
  }

  return (
    <div
      className="power-wall-metric-hover"
      tabIndex={0}
      onMouseEnter={requestHistory}
      onFocus={requestHistory}
    >
      <span>Power</span>
      <strong>{powerWallMetricText(value, " W", 1)}</strong>
      <div className="power-wall-popover">
        <div className="power-wall-popover-head">
          <strong>{powerWallDisplayName(device)}</strong>
          <span>{history?.loading ? "loading..." : `${summary.samples || rows.length} samples | 24h`}</span>
        </div>
        {history?.error ? (
          <div className="power-wall-popover-empty">{history.error}</div>
        ) : history?.loading && !rows.length ? (
          <div className="power-wall-popover-empty">Loading chart...</div>
        ) : (
          <PowerWallMiniChart rows={rows} />
        )}
      </div>
    </div>
  );
}

function switchOn(value) {
  if (value === true) return true;
  if (value === false) return false;
  const text = String(value ?? "").trim().toUpperCase();
  if (text === "ON" || text === "TRUE" || text === "1") return true;
  if (text === "OFF" || text === "FALSE" || text === "0") return false;
  return null;
}

function powerWallDisplayName(device = {}) {
  return displayEntityName(device.display_name || device.entity_name || device.device_name);
}

function PowerWall({ variant = "v1" }) {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [displayNameBusy, setDisplayNameBusy] = useState("");
  const [displayNameEditor, setDisplayNameEditor] = useState(null);
  const [historyByEntity, setHistoryByEntity] = useState({});
  const [error, setError] = useState("");

  async function loadPowerWall(silent = false) {
    if (!silent) setLoading(true);
    setError("");
    try {
      setState(await api("/api/context/power_wall"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPowerWall();
    const id = window.setInterval(() => loadPowerWall(true), 10000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/power_wall"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function setPowerWallSwitch(device, value) {
    const busyKey = `${device.entity_id}:${value ? "on" : "off"}`;
    setBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/command", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, value }),
      });
      window.setTimeout(() => loadPowerWall(true), 1200);
    } catch (err) {
      setError(err.message);
    } finally {
      setBusy("");
    }
  }

  async function setPowerWallAlwaysOn(device, alwaysOn) {
    const busyKey = `${device.entity_id}:always-on`;
    setPolicyBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/policy", {
        method: "POST",
        body: JSON.stringify({ entity_id: device.entity_id, always_on: alwaysOn }),
      });
      await loadPowerWall(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setPolicyBusy("");
    }
  }

  function editPowerWallDisplayName(device) {
    setDisplayNameEditor({
      entityId: device.entity_id,
      value: device.power_wall_display_name || device.display_name || device.entity_name || "",
    });
  }

  async function savePowerWallDisplayName(device) {
    const busyKey = `${device.entity_id}:display-name`;
    const value = String(displayNameEditor?.value || "").trim();
    setDisplayNameBusy(busyKey);
    setError("");
    try {
      await api("/api/power-wall/display-name", {
        method: "PUT",
        body: JSON.stringify({ entity_id: device.entity_id, display_name: value || null }),
      });
      setDisplayNameEditor(null);
      await loadPowerWall(true);
    } catch (err) {
      setError(err.message);
    } finally {
      setDisplayNameBusy("");
    }
  }

  async function loadPowerWallHistory(entityId) {
    if (!entityId || historyByEntity[entityId]?.data || historyByEntity[entityId]?.loading) return;
    setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: true, error: "", data: null } }));
    try {
      const data = await api(`/api/power-wall/history?entity_id=${encodeURIComponent(entityId)}`);
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: "", data } }));
    } catch (err) {
      setHistoryByEntity((current) => ({ ...current, [entityId]: { loading: false, error: err.message, data: null } }));
    }
  }

  const devices = state?.devices || [];
  const batteryDevices = state?.battery_devices || [];
  const summary = state?.summary || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const totalPower = devices.reduce((sum, device) => sum + (Number(powerWallValue(device, ["power_w", "power"])) || 0), 0);
  const onlineCount = Number(summary.online || 0);
  const degradedCount = Number(summary.degraded || 0);
  const isV2 = variant === "v2";

  const content = (
    <>
      {isV2 ? (
        <V2Toolbar>
          <div>
            <h2>Power Wall</h2>
            <span>{error || `${devices.length} socket | ${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya | ${onlineCount} online`}</span>
          </div>
          <IconButton icon={RefreshCw} onClick={loadPowerWall} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
        </V2Toolbar>
      ) : (
        <section className="stats-head">
          <div>
            <h2>Power Wall</h2>
            <span>{error || `${devices.length} socket | ${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya | ${onlineCount} online`}</span>
          </div>
          <IconButton icon={RefreshCw} onClick={loadPowerWall} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
        </section>
      )}

      {isV2 ? (
        <V2KpiRow className="power-wall-summary">
          <Card title="Sockets" value={String(summary.total ?? devices.length)} meta={`${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya`} icon={Power} />
          <Card title="Online" value={String(onlineCount)} meta={`${degradedCount} degraded`} tone={degradedCount ? "warn" : ""} icon={Activity} />
          <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power" icon={Gauge} />
          <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
          <Card title="Battery Devices" value={String(summary.battery_total ?? batteryDevices.length)} meta={`${summary.battery_low || 0} low`} tone={summary.battery_low ? "warn" : ""} icon={BatteryCharging} />
        </V2KpiRow>
      ) : (
        <section className="tile-grid stats-tiles tuya-summary power-wall-summary">
          <Card title="Sockets" value={String(summary.total ?? devices.length)} meta={`${summary.zigbee || 0} zigbee | ${summary.tuya || 0} tuya`} icon={Power} />
          <Card title="Online" value={String(onlineCount)} meta={`${degradedCount} degraded`} tone={degradedCount ? "warn" : ""} icon={Activity} />
          <Card title="Current Power" value={`${tuyaValueText(totalPower, 1)} W`} meta="sum of latest power" icon={Gauge} />
          <Card title="Samples" value={String(measurementRows.reduce((sum, row) => sum + Number(row.sample_count || 0), 0))} meta="last 6 hours" icon={Database} />
          <Card title="Battery Devices" value={String(summary.battery_total ?? batteryDevices.length)} meta={`${summary.battery_low || 0} low`} tone={summary.battery_low ? "warn" : ""} icon={BatteryCharging} />
        </section>
      )}

      <section className={isV2 ? "tuya-device-grid power-wall-v2-devices" : "tuya-device-grid"}>
        {devices.map((device) => {
          const status = device.status || "unknown";
          const isDegraded = status === "degraded";
          const isOffline = status === "offline";
          const switchState = powerWallValue(device, ["switch_state", "state"]);
          const switchStateOn = switchOn(switchState);
          const canCommand = ["zigbee", "tuya"].includes(device.platform) && status === "online";
          const powerValue = powerWallValue(device, ["power_w", "power"]);
          const currentValue = powerWallValue(device, ["current_a", "current"]);
          const voltageValue = powerWallValue(device, ["voltage_v", "mains_voltage_v"]);
          const energyValue = powerWallValue(device, ["energy_kwh"]);
          const lagValue = powerWallValue(device, ["lag_sec"]);
          const alwaysOn = Boolean(device.always_on);
          const isEditingDisplayName = displayNameEditor?.entityId === device.entity_id;
          return (
            <article className={`panel tuya-device ${alwaysOn ? "always-on" : ""} ${isOffline ? "bad" : isDegraded ? "warn" : ""}`} key={device.entity_id}>
              <div className="panel-head">
                <div className="power-wall-title-wrap">
                  {isEditingDisplayName ? (
                    <div className="power-wall-name-editor">
                      <Power size={17} aria-hidden="true" />
                      <input
                        value={displayNameEditor.value}
                        maxLength={80}
                        autoFocus
                        onChange={(event) => setDisplayNameEditor((current) => ({ ...current, value: event.target.value }))}
                        onKeyDown={(event) => {
                          if (event.key === "Enter") savePowerWallDisplayName(device);
                          if (event.key === "Escape") setDisplayNameEditor(null);
                        }}
                      />
                      <IconButton
                        icon={Save}
                        className="secondary compact-icon-button"
                        disabled={displayNameBusy === `${device.entity_id}:display-name`}
                        onClick={() => savePowerWallDisplayName(device)}
                      >
                        Save
                      </IconButton>
                    </div>
                  ) : (
                    <h2 className="panel-title"><Power size={17} aria-hidden="true" /> {powerWallDisplayName(device)}</h2>
                  )}
                  {!isEditingDisplayName && (
                    <IconButton
                      icon={Settings}
                      className="secondary compact-icon-button"
                      title="Edit Power Wall display name"
                      onClick={() => editPowerWallDisplayName(device)}
                    >
                      Rename
                    </IconButton>
                  )}
                </div>
                <label className="always-on-toggle" title="Keep this socket switched on">
                  <input
                    type="checkbox"
                    checked={alwaysOn}
                    disabled={policyBusy === `${device.entity_id}:always-on`}
                    onChange={(event) => setPowerWallAlwaysOn(device, event.target.checked)}
                  />
                  <span>Always on</span>
                </label>
                <div className="power-wall-badges">
                  <span className={`platform-pill ${device.platform}`}>{device.platform}</span>
                  <span className={`status-pill ${status === "online" ? "ok" : isDegraded ? "warn" : "bad"}`}>{status}</span>
                </div>
              </div>
              <div className="tuya-device-meta">
                <span>{device.topic_base}</span>
                <span>{device.ext_id || "-"}</span>
                <span>{device.last_seen_ts ? `seen ${dateText(device.last_seen_ts)}` : "not seen yet"}</span>
              </div>
              <div className="tuya-metrics">
                <div><span>Switch</span><strong>{tuyaValueText(switchState)}</strong></div>
                <PowerWallPowerMetric
                  device={device}
                  value={powerValue}
                  history={historyByEntity[device.entity_id]}
                  loadHistory={loadPowerWallHistory}
                />
                <div><span>Voltage</span><strong>{powerWallMetricText(voltageValue, " V", 1)}</strong></div>
                <div><span>Current</span><strong>{powerWallMetricText(currentValue, " A", 3)}</strong></div>
                <div><span>Energy</span><strong>{powerWallMetricText(energyValue, " kWh", 2)}</strong></div>
                <div><span>Lag</span><strong>{powerWallMetricText(lagValue, " s", 0)}</strong></div>
              </div>
              {["zigbee", "tuya"].includes(device.platform) && (
                <div className="tuya-actions">
                  <IconButton
                    icon={Power}
                    className={switchStateOn === true ? "secondary" : ""}
                    disabled={!canCommand || Boolean(busy)}
                    onClick={() => setPowerWallSwitch(device, true)}
                  >
                    {busy === `${device.entity_id}:on` ? "Turning on" : "ON"}
                  </IconButton>
                  <IconButton
                    icon={Power}
                    className={switchStateOn === false ? "secondary" : ""}
                    disabled={!canCommand || Boolean(busy)}
                    onClick={() => setPowerWallSwitch(device, false)}
                  >
                    {busy === `${device.entity_id}:off` ? "Turning off" : "OFF"}
                  </IconButton>
                </div>
              )}
            </article>
          );
        })}
      </section>

      <section className={isV2 ? "panel power-wall-v2-battery" : "panel"}>
        <div>
          <div className="panel-head">
            <h2>Battery Devices</h2>
            <span>{batteryDevices.length} device | low threshold 30%</span>
          </div>
          <Table
            rows={batteryDevices}
            columns={[
              { key: "entity_name", label: "Device", render: (row) => displayEntityName(row.entity_name) },
              { key: "location", label: "Location", render: (row) => displayEntityName(row.location) },
              { key: "platform", label: "Type" },
              {
                key: "battery_percent",
                label: "Battery",
                render: (row) => {
                  const rawValue = row.battery_percent;
                  const hasValue = rawValue !== undefined && rawValue !== null && rawValue !== "";
                  const value = Number(rawValue);
                  const isKnown = hasValue && Number.isFinite(value);
                  const low = row.battery_low === true || (isKnown && value <= 30);
                  const bad = row.battery_low === true || (isKnown && value <= 15);
                  return (
                    <span className={`status-pill ${bad ? "bad" : low ? "warn" : "ok"}`}>
                      {isKnown ? unitValue(value, "%", 0) : row.battery_low === true ? "LOW" : "-"}
                    </span>
                  );
                },
              },
              { key: "battery_low", label: "Low Flag", render: (row) => (row.battery_low === true ? "Low" : row.battery_low === false ? "OK" : "-") },
              { key: "linkquality", label: "LQI", render: (row) => numberText(row.linkquality, 0) },
              { key: "battery_ts", label: "Battery Updated", render: (row) => dateText(row.battery_ts || row.battery_low_ts) },
              { key: "last_seen_ts", label: "Last Seen", render: (row) => dateText(row.last_seen_ts) },
            ]}
          />
        </div>
      </section>

      {isV2 ? (
        <V2SectionGrid className="power-wall-v2-tables">
          <article className="panel v2-span-6">
            <div className="panel-head">
              <h2>Current Socket State</h2>
              <span>{stateRows.length} rows</span>
            </div>
            <Table
              rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
              columns={[
                { key: "platform", label: "Type" },
                { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
                { key: "key", label: "Metric" },
                { key: "value", label: "Value", render: valueText },
                { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
              ]}
            />
          </article>
          <article className="panel v2-span-6">
            <div className="panel-head">
              <h2>Recent Socket Measurements</h2>
              <span>last 6 hours</span>
            </div>
            <Table
              rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
              columns={[
                { key: "platform", label: "Type" },
                { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
                { key: "key", label: "Metric" },
                { key: "sample_count", label: "Samples" },
                { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
                { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
                { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
              ]}
            />
          </article>
        </V2SectionGrid>
      ) : (
        <section className="grid two">
          <article className="panel">
          <div className="panel-head">
            <h2>Current Socket State</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "platform", label: "Type" },
              { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "value", label: "Value", render: valueText },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Socket Measurements</h2>
            <span>last 6 hours</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.entity_id}-${row.key}-${index}` }))}
            columns={[
              { key: "platform", label: "Type" },
              { key: "display_name", label: "Socket", render: (row) => displayEntityName(row.display_name || row.entity_name) },
              { key: "key", label: "Metric" },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => tuyaValueText(row.avg_num, 2) },
              { key: "max_num", label: "Max", render: (row) => tuyaValueText(row.max_num, 2) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
          </article>
        </section>
      )}
    </>
  );

  return isV2 ? <V2Page className="power-wall-v2">{content}</V2Page> : content;
}

const solarMetricLabels = {
  system_power_w: ["System Power", "W", 0],
  output_power_w: ["Inverter Output", "W", 0],
  plant_output_power_w: ["Plant Output", "W", 0],
  energy_today_kwh: ["Energy Today", "kWh", 1],
  plant_energy_today_kwh: ["Plant Today", "kWh", 1],
  lifetime_energy_kwh: ["Lifetime Energy", "kWh", 1],
  plant_lifetime_energy_kwh: ["Plant Lifetime", "kWh", 1],
  solar_energy_today_kwh: ["Solar Today", "kWh", 1],
  lifetime_solar_energy_kwh: ["Solar Lifetime", "kWh", 1],
  battery_soc_percent: ["Battery SoC", "%", 0],
  local_load_power_w: ["Local Load", "W", 0],
  import_power_w: ["Import", "W", 0],
  export_power_w: ["Export", "W", 0],
  load_consumption_today_kwh: ["Load Today", "kWh", 1],
  export_to_grid_today_kwh: ["Export Today", "kWh", 1],
  import_from_grid_today_kwh: ["Import Today", "kWh", 1],
  self_consumption_today_kwh: ["Self Use Today", "kWh", 1],
  input_1_wattage_w: ["PV1 Power", "W", 0],
  input_2_wattage_w: ["PV2 Power", "W", 0],
  input_1_voltage_v: ["PV1 Voltage", "V", 1],
  input_2_voltage_v: ["PV2 Voltage", "V", 1],
  input_1_current_a: ["PV1 Current", "A", 1],
  input_2_current_a: ["PV2 Current", "A", 1],
  growatt_grid_voltage_l1_v: ["Grid L1 Voltage", "V", 1],
  growatt_grid_voltage_l2_v: ["Grid L2 Voltage", "V", 1],
  growatt_grid_voltage_l3_v: ["Grid L3 Voltage", "V", 1],
  growatt_grid_current_l1_a: ["Grid L1 Current", "A", 1],
  growatt_grid_current_l2_a: ["Grid L2 Current", "A", 1],
  growatt_grid_current_l3_a: ["Grid L3 Current", "A", 1],
  growatt_grid_frequency_hz: ["Grid Frequency", "Hz", 2],
  ac_frequency_hz: ["AC Frequency", "Hz", 2],
  temperature_1_c: ["Temperature", "C", 1],
  entity_count: ["Fetched Entities", "", 0],
  sample_time: ["Sample Time", "", 0],
  source: ["Source", "", 0],
};

function solarStateValue(state, key) {
  return state?.[key]?.value ?? null;
}

function solarMetricText(value, key) {
  const [, unit = "", digits = 1] = solarMetricLabels[key] || [key, "", 1];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number" || Number.isFinite(Number(value))) {
    return unit ? unitValue(Number(value), unit, digits) : numberText(Number(value), digits);
  }
  return String(value);
}

function SolarDashboard() {
  const [state, setState] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  async function loadSolar(silent = false) {
    if (!silent) setLoading(true);
    try {
      const data = await api("/api/context/solar");
      setState(data);
      setError("");
    } catch (err) {
      setError(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadSolar();
    const id = window.setInterval(() => loadSolar(true), 30000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/solar"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  const values = state?.state || {};
  const summary = state?.summary || {};
  const entity = state?.entity || {};
  const stateRows = state?.state_rows || [];
  const measurementRows = state?.recent_measurements || [];
  const chartRows = state?.charts || {};
  const loadPower24h = chartRows.load_power_24h || [];
  const productionDaily30d = chartRows.production_daily_30d || [];
  const updatedAt = summary.updated_at || entity.last_seen_ts || entity.presence_updated_at;
  const powerNow = solarStateValue(values, "system_power_w") ?? solarStateValue(values, "output_power_w") ?? solarStateValue(values, "plant_output_power_w");
  const todayEnergy = solarStateValue(values, "energy_today_kwh") ?? solarStateValue(values, "plant_energy_today_kwh");
  const lifetimeEnergy = solarStateValue(values, "plant_lifetime_energy_kwh") ?? solarStateValue(values, "lifetime_energy_kwh");
  const monthProduction = summary.production_month_kwh ?? null;
  const status = summary.status || entity.status || "unknown";
  const flowRows = [
    ["PV1", "input_1_wattage_w", "input_1_voltage_v", "input_1_current_a"],
    ["PV2", "input_2_wattage_w", "input_2_voltage_v", "input_2_current_a"],
    ["Grid", "export_power_w", "import_power_w", "ac_frequency_hz"],
    ["Load", "local_load_power_w", "load_consumption_today_kwh", "lifetime_load_consumption_kwh"],
  ].map(([name, a, b, c]) => ({
    name,
    a_key: a,
    a: solarMetricText(solarStateValue(values, a), a),
    b_key: b,
    b: solarMetricText(solarStateValue(values, b), b),
    c_key: c,
    c: solarMetricText(solarStateValue(values, c), c),
  }));

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading solar...</span>
      </section>
    );
  }

  return (
    <>
      <section className="stats-head solar-head">
        <div>
          <h2>{entity.entity_name || "Growatt Solar"}</h2>
          <span>{error || `${entity.topic_base || "homecontrol/tele/growatt/cloud"} | ${status} | updated ${dateText(updatedAt)}`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={() => loadSolar()} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles solar-summary">
        <Card title="Power Now" value={solarMetricText(powerNow, "system_power_w")} meta={`plant ${solarMetricText(solarStateValue(values, "plant_output_power_w"), "plant_output_power_w")}`} icon={Zap} tone={Number(powerNow || 0) > 0 ? "" : "warn"} />
        <Card title="Today" value={solarMetricText(todayEnergy, "energy_today_kwh")} meta={`plant ${solarMetricText(solarStateValue(values, "plant_energy_today_kwh"), "plant_energy_today_kwh")}`} icon={BatteryCharging} />
        <Card title="This Month" value={solarMetricText(monthProduction, "energy_today_kwh")} meta={`${summary.production_month_days || 0} days`} icon={CalendarDays} />
        <Card title="Lifetime" value={solarMetricText(lifetimeEnergy, "plant_lifetime_energy_kwh")} meta={solarMetricText(solarStateValue(values, "lifetime_solar_energy_kwh"), "lifetime_solar_energy_kwh")} icon={Archive} />
      </section>

      <section className="grid two solar-grid">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Consumption 24h</h2>
            <span>{loadPower24h.reduce((sum, row) => sum + Number(row.sample_count || 0), 0)} samples | hourly average</span>
          </div>
          <TimeLineChart rows={loadPower24h} valueKey="avg_load_power_w" unit="W" digits={0} color="blue" />
        </article>
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Daily Production</h2>
            <span>{productionDaily30d.length} days | monthly view</span>
          </div>
          <StatBarChart rows={productionDaily30d} valueKey="production_kwh" unit="kWh" digits={1} color="yellow" />
        </article>
      </section>

      <section className="grid solar-grid">
        <article className="panel">
          <div className="panel-head">
            <h2>Solar Flow</h2>
            <span>{summary.state_count || stateRows.length} current metrics</span>
          </div>
          <Table
            rows={flowRows}
            columns={[
              { key: "name", label: "Area" },
              { key: "a", label: "Primary" },
              { key: "b", label: "Secondary" },
              { key: "c", label: "Tertiary" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Current Solar State</h2>
            <span>{stateRows.length} rows</span>
          </div>
          <Table
            rows={stateRows.map((row, index) => ({ ...row, id: `${row.key}-${index}` }))}
            columns={[
              { key: "key", label: "Metric", render: (row) => solarMetricLabels[row.key]?.[0] || row.key },
              { key: "value", label: "Value", render: (row) => solarMetricText(row.v_num ?? row.v_text ?? row.v_json, row.key) },
              { key: "ts", label: "Updated", render: (row) => dateText(row.ts) },
            ]}
          />
        </article>
        <article className="panel">
          <div className="panel-head">
            <h2>Recent Measurements</h2>
            <span>{summary.measurement_count_24h || 0} samples in 24h</span>
          </div>
          <Table
            rows={measurementRows.map((row, index) => ({ ...row, id: `${row.key}-${index}` }))}
            columns={[
              { key: "key", label: "Metric", render: (row) => solarMetricLabels[row.key]?.[0] || row.key },
              { key: "sample_count", label: "Samples" },
              { key: "avg_num", label: "Avg", render: (row) => solarMetricText(row.avg_num, row.key) },
              { key: "max_num", label: "Max", render: (row) => solarMetricText(row.max_num, row.key) },
              { key: "last_ts", label: "Last", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>
    </>
  );
}

function HcStatistics() {
  const [stats, setStats] = useState(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadStats() {
    setLoading(true);
    setError("");
    try {
      setStats(await api("/api/context/home_statistics?force=1"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadStats();
  }, []);
  useContextRefresh(["/api/context/home_statistics"], (payload) => {
    setStats(payload);
    setLoading(false);
  });

  if (loading && !stats) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading HC statistics...</span>
      </section>
    );
  }

  const sensors = stats?.temp_humidity_sensors || [];
  const openingSensors = stats?.opening_sensors || [];
  const indoorSensors = sensors.filter((sensor) => sensor.entity_name !== "Udvar");
  const tempValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_temperature")).filter((value) => value !== null);
  const humidityValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_humidity")).filter((value) => value !== null);
  const avgTemp = tempValues.length ? tempValues.reduce((sum, value) => sum + value, 0) / tempValues.length : null;
  const avgHumidity = humidityValues.length ? humidityValues.reduce((sum, value) => sum + value, 0) / humidityValues.length : null;

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl Statistics</h2>
          <span>{error || `${sensors.length} temp/humidity sensors | 24h curves`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadStats} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles">
        <Card title="Sensors" value={sensors.length} meta="temperature / humidity" icon={Activity} />
        <Card title="Indoor Avg Temp" value={unitValue(avgTemp, "C", 1)} meta={`${indoorSensors.length} indoor sensors`} icon={Gauge} />
        <Card title="Indoor Avg Humidity" value={unitValue(avgHumidity, "%", 0)} meta={`${indoorSensors.length} indoor sensors`} icon={Droplets} />
        <Card title="Last Update" value={sensors[0] ? timestampLabel(sensors.reduce((latest, sensor) => new Date(sensor.latest_ts) > new Date(latest.latest_ts) ? sensor : latest, sensors[0]).latest_ts) : "-"} meta="newest sample" icon={Clock} />
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Sensor Snapshot</h2>
          <span>Latest temperature, relative humidity and absolute humidity</span>
        </div>
        <SensorSnapshotTable sensors={sensors} openingSensors={openingSensors} />
      </section>

      <section className="sensor-grid">
        {sensors.map((sensor) => (
          <article className="panel sensor-panel" key={sensor.entity_id}>
            <div className="panel-head">
              <h2>{displayEntityName(sensor.entity_name)}</h2>
              <span>{unitValue(sensor.latest_temperature, "C", 1)} | {unitValue(sensor.latest_humidity, "%", 0)} | {unitValue(sensor.latest_absolute_humidity_g_m3, "g/m3", 1)} | {timestampLabel(sensor.latest_ts)}</span>
            </div>
            <div className="mini-chart-title">Climate Trend</div>
            <StatNormalizedMultiLineChart
              rows={sensor.samples}
              height={190}
              series={[
                { key: "temperature", label: "Temp", unit: "C", digits: 1, color: "red" },
                { key: "humidity", label: "RH", unit: "%", digits: 0, color: "blue" },
                { key: "absolute_humidity_g_m3", label: "Abs", unit: "g/m3", digits: 1, color: "green" },
              ]}
            />
          </article>
        ))}
      </section>
    </>
  );
}

function SchedulerHub({ initialState, setToast }) {
  const [state, setState] = useState(initialState || null);
  const [loading, setLoading] = useState(!initialState);
  const [busy, setBusy] = useState("");
  const [simulationDraft, setSimulationDraft] = useState({
    domain: "irrigation",
    action: "water_start",
    schedule_id: "simulation",
    label: "Simulation",
    start_time: "17:00",
    stop_time: "18:30",
    duration_minutes: 90,
    map_id: 3,
    segments: "1",
    suction: 3,
    water_level: 2,
    power: "on",
    climate_mode: "heat",
    target_temperature: 23,
    fan_speed: "auto",
  });
  const [simulationResult, setSimulationResult] = useState(null);

  async function loadScheduler(silent = false) {
    if (!silent) setLoading(true);
    try {
      setState(await api("/api/context/scheduler"));
    } catch (err) {
      setToast(err.message);
    } finally {
      if (!silent) setLoading(false);
    }
  }

  useEffect(() => {
    loadScheduler(Boolean(initialState));
    const id = window.setInterval(() => loadScheduler(true), 5000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/scheduler"], (payload) => {
    setState(payload);
    setLoading(false);
  });

  async function setMode(mode) {
    setBusy(mode);
    try {
      const data = await api("/api/scheduler/config", {
        method: "PUT",
        body: JSON.stringify({ mode, updated_by: "react-admin" }),
      });
      setState(data.state);
      setToast(`${mode.replaceAll("_", " ")} saved; command publishing remains guarded by feature flags`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateSimulationDraft(key, value) {
    setSimulationDraft((current) => {
      const next = { ...current, [key]: value };
      if (key === "domain") {
        if (value === "irrigation") {
          next.action = "water_start";
          next.start_time = next.start_time || "17:00";
          next.stop_time = next.stop_time || "18:30";
          next.duration_minutes = next.duration_minutes || 90;
        } else if (value === "xiaomi_x10") {
          next.action = "clean_start";
          next.start_time = next.start_time || "14:00";
          next.segments = next.segments || "1";
          next.map_id = next.map_id || 3;
        } else {
          next.action = "climate_set";
          next.start_time = next.start_time || "06:30";
          next.power = next.power || "on";
          next.climate_mode = next.climate_mode || "heat";
          next.target_temperature = next.target_temperature || 23;
          next.fan_speed = next.fan_speed || "auto";
        }
      }
      return next;
    });
  }

  async function runSimulation(event) {
    event.preventDefault();
    setBusy("simulate");
    try {
      const payload = {
        ...simulationDraft,
        duration_minutes: Number(simulationDraft.duration_minutes || 0) || undefined,
        map_id: Number(simulationDraft.map_id || 0) || undefined,
        suction: Number(simulationDraft.suction || 0) || undefined,
        water_level: Number(simulationDraft.water_level || 0) || undefined,
        target_temperature: Number(simulationDraft.target_temperature || 0) || undefined,
        segments: String(simulationDraft.segments || "").split(",").map((item) => Number(item.trim())).filter(Boolean),
      };
      const data = await api("/api/v2/simulate/scheduler", {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setSimulationResult(data);
      setToast("V2 simulation complete; no rows written and no command published");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading scheduler...</span>
      </section>
    );
  }

  const config = state?.config || {};
  const summary = state?.summary || {};
  const v2 = state?.v2 || {};
  const v2Counts = v2.counts || {};
  const v2Activity = v2.activity || [];
  const v2Chains = v2.chains || [];
  const irrigationPreflight = v2.preflight?.irrigation || {};
  const x10Preflight = v2.preflight?.xiaomi_x10 || {};
  const climatePreflight = v2.preflight?.climate || {};
  const mode = config.mode || "v2_execute_all";
  const v2Modes = v2.modes || [
    { value: "v2_execute_irrigation", label: "V2 execute irrigation", command_owner: "v2" },
    { value: "v2_execute_x10", label: "V2 execute X10", command_owner: "v2" },
    { value: "v2_execute_climate", label: "V2 execute Climate", command_owner: "v2" },
    { value: "v2_execute_x10_climate", label: "V2 execute X10 + Climate", command_owner: "v2" },
    { value: "v2_execute_all", label: "V2 execute all", command_owner: "v2" },
  ];
  const executionEngine = v2.execution_engine || {};
  const modeLabel = v2Modes.find((item) => item.value === mode)?.label || mode.replaceAll("_", " ");
  const jobs = state?.jobs || [];
  const runs = state?.history || state?.runs || [];

  return (
    <>
      <section className="tile-grid scheduler-tiles">
        <Card title="V2 Scheduler" value={modeLabel} meta={executionEngine.publish_enabled ? "V2 owns scheduled publishing" : "V2 publish guarded"} icon={CalendarDays} tone={executionEngine.publish_enabled ? "" : "warn"} />
        <Card title="Known Jobs" value={String(summary.job_count || 0)} meta={`${summary.enabled_count || 0} enabled | ${(summary.domains || []).join(", ") || "-"}`} icon={Clock} />
        <Card title="V2 Events" value={String(v2Counts.events || 0)} meta={v2.available ? "EventStore ready" : "EventStore missing"} icon={Radio} />
        <Card title="V2 Plans" value={String(v2Counts.plans || 0)} meta="PlanStore audit records" icon={MapIcon} />
        <Card title="V2 Executions" value={String(v2Counts.executions || 0)} meta={executionEngine.publish_enabled ? "publish enabled" : "publish disabled"} icon={Activity} />
      </section>

      <section className="scheduler-top-layout">
        <div className="scheduler-compact-stack">
          <article className="panel">
            <div className="panel-head">
              <h2 className="panel-title"><Settings size={17} aria-hidden="true" /> V2 Runtime Switch</h2>
              <span>Publishing is blocked unless execution feature flags are enabled</span>
            </div>
            <div className="mode-switch">
              {v2Modes.map((item) => {
                const Icon = item.value.startsWith("v2_execute") ? Play : Radio;
                return (
                  <button
                    className={mode === item.value ? "active" : "secondary"}
                    type="button"
                    disabled={Boolean(busy)}
                    onClick={() => setMode(item.value)}
                    key={item.value}
                  >
                    <Icon size={16} aria-hidden="true" />
                    <span>{item.label}</span>
                  </button>
                );
              })}
            </div>
            <div className="scheduler-note">
              <strong>{executionEngine.publish_enabled ? "V2 publishing is enabled for the selected domain." : "V2 publishing is disabled by feature flags."}</strong>
              <span>{`Current command owner: ${executionEngine.command_owner || "blocked"} | reason: ${executionEngine.reason || "-"}`}</span>
            </div>
          </article>

          <article className="panel scheduler-v2-panel">
            <div className="panel-head">
              <h2 className="panel-title"><Database size={17} aria-hidden="true" /> V2 Core Stores</h2>
              <span>Event-State-Rule-Plan-Execution foundation, read-only here</span>
            </div>
            <div className="v2-store-grid">
              <div><span>EventStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
              <div><span>StateStore</span><strong>entity_state</strong></div>
              <div><span>PlanStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
              <div><span>ExecutionStore</span><strong>{v2.available ? "ready" : "missing"}</strong></div>
            </div>
            <div className="scheduler-note">
              <strong>Scheduler tab is the V2 scheduler workspace.</strong>
              <span>Execution engine enabled={String(Boolean(executionEngine.enabled))}; publish enabled={String(Boolean(executionEngine.publish_enabled))}; owner={executionEngine.command_owner || "blocked"}.</span>
            </div>
          </article>
        </div>
      </section>

      <section className="scheduler-preflight-grid">
        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 Irrigation Preflight</h2>
            <span>Readiness before any future V2 publish is allowed</span>
          </div>
          <div className={`preflight-status ${String(irrigationPreflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{irrigationPreflight.overall || "BLOCKED"}</strong>
            <span>{irrigationPreflight.block_count || 0} blocked | {irrigationPreflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(irrigationPreflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 X10 Preflight</h2>
            <span>Readiness before V2 owns the robot weekly schedule</span>
          </div>
          <div className={`preflight-status ${String(x10Preflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{x10Preflight.overall || "BLOCKED"}</strong>
            <span>{x10Preflight.block_count || 0} blocked | {x10Preflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(x10Preflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel scheduler-v2-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> V2 Climate Preflight</h2>
            <span>Readiness before V2 owns the climate schedule</span>
          </div>
          <div className={`preflight-status ${String(climatePreflight.overall || "BLOCKED").toLowerCase()}`}>
            <strong>{climatePreflight.overall || "BLOCKED"}</strong>
            <span>{climatePreflight.block_count || 0} blocked | {climatePreflight.warn_count || 0} warning</span>
          </div>
          <div className="preflight-list">
            {(climatePreflight.checks || []).map((check) => (
              <div className={`preflight-check ${check.status}`} key={check.key}>
                <strong>{check.key.replaceAll("_", " ")}</strong>
                <span>{check.message}</span>
              </div>
            ))}
          </div>
        </article>
      </section>

      <section className="scheduler-layout">
        <article className="panel scheduler-jobs-panel">
          <div className="panel-head">
            <h2 className="panel-title"><CalendarDays size={17} aria-hidden="true" /> V2 Job View</h2>
            <span>Read-through view over scheduler sources; execution history tracks V2 audit and publish decisions</span>
          </div>
          <Table
            rows={jobs.map((job, index) => ({ ...job, id: `${job.domain}-${job.source_ref}-${job.day_of_week ?? index}` }))}
            columns={[
              { key: "domain", label: "Domain", render: (row) => row.domain === "xiaomi_x10" ? "X10" : row.domain === "climate" ? "Climate" : "Irrigation" },
              { key: "label", label: "Job" },
              { key: "day_of_week", label: "Day", render: (row) => row.days_label || (row.day_of_week === null || row.day_of_week === undefined ? "-" : dayLabels[row.day_of_week]) },
              { key: "start_time", label: "Start" },
              { key: "stop_time", label: "Stop", render: (row) => row.stop_time || "-" },
              { key: "is_enabled", label: "Enabled", render: (row) => row.is_enabled ? "Yes" : "No" },
              { key: "status", label: "Status", render: (row) => String(row.status || "-").replaceAll("_", " ") },
            ]}
          />
        </article>
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Play size={17} aria-hidden="true" /> V2 Scheduler Simulation</h2>
          <span>Dry-run only: no database writes and no MQTT publish</span>
        </div>
        <form className="v2-sim-form" onSubmit={runSimulation}>
          <label>
            Domain
            <select value={simulationDraft.domain} onChange={(event) => updateSimulationDraft("domain", event.target.value)}>
              <option value="irrigation">Irrigation</option>
              <option value="xiaomi_x10">X10</option>
              <option value="climate">Climate</option>
            </select>
          </label>
          <label>
            Action
            <select value={simulationDraft.action} onChange={(event) => updateSimulationDraft("action", event.target.value)}>
              {simulationDraft.domain === "irrigation" ? (
                <>
                  <option value="water_start">Water start</option>
                  <option value="water_stop">Water stop</option>
                </>
              ) : simulationDraft.domain === "xiaomi_x10" ? (
                <option value="clean_start">Clean start</option>
              ) : (
                <option value="climate_set">Climate set</option>
              )}
            </select>
          </label>
          <label>
            Ref
            <input type="text" value={simulationDraft.schedule_id} onChange={(event) => updateSimulationDraft("schedule_id", event.target.value)} />
          </label>
          <label>
            Label
            <input type="text" value={simulationDraft.label} onChange={(event) => updateSimulationDraft("label", event.target.value)} />
          </label>
          <label>
            Start
            <input type="time" value={simulationDraft.start_time} onChange={(event) => updateSimulationDraft("start_time", event.target.value)} />
          </label>
          {simulationDraft.domain === "irrigation" ? (
            <>
              <label>
                Stop
                <input type="time" value={simulationDraft.stop_time} onChange={(event) => updateSimulationDraft("stop_time", event.target.value)} />
              </label>
              <label>
                Duration
                <input type="number" min="1" max="720" value={simulationDraft.duration_minutes} onChange={(event) => updateSimulationDraft("duration_minutes", event.target.value)} />
              </label>
            </>
          ) : simulationDraft.domain === "xiaomi_x10" ? (
            <>
              <label>
                Map
                <input type="number" min="1" value={simulationDraft.map_id} onChange={(event) => updateSimulationDraft("map_id", event.target.value)} />
              </label>
              <label>
                Segments
                <input type="text" value={simulationDraft.segments} onChange={(event) => updateSimulationDraft("segments", event.target.value)} />
              </label>
              <label>
                Suction
                <input type="number" min="0" max="3" value={simulationDraft.suction} onChange={(event) => updateSimulationDraft("suction", event.target.value)} />
              </label>
              <label>
                Water
                <input type="number" min="1" max="3" value={simulationDraft.water_level} onChange={(event) => updateSimulationDraft("water_level", event.target.value)} />
              </label>
            </>
          ) : (
            <>
              <label>
                Power
                <select value={simulationDraft.power} onChange={(event) => updateSimulationDraft("power", event.target.value)}>
                  <option value="on">On</option>
                  <option value="off">Off</option>
                </select>
              </label>
              <label>
                Mode
                <select value={simulationDraft.climate_mode} onChange={(event) => updateSimulationDraft("climate_mode", event.target.value)}>
                  {climateModeOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
              <label>
                Target
                <input type="number" min="8" max="30" value={simulationDraft.target_temperature} onChange={(event) => updateSimulationDraft("target_temperature", event.target.value)} />
              </label>
              <label>
                Fan
                <select value={simulationDraft.fan_speed} onChange={(event) => updateSimulationDraft("fan_speed", event.target.value)}>
                  {climateFanOptions.map((option) => <option key={option.value} value={option.value}>{option.label}</option>)}
                </select>
              </label>
            </>
          )}
          <IconButton icon={Play} disabled={busy === "simulate"}>{busy === "simulate" ? "Simulating" : "Dry Run"}</IconButton>
        </form>
        {simulationResult?.chain && (
          <div className="v2-sim-result">
            <div className="v2-chain-grid">
              <div><span>Event</span><strong>{simulationResult.chain.event_type}</strong><small>{simulationResult.chain.event_status}</small></div>
              <div><span>Plan</span><strong>{simulationResult.chain.plan_type}</strong><small>{simulationResult.chain.plan_status}</small></div>
              <div><span>Execution</span><strong>{simulationResult.chain.executor}</strong><small>{simulationResult.chain.execution_status}</small></div>
              <div><span>Publish</span><strong>{String(Boolean(simulationResult.chain.execution_engine?.can_publish))}</strong><small>{simulationResult.chain.execution_engine?.reason || "-"}</small></div>
              <div><span>Confirm</span><strong>{simulationResult.chain.confirmation_diagnostics?.status || "-"}</strong><small>{simulationResult.chain.confirmation_diagnostics?.strategy || "-"}</small></div>
              <div><span>Observed</span><strong>{simulationResult.chain.legacy_comparison?.status || "-"}</strong><small>{simulationResult.chain.legacy_comparison?.summary || "-"}</small></div>
              <div><span>Writes</span><strong>{String(Boolean(simulationResult.writes))}</strong><small>publishes={String(Boolean(simulationResult.publishes))}</small></div>
            </div>
            <div className="v2-json-grid">
              <div>
                <h3>Simulated Event</h3>
                <pre className="json-box">{jsonText(simulationResult.chain.event_payload)}</pre>
              </div>
              <div>
                <h3>Simulated Plan</h3>
                <pre className="json-box">{jsonText({ inputs: simulationResult.chain.plan_inputs, actions: simulationResult.chain.plan_actions })}</pre>
              </div>
              <div>
                <h3>Simulated Execution</h3>
                <pre className="json-box">{jsonText({ topic: simulationResult.chain.command_topic, payload: simulationResult.chain.command_payload, result: simulationResult.chain.execution_result })}</pre>
              </div>
              <div>
                <h3>Diagnostics</h3>
                <pre className="json-box">{jsonText({ engine: simulationResult.engine, confirmation: simulationResult.chain.confirmation_diagnostics, comparison: simulationResult.chain.legacy_comparison })}</pre>
              </div>
            </div>
          </div>
        )}
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Database size={17} aria-hidden="true" /> V2 Core Activity</h2>
          <span>Latest EventStore, PlanStore and ExecutionStore records</span>
        </div>
        <Table
          rows={v2Activity}
          columns={[
            { key: "ts", label: "Time", render: (row) => dateText(row.ts) },
            { key: "kind", label: "Store", render: (row) => String(row.kind || "-").toUpperCase() },
            { key: "domain", label: "Domain" },
            { key: "label", label: "Type" },
            { key: "status", label: "Status" },
            { key: "detail", label: "Detail" },
            { key: "correlation_id", label: "Correlation", render: (row) => row.correlation_id ? row.correlation_id.slice(0, 8) : "-" },
          ]}
        />
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Diagnostics</h2>
          <span>Read-only comparison between V2 intent and observed scheduler evidence</span>
        </div>
        <Table
          rows={v2Chains.map((chain, index) => ({ ...chain, id: chain.event_id || index }))}
          columns={[
              { key: "domain", label: "Domain", render: (row) => row.domain === "xiaomi_x10" ? "X10" : row.domain === "climate" ? "Climate" : "Irrigation" },
            { key: "event_type", label: "V2 Event" },
            { key: "v2_wanted", label: "V2 Wanted", render: (row) => shortValue(row.legacy_comparison?.v2_wanted || row.command_payload, 120) },
            { key: "legacy_observed", label: "Observed", render: (row) => shortValue(row.legacy_comparison?.legacy_observed, 120) },
            { key: "compare", label: "Compare", render: (row) => row.legacy_comparison?.status || "-" },
            { key: "summary", label: "Summary", render: (row) => row.legacy_comparison?.summary || "-" },
          ]}
        />
      </section>

      <section className="panel scheduler-explain-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Chain Explain</h2>
          <span>Event, plan and execution detail for each observed scheduler intent</span>
        </div>
        {v2Chains.length ? (
          <div className="v2-chain-list">
            {v2Chains.map((chain, index) => {
              const action = Array.isArray(chain.plan_actions) ? chain.plan_actions[0] : null;
              const published = chain.execution_result?.published;
              const engineDecision = chain.execution_engine || {};
              const confirmation = chain.confirmation_diagnostics || {};
              const comparison = chain.legacy_comparison || {};
              return (
                <details className="v2-chain" key={chain.event_id || index} open={index === 0}>
                  <summary>
                    <span>{chain.domain === "xiaomi_x10" ? "X10" : chain.domain === "climate" ? "Climate" : chain.domain}</span>
                    <strong>{chain.event_type || "-"}</strong>
                    <em>{chain.execution_status || chain.plan_status || chain.event_status || "-"}</em>
                  </summary>
                  <div className="v2-chain-grid">
                    <div>
                      <span>Event</span>
                      <strong>{chain.event_status || "-"}</strong>
                      <small>{dateText(chain.event_ts)} | {chain.event_source || "-"}</small>
                    </div>
                    <div>
                      <span>Plan</span>
                      <strong>{chain.plan_type || "missing"}</strong>
                      <small>{chain.target_type && chain.target_ref ? `${chain.target_type}:${chain.target_ref}` : "-"}</small>
                    </div>
                    <div>
                      <span>Action</span>
                      <strong>{action?.capability || "-"}</strong>
                      <small>{shortValue(action?.command || action, 90)}</small>
                    </div>
                    <div>
                      <span>Execution</span>
                      <strong>{chain.executor || "missing"}</strong>
                      <small>{chain.command_topic || "-"} | published={published === undefined ? "-" : String(published)}</small>
                    </div>
                    <div>
                      <span>Engine</span>
                      <strong>{engineDecision.can_publish ? "can publish" : "blocked"}</strong>
                      <small>{engineDecision.reason || "-"}</small>
                    </div>
                    <div>
                      <span>Confirm</span>
                      <strong>{confirmation.status || "-"}</strong>
                      <small>{confirmation.strategy || "-"}</small>
                    </div>
                    <div>
                      <span>Compare</span>
                      <strong>{comparison.status || "-"}</strong>
                      <small>{comparison.summary || "-"}</small>
                    </div>
                  </div>
                  <div className="v2-json-grid">
                    <div>
                      <h3>Event Payload</h3>
                      <pre className="json-box">{jsonText(chain.event_payload)}</pre>
                    </div>
                    <div>
                      <h3>Plan Inputs</h3>
                      <pre className="json-box">{jsonText(chain.plan_inputs)}</pre>
                    </div>
                    <div>
                      <h3>Plan Actions</h3>
                      <pre className="json-box">{jsonText(chain.plan_actions)}</pre>
                    </div>
                    <div>
                      <h3>Execution Command</h3>
                      <pre className="json-box">{jsonText({ topic: chain.command_topic, payload: chain.command_payload, result: chain.execution_result })}</pre>
                    </div>
                    <div>
                      <h3>Confirmation Diagnostics</h3>
                      <pre className="json-box">{jsonText(confirmation)}</pre>
                    </div>
                    <div>
                      <h3>Execution Engine</h3>
                      <pre className="json-box">{jsonText({ decision: engineDecision, engine: executionEngine })}</pre>
                    </div>
                    <div>
                      <h3>Observed Evidence</h3>
                      <pre className="json-box">{jsonText(comparison)}</pre>
                    </div>
                  </div>
                  <div className="scheduler-note">
                    <strong>{chain.reasoning || "V2 audit chain is read-only."}</strong>
                    <span>Publishing follows the current V2 engine decision for the domain.</span>
                  </div>
                </details>
              );
            })}
          </div>
        ) : (
          <div className="chart-empty">No V2 chains yet</div>
        )}
      </section>

      <section className="panel scheduler-history-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> V2 Scheduler History</h2>
          <span>What the V2 scheduler observed or wanted to do</span>
        </div>
        <Table
          rows={runs}
          columns={[
            { key: "requested_at", label: "Seen", render: (row) => dateText(row.requested_at) },
            { key: "domain_label", label: "Domain" },
            { key: "job_label", label: "Job" },
            { key: "action_label", label: "Wanted Action" },
            { key: "status_label", label: "Status" },
            { key: "event_time", label: "Planned Time", render: (row) => row.observed_date && row.event_time ? `${row.observed_date} ${row.event_time}` : row.event_time || "-" },
            { key: "mode", label: "Mode", render: (row) => row.mode || "-" },
            { key: "shadow_only", label: "Command", render: (row) => row.shadow_only ? "No command" : "Command path" },
            { key: "source", label: "Source", render: (row) => row.source_ref ? `${row.source}:${row.source_ref}` : row.source || "-" },
            { key: "legacy_status", label: "Source Status", render: (row) => String(row.legacy_status || "-").replaceAll("_", " ") },
            { key: "error", label: "Error", render: (row) => row.error || "-" },
          ]}
        />
      </section>
    </>
  );
}

function Backup() {
  const [state, setState] = useState(null);
  const [contents, setContents] = useState(null);
  const [selectedBackup, setSelectedBackup] = useState("");
  const [selectedPaths, setSelectedPaths] = useState([]);
  const [restoreMode, setRestoreMode] = useState("staging");
  const [confirmText, setConfirmText] = useState("");
  const [compare, setCompare] = useState(null);
  const [comparePath, setComparePath] = useState("");
  const [activeDiffIndex, setActiveDiffIndex] = useState(null);
  const [toast, setLocalToast] = useState("");
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");
  const [giteaMessage, setGiteaMessage] = useState("Manual HomeControl configuration snapshot");
  const [giteaRestoreRef, setGiteaRestoreRef] = useState("main");
  const [giteaResult, setGiteaResult] = useState(null);
  const diffGridRef = useRef(null);

  async function loadBackup() {
    setLoading(true);
    try {
      const data = await api("/api/context/backup");
      setState(data);
      if (!selectedBackup && data.backups?.length) setSelectedBackup(data.backups[0].name);
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function loadContents(name = selectedBackup) {
    if (!name) return;
    setBusy("contents");
    try {
      const data = await api(`/api/backup/${encodeURIComponent(name)}/contents`);
      setContents(data);
      const restoreDefaults = new Set(["apps", "infra", "zigbee2mqtt/data", "homeassistant", "scripts"]);
      setSelectedPaths(data.components?.map((item) => item.name).filter((name) => restoreDefaults.has(name)) || []);
      setCompare(null);
      setComparePath("");
      setActiveDiffIndex(null);
      setLocalToast("");
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  useEffect(() => {
    loadBackup();
  }, []);
  useContextRefresh(["/api/context/backup"], (payload) => {
    setState(payload);
    setLoading(false);
    if (!selectedBackup && payload.backups?.length) setSelectedBackup(payload.backups[0].name);
  });

  useEffect(() => {
    if (selectedBackup) loadContents(selectedBackup);
  }, [selectedBackup]);

  useEffect(() => {
    const running = Boolean(state?.ai_shutdown_guard?.backup_running) || ["create", "full-ai", "gitea-commit", "gitea-status", "gitea-restore"].includes(busy);
    if (!running) return undefined;
    const timer = window.setInterval(() => {
      loadBackup();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [state?.ai_shutdown_guard?.backup_running, busy]);

  async function saveSettings(event) {
    event.preventDefault();
    setBusy("settings");
    try {
      const data = await api("/api/backup/settings", {
        method: "PUT",
        body: JSON.stringify(state.settings),
      });
      setState((current) => ({ ...current, settings: data.settings, timer: data.timer, plan: data.plan || current?.plan }));
      setLocalToast(data.timer?.systemctl_ok ? "Backup settings and timer saved" : "Settings saved; systemd reload may be needed on host");
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function createBackup() {
    setBusy("create");
    try {
      const data = await api("/api/backup/create", { method: "POST", body: JSON.stringify({}) });
      setState((current) => ({ ...current, backups: data.backups }));
      setSelectedBackup(data.backup.name);
      setLocalToast(`Backup created: ${data.backup.name}`);
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function runFullAiBackup() {
    setBusy("full-ai");
    try {
      const data = await api("/api/backup/full-ai", { method: "POST", body: JSON.stringify({}) });
      setLocalToast(data.message || "Full AI backup requested");
      loadBackup();
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function runGiteaAction(action) {
    const body = action === "commit"
      ? { message: giteaMessage }
      : action === "restore"
        ? { ref: giteaRestoreRef }
        : {};
    if (action === "restore" && !window.confirm(`Restore Gitea ref "${giteaRestoreRef || "main"}" to staging? This will not overwrite live files.`)) return;
    setBusy(`gitea-${action}`);
    try {
      const data = await api(`/api/backup/gitea/${action}`, {
        method: "POST",
        body: JSON.stringify(body),
      });
      setGiteaResult(data);
      setLocalToast(data.message || `Gitea ${action} finished`);
      loadBackup();
    } catch (err) {
      setGiteaResult({ ok: false, error: err.message });
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function restoreSelected() {
    setBusy("restore");
    try {
      const result = await api("/api/backup/restore", {
        method: "POST",
        body: JSON.stringify({
          backup: selectedBackup,
          paths: selectedPaths,
          mode: restoreMode,
          confirm: confirmText,
        }),
      });
      setLocalToast(`Restored ${result.restored.length} file(s) to ${result.target}`);
      setConfirmText("");
    } catch (err) {
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function compareFile(path) {
    if (!selectedBackup || !path) return;
    setBusy("compare");
    setComparePath(path);
    try {
      const data = await api(`/api/backup/${encodeURIComponent(selectedBackup)}/compare?path=${encodeURIComponent(path)}`);
      setCompare(data);
      const firstDiff = data.rows?.findIndex((row) => isVisibleDiff(row)) ?? -1;
      setActiveDiffIndex(firstDiff >= 0 ? firstDiff : null);
      const visibleDiffs = data.rows?.filter((row) => isVisibleDiff(row)).length || 0;
      setLocalToast(data.same || visibleDiffs === 0 ? "Current and backup file are identical" : `${visibleDiffs} visible diff row(s)`);
    } catch (err) {
      setCompare(null);
      setActiveDiffIndex(null);
      setLocalToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function updateSetting(key, value) {
    setState((current) => ({
      ...current,
      settings: (() => {
        const next = { ...(current?.settings || {}), [key]: value };
        if (["ai_backup_host", "ai_backup_user", "ai_backup_mount"].includes(key)) {
          const user = next.ai_backup_user || "a";
          const host = next.ai_backup_host || "192.168.1.2";
          const mount = next.ai_backup_mount || "/mnt/hc-backup";
          next.restic_repository = `sftp:${user}@${host}:${mount}/restic/homecontrol`;
        }
        return next;
      })(),
    }));
  }

  function togglePath(path, checked) {
    setSelectedPaths((current) => checked ? [...new Set([...current, path])] : current.filter((item) => item !== path));
  }

  function isVisibleDiff(row) {
    return row?.type !== "same" && row?.current !== row?.backup;
  }

  function diffGroupsFromIndexes(indexes) {
    const groups = [];
    for (const index of indexes) {
      const last = groups[groups.length - 1];
      if (last && index <= last.end + 1) {
        last.end = index;
      } else {
        groups.push({ start: index, end: index });
      }
    }
    return groups;
  }

  function jumpDiff(direction) {
    if (!diffGroups.length) return;
    const currentPosition = diffGroups.findIndex((group) => activeDiffIndex >= group.start && activeDiffIndex <= group.end);
    const nextPosition = currentPosition === -1
      ? 0
      : (currentPosition + direction + diffGroups.length) % diffGroups.length;
    setActiveDiffIndex(diffGroups[nextPosition].start);
  }

  useEffect(() => {
    if (activeDiffIndex === null || !diffGridRef.current) return;
    const target = diffGridRef.current.querySelector(`[data-diff-index="${activeDiffIndex}"]`);
    if (target) {
      diffGridRef.current.scrollTo({
        top: Math.max(0, target.offsetTop - 44),
        behavior: "smooth",
      });
    }
  }, [activeDiffIndex]);

  if (loading && !state) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading backups...</span>
      </section>
    );
  }

  const backups = state?.backups || [];
  const settings = state?.settings || {};
  const timer = state?.timer || settings.timer_source || {};
  const plan = state?.plan || {};
  const activity = state?.activity || {};
  const aiShutdownGuard = state?.ai_shutdown_guard || {};
  const aiBackupRunning = Boolean(aiShutdownGuard.backup_running);
  const aiShutdownDeferred = Boolean(aiShutdownGuard.deferred_shutdown);
  const backupStateDetail = aiShutdownGuard.state?.detail || (aiBackupRunning ? "full AI backup lock is active" : "");
  const activeBackupUi = aiBackupRunning || ["create", "full-ai", "gitea-commit", "gitea-status", "gitea-restore"].includes(busy);
  const activeBackupTitle = aiBackupRunning
    ? "Full AI Backup Running"
    : busy === "create"
      ? "Local Backup Creating"
      : busy === "full-ai"
        ? "Full AI Backup Queued"
        : busy?.startsWith("gitea-")
          ? "Gitea Operation Running"
          : "Backup Activity";
  const activeBackupMeta = aiBackupRunning
    ? backupStateDetail || "Gitea, GitHub, Gitea dump and restic steps may be running"
    : busy === "create"
      ? "creating local tar.gz archive"
      : busy === "full-ai"
        ? "host systemd helper will start the full AI backup"
        : busy === "gitea-commit"
          ? "snapshot commit and push in progress"
          : busy === "gitea-status"
            ? "checking current snapshot against Gitea"
            : busy === "gitea-restore"
              ? "cloning selected ref to staging"
              : "";
  const latest = backups[0];
  const settingChecks = [
    ["include_postgres", "PostgreSQL dump"],
    ["include_apps", "Apps"],
    ["include_infra", "Infra config"],
    ["include_zigbee2mqtt", "Zigbee2MQTT data"],
    ["include_homeassistant", "Home Assistant"],
    ["include_scripts", "Scripts"],
    ["include_docker_meta", "Docker meta"],
  ];
  const resticChecks = [
    ["include_docker_volumes", "Docker volumes"],
    ["include_media", "Media files"],
    ["include_gitea", "Local Gitea data"],
  ];
  const comparableFiles = (contents?.files || []).filter((item) => item.type === "file" && item.size_bytes <= 300000);
  const diffIndexes = compare?.rows?.map((row, index) => isVisibleDiff(row) ? index : null).filter((index) => index !== null) || [];
  const diffGroups = diffGroupsFromIndexes(diffIndexes);
  const activeDiffGroup = activeDiffIndex === null ? null : diffGroups.find((group) => activeDiffIndex >= group.start && activeDiffIndex <= group.end);
  const activeDiffPosition = activeDiffGroup ? diffGroups.indexOf(activeDiffGroup) : -1;
  const resticRetention = plan.restic?.retention || {};

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Backup</h2>
          <span>{toast || `${backups.length} archive | root ${state?.backup_root || "-"}`}</span>
        </div>
        <div className="button-row compact">
          <IconButton icon={RefreshCw} onClick={loadBackup} disabled={loading}>Refresh</IconButton>
          <IconButton icon={Archive} onClick={createBackup} disabled={busy === "create"}>{busy === "create" ? "Creating" : "Create Backup"}</IconButton>
          <IconButton icon={HardDrive} onClick={runFullAiBackup} disabled={busy === "full-ai" || aiBackupRunning}>{busy === "full-ai" ? "Requesting" : aiBackupRunning ? "Full Backup Running" : "Run Full AI Backup"}</IconButton>
        </div>
      </section>

      {activeBackupUi && (
        <section className="backup-running-banner" aria-live="polite">
          <div className="backup-running-pulse" aria-hidden="true" />
          <div>
            <strong>{activeBackupTitle}</strong>
            <span>{activeBackupMeta}</span>
          </div>
          <div className="backup-running-steps">
            <span>Gitea</span>
            <span>GitHub</span>
            <span>Restic</span>
            <span>AI HDD</span>
          </div>
        </section>
      )}

      <section className="tile-grid stats-tiles">
        <Card title="Latest Backup" value={latest ? dateText(latest.timestamp) : "-"} meta={latest ? latest.name : "no archive"} icon={Archive} />
        <Card title="Backup Size" value={latest ? byteText(latest.size_bytes) : "-"} meta="latest archive" icon={HardDrive} />
        <Card title="Schedule" value={settings.schedule_enabled ? (timer.schedule_time || settings.schedule_time || "-") : "Disabled"} meta={timer.source_enabled ? "systemd timer source enabled" : "systemd timer source disabled"} tone={settings.schedule_enabled && !timer.source_enabled ? "warn" : ""} icon={Clock} />
        <Card title="Timer State" value={timer.active || (timer.systemctl_ok ? "Unknown" : "Host helper")} meta={timer.systemctl_ok ? `next ${timer.next_elapse || "-"}` : "source changes are applied by systemd path helper"} tone={timer.systemctl_ok ? "" : "warn"} icon={Settings} />
        <Card title="Restic Retention" value={`${resticRetention.daily || "-"}d / ${resticRetention.weekly || "-"}w / ${resticRetention.monthly || "-"}m`} meta={plan.restic?.repository || settings.restic_repository || "AI HDD repo"} icon={Database} />
        <Card title="Restore Mode" value={restoreMode === "staging" ? "Staging" : "In-place"} meta={restoreMode === "staging" ? state?.staging_root : "requires RESTORE"} tone={restoreMode === "in_place" ? "warn" : ""} icon={RefreshCw} />
        <Card title="AI Shutdown Guard" value={aiBackupRunning ? "Backup running" : aiShutdownDeferred ? "Shutdown queued" : "Clear"} meta={aiShutdownDeferred ? "AI PC will shut down after backup" : "shutdown is protected during full backup"} tone={aiBackupRunning || aiShutdownDeferred ? "warn" : ""} icon={Power} />
      </section>

      <section className="backup-plan-grid">
        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <GitBranch size={18} />
            <div>
              <h2>Gitea / Git</h2>
              <span>{settings.git_enabled ? "version tracking enabled" : "version tracking disabled"}</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{settings.gitea_url || "-"}</span>
            <strong>{settings.git_repository || "-"}{settings.git_offsite_enabled ? ` | offsite ${settings.git_offsite_branch || "main"}` : ""}</strong>
          </div>
          <div className="pill-list">
            {(plan.git?.paths || settings.git_paths || []).map((path) => <span key={path}>{path}</span>)}
          </div>
        </article>

        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <Database size={18} />
            <div>
              <h2>Restic / AI HDD</h2>
              <span>{settings.restic_enabled ? "snapshot backup enabled" : "snapshot backup disabled"}</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{settings.ai_backup_user || "-"}@{settings.ai_backup_host || "-"}:{settings.ai_backup_mount || "-"}</span>
            <strong>daily best-effort, weekly required | keep {settings.restic_keep_daily || "-"}d/{settings.restic_keep_weekly || "-"}w/{settings.restic_keep_monthly || "-"}m</strong>
          </div>
          <div className="pill-list">
            {(plan.restic?.covers || []).map((item) => <span key={item}>{item}</span>)}
          </div>
        </article>

        <article className="panel backup-plan-card">
          <div className="plan-card-head">
            <Archive size={18} />
            <div>
              <h2>HC Archive</h2>
              <span>manual and scheduled tar.gz fallback</span>
            </div>
          </div>
          <div className="plan-meta">
            <span>{state?.backup_root || "-"}</span>
            <strong>{settings.retention_days || "-"} day local retention</strong>
          </div>
          <div className="pill-list">
            {(plan.local_archive?.covers || []).map((item) => <span key={item}>{item}</span>)}
          </div>
        </article>
      </section>

      <section className="panel backup-activity">
        <div className="panel-head">
          <h2>Backup Activity</h2>
          <span>{activity.log_file || "backup.log"}</span>
        </div>
        <div className="backup-check-grid">
          <div className="status-chip">
            <span>Archive</span>
            <strong>{activity.latest_backup || "no completed archive yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Restic</span>
            <strong>{activity.latest_restic_backup || "no restic snapshot yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Restic check</span>
            <strong>{activity.latest_restic_check || "no repository check yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Gitea</span>
            <strong>{activity.latest_gitea_sync || "no config sync yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Gitea dump</span>
            <strong>{activity.latest_gitea_dump || "no Gitea dump yet"}</strong>
          </div>
          <div className={`status-chip ${activity.latest_error ? "warn" : ""}`}>
            <span>Last error</span>
            <strong>{activity.latest_error || "none in recent log"}</strong>
          </div>
        </div>
      </section>

      <section className="panel backup-activity">
        <div className="panel-head">
          <h2>Gitea Control</h2>
          <span>{settings.gitea_url || "Gitea web"} | {settings.git_repository || "repository"}</span>
        </div>
        <div className="backup-check-grid">
          <div className="status-chip">
            <span>Repository</span>
            <strong>{settings.git_repository || "-"}</strong>
          </div>
          <div className="status-chip">
            <span>Remote</span>
            <strong>git@{settings.ai_backup_host || "192.168.1.2"}:2222</strong>
          </div>
          <div className="status-chip">
            <span>Last sync</span>
            <strong>{activity.latest_gitea_sync || "no config sync yet"}</strong>
          </div>
          <div className="status-chip">
            <span>Web UI</span>
            <strong>{settings.gitea_url || "-"}</strong>
          </div>
          <div className={`status-chip ${settings.git_offsite_enabled ? "" : "warn"}`}>
            <span>Offsite Git</span>
            <strong>{settings.git_offsite_enabled ? (settings.git_offsite_remote || "enabled, no remote") : "disabled"}</strong>
          </div>
        </div>
        <div className="form-grid backup-settings-grid">
          <label className="wide">Commit message
            <input value={giteaMessage} onChange={(event) => setGiteaMessage(event.target.value)} />
          </label>
          <label>Restore ref
            <input value={giteaRestoreRef} onChange={(event) => setGiteaRestoreRef(event.target.value)} />
          </label>
          <div className="wide actions">
            <IconButton icon={RefreshCw} type="button" className="secondary" disabled={busy === "gitea-status"} onClick={() => runGiteaAction("status")}>{busy === "gitea-status" ? "Checking" : "Status / Diff"}</IconButton>
            <IconButton icon={GitBranch} type="button" disabled={busy === "gitea-commit"} onClick={() => runGiteaAction("commit")}>{busy === "gitea-commit" ? "Pushing" : "Commit & Push"}</IconButton>
            <IconButton icon={RefreshCw} type="button" className="secondary" disabled={busy === "gitea-restore"} onClick={() => runGiteaAction("restore")}>{busy === "gitea-restore" ? "Restoring" : "Restore to Staging"}</IconButton>
            {settings.gitea_url && <a className="ai-node-link" href={`${settings.gitea_url}/${settings.git_repository || ""}`} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" /> Open Gitea</a>}
          </div>
        </div>
        {giteaResult && (
          <pre className="json-box">{[giteaResult.message || giteaResult.error || "", giteaResult.stdout, giteaResult.stderr].filter(Boolean).join("\n\n")}</pre>
        )}
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Backup Archives</h2>
            <span>Select and inspect an archive</span>
          </div>
          <div className="backup-picker">
            <label>Archive
              <select value={selectedBackup} onChange={(event) => setSelectedBackup(event.target.value)}>
                {backups.map((backup) => <option value={backup.name} key={backup.name}>{backup.name}</option>)}
              </select>
            </label>
            <IconButton icon={Archive} onClick={() => loadContents()} disabled={!selectedBackup || busy === "contents"}>{busy === "contents" ? "Opening" : "Open"}</IconButton>
          </div>
          <Table
            rows={backups}
            columns={[
              { key: "name", label: "Archive" },
              { key: "size_bytes", label: "Size", render: (row) => byteText(row.size_bytes) },
              { key: "timestamp", label: "Created", render: (row) => dateText(row.timestamp) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Backup Settings</h2>
            <span>Git tracks config, restic protects full system state</span>
          </div>
          <form onSubmit={saveSettings}>
            <h3>Local archive</h3>
            <div className="backup-check-grid">
              {settingChecks.map(([key, label]) => (
                <label className="check" key={key}>
                  <input type="checkbox" checked={Boolean(settings[key])} onChange={(event) => updateSetting(key, event.target.checked)} />
                  {label}
                </label>
              ))}
            </div>
            <div className="form-grid backup-settings-grid">
              <label>Retention days
                <input type="number" min="1" max="365" value={settings.retention_days || 14} onChange={(event) => updateSetting("retention_days", Number(event.target.value))} />
              </label>
              <label>Schedule time
                <input type="time" value={settings.schedule_time || "02:15"} onChange={(event) => updateSetting("schedule_time", event.target.value)} />
              </label>
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.schedule_enabled)} onChange={(event) => updateSetting("schedule_enabled", event.target.checked)} />
                Schedule enabled
              </label>
            </div>
            <h3>Gitea / Git</h3>
            <div className="form-grid backup-settings-grid">
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.git_enabled)} onChange={(event) => updateSetting("git_enabled", event.target.checked)} />
                Git version tracking enabled
              </label>
              <label>Gitea URL
                <input value={settings.gitea_url || ""} onChange={(event) => updateSetting("gitea_url", event.target.value)} />
              </label>
              <label>Repository
                <input value={settings.git_repository || ""} onChange={(event) => updateSetting("git_repository", event.target.value)} />
              </label>
              <label className="check wide">
                <input type="checkbox" checked={Boolean(settings.git_offsite_enabled)} onChange={(event) => updateSetting("git_offsite_enabled", event.target.checked)} />
                Offsite Git mirror enabled
              </label>
              <label className="wide">Offsite remote
                <input placeholder="https://github.com/user/homecontrol.git" value={settings.git_offsite_remote || ""} onChange={(event) => updateSetting("git_offsite_remote", event.target.value)} />
              </label>
              <label>Offsite branch
                <input value={settings.git_offsite_branch || "main"} onChange={(event) => updateSetting("git_offsite_branch", event.target.value)} />
              </label>
              <label className="wide">Offsite token file
                <input value={settings.git_offsite_token_file || ""} onChange={(event) => updateSetting("git_offsite_token_file", event.target.value)} />
              </label>
              <label className="wide">Offsite SSH key
                <input value={settings.git_offsite_ssh_key || ""} onChange={(event) => updateSetting("git_offsite_ssh_key", event.target.value)} />
              </label>
            </div>
            <h3>AI backup HDD</h3>
            <div className="form-grid backup-settings-grid">
              <label>Host
                <input value={settings.ai_backup_host || ""} onChange={(event) => updateSetting("ai_backup_host", event.target.value)} />
              </label>
              <label>User
                <input value={settings.ai_backup_user || ""} onChange={(event) => updateSetting("ai_backup_user", event.target.value)} />
              </label>
              <label className="wide">Mount path
                <input value={settings.ai_backup_mount || ""} onChange={(event) => updateSetting("ai_backup_mount", event.target.value)} />
              </label>
              <label className="wide">SSH key
                <input value={settings.ai_backup_ssh_key || ""} onChange={(event) => updateSetting("ai_backup_ssh_key", event.target.value)} />
              </label>
            </div>
            <h3>Restic / AI HDD</h3>
            <div className="backup-check-grid">
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.restic_enabled)} onChange={(event) => updateSetting("restic_enabled", event.target.checked)} />
                Restic enabled
              </label>
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.ai_weekly_backup_enabled)} onChange={(event) => updateSetting("ai_weekly_backup_enabled", event.target.checked)} />
                Weekly AI backup
              </label>
              {resticChecks.map(([key, label]) => (
                <label className="check" key={key}>
                  <input type="checkbox" checked={Boolean(settings[key])} onChange={(event) => updateSetting(key, event.target.checked)} />
                  {label}
                </label>
              ))}
            </div>
            <div className="form-grid backup-settings-grid">
              <label className="wide">Restic repository
                <input value={settings.restic_repository || ""} onChange={(event) => updateSetting("restic_repository", event.target.value)} />
              </label>
              <label className="wide">Password file
                <input value={settings.restic_password_file || ""} onChange={(event) => updateSetting("restic_password_file", event.target.value)} />
              </label>
              <label>Keep daily
                <input type="number" min="1" max="365" value={settings.restic_keep_daily || 14} onChange={(event) => updateSetting("restic_keep_daily", Number(event.target.value))} />
              </label>
              <label>Keep weekly
                <input type="number" min="1" max="365" value={settings.restic_keep_weekly || 8} onChange={(event) => updateSetting("restic_keep_weekly", Number(event.target.value))} />
              </label>
              <label>Keep monthly
                <input type="number" min="1" max="365" value={settings.restic_keep_monthly || 6} onChange={(event) => updateSetting("restic_keep_monthly", Number(event.target.value))} />
              </label>
              <label>Weekly schedule
                <input value={settings.ai_weekly_backup_schedule || "Sun 03:30"} onChange={(event) => updateSetting("ai_weekly_backup_schedule", event.target.value)} />
              </label>
              <label className="check">
                <input type="checkbox" checked={Boolean(settings.ai_weekly_shutdown_after)} onChange={(event) => updateSetting("ai_weekly_shutdown_after", event.target.checked)} />
                Shutdown if backup woke AI
              </label>
              <div className="wide actions"><IconButton icon={Save} type="submit" disabled={busy === "settings"}>{busy === "settings" ? "Saving" : "Save Settings"}</IconButton></div>
            </div>
          </form>
          <div className="timer-source">
            <strong>Systemd source</strong>
            <span>{timer.timer_file || "-"}</span>
            <span>{timer.on_calendar ? `OnCalendar=${timer.on_calendar}` : "OnCalendar is disabled"}</span>
            <span>Helper: homecontrol-backup-apply.path watches this file on the host</span>
          </div>
        </article>
      </section>

      <details className="backup-advanced">
        <summary>
          <span>Restore and file compare</span>
          <b>{selectedBackup || "no archive selected"}</b>
        </summary>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Archive Contents</h2>
            <span>{contents?.components?.length || 0} component | {selectedBackup || "-"}</span>
          </div>
          <div className="restore-components">
            {(contents?.components || []).map((component) => (
              <label className="restore-component" key={component.name}>
                <input type="checkbox" checked={selectedPaths.includes(component.name)} onChange={(event) => togglePath(component.name, event.target.checked)} />
                <span>{component.name}</span>
                <b>{byteText(component.size_bytes)}</b>
              </label>
            ))}
          </div>
          <div className="table-spacer" />
          <Table
            rows={contents?.files || []}
            columns={[
              { key: "path", label: "Path" },
              { key: "type", label: "Type" },
              { key: "size_bytes", label: "Size", render: (row) => row.type === "dir" ? "-" : byteText(row.size_bytes) },
              {
                key: "compare",
                label: "Compare",
                render: (row) => row.type === "file" && row.size_bytes <= 300000 ? (
                  <button className="mini-action" type="button" onClick={() => compareFile(row.path)} disabled={busy === "compare"}>
                    Compare
                  </button>
                ) : "-",
              },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Restore</h2>
            <span>{selectedPaths.length} selected component/path</span>
          </div>
          <div className="restore-box">
            <label>Mode
              <select value={restoreMode} onChange={(event) => setRestoreMode(event.target.value)}>
                <option value="staging">staging preview</option>
                <option value="in_place">restore in-place</option>
              </select>
            </label>
            {restoreMode === "in_place" && (
              <label>Confirmation
                <input value={confirmText} onChange={(event) => setConfirmText(event.target.value)} placeholder="RESTORE" />
              </label>
            )}
            <div className={restoreMode === "in_place" ? "restore-warning active" : "restore-warning"}>
              {restoreMode === "in_place"
                ? "In-place restore overwrites matching files in the live HomeControl folders. PostgreSQL dumps are not restored in-place in this version."
                : `Staging restore extracts selected files under ${state?.staging_root || "-"}.`}
            </div>
            <IconButton icon={RefreshCw} onClick={restoreSelected} disabled={!selectedBackup || !selectedPaths.length || busy === "restore"}>
              {busy === "restore" ? "Restoring" : "Restore Selected"}
            </IconButton>
          </div>
        </article>
      </section>

      <section className="panel diff-panel">
        <div className="panel-head">
          <h2>File Compare</h2>
          <span>{compare ? `${compare.path} | ${diffGroups.length} diff block(s)` : "Select a file from Archive Contents"}</span>
        </div>
        <div className="backup-picker">
          <label>File
            <select value={comparePath} onChange={(event) => setComparePath(event.target.value)}>
              <option value="">Select file</option>
              {comparableFiles.map((item) => <option value={item.path} key={item.path}>{item.path}</option>)}
            </select>
          </label>
          <IconButton icon={Activity} onClick={() => compareFile(comparePath)} disabled={!comparePath || busy === "compare"}>
            {busy === "compare" ? "Comparing" : "Compare"}
          </IconButton>
        </div>
        {compare ? (
          <>
            <div className="diff-meta">
              <span>Current: {compare.current_exists ? `${compare.current_path} | ${byteText(compare.current_size_bytes)}` : "missing"}</span>
              <span>Backup: {byteText(compare.backup_size_bytes)}</span>
              <span>{diffGroups.length ? `${activeDiffPosition + 1}/${diffGroups.length} diff block` : "no differences"}</span>
              {compare.truncated && <span>Diff display truncated</span>}
              <div className="diff-nav">
                <IconButton icon={ChevronLeft} onClick={() => jumpDiff(-1)} disabled={!diffGroups.length}>Prev</IconButton>
                <IconButton icon={ChevronRight} onClick={() => jumpDiff(1)} disabled={!diffGroups.length}>Next</IconButton>
              </div>
            </div>
            <div className="diff-grid" ref={diffGridRef}>
              <div className="diff-head">Current</div>
              <div className="diff-head">Backup</div>
              {compare.rows.map((row, index) => (
                <React.Fragment key={`${row.current_line || "x"}-${row.backup_line || "x"}-${index}`}>
                  <pre data-diff-index={index} className={`diff-cell left ${row.type} ${activeDiffGroup && index >= activeDiffGroup.start && index <= activeDiffGroup.end ? "active-diff" : ""}`}><span>{row.current_line || ""}</span>{row.current || " "}</pre>
                  <pre className={`diff-cell right ${row.type} ${activeDiffGroup && index >= activeDiffGroup.start && index <= activeDiffGroup.end ? "active-diff" : ""}`}><span>{row.backup_line || ""}</span>{row.backup || " "}</pre>
                </React.Fragment>
              ))}
            </div>
          </>
        ) : (
          <div className="chart-empty diff-empty">No file selected</div>
        )}
      </section>
      </details>
    </>
  );
}

function Performance() {
  const [perf, setPerf] = useState(null);
  const [clientResponseMs, setClientResponseMs] = useState(null);
  const [resourceHistory, setResourceHistory] = useState([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadPerformance() {
    setLoading(true);
    setError("");
    const started = performance.now();
    try {
      const data = await api("/api/context/performance");
      setClientResponseMs(performance.now() - started);
      setPerf(data);
      setResourceHistory((current) => {
        const ts = data.generated_at || new Date().toISOString();
        const next = [
          ...current,
          {
            ts,
            cpu_percent: data.cpu?.ok ? Number(data.cpu.percent) : null,
            memory_percent: data.memory?.ok ? Number(data.memory.percent) : null,
          },
        ].filter((row) => new Date(ts).getTime() - new Date(row.ts).getTime() <= 15 * 60_000);
        return next.slice(-180);
      });
    } catch (err) {
      setClientResponseMs(performance.now() - started);
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadPerformance();
    const id = window.setInterval(loadPerformance, 30000);
    return () => window.clearInterval(id);
  }, []);
  useContextRefresh(["/api/context/performance"], (payload) => {
    setPerf(payload);
    setLoading(false);
    setResourceHistory((current) => {
      const ts = payload.generated_at || new Date().toISOString();
      const next = [
        ...current,
        {
          ts,
          cpu_percent: payload.cpu?.ok ? Number(payload.cpu.percent) : null,
          memory_percent: payload.memory?.ok ? Number(payload.memory.percent) : null,
        },
      ].filter((row) => new Date(ts).getTime() - new Date(row.ts).getTime() <= 15 * 60_000);
      return next.slice(-180);
    });
  });

  if (loading && !perf) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading performance...</span>
      </section>
    );
  }

  const cpu = perf?.cpu || {};
  const memory = perf?.memory || {};
  const postgres = perf?.postgres || {};
  const mqtt = perf?.mqtt || {};
  const apiLog = perf?.api_log || {};
  const slowEndpoints = apiLog.slow_endpoints || [];
  const summary = perf?.summary || {};
  const dockerContainers = perf?.docker?.containers || [];
  const dockerByCpu = dockerContainers
    .slice()
    .sort((a, b) => (metricNumber(b, "cpu_percent") || 0) - (metricNumber(a, "cpu_percent") || 0));
  const topContainer = dockerByCpu[0] || null;
  const heartbeats = perf?.heartbeats || [];
  const workers = perf?.workers || [];
  const staleHeartbeats = heartbeats.filter((item) => item.status !== "online").length;
  const clientMs = clientResponseMs === null ? null : Math.round(clientResponseMs);
  const serverPower = perf?.server_power || {};
  const serverPowerSummary = serverPower.summary || {};
  const serverPowerDevice = serverPower.device || {};
  const serverPowerRows = serverPower.power_24h || [];
  const serverPowerDailyRows = serverPower.daily_30d || [];
  const serverPowerTitle = serverPowerDevice.display_name || serverPowerDevice.entity_name || "HC szerver";

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>Performance</h2>
          <span>{error || `Updated ${dateText(perf?.generated_at)} | auto refresh 30s`}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadPerformance} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid performance-tiles">
        <Card
          title="CPU"
          value={unitValue(cpu.percent, "%", 1)}
          meta={cpu.ok ? "host/container view" : cpu.error || "unavailable"}
          tone={cpu.ok && cpu.percent >= 85 ? "warn" : ""}
          icon={Cpu}
        />
        <Card
          title="RAM"
          value={unitValue(memory.percent, "%", 1)}
          meta={`${byteText(memory.used_bytes)} / ${byteText(memory.total_bytes)}`}
          tone={memory.ok && memory.percent >= 85 ? "warn" : ""}
          icon={HardDrive}
        />
        <Card
          title="Top Container"
          value={topContainer ? unitValue(topContainer.cpu_percent, "%", 1) : "-"}
          meta={topContainer?.name || "no container stats"}
          tone={topContainer && metricNumber(topContainer, "cpu_percent") >= 80 ? "warn" : ""}
          icon={Server}
        />
        <Card
          title="PostgreSQL"
          value={postgres.ok ? `${postgres.total ?? "-"} conn` : "Offline"}
          meta={postgres.ok ? `${postgres.active ?? 0} active | ${postgres.idle ?? 0} idle | max ${postgres.max ?? "-"}` : postgres.error}
          tone={postgres.ok ? "" : "bad"}
          icon={Database}
        />
        <Card
          title="MQTT"
          value={mqtt.connected ? "Connected" : "Disconnected"}
          meta={mqtt.connected ? `${mqtt.broker?.host || "-"}:${mqtt.broker?.port || "-"}` : mqtt.last_error || "broker unavailable"}
          tone={mqtt.connected ? "" : "bad"}
          icon={Radio}
        />
        <Card
          title="API Response"
          value={clientMs === null ? "-" : `${clientMs} ms`}
          meta={`server ${numberText(perf?.api?.response_ms, 1)} ms | db ${numberText(perf?.api?.db_response_ms, 1)} ms`}
          tone={clientMs !== null && clientMs > 1000 ? "warn" : ""}
          icon={Gauge}
        />
      </section>

      <section className="grid two">
        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>{serverPowerTitle} Power / 24h</h2>
            <span>
              {serverPower.ok === false
                ? serverPower.error || "plug unavailable"
                : `${unitValue(serverPowerSummary.current_power_w, "W", 0)} now | avg ${unitValue(serverPowerSummary.avg_power_w_24h, "W", 1)} | max ${unitValue(serverPowerSummary.max_power_w, "W", 0)} | ${serverPowerSummary.power_samples || serverPowerRows.length} samples`}
            </span>
          </div>
          <TimeLineChart rows={serverPowerRows} valueKey="power_w" unit="W" digits={0} color="blue" />
        </article>

        <article className="panel chart-panel">
          <div className="panel-head">
            <h2>Daily {serverPowerTitle} Use</h2>
            <span>
              {serverPower.ok === false
                ? serverPower.error || "plug unavailable"
                : `${unitValue(serverPowerSummary.today_energy_kwh, "kWh", 2)} today | total ${unitValue(serverPowerSummary.total_energy_kwh, "kWh", 2)}`}
            </span>
          </div>
          <StatBarChart rows={serverPowerDailyRows} valueKey="energy_kwh" unit="kWh" digits={2} color="green" />
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> API Request Log</h2>
          <span>
            {apiLog.sample_count || 0} samples | {apiLog.endpoint_count || 0} endpoints | {unitValue((apiLog.window_sec || 0) / 3600, "h", 1)} window
          </span>
        </div>
        <Table
          rows={slowEndpoints}
          columns={[
            {
              key: "route",
              label: "Endpoint",
              render: (row) => (
                <span className="inline-endpoint">
                  <strong>{row.method || "-"}</strong>
                  <code>{row.route || row.path || "-"}</code>
                </span>
              ),
            },
            { key: "count", label: "Count" },
            { key: "avg_ms", label: "Avg", render: (row) => unitValue(row.avg_ms, "ms", 1) },
            { key: "p95_ms", label: "P95", render: (row) => unitValue(row.p95_ms, "ms", 1) },
            { key: "max_ms", label: "Max", render: (row) => unitValue(row.max_ms, "ms", 1) },
            { key: "last_ms", label: "Last", render: (row) => unitValue(row.last_ms, "ms", 1) },
            {
              key: "last_status",
              label: "Status",
              render: (row) => {
                const status = Number(row.last_status);
                return <span className={`status-pill ${statusTone(status > 0 && status < 400, status >= 400 && status < 500)}`}>{row.last_status || "-"}</span>;
              },
            },
            { key: "last_seen", label: "Seen", render: (row) => dateText(row.last_seen) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Clock size={17} aria-hidden="true" /> Device Heartbeats</h2>
            <span>{heartbeats.length} device/entity | {staleHeartbeats} not online</span>
          </div>
          <Table
            rows={heartbeats}
            columns={[
              { key: "entity_name", label: "Entity", render: (row) => displayEntityName(row.entity_name) },
              { key: "device_name", label: "Device" },
              { key: "platform", label: "Platform" },
              { key: "status", label: "Status", render: (row) => <span className={`status-pill ${statusTone(row.status === "online", row.status !== "offline")}`}>{row.status || "unknown"}</span> },
              { key: "last_seen_ts", label: "Last heartbeat", render: (row) => dateText(row.last_seen_ts) },
              { key: "age_sec", label: "Age", render: (row) => row.age_sec === null || row.age_sec === undefined ? "-" : `${row.age_sec} s` },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Server size={17} aria-hidden="true" /> Docker Containers</h2>
            <span>{perf?.docker?.ok ? `${summary.docker_running || 0}/${summary.docker_total || 0} running` : perf?.docker?.error || "unavailable"}</span>
          </div>
          <Table
            rows={dockerByCpu}
            columns={[
              { key: "name", label: "Name" },
              { key: "cpu_percent", label: "CPU", render: (row) => unitValue(row.cpu_percent, "%", 1) },
              { key: "memory_percent", label: "RAM", render: (row) => row.memory_usage ? row.memory_usage : `${byteText(row.memory_usage_bytes)} | ${unitValue(row.memory_percent, "%", 1)}` },
              { key: "pids", label: "PIDs", render: (row) => row.pids ?? "-" },
              { key: "network_io", label: "Net I/O", render: (row) => row.network_io || `${byteText(row.network_rx_bytes)} / ${byteText(row.network_tx_bytes)}` },
              { key: "block_io", label: "Block I/O", render: (row) => row.block_io || `${byteText(row.block_read_bytes)} / ${byteText(row.block_write_bytes)}` },
              { key: "state", label: "State", render: (row) => <span className={`status-pill ${statusTone(row.state === "running")}`}>{row.state || "-"}</span> },
              { key: "status", label: "Status" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Activity size={17} aria-hidden="true" /> Background Processes</h2>
            <span>{summary.workers_running || 0}/{summary.workers_total || workers.length} running | {perf?.thread_count || 0} threads</span>
          </div>
          <div className="worker-list">
            {workers.map((worker) => (
              <div className="worker-row" key={worker.key}>
                <div>
                  <strong>{worker.name}</strong>
                  <span>{worker.enabled ? "enabled" : "disabled"}</span>
                </div>
                <span className={`status-pill ${statusTone(worker.running, worker.enabled === false)}`}>{boolText(worker.running)}</span>
              </div>
            ))}
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2 className="panel-title"><Gauge size={17} aria-hidden="true" /> Resource Usage</h2>
            <span>{resourceHistory.length} samples | 30s refresh | 15 min window</span>
          </div>
          <ResourceUsageChart rows={resourceHistory} />
        </article>
      </section>
    </>
  );
}

function HcAdmin({ snapshot, reload, setToast, skin, setSkin, navItems = [], uiV2Tabs = {}, setUiV2Tabs }) {
  const [deviceForm, setDeviceForm] = useState({ platform: "zigbee", preset: "zigbee_plug", device_id: "" });
  const [metricForm, setMetricForm] = useState({ value_type: "num", enforce_validation: true });
  const [processBindings, setProcessBindings] = useState({});
  const [bindingBusy, setBindingBusy] = useState("");
  const devices = Array.isArray(snapshot?.devices) ? snapshot.devices : [];
  const entities = Array.isArray(snapshot?.entities) ? snapshot.entities : [];
  const metrics = Array.isArray(snapshot?.metrics) ? snapshot.metrics : [];
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
  const uiV2EnabledCount = navItems.filter((item) => uiV2Tabs[item.id]).length;
  const bindingRows = Object.values(processBindings).sort((a, b) => String(a.label || "").localeCompare(String(b.label || "")));

  async function loadProcessBindings() {
    try {
      const data = await api("/api/process-bindings");
      setProcessBindings(data.bindings || {});
    } catch (err) {
      setToast(err.message);
    }
  }

  useEffect(() => {
    loadProcessBindings();
  }, []);

  function setTabUiV2(tabId, enabled) {
    if (!setUiV2Tabs) return;
    setUiV2Tabs((current) => {
      const next = { ...current };
      if (enabled) next[tabId] = true;
      else delete next[tabId];
      return next;
    });
    const label = navItems.find((item) => item.id === tabId)?.label || tabId;
    setToast(`${label}: ${enabled ? "V2 preview enabled" : "Stable UI enabled"}`);
  }

  function setAllUiV2(enabled) {
    if (!setUiV2Tabs) return;
    setUiV2Tabs(() => {
      if (!enabled) return {};
      return Object.fromEntries(navItems.map((item) => [item.id, true]));
    });
    setToast(enabled ? "V2 preview enabled for all tabs" : "Stable UI enabled for all tabs");
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
    setDeviceForm((current) => ({
      ...current,
      device_id: value,
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
    }));
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
      setDeviceForm({ platform: selectedPreset.platform, preset: deviceForm.preset, opening_type: selectedPreset.openingType || "window", device_id: "", rain_alert_enabled: false });
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
      <section className="panel admin-overview-panel">
        <div className="panel-head">
          <h2>Device Maintenance</h2>
          <span>{devices.length} device | {entities.length} entity | {metrics.length} metric</span>
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
                      {binding.uses_fallback && <small>fallback</small>}
                    </td>
                    <td>
                      <select
                        value={selectedId}
                        disabled={bindingBusy === binding.process_key}
                        onChange={(event) => saveProcessBinding(binding.process_key, event.target.value)}
                      >
                        {!candidates.length && <option value="">No candidates</option>}
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

      <section className="panel ui-v2-panel">
        <div className="panel-head">
          <h2>UI V2 Preview</h2>
          <span>{uiV2EnabledCount}/{navItems.length} tab enabled | stable UI remains the fallback</span>
        </div>
        <div className="ui-v2-toolbar">
          <IconButton icon={Play} className={uiV2EnabledCount === navItems.length ? "" : "secondary"} onClick={() => setAllUiV2(true)}>Enable all</IconButton>
          <IconButton icon={Square} className={uiV2EnabledCount === 0 ? "" : "secondary"} onClick={() => setAllUiV2(false)}>Stable all</IconButton>
        </div>
        <div className="ui-v2-grid">
          {navItems.map(({ id, label, icon: Icon }) => {
            const enabled = Boolean(uiV2Tabs[id]);
            return (
              <article className={enabled ? "ui-v2-row active" : "ui-v2-row"} key={id}>
                <div className="ui-v2-row-title">
                  <Icon size={17} aria-hidden="true" />
                  <div>
                    <strong>{label}</strong>
                    <span>{enabled ? "V2 preview selected" : "Stable UI selected"}</span>
                  </div>
                </div>
                <div className="mode-switch ui-v2-switch" aria-label={`${label} UI version`}>
                  <button className={!enabled ? "active" : "secondary"} type="button" onClick={() => setTabUiV2(id, false)}>Stable</button>
                  <button className={enabled ? "active" : "secondary"} type="button" onClick={() => setTabUiV2(id, true)}>V2 Preview</button>
                </div>
              </article>
            );
          })}
        </div>
      </section>

      <section className="grid two">
        <article className="panel">
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
            {(deviceForm.preset === "window_contact" || selectedMetricRules.some((rule) => rule.metric_key === "contact") || deviceForm.opening_type) && (
              <label>Opening type
                <select value={deviceForm.opening_type || "window"} onChange={(event) => updateDevice("opening_type", event.target.value)}>
                  <option value="window">Window</option>
                  <option value="door">Door</option>
                </select>
              </label>
            )}
            {(deviceForm.preset === "window_contact" || selectedMetricRules.some((rule) => rule.metric_key === "contact") || deviceForm.opening_type) && (
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
              </>
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
              label: "Opening",
              render: (row) => row.opening_type
                ? `${row.opening_type}${row.room_position == null ? "" : ` #${row.room_position}`}${row.opening_label ? ` | ${row.opening_label}` : ""}${row.has_mosquito_net ? " | net" : ""}${row.rain_alert_enabled ? " | rain alert" : ""}`
                : "-",
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

const AI_CHAT_STORAGE_KEY = "hc-ai-chat-session-v1";
const AI_CHAT_CONTEXT_WINDOW = 10;
const AI_POWER_OFF_DELAY_STORAGE_KEY = "hc-ai-power-off-delay-min";
const AI_POWER_OFF_UNTIL_STORAGE_KEY = "hc-ai-power-off-until";
const defaultAiMessages = () => [
  {
    role: "assistant",
    content: "Szia! Az AI szerver első alapverziója vagyok. Most még nincs HomeControl hatásköröm, csak beszélgetünk.",
    ts: new Date().toISOString(),
  },
];

function loadStoredAiMessages() {
  try {
    const rows = JSON.parse(window.localStorage.getItem(AI_CHAT_STORAGE_KEY) || "[]");
    if (Array.isArray(rows) && rows.length) return rows.filter((item) => item?.role && item?.content).slice(-AI_CHAT_CONTEXT_WINDOW);
  } catch {
    // Ignore invalid stored chat state and start clean.
  }
  return defaultAiMessages();
}

function AiChat({ setToast }) {
  const [status, setStatus] = useState({ ok: false, ready: false, provider: "-", model: "-", error: "", detail: "" });
  const [config, setConfig] = useState({
    provider: "ollama",
    model: "qwen3:1.7b",
    ollama_url: "http://ollama:11434",
    openai_base_url: "https://api.openai.com/v1",
    openai_api_key: "",
    openai_api_key_set: false,
    temperature: 0.2,
    num_ctx: 16384,
    num_predict: 1536,
    system_prompt: "",
  });
  const [recommendedModels, setRecommendedModels] = useState([]);
  const [localModels, setLocalModels] = useState([]);
  const [pull, setPull] = useState({ running: false, model: "", status: "idle", completed: 0, total: 0, error: "" });
  const [selectedModel, setSelectedModel] = useState("qwen3:1.7b");
  const [messages, setMessages] = useState(() => loadStoredAiMessages());
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [configBusy, setConfigBusy] = useState("");
  const [node, setNode] = useState({ configured: false, node: {}, ssh: {}, ollama: { models: [] } });
  const [nodeBusy, setNodeBusy] = useState("");
  const [gatewayBusy, setGatewayBusy] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [powerOffDelayMin, setPowerOffDelayMin] = useState(() => {
    const saved = Number(window.localStorage.getItem(AI_POWER_OFF_DELAY_STORAGE_KEY));
    return Number.isFinite(saved) && saved >= 0 ? saved : 5;
  });
  const [powerOffUntil, setPowerOffUntil] = useState(() => Number(window.localStorage.getItem(AI_POWER_OFF_UNTIL_STORAGE_KEY) || 0));
  const [nowMs, setNowMs] = useState(() => Date.now());
  const messageListRef = useRef(null);
  const typingTimersRef = useRef([]);
  const refreshTimersRef = useRef([]);

  useEffect(() => {
    loadAiAdmin();
  }, []);

  useEffect(() => {
    let modelRefreshTick = 0;
    const id = window.setInterval(() => {
      if (document.visibilityState === "hidden") return;
      loadAiStatus();
      loadAiNode();
      modelRefreshTick += 1;
      if (modelRefreshTick % 3 === 0) loadAiModels();
    }, 5000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    const id = window.setInterval(() => setNowMs(Date.now()), 1000);
    return () => window.clearInterval(id);
  }, []);

  useEffect(() => {
    window.localStorage.setItem(AI_POWER_OFF_DELAY_STORAGE_KEY, String(powerOffDelayMin));
  }, [powerOffDelayMin]);

  useEffect(() => {
    if (powerOffUntil > Date.now()) {
      window.localStorage.setItem(AI_POWER_OFF_UNTIL_STORAGE_KEY, String(powerOffUntil));
    } else {
      window.localStorage.removeItem(AI_POWER_OFF_UNTIL_STORAGE_KEY);
    }
  }, [powerOffUntil, nowMs]);

	  useEffect(() => {
	    const stored = messages.map(({ typing, fullContent, ...message }) => ({
	      ...message,
	      content: fullContent || message.content,
	    })).slice(-AI_CHAT_CONTEXT_WINDOW);
	    window.localStorage.setItem(AI_CHAT_STORAGE_KEY, JSON.stringify(stored));
	    messageListRef.current?.scrollTo({ top: messageListRef.current.scrollHeight, behavior: "smooth" });
	  }, [messages]);

  useEffect(() => () => {
    typingTimersRef.current.forEach((id) => window.clearInterval(id));
    typingTimersRef.current = [];
    refreshTimersRef.current.forEach((id) => window.clearTimeout(id));
    refreshTimersRef.current = [];
  }, []);

  useEffect(() => {
    if (!pull.running) return undefined;
    const id = window.setInterval(loadPullStatus, 1500);
    return () => window.clearInterval(id);
  }, [pull.running]);

  async function loadAiStatus() {
    try {
      const data = await api("/api/ai/status", { allowOkFalse: true });
      setStatus({
        ok: Boolean(data.gateway_ok || data.ok),
        ready: Boolean(data.ready ?? data.ok),
        provider: data.provider || "-",
        model: data.model || "-",
        error: "",
        detail: data.ready || data.ok ? data.detail || "" : "AI server unavailable",
      });
    } catch (err) {
      setStatus({ ok: false, ready: false, provider: "-", model: "-", error: "", detail: "AI gateway unavailable" });
    }
  }

  async function loadAiAdmin() {
    await Promise.all([loadAiStatus(), loadAiConfig(), loadAiModels(), loadPullStatus(), loadAiNode()]);
  }

  async function loadAiNode() {
    try {
      const data = await api("/api/ai/node/status", { allowOkFalse: true });
      setNode({ ...data, error: "" });
    } catch (err) {
      setNode((current) => ({ ...current, ok: false, error: "AI node status unavailable" }));
    }
  }

  async function loadAiConfig() {
    try {
      const data = await api("/api/ai/config");
      if (data.config) {
        setConfig(data.config);
        setSelectedModel(data.config.model || "qwen3:8b");
      }
      setRecommendedModels(data.recommended_models || []);
    } catch (err) {
      setToast(err.message);
    }
  }

  async function loadAiModels() {
    try {
      const data = await api("/api/ai/models", { allowOkFalse: true });
      setLocalModels(data.local_models || []);
      if (data.recommended_models?.length) setRecommendedModels(data.recommended_models);
      if (data.error) setStatus((current) => ({ ...current, detail: current.ready ? current.detail : "AI server unavailable" }));
    } catch (err) {
      setStatus((current) => ({ ...current, detail: current.ready ? current.detail : "AI models unavailable" }));
    }
  }

  async function loadPullStatus() {
    try {
      const data = await api("/api/ai/models/pull/status");
      setPull(data.pull || { running: false, status: "idle" });
    } catch {
      // Pull status is best-effort; the main status panel shows connectivity errors.
    }
  }

  function scheduleAiRefresh(delays = [1500, 5000, 12000]) {
    delays.forEach((delay) => {
      const id = window.setTimeout(() => {
        loadAiStatus();
        loadAiNode();
        loadAiModels();
        refreshTimersRef.current = refreshTimersRef.current.filter((item) => item !== id);
      }, delay);
      refreshTimersRef.current.push(id);
    });
  }

  function updateConfig(key, value) {
    setConfig((current) => ({ ...current, [key]: value }));
    if (key === "model") setSelectedModel(value);
  }

  async function saveAiConfig(nextConfig = config) {
    setConfigBusy("save");
    try {
      const data = await api("/api/ai/config", {
        method: "POST",
        body: JSON.stringify({ config: nextConfig }),
      });
      setConfig(data.config || nextConfig);
      setStatus((current) => ({ ...current, provider: data.config?.provider || nextConfig.provider, model: data.config?.model || nextConfig.model, error: "" }));
      setToast("AI config saved");
    } catch (err) {
      setToast(err.message);
    } finally {
      setConfigBusy("");
    }
  }

  async function pullModel() {
    const model = selectedModel.trim();
    if (!model) return;
    setConfigBusy("pull");
    try {
      const data = await api("/api/ai/models/pull", {
        method: "POST",
        body: JSON.stringify({ model }),
      });
      setPull(data.pull || { running: true, model, status: "queued" });
      setToast(`Model download started: ${model}`);
    } catch (err) {
      setToast(err.message);
    } finally {
      setConfigBusy("");
    }
  }

  async function useModel(model) {
    const nextConfig = { ...config, provider: config.provider === "remote_ollama" ? "remote_ollama" : "ollama", model };
    setConfig(nextConfig);
    setSelectedModel(model);
    await saveAiConfig(nextConfig);
  }

  async function wakeAiNode() {
    setNodeBusy("wake");
    try {
      await api("/api/ai/node/wake", { method: "POST", body: "{}" });
      setToast("Wake packet sent");
      scheduleAiRefresh([2500, 7000, 15000, 30000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setNodeBusy("");
    }
  }

  async function runAiNodeCommand(action, message) {
    const delaySec = Math.max(0, Math.min(1440, Number(powerOffDelayMin) || 0)) * 60;
    const backupRunning = Boolean(node.backup_guard?.backup_running);
    const confirmText = backupRunning
      ? `A full AI backup is running. Queue shutdown after the backup finishes, then cut power after ${Math.round(delaySec / 60)} minutes?`
      : `Shut down the remote AI PC and cut its power plug after ${Math.round(delaySec / 60)} minutes?`;
    if (action === "shutdown" && !window.confirm(confirmText)) return;
    setNodeBusy(action);
    try {
      const data = await api("/api/ai/node/command", {
        method: "POST",
        body: JSON.stringify({ action, schedule_power_off_on_failure: action === "shutdown", power_off_delay_sec: delaySec, defer_if_backup_running: true }),
      });
      if (action === "shutdown" && data.power_off?.scheduled) {
        setPowerOffUntil(Date.now() + Number(data.power_off.delay_sec || delaySec) * 1000);
      }
      setToast(data.deferred ? "Shutdown queued after backup" : message);
      scheduleAiRefresh(action === "shutdown" ? [1500, 5000] : [1500, 5000, 12000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setNodeBusy("");
    }
  }

  async function restartAiGateway() {
    if (!window.confirm("Restart the HomeControl AI gateway and reload AI knowledge files?")) return;
    setGatewayBusy(true);
    try {
      const data = await api("/api/ai/restart", { method: "POST", body: "{}" });
      setToast(data.ready === false ? "AI gateway restart requested" : "AI gateway restarted");
      scheduleAiRefresh([1000, 3000, 7000, 12000]);
    } catch (err) {
      setToast(err.message);
    } finally {
      setGatewayBusy(false);
    }
  }

  async function connectRemoteNode() {
    const ollamaUrl = node?.node?.ollama_url || "";
    if (!ollamaUrl) {
      setToast("Remote Ollama URL is not configured");
      return;
    }
    const model = node?.ollama?.models?.[0]?.name || localModels?.[0]?.name || (config.model === "remote-model-pending" ? "" : config.model) || "qwen3:8b";
    const nextConfig = { ...config, provider: "remote_ollama", ollama_url: ollamaUrl, model };
    setConfig(nextConfig);
    setSelectedModel(model);
    await saveAiConfig(nextConfig);
    scheduleAiRefresh();
  }

	  function animateAssistantMessage(content, meta = "", error = false) {
    const fullContent = content || "Nincs válasz.";
    const id = `assistant-${Date.now()}-${Math.random().toString(36).slice(2)}`;
    setMessages((current) => [
      ...current,
      {
        id,
        role: "assistant",
        content: "",
        fullContent,
        typing: true,
        ts: new Date().toISOString(),
        meta,
        error,
      },
    ]);
    let index = 0;
    const step = Math.max(1, Math.ceil(fullContent.length / 180));
    const timer = window.setInterval(() => {
      index = Math.min(fullContent.length, index + step);
      setMessages((current) => current.map((message) => (
        message.id === id
          ? { ...message, content: fullContent.slice(0, index), typing: index < fullContent.length }
          : message
      )));
      if (index >= fullContent.length) {
        window.clearInterval(timer);
        typingTimersRef.current = typingTimersRef.current.filter((item) => item !== timer);
      }
    }, 18);
    typingTimersRef.current.push(timer);
	  }

	  function clearAiContextWindow() {
	    typingTimersRef.current.forEach((id) => window.clearInterval(id));
	    typingTimersRef.current = [];
	    window.localStorage.removeItem(AI_CHAT_STORAGE_KEY);
	    setMessages(defaultAiMessages());
	    setDraft("");
	    setToast("AI context window cleared");
	  }

	  async function sendMessage(event) {
    event.preventDefault();
    const text = draft.trim();
    if (!text || busy) return;

	    const historyForApi = messages
	      .filter((item) => !item.error && ["user", "assistant"].includes(item.role) && item.content)
	      .map(({ role, content }) => ({ role, content }))
	      .slice(-AI_CHAT_CONTEXT_WINDOW);
    const nextMessages = [...messages, { role: "user", content: text, ts: new Date().toISOString() }];
    setMessages(nextMessages);
    setDraft("");
    setBusy(true);

    try {
      const data = await api("/api/ai/chat", {
        method: "POST",
        body: JSON.stringify({
          message: text,
          history: historyForApi,
        }),
      });
      setStatus((current) => ({ ...current, ok: true, ready: true, provider: data.provider || status.provider, model: data.model || status.model, error: "", detail: "" }));
      animateAssistantMessage(data.reply || "Nincs válasz.", `${data.provider || "-"} | ${data.model || "-"} | ${data.elapsed_ms ?? "-"} ms`);
    } catch (err) {
      const message = aiFriendlyError(err.message);
      setStatus((current) => ({ ...current, ok: false, ready: false, error: "", detail: message }));
      animateAssistantMessage(message, "", true);
      setToast(message);
    } finally {
      setBusy(false);
    }
  }

  function handleKeyDown(event) {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      sendMessage(event);
    }
  }

  const machineReachable = Boolean(node.ssh?.ok);
  const ollamaRunning = Boolean(node.ollama?.ok);
  const gatewayConnected = config.provider === "remote_ollama" && config.ollama_url === node.node?.ollama_url;
  const modelReady = Boolean(status.ready);
  const aiNodeUnavailable = node.configured && !machineReachable && !ollamaRunning;
  const aiGatewayUnavailable = !status.ready;
  const installedModelNames = new Set(localModels.map((model) => model.name));
  const pullPercent = pull.total > 0 ? Math.round((Number(pull.completed || 0) / Number(pull.total)) * 100) : null;
  const powerOffRemainingSec = Math.max(0, Math.ceil((Number(powerOffUntil || 0) - nowMs) / 1000));
  const powerOffCountdown = powerOffRemainingSec > 0
    ? `${Math.floor(powerOffRemainingSec / 60)}:${String(powerOffRemainingSec % 60).padStart(2, "0")}`
    : "";
  const backupGuard = node.backup_guard || {};
  const shutdownDeferred = Boolean(backupGuard.deferred_shutdown);
  const backupGuardText = backupGuard.backup_running ? "backup running" : shutdownDeferred ? "shutdown queued" : "clear";

  return (
    <section className="ai-page">
      <section className="panel ai-infra-panel">
        <div className="panel-head">
          <h2 className="panel-title"><Server size={17} aria-hidden="true" /> AI Infrastructure</h2>
          <div className="ai-infra-badges">
            <span className={machineReachable ? "ai-status online" : "ai-status offline"}>machine</span>
            <span className={ollamaRunning ? "ai-status online" : "ai-status offline"}>ollama</span>
            <span className={gatewayConnected ? "ai-status online" : "ai-status offline"}>gateway</span>
            <span className={modelReady ? "ai-status online" : "ai-status offline"}>model</span>
          </div>
        </div>
        <div className="ai-infra-grid">
          <div>
            <span>Remote PC</span>
            <strong>{node.node?.host || "not configured"}</strong>
            <small>{machineReachable ? "SSH reachable" : aiNodeUnavailable ? "AI server unavailable" : node.ssh?.detail || "-"}</small>
          </div>
          <div>
            <span>Ollama</span>
            <strong>{ollamaRunning ? `${node.ollama.models?.length || 0} model` : "stopped"}</strong>
            <small>{ollamaRunning ? node.node?.ollama_url : aiNodeUnavailable ? "remote service unavailable" : node.ollama?.detail || "-"}</small>
          </div>
          <div>
            <span>Gateway</span>
            <strong>{status.provider}</strong>
            <small>{status.ready ? `${status.model} | ready` : aiGatewayUnavailable ? "AI server unavailable" : status.detail || "not ready"}</small>
          </div>
          <div>
            <span>Power Plug</span>
            <strong>{node.node?.power_entity_id || "not configured"}</strong>
            <small>{powerOffCountdown ? `power off in ${powerOffCountdown}` : `off ${powerOffDelayMin} min after shutdown`}</small>
          </div>
          <div>
            <span>Backup Guard</span>
            <strong>{backupGuardText}</strong>
            <small>{shutdownDeferred ? "shutdown will run after backup" : "AI PC shutdown is deferred during backup"}</small>
          </div>
        </div>
        <div className="ai-power-off-control">
          <label>
            <span>Power-off delay</span>
            <input
              type="number"
              min="0"
              max="1440"
              step="1"
              value={powerOffDelayMin}
              onChange={(event) => setPowerOffDelayMin(Math.max(0, Math.min(1440, Number(event.target.value) || 0)))}
            />
          </label>
          <strong>{powerOffCountdown || "not scheduled"}</strong>
        </div>
        <div className="ai-node-actions">
          <IconButton icon={Power} title="Bekapcsolja a tavoli AI gepet es WOL csomagot kuld." disabled={Boolean(nodeBusy) || !node.node?.mac_set} onClick={wakeAiNode}>{nodeBusy === "wake" ? "Waking" : "Wake PC"}</IconButton>
          <IconButton icon={Play} title="Elinditja a tavoli AI stack szolgaltatasait." disabled={Boolean(nodeBusy) || !machineReachable} onClick={() => runAiNodeCommand("start_stack", "Remote AI stack started")}>Start AI</IconButton>
          <IconButton icon={RefreshCw} title="Ujrainditja a tavoli AI PC stackjet." className="secondary" disabled={Boolean(nodeBusy) || !machineReachable} onClick={() => runAiNodeCommand("restart_stack", "Remote AI stack restarted")}>Restart AI</IconButton>
          <IconButton icon={RefreshCw} title="Ujrainditja a HomeControl AI gatewayt es frissiti a tanitasi cache-t." className="secondary" disabled={gatewayBusy} onClick={restartAiGateway}>{gatewayBusy ? "Restarting Gateway" : "Restart Gateway"}</IconButton>
          <IconButton icon={Square} title="Leallitja a tavoli AI stack szolgaltatasait." className="secondary" disabled={Boolean(nodeBusy) || !machineReachable || !ollamaRunning} onClick={() => runAiNodeCommand("stop_stack", "Remote AI stack stopped")}>Stop AI</IconButton>
          <IconButton icon={Save} title="A gatewayt a tavoli Ollama vegpontra allitja." className="secondary" disabled={Boolean(configBusy) || !ollamaRunning || !node.node?.ollama_url} onClick={connectRemoteNode}>Connect</IconButton>
          <IconButton icon={RefreshCw} title="Frissiti az AI statuszt, modelleket es node adatokat." className="secondary" disabled={Boolean(nodeBusy)} onClick={loadAiAdmin}>Refresh</IconButton>
          <IconButton icon={Power} title="Backup kozben sorba allitja, egyebkent leallitja a tavoli AI PC-t es kesleltetett aramtalanitast ker." className="danger" disabled={Boolean(nodeBusy) || !node.node?.power_entity_id} onClick={() => runAiNodeCommand("shutdown", "Remote AI PC shutdown requested; delayed power off scheduled")}>{backupGuard.backup_running ? "Shutdown After Backup" : "Shut Down PC"}</IconButton>
        </div>
        {node.error && <div className="ai-error">{node.error}</div>}
        {node.node?.openwebui_url && <a className="ai-node-link" href={node.node.openwebui_url} target="_blank" rel="noreferrer"><ExternalLink size={14} aria-hidden="true" /> Open WebUI</a>}
      </section>

      <section className="ai-chat-shell">
        <section className="panel ai-chat-panel">
          <div className="panel-head">
            <h2 className="panel-title"><Bot size={17} aria-hidden="true" /> Chat</h2>
            <div className="ai-chat-head-actions">
              <span className={status.ready ? "ai-status online" : "ai-status offline"}>{status.ready ? "ready" : "not ready"}</span>
              <IconButton icon={Trash2} className="secondary" type="button" title="Clear local AI chat context" onClick={clearAiContextWindow}>Clear</IconButton>
            </div>
          </div>
          <div className="ai-message-list" aria-live="polite" ref={messageListRef}>
            {messages.map((message, index) => (
              <article className={`ai-message ${message.role} ${message.error ? "error" : ""} ${message.typing ? "typing" : ""}`.trim()} key={message.id || `${message.role}-${index}-${message.ts}`}>
                <div className="ai-message-role">{message.role === "user" ? "You" : "AI"}</div>
                <p>{message.content}{message.typing && <span className="ai-typing-caret" aria-hidden="true" />}</p>
                {message.meta && <small>{message.meta}</small>}
              </article>
            ))}
            {busy && (
              <article className="ai-message assistant">
                <div className="ai-message-role">AI</div>
                <p><span className="ai-thinking-dot" /> <span className="ai-thinking-dot" /> <span className="ai-thinking-dot" /></p>
              </article>
            )}
          </div>
          <form className="ai-chat-form" onSubmit={sendMessage}>
            <textarea
              value={draft}
              onChange={(event) => setDraft(event.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="Message AI..."
              rows="3"
            />
            <IconButton icon={Play} type="submit" disabled={busy || !draft.trim() || !status.ready}>{busy ? "Sending" : "Send"}</IconButton>
          </form>
        </section>

        <section className="panel ai-side-panel">
        <div className="ai-model-manager">
          <div className="panel-head">
            <h2>Models</h2>
            <span>{localModels.length} local</span>
          </div>
          <label>
            <span>Download model</span>
            <input value={selectedModel} onChange={(event) => setSelectedModel(event.target.value)} placeholder="qwen3:8b" list="ai-model-suggestions" />
            <datalist id="ai-model-suggestions">
              {recommendedModels.map((model) => <option value={model.name} key={model.name}>{model.label}</option>)}
            </datalist>
          </label>
          <IconButton icon={Database} disabled={Boolean(configBusy) || pull.running || !selectedModel.trim()} onClick={pullModel}>
            {pull.running ? "Downloading" : "Download"}
          </IconButton>
          <div className="ai-pull-status">
            <span>{pull.model || "no active download"}</span>
            <strong>{pull.status || "idle"}</strong>
            {pullPercent !== null && <small>{pullPercent}%</small>}
            {pull.error && <small className="bad">{pull.error}</small>}
          </div>
          <div className="ai-model-list">
            {recommendedModels.map((model) => (
              <button className={model.installed || installedModelNames.has(model.name) ? "installed" : ""} type="button" onClick={() => useModel(model.name)} key={model.name}>
                <span>{model.name}</span>
                <small>{model.size} | {model.installed || installedModelNames.has(model.name) ? "installed" : model.note}</small>
              </button>
            ))}
            {localModels.filter((model) => !recommendedModels.some((item) => item.name === model.name)).map((model) => (
              <button className="installed" type="button" onClick={() => useModel(model.name)} key={model.name}>
                <span>{model.name}</span>
                <small>local model</small>
              </button>
            ))}
          </div>
        </div>

          <div className="ai-advanced">
            <button className="secondary ai-advanced-toggle" type="button" onClick={() => setAdvancedOpen((open) => !open)}>
              <Settings size={16} aria-hidden="true" />
              <span>{advancedOpen ? "Hide Advanced" : "Advanced Config"}</span>
            </button>
            {advancedOpen && (
              <div className="ai-config-form">
                <label>
                  <span>Provider</span>
                  <select value={config.provider} onChange={(event) => updateConfig("provider", event.target.value)}>
                    <option value="fallback">Fallback</option>
                    <option value="ollama">Ollama</option>
                    <option value="local_ollama">Local Ollama</option>
                    <option value="remote_ollama">Remote Ollama</option>
                    <option value="openai_compatible">OpenAI compatible</option>
                  </select>
                </label>
                <label>
                  <span>Model</span>
                  <input value={config.model} onChange={(event) => updateConfig("model", event.target.value)} placeholder="qwen3:8b" />
                </label>
                <label>
                  <span>Ollama URL</span>
                  <input value={config.ollama_url || ""} onChange={(event) => updateConfig("ollama_url", event.target.value)} placeholder="http://192.168.1.2:11434" />
                </label>
                <label>
                  <span>Cloud Base URL</span>
                  <input value={config.openai_base_url || ""} onChange={(event) => updateConfig("openai_base_url", event.target.value)} placeholder="https://api.openai.com/v1" />
                </label>
                <label>
                  <span>Cloud API Key</span>
                  <input type="password" value={config.openai_api_key || ""} onChange={(event) => updateConfig("openai_api_key", event.target.value)} placeholder={config.openai_api_key_set ? "saved" : "not set"} />
                </label>
                <label>
                  <span>Temperature</span>
                  <input type="number" min="0" max="2" step="0.1" value={config.temperature} onChange={(event) => updateConfig("temperature", event.target.value)} />
                </label>
                <label>
                  <span>Context</span>
                  <input type="number" min="512" max="262144" step="512" value={config.num_ctx} onChange={(event) => updateConfig("num_ctx", event.target.value)} />
                </label>
                <label>
                  <span>Max Tokens</span>
                  <input type="number" min="16" max="4096" step="16" value={config.num_predict} onChange={(event) => updateConfig("num_predict", event.target.value)} />
                </label>
                <label className="wide">
                  <span>System Prompt</span>
                  <textarea value={config.system_prompt} onChange={(event) => updateConfig("system_prompt", event.target.value)} rows="4" />
                </label>
                <div className="ai-config-actions wide">
                  <IconButton icon={Save} disabled={Boolean(configBusy)} onClick={() => saveAiConfig()}>{configBusy === "save" ? "Saving" : "Save Config"}</IconButton>
                  <IconButton icon={RefreshCw} className="secondary" disabled={Boolean(configBusy)} onClick={loadAiAdmin}>Refresh Config</IconButton>
                </div>
              </div>
            )}
          </div>
        </section>
      </section>
    </section>
  );
}

function Notes({ setToast }) {
  const [notes, setNotes] = useState({ issues: [], requests: [] });
  const [noteDraft, setNoteDraft] = useState({ type: "issues", text: "" });
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState("");

  useEffect(() => {
    loadNotes();
  }, []);
  useContextRefresh(["/api/context/notes"], (payload) => {
    setNotes({ issues: payload.issues || [], requests: payload.requests || [] });
    setLoading(false);
  });

  async function loadNotes() {
    setLoading(true);
    try {
      const data = await api("/api/context/notes");
      setNotes({ issues: data.issues || [], requests: data.requests || [] });
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  async function addNote(event) {
    event.preventDefault();
    const type = noteDraft.type === "requests" ? "requests" : "issues";
    const text = String(noteDraft.text || "").trim();
    if (!text) return;
    setBusy("add-note");
    try {
      const data = await api("/api/notes", {
        method: "POST",
        body: JSON.stringify({ type, text }),
      });
      setNotes(data.notes || { issues: [], requests: [] });
      setNoteDraft((current) => ({ ...current, text: "" }));
      setToast(type === "issues" ? "Issue added" : "Request added");
    } catch (err) {
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  async function updateNote(type, id, patch) {
    if ("text" in patch && !String(patch.text || "").trim()) {
      setToast("Note text is required");
      await loadNotes();
      return;
    }
    const previous = notes;
    setNotes((current) => ({
      ...current,
      [type]: (current[type] || []).map((item) => (item.id === id ? { ...item, ...patch } : item)),
    }));
    try {
      const data = await api(`/api/notes/${id}`, {
        method: "PUT",
        body: JSON.stringify(patch),
      });
      setNotes(data.notes || previous);
    } catch (err) {
      setNotes(previous);
      setToast(err.message);
    }
  }

  function editNoteText(type, id, text) {
    setNotes((current) => ({
      ...current,
      [type]: (current[type] || []).map((item) => (item.id === id ? { ...item, text } : item)),
    }));
  }

  function editNoteComment(type, id, comment) {
    setNotes((current) => ({
      ...current,
      [type]: (current[type] || []).map((item) => (item.id === id ? { ...item, comment } : item)),
    }));
  }

  async function deleteNote(type, id) {
    const previous = notes;
    setBusy(`delete-${id}`);
    setNotes((current) => ({
      ...current,
      [type]: (current[type] || []).filter((item) => item.id !== id),
    }));
    try {
      const data = await api(`/api/notes/${id}`, { method: "DELETE" });
      setNotes(data.notes || { issues: [], requests: [] });
    } catch (err) {
      setNotes(previous);
      setToast(err.message);
    } finally {
      setBusy("");
    }
  }

  function noteDate(value) {
    if (!value) return "-";
    return new Date(value).toLocaleString("en-GB", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
  }

  const noteTables = [
    { type: "issues", title: "Issues" },
    { type: "requests", title: "Requests" },
  ];

  return (
    <section className="notes-page">
      <article className="panel notes-entry-panel">
        <div className="panel-head">
          <h2>New Note</h2>
          <span>{(notes.issues || []).length} issues | {(notes.requests || []).length} requests</span>
        </div>
        <form className="notes-entry-form" onSubmit={addNote}>
          <div className="mode-toggle notes-type-toggle">
            <button className={noteDraft.type !== "requests" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => setNoteDraft((current) => ({ ...current, type: "issues" }))}>Issues</button>
            <button className={noteDraft.type === "requests" ? "mode-btn active" : "mode-btn"} type="button" onClick={() => setNoteDraft((current) => ({ ...current, type: "requests" }))}>Requests</button>
          </div>
          <textarea
            value={noteDraft.text}
            onChange={(event) => setNoteDraft((current) => ({ ...current, text: event.target.value }))}
            placeholder={noteDraft.type === "requests" ? "New request..." : "New issue..."}
          />
          <IconButton icon={Plus} type="submit" disabled={Boolean(busy)}>{busy === "add-note" ? "Adding" : "Add"}</IconButton>
        </form>
      </article>

      <section className="notes-grid">
        {noteTables.map(({ type, title }) => {
        const rows = notes[type] || [];
        return (
          <article className="panel notes-panel" key={type}>
            <div className="panel-head">
              <h2>{title}</h2>
              <span>{rows.filter((item) => item.done).length}/{rows.length} done</span>
            </div>
            <div className="table-wrap notes-table-wrap">
              <table className="notes-table">
                <thead>
                  <tr><th>Done</th><th>Text</th><th>Comment</th><th>Created</th><th>Action</th></tr>
                </thead>
                <tbody>
                  {loading ? (
                    <tr>
                      <td colSpan="5">Loading notes...</td>
                    </tr>
                  ) : rows.length ? rows.map((item) => (
                    <tr className={item.done ? "done" : ""} key={item.id}>
                      <td>
                        <input
                          aria-label={`Mark ${title.slice(0, -1)} done`}
                          type="checkbox"
                          checked={Boolean(item.done)}
                          onChange={(event) => updateNote(type, item.id, { done: event.target.checked })}
                        />
                      </td>
                      <td>
                        <input
                          className="notes-row-input"
                          value={item.text || ""}
                          onChange={(event) => editNoteText(type, item.id, event.target.value)}
                          onBlur={(event) => updateNote(type, item.id, { text: event.target.value })}
                        />
                      </td>
                      <td>
                        <textarea
                          className="notes-row-comment"
                          value={item.comment || ""}
                          onChange={(event) => editNoteComment(type, item.id, event.target.value)}
                          onBlur={(event) => updateNote(type, item.id, { comment: event.target.value })}
                          placeholder="Comment..."
                        />
                      </td>
                      <td>{noteDate(item.created_at)}</td>
                      <td>
                        <IconButton icon={Trash2} className="secondary notes-delete" type="button" disabled={busy === `delete-${item.id}`} onClick={() => deleteNote(type, item.id)}>
                          {busy === `delete-${item.id}` ? "Deleting" : "Delete"}
                        </IconButton>
                      </td>
                    </tr>
                  )) : (
                    <tr>
                      <td colSpan="5">No notes</td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </article>
        );
      })}
      </section>
    </section>
  );
}

function DocumentationPage({ setToast }) {
  const [docs, setDocs] = useState(null);
  const [selectedKey, setSelectedKey] = useState("");
  const [loading, setLoading] = useState(true);

  async function loadDocs() {
    setLoading(true);
    try {
      const data = await api("/api/documentation");
      setDocs(data);
      setSelectedKey((current) => current || data.modules?.[0]?.key || "");
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadDocs();
  }, []);

  if (loading && !docs) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading documentation...</span>
      </section>
    );
  }

  const modules = docs?.modules || [];
  const selected = modules.find((item) => item.key === selectedKey) || modules[0] || {};
  const source = selected.source || {};
  const bindings = selected.bindings || [];
  const devices = selected.devices || [];
  const buttons = selected.buttons || [];
  const deepDive = selected.deep_dive || [];

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl Documentation</h2>
          <span>{docs?.generated_at ? `${numberText(docs?.summary?.module_count, 0)} modules | ${numberText(docs?.summary?.binding_count, 0)} bindings | generated ${dateText(docs.generated_at)}` : "Module handbook"}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadDocs} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="documentation-layout">
        <aside className="panel documentation-nav">
          <div className="panel-head">
            <h2>Modules</h2>
            <span>{numberText(modules.length, 0)} entries</span>
          </div>
          <div className="documentation-module-list">
            {modules.map((module) => (
              <button
                type="button"
                key={module.key}
                className={module.key === selected.key ? "active" : ""}
                onClick={() => setSelectedKey(module.key)}
              >
                <BookOpen size={16} aria-hidden="true" />
                <span>{module.label}</span>
                <small>{module.domain}</small>
              </button>
            ))}
          </div>
        </aside>

        <article className="panel documentation-detail">
          <div className="panel-head">
            <h2>{selected.label || "Module"}</h2>
            <span>{selected.domain || "-"} | {source.path || "runtime"}</span>
          </div>

          <section className="documentation-section">
            <h3>Mit csinal?</h3>
            <p>{selected.summary || "-"}</p>
          </section>

          <section className="documentation-section">
            <h3>Hogyan mukodik, lepesrol lepesre?</h3>
            <ol>
              {(selected.responsibilities || []).map((item) => <li key={item}>{item}</li>)}
            </ol>
          </section>

          <section className="documentation-section">
            <h3>Gombok es muveletek</h3>
            <Table
              rows={buttons}
              columns={[
                { key: "name", label: "Button" },
                { key: "does", label: "What it does" },
                { key: "guard", label: "Guard / condition" },
              ]}
            />
          </section>

          {deepDive.length > 0 && (
            <section className="documentation-section documentation-deep-dive">
              <h3>Reszletes folyamatleiras</h3>
              <div className="documentation-deep-list">
                {deepDive.map((section) => (
                  <article className="documentation-deep-card" key={section.title}>
                    <h4>{section.title}</h4>
                    {section.body && <p>{section.body}</p>}
                    <ul>
                      {(section.items || []).map((item) => <li key={item}>{item}</li>)}
                    </ul>
                  </article>
                ))}
              </div>
            </section>
          )}

          <section className="documentation-grid">
            <section className="documentation-section">
              <h3>Elofeltetelek</h3>
              <ul>{(selected.prerequisites || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
            <section className="documentation-section">
              <h3>Kimenetek</h3>
              <ul>{(selected.outputs || []).map((item) => <li key={item}>{item}</li>)}</ul>
            </section>
          </section>

          <section className="documentation-section">
            <h3>Forraskod es meret</h3>
            <div className="about-fact-grid documentation-facts">
              <div><span>Path</span><strong>{source.path || (selected.files || []).join(", ") || "-"}</strong></div>
              <div><span>Files</span><strong>{numberText(source.files, 0)}</strong></div>
              <div><span>Lines</span><strong>{numberText(source.lines, 0)}</strong></div>
              <div><span>Size</span><strong>{byteText(source.bytes)}</strong></div>
            </div>
            <ul className="documentation-file-list">
              {(selected.files || []).map((item) => <li key={item}>{item}</li>)}
            </ul>
          </section>

          <section className="documentation-section">
            <h3>Csatolt funkciok</h3>
            <Table
              rows={bindings}
              columns={[
                { key: "label", label: "Function" },
                { key: "device_name", label: "Device", render: (row) => row.device_name || row.entity_name || "-" },
                { key: "location", label: "Location" },
                { key: "device_type", label: "Type" },
                { key: "topic_base", label: "Topic", render: (row) => shortValue(row.topic_base, 80) },
              ]}
            />
          </section>

          <section className="documentation-section">
            <h3>Dinamikusan talalt eszkozok</h3>
            <Table
              rows={devices}
              columns={[
                { key: "name", label: "Device" },
                { key: "location", label: "Location" },
                { key: "platform", label: "Platform" },
                { key: "device_type", label: "Type" },
                { key: "metrics", label: "Metrics", render: (row) => (row.metrics || []).slice(0, 8).join(", ") || "-" },
              ]}
            />
            <p className="documentation-note">
              {selected.device_count > devices.length
                ? `${numberText(selected.device_count, 0)} matching devices found; showing the first ${numberText(devices.length, 0)}.`
                : `${numberText(devices.length, 0)} matching devices shown.`}
            </p>
          </section>
        </article>
      </section>
    </>
  );
}

function AboutHomeControl({ setToast }) {
  const [about, setAbout] = useState(null);
  const [loading, setLoading] = useState(true);

  async function loadAbout() {
    setLoading(true);
    try {
      setAbout(await api("/api/about"));
    } catch (err) {
      setToast(err.message);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    loadAbout();
  }, []);

  if (loading && !about) {
    return (
      <section className="loading">
        <Activity size={22} />
        <span>Loading About...</span>
      </section>
    );
  }

  const source = about?.source || {};
  const totals = source.totals || {};
  const inventory = about?.inventory || {};
  const devices = inventory.devices || {};
  const entities = inventory.entities || {};
  const docker = about?.docker || {};
  const dockerSummary = docker.summary || {};
  const modules = source.modules || [];
  const sensorTypes = inventory.sensor_types || [];
  const metricTypes = inventory.metric_types || [];
  const containers = docker.containers || [];
  const server = about?.server || {};
  const cpu = server.cpu || {};
  const memory = server.memory || {};
  const diskRoot = server.disk?.root || {};
  const database = about?.database || {};
  const relationSummary = database.relation_summary || {};
  const measurement = database.measurement || {};
  const dbConnections = database.connections || {};
  const topTables = database.top_tables || [];
  const metricActivity = database.metric_activity_24h || [];
  const schemaTables = database.schema_tables || [];
  const loadAvgText = Array.isArray(cpu.load_avg) && cpu.load_avg.length ? cpu.load_avg.map((value) => numberText(value, 2)).join(" / ") : "-";
  const cpuTypeText = [cpu.vendor, cpu.architecture].filter(Boolean).join(" | ") || "-";

  return (
    <>
      <section className="stats-head">
        <div>
          <h2>HomeControl About</h2>
          <span>{about?.generated_at ? `Generated ${dateText(about.generated_at)} | ${numberText(about?.api?.response_ms, 1)} ms` : "Static inventory"}</span>
        </div>
        <IconButton icon={RefreshCw} onClick={loadAbout} disabled={loading}>{loading ? "Refreshing" : "Refresh"}</IconButton>
      </section>

      <section className="tile-grid stats-tiles about-tiles">
        <Card title="Source Size" value={byteText(totals.bytes)} meta={`${numberText(totals.files, 0)} files`} icon={Archive} />
        <Card title="Program Lines" value={numberText(totals.lines, 0)} meta="source + config + docs" icon={ClipboardList} />
        <Card title="Modules" value={numberText(source.module_count, 0)} meta={source.root || "-"} icon={Database} />
        <Card title="Containers" value={numberText(dockerSummary.total, 0)} meta={`${numberText(dockerSummary.running, 0)} running`} icon={Server} tone={docker.ok === false ? "warn" : ""} />
        <Card title="Devices" value={numberText(devices.devices_active ?? devices.devices_total, 0)} meta={`${numberText(entities.entities_active ?? entities.entities_total, 0)} entities`} icon={Radio} />
        <Card title="Sensor Types" value={numberText(sensorTypes.length, 0)} meta={`${numberText(metricTypes.length, 0)} metric types`} icon={Gauge} />
        <Card title="CPU" value={unitValue(cpu.percent, "%", 1)} meta={`${cpu.model || "-"} | ${numberText(cpu.cores, 0)} cores`} icon={Cpu} tone={cpu.ok && cpu.percent >= 85 ? "warn" : ""} />
        <Card title="RAM" value={byteText(memory.total_bytes)} meta={`${byteText(memory.available_bytes)} free | ${unitValue(memory.percent, "%", 1)} used`} icon={HardDrive} tone={memory.ok && memory.percent >= 85 ? "warn" : ""} />
        <Card title="SSD Free" value={byteText(diskRoot.free_bytes)} meta={`${byteText(diskRoot.total_bytes)} total | ${unitValue(diskRoot.percent, "%", 1)} used`} icon={HardDrive} tone={diskRoot.ok && diskRoot.percent >= 85 ? "warn" : ""} />
        <Card title="Database" value={byteText(database.size_bytes)} meta={`${numberText(relationSummary.table_count ?? database.table_count, 0)} tables | ${numberText(database.index_count, 0)} indexes`} icon={Database} tone={database.ok === false ? "warn" : ""} />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>HC Server</h2>
            <span>{server.hostname || "-"} | uptime {uptimeText(server.uptime_sec)}</span>
          </div>
          <div className="about-fact-grid">
            <div><span>CPU model</span><strong>{cpu.model || "-"}</strong></div>
            <div><span>CPU type</span><strong>{cpuTypeText}</strong></div>
            <div><span>CPU cores</span><strong>{numberText(cpu.cores, 0)}</strong></div>
            <div><span>CPU MHz</span><strong>{unitValue(cpu.mhz, "MHz", 0)}</strong></div>
            <div><span>CPU cache</span><strong>{cpu.cache || "-"}</strong></div>
            <div><span>CPU family/model</span><strong>{[cpu.family, cpu.model_id, cpu.stepping].filter(Boolean).join(" / ") || "-"}</strong></div>
            <div><span>CPU flags</span><strong>{numberText(cpu.flags_count, 0)}</strong></div>
            <div><span>CPU load</span><strong>{loadAvgText}</strong></div>
            <div><span>CPU now</span><strong>{unitValue(cpu.percent, "%", 1)}</strong></div>
            <div><span>BogoMIPS</span><strong>{numberText(cpu.bogomips, 1)}</strong></div>
            <div><span>RAM total</span><strong>{byteText(memory.total_bytes)}</strong></div>
            <div><span>RAM free</span><strong>{byteText(memory.available_bytes)}</strong></div>
            <div><span>RAM used</span><strong>{byteText(memory.used_bytes)}</strong></div>
            <div><span>RAM usage</span><strong>{unitValue(memory.percent, "%", 1)}</strong></div>
            <div><span>SSD total</span><strong>{byteText(diskRoot.total_bytes)}</strong></div>
            <div><span>SSD free</span><strong>{byteText(diskRoot.free_bytes)}</strong></div>
            <div><span>SSD used</span><strong>{byteText(diskRoot.used_bytes)}</strong></div>
            <div><span>SSD usage</span><strong>{unitValue(diskRoot.percent, "%", 1)}</strong></div>
          </div>
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Database Snapshot</h2>
            <span>{database.ok === false ? database.error || "unavailable" : `${numberText(database.response_ms, 1)} ms`}</span>
          </div>
          <div className="about-fact-grid">
            <div><span>Database</span><strong>{database.name || "-"}</strong></div>
            <div><span>PostgreSQL</span><strong>{database.server_version || "-"}</strong></div>
            <div><span>Encoding</span><strong>{database.encoding || "-"}</strong></div>
            <div><span>Timezone</span><strong>{database.timezone || "-"}</strong></div>
            <div><span>DB size</span><strong>{byteText(database.size_bytes)}</strong></div>
            <div><span>Schemas</span><strong>{numberText(database.schema_count, 0)}</strong></div>
            <div><span>HC tables</span><strong>{numberText(relationSummary.table_count ?? database.table_count, 0)}</strong></div>
            <div><span>Indexes</span><strong>{numberText(database.index_count, 0)}</strong></div>
            <div><span>Estimated rows</span><strong>{numberText(relationSummary.estimated_rows, 0)}</strong></div>
            <div><span>Measurement rows</span><strong>{numberText(measurement.row_estimate, 0)}</strong></div>
            <div><span>Samples 24h</span><strong>{numberText(measurement.samples_24h, 0)}</strong></div>
            <div><span>Active entities 24h</span><strong>{numberText(measurement.active_entities_24h, 0)}</strong></div>
            <div><span>Connections</span><strong>{database.ok === false ? "-" : `${numberText(dbConnections.total, 0)} / ${numberText(dbConnections.max, 0)}`}</strong></div>
            <div><span>Active / idle</span><strong>{`${numberText(dbConnections.active, 0)} / ${numberText(dbConnections.idle, 0)}`}</strong></div>
            <div><span>First sample</span><strong>{dateText(measurement.first_ts)}</strong></div>
            <div><span>Last sample</span><strong>{dateText(measurement.last_ts)}</strong></div>
          </div>
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Largest DB Tables</h2>
            <span>{byteText(relationSummary.total_bytes)} stored in hc schema</span>
          </div>
          <Table
            rows={topTables}
            columns={[
              { key: "name", label: "Table" },
              { key: "row_estimate", label: "Rows", render: (row) => numberText(row.row_estimate, 0) },
              { key: "total_bytes", label: "Total", render: (row) => byteText(row.total_bytes) },
              { key: "table_bytes", label: "Data", render: (row) => byteText(row.table_bytes) },
              { key: "index_bytes", label: "Index", render: (row) => byteText(row.index_bytes) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Metric Activity 24h</h2>
            <span>{numberText(measurement.metric_keys_24h, 0)} metric keys</span>
          </div>
          <Table
            rows={metricActivity}
            columns={[
              { key: "key", label: "Metric" },
              { key: "samples_24h", label: "Samples", render: (row) => numberText(row.samples_24h, 0) },
              { key: "entities_24h", label: "Entities", render: (row) => numberText(row.entities_24h, 0) },
              { key: "last_ts", label: "Latest", render: (row) => dateText(row.last_ts) },
            ]}
          />
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Database Structure</h2>
          <span>{numberText(schemaTables.length, 0)} hc tables</span>
        </div>
        <Table
          rows={schemaTables}
          columns={[
            { key: "name", label: "Table" },
            { key: "primary_key", label: "PK", render: (row) => row.primary_key || "-" },
            { key: "column_count", label: "Columns", render: (row) => numberText(row.column_count, 0) },
            { key: "foreign_key_count", label: "FKs", render: (row) => numberText(row.foreign_key_count, 0) },
            { key: "columns", label: "Structure", render: (row) => shortValue(row.columns, 260) },
          ]}
        />
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Source Modules</h2>
            <span>{numberText(totals.lines, 0)} total lines</span>
          </div>
          <Table
            rows={modules}
            columns={[
              { key: "name", label: "Module" },
              { key: "path", label: "Path" },
              { key: "files", label: "Files", render: (row) => numberText(row.files, 0) },
              { key: "lines", label: "Lines", render: (row) => numberText(row.lines, 0) },
              { key: "bytes", label: "Size", render: (row) => byteText(row.bytes) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Sensor Types</h2>
            <span>{numberText(devices.devices_active, 0)} active devices</span>
          </div>
          <Table
            rows={sensorTypes}
            columns={[
              { key: "type", label: "Type" },
              { key: "capabilities", label: "What it does", render: (row) => (row.capabilities || []).join(", ") || "-" },
              { key: "examples", label: "Examples", render: (row) => row.examples || row.locations || "-" },
              { key: "platform", label: "Platform" },
              { key: "device_count", label: "Devices", render: (row) => numberText(row.device_count, 0) },
              { key: "entity_count", label: "Entities", render: (row) => numberText(row.entity_count, 0) },
              { key: "metrics", label: "Metrics", render: (row) => (row.metrics || []).slice(0, 6).join(", ") || "-" },
            ]}
          />
        </article>
      </section>

      <section className="grid two">
        <article className="panel">
          <div className="panel-head">
            <h2>Metric Types</h2>
            <span>enabled entity metrics</span>
          </div>
          <Table
            rows={metricTypes}
            columns={[
              { key: "metric_key", label: "Metric" },
              { key: "entity_count", label: "Entities", render: (row) => numberText(row.entity_count, 0) },
            ]}
          />
        </article>

        <article className="panel">
          <div className="panel-head">
            <h2>Containers</h2>
            <span>{docker.ok === false ? docker.error || "Docker unavailable" : `${numberText(dockerSummary.running, 0)} running`}</span>
          </div>
          <Table
            rows={containers}
            columns={[
              { key: "name", label: "Name" },
              { key: "image", label: "Image" },
              { key: "state", label: "State" },
              { key: "status", label: "Status" },
            ]}
          />
        </article>
      </section>
    </>
  );
}

function App() {
  const { snapshot, error, loading, load, refreshIrrigation, setSnapshot } = useBootstrap();
  const [activeTab, setActiveTab] = useState(defaultTabForViewport);
  const [viewportHomeTab, setViewportHomeTab] = useState(dashboardTabForViewport);
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [aiTopbarStatus, setAiTopbarStatus] = useState({ ok: false, detail: "checking" });
  const [toast, setToast] = useState("");
  const [theme] = useState(() => {
    const saved = window.localStorage.getItem("hc-theme");
    if (saved === "light" || saved === "dark") return saved;
    return "dark";
  });
  const [skin, setSkin] = useState(() => {
    const saved = window.localStorage.getItem("hc-skin");
    return skinOptions.some((option) => option.value === saved) ? saved : "premium";
  });
  const [uiV2Tabs, setUiV2Tabs] = useState(readUiV2Tabs);

  useEffect(() => {
    if (!toast) return undefined;
    const id = window.setTimeout(() => setToast(""), 2800);
    return () => window.clearTimeout(id);
  }, [toast]);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    window.localStorage.setItem("hc-theme", theme);
  }, [theme]);

  useEffect(() => {
    document.documentElement.dataset.skin = skin;
    window.localStorage.setItem("hc-skin", skin);
  }, [skin]);

  useEffect(() => {
    const applyTooltips = () => document.querySelectorAll("button").forEach(ensureButtonTooltip);
    const handlePointer = (event) => {
      const button = event.target?.closest?.("button");
      ensureButtonTooltip(button);
    };
    applyTooltips();
    document.addEventListener("mouseover", handlePointer);
    document.addEventListener("focusin", handlePointer);
    const observer = new MutationObserver(applyTooltips);
    observer.observe(document.body, { childList: true, subtree: true });
    return () => {
      document.removeEventListener("mouseover", handlePointer);
      document.removeEventListener("focusin", handlePointer);
      observer.disconnect();
    };
  }, []);

  useEffect(() => {
    window.localStorage.setItem(UI_V2_STORAGE_KEY, JSON.stringify(uiV2Tabs));
  }, [uiV2Tabs]);

  const navIds = new Set(navItems.map((item) => item.id));
  const visibleNavItems = navItems.filter((item) => !item.homeViewport || item.id === viewportHomeTab);
  const activeUiVersion = uiV2Tabs[activeTab] ? "v2-preview" : "stable";
  const activeNavItem = navItems.find((item) => item.id === activeTab);
  const activeNavLabel = activeNavItem?.label || "HomeControl";
  const activeNavTone = activeNavItem?.tone || "var(--tone-blue)";

  useEffect(() => {
    const syncHash = () => {
      const hash = window.location.hash.replace("#", "");
      if (!hash || !navIds.has(hash)) return;
      const nextHomeTab = dashboardTabForViewport();
      if (HOME_DASHBOARD_TABS.has(hash) && hash !== nextHomeTab) {
        setActiveTab(nextHomeTab);
        return;
      }
      setActiveTab(hash);
    };
    syncHash();
    window.addEventListener("hashchange", syncHash);
    return () => window.removeEventListener("hashchange", syncHash);
  }, []);

  useEffect(() => {
    const mobileQuery = window.matchMedia?.(MOBILE_DASHBOARD_MEDIA);
    const tabletQuery = window.matchMedia?.(TABLET_DASHBOARD_MEDIA);
    if (!mobileQuery || !tabletQuery) return undefined;

    const syncDashboardViewport = () => {
      const nextHomeTab = dashboardTabForViewport();
      setViewportHomeTab(nextHomeTab);
      setActiveTab((current) => {
        if (HOME_DASHBOARD_TABS.has(current) && current !== nextHomeTab) {
          window.location.hash = nextHomeTab;
          return nextHomeTab;
        }
        return current;
      });
    };

    syncDashboardViewport();
    mobileQuery.addEventListener("change", syncDashboardViewport);
    tabletQuery.addEventListener("change", syncDashboardViewport);
    return () => {
      mobileQuery.removeEventListener("change", syncDashboardViewport);
      tabletQuery.removeEventListener("change", syncDashboardViewport);
    };
  }, []);

  useEffect(() => {
    if (!["home", "irrigation"].includes(activeTab)) return undefined;
    refreshIrrigation();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") refreshIrrigation();
    }, 10000);
    return () => window.clearInterval(id);
  }, [activeTab]);

  useEffect(() => {
    let cancelled = false;
    async function loadAiTopbarStatus() {
      try {
        const response = await fetch("/api/ai/status", { headers: { "Content-Type": "application/json" } });
        const data = await readJsonResponse(response);
        if (!cancelled) {
          const ready = Boolean(data.ready);
          const detail = ready
            ? data.detail || `${data.provider || "AI"} ${data.model || ""}`.trim()
            : data.detail || data.error || "AI server unavailable";
          setAiTopbarStatus({ ok: ready, detail });
        }
      } catch (err) {
        if (!cancelled) setAiTopbarStatus({ ok: false, detail: err.message });
      }
    }
    loadAiTopbarStatus();
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") loadAiTopbarStatus();
    }, 15000);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);

  const statusItems = [
    ["HC Online", Boolean(snapshot) && !error],
    ["MQTT", Boolean(snapshot?.irrigation?.live)],
    ["PostgreSQL", Boolean(snapshot?.devices)],
    ["AI Server", aiTopbarStatus.ok],
    ["Zigbee", snapshot?.devices?.some((device) => device.platform === "zigbee")],
    ["Tuya", snapshot?.devices?.some((device) => device.platform === "tuya")],
  ];

  if (loading && !snapshot) {
    return (
      <main className="loading">
        <Activity size={22} />
        <span>Loading data...</span>
      </main>
    );
  }

  return (
    <div className="app-shell" data-section={activeTab} data-ui-version={activeUiVersion}>
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark"><Home size={20} aria-hidden="true" /></div>
          <div>
            <h1>HomeControl</h1>
            <p>Smart home OS</p>
          </div>
          <button
            className="mobile-menu-toggle"
            type="button"
            aria-expanded={mobileMenuOpen}
            aria-controls="primary-nav"
            onClick={() => setMobileMenuOpen((open) => !open)}
          >
            <Menu size={17} aria-hidden="true" />
            <span>Menu</span>
          </button>
        </div>
        <div className="sidebar-health">
          <span>DB online</span>
          <span>{snapshot ? `${snapshot.devices.length} device | ${snapshot.entities.length} entity` : "connecting"}</span>
        </div>
        <nav className={mobileMenuOpen ? "side-nav open" : "side-nav"} id="primary-nav" aria-label="Admin tabs">
          {visibleNavItems.map(({ id, label, icon: Icon, tone }) => (
            <button
              className={activeTab === id ? "side-nav-btn active" : "side-nav-btn"}
              style={{ "--tone": tone }}
              type="button"
              onClick={() => {
                setActiveTab(id);
                window.location.hash = id;
                setMobileMenuOpen(false);
              }}
              key={id}
            >
              <Icon size={17} aria-hidden="true" />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      </aside>

      <div className={`app-content section-${activeTab}`} data-section={activeTab} data-ui-version={activeUiVersion} style={{ "--section-tone": activeNavTone }}>
        <header className="topbar">
          <div>
            <h1>{activeNavLabel}</h1>
            <p>{error || (snapshot ? `${snapshot.devices.length} device | ${snapshot.entities.length} entity` : "Connecting...")}</p>
          </div>
          <div className="top-actions">
            {activeUiVersion === "v2-preview" && <span className="ui-version-badge">V2 Preview</span>}
            <div className="status-strip" aria-label="System status">
              {statusItems.map(([label, ok]) => (
                <span className={ok ? "online" : "offline"} title={label === "AI Server" ? aiTopbarStatus.detail : ""} key={label}><i />{label}</span>
              ))}
            </div>
          </div>
        </header>

        <main>
        {snapshot && activeTab === "home" && (
          <UserDashboard snapshot={snapshot} reload={load} setToast={setToast} variant={uiV2Tabs.home ? "v2" : "v1"} />
        )}
        {snapshot && activeTab === "mobile-dashboard" && (
          <RenderErrorBoundary>
            <MobileDashboard snapshot={snapshot} reload={load} setToast={setToast} />
          </RenderErrorBoundary>
        )}
        {snapshot && activeTab === "tablet-dashboard" && (
          <RenderErrorBoundary>
            <TabletDashboard snapshot={snapshot} reload={load} setToast={setToast} activeTab={activeTab} setActiveTab={setActiveTab} menuItems={visibleNavItems} />
          </RenderErrorBoundary>
        )}
        {snapshot && activeTab === "irrigation" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.irrigation)} sectionId="irrigation">
            <Irrigation snapshot={snapshot} reload={load} setToast={setToast} />
          </V2AutoPage>
        )}
        {activeTab === "solar" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.solar)} sectionId="solar">
            <SolarDashboard />
          </V2AutoPage>
        )}
        {activeTab === "statistics" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.statistics)} sectionId="statistics">
            <IrrigationStatistics />
          </V2AutoPage>
        )}
        {activeTab === "power-wall" && (
          <RenderErrorBoundary>
            <PowerWall variant={uiV2Tabs["power-wall"] ? "v2" : "v1"} />
          </RenderErrorBoundary>
        )}
        {activeTab === "nyest-scheduler" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs["nyest-scheduler"])} sectionId="nyest-scheduler">
            <NyestriasztoScheduler setToast={setToast} />
          </V2AutoPage>
        )}
        <section hidden={activeTab !== "ai"}>
          <RenderErrorBoundary>
            <V2AutoPage enabled={Boolean(uiV2Tabs.ai)} sectionId="ai">
              <AiChat setToast={setToast} />
            </V2AutoPage>
          </RenderErrorBoundary>
        </section>
        {activeTab === "tuya" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.tuya)} sectionId="tuya">
            <TuyaPlayground />
          </V2AutoPage>
        )}
        {activeTab === "x10" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.x10)} sectionId="x10">
            <XiaomiX10 setToast={setToast} />
          </V2AutoPage>
        )}
        {activeTab === "climate" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.climate)} sectionId="climate">
            <ClimateControl setToast={setToast} />
          </V2AutoPage>
        )}
        {snapshot && activeTab === "scheduler" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.scheduler)} sectionId="scheduler">
            <SchedulerHub initialState={snapshot.scheduler} setToast={setToast} />
          </V2AutoPage>
        )}
        {activeTab === "hc-stat" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs["hc-stat"])} sectionId="hc-stat">
            <HcStatistics />
          </V2AutoPage>
        )}
        {activeTab === "performance" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.performance)} sectionId="performance">
            <Performance />
          </V2AutoPage>
        )}
        {activeTab === "backup" && (
          <V2AutoPage enabled={Boolean(uiV2Tabs.backup)} sectionId="backup">
            <Backup />
          </V2AutoPage>
        )}
        {snapshot && activeTab === "hc-admin" && (
          <RenderErrorBoundary>
            <V2AutoPage enabled={Boolean(uiV2Tabs["hc-admin"])} sectionId="hc-admin">
              <HcAdmin
                snapshot={snapshot}
                reload={load}
                setToast={setToast}
                setSnapshot={setSnapshot}
                skin={skin}
                setSkin={setSkin}
                navItems={navItems}
                uiV2Tabs={uiV2Tabs}
                setUiV2Tabs={setUiV2Tabs}
              />
            </V2AutoPage>
          </RenderErrorBoundary>
        )}
        {activeTab === "notes" && (
          <RenderErrorBoundary>
            <V2AutoPage enabled={Boolean(uiV2Tabs.notes)} sectionId="notes">
              <Notes setToast={setToast} />
            </V2AutoPage>
          </RenderErrorBoundary>
        )}
        {activeTab === "documentation" && (
          <RenderErrorBoundary>
            <V2AutoPage enabled={Boolean(uiV2Tabs.documentation)} sectionId="documentation">
              <DocumentationPage setToast={setToast} />
            </V2AutoPage>
          </RenderErrorBoundary>
        )}
        {activeTab === "about" && (
          <RenderErrorBoundary>
            <V2AutoPage enabled={Boolean(uiV2Tabs.about)} sectionId="about">
              <AboutHomeControl setToast={setToast} />
            </V2AutoPage>
          </RenderErrorBoundary>
        )}
        </main>
      </div>

      {activeUiVersion === "v2-preview" && (
        <VisualAuditButton activeTab={activeTab} activeLabel={activeNavLabel} uiV2Tabs={uiV2Tabs} setToast={setToast} />
      )}
      <div className={`toast ${toast ? "show" : ""}`}>{toast}</div>
    </div>
  );
}

createRoot(document.getElementById("root")).render(<App />);
