import { dateText, metricNumber, numberText, textValue, unitValue } from "../../formatters";

export function shortTimeText(value) {
  if (!value) return "--:--";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "--:--";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function scheduleDateTime(schedule, base = new Date()) {
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

export function nextActiveSchedule(schedules = []) {
  const now = new Date();
  return schedules
    .filter((schedule) => schedule?.is_active)
    .map((schedule) => ({ schedule, at: schedule.should_run_now ? now : scheduleDateTime(schedule, now) }))
    .filter((item) => item.at)
    .sort((a, b) => a.at - b.at)[0] || null;
}

export function firstTimestamp(row, keys = ["stopped_at", "ended_at", "started_at", "created_at", "updated_at", "ts"]) {
  for (const key of keys) {
    if (row?.[key]) return row[key];
  }
  return null;
}

export function signedNumberText(value, digits = 1) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const text = Math.abs(number) < 0.05 ? "0" : numberText(number, digits);
  return number > 0 ? `+${text}` : text;
}

export function irrigationUserStatus(irrigation = {}) {
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

export function x10UserStatus(state) {
  const stateText = String(state?.robot_state_text || state?.state?.state_text || "").toLowerCase();
  const roomStatus = state?.room_clean_status || {};
  const roomStatusText = String(roomStatus.status || "").toLowerCase();
  const terminal = ["charging", "docked", "idle", "standby", "sleeping", "stopped", "completed"]
    .some((part) => stateText.includes(part));
  const robotRunning = ["cleaning", "room_cleaning", "working", "returning"]
    .some((part) => stateText.includes(part));
  const scheduledOrActive = ["scheduled", "active", "running"].includes(roomStatusText);
  const active = !terminal && (robotRunning || scheduledOrActive);
  return {
    active,
    value: active ? "ON" : "OFF",
    meta: active ? (robotRunning ? state?.robot_state_text || "active" : `room clean ${roomStatusText}`) : state?.robot_state_text || "idle",
  };
}

export function climateUserStatus(state) {
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

export function homeSensorSnapshot(irrigation = {}) {
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

export function shortChartTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function windDirectionLabel(degrees) {
  const value = Number(degrees);
  if (!Number.isFinite(value)) return "-";
  const labels = ["N", "NE", "E", "SE", "S", "SW", "W", "NW"];
  return labels[Math.round((((value % 360) + 360) % 360) / 45) % 8];
}

export function weatherWindDegrees(row = {}) {
  const direct = metricNumber(row, "wind_deg");
  if (direct !== null) return direct;
  const raw = row.raw || {};
  return Number(raw?.current?.wind?.deg ?? raw?.payload?.current?.wind_deg ?? raw?.current?.wind_deg ?? raw?.wind?.deg ?? NaN);
}

export function metersPerSecondToKmh(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number * 3.6 : null;
}

export function weatherDescription(row = {}) {
  const raw = row.raw || {};
  const weather = raw?.current?.weather || raw?.payload?.current?.weather || raw?.weather || [];
  const first = Array.isArray(weather) ? weather[0] : weather;
  return first?.description || first?.main || (metricNumber(row, "rain_mm") > 0 ? "rain" : "clear");
}

export function weatherDailyMin(row = {}) {
  const raw = row.raw || {};
  const value = raw?.daily?.[0]?.temp?.min
    ?? raw?.payload?.daily?.[0]?.temp?.min
    ?? raw?.forecast?.daily?.[0]?.temp?.min;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function pressureDeltaSummary(rows = []) {
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
