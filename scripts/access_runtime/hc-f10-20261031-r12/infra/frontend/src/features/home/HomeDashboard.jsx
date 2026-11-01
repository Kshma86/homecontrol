import React, { useEffect, useState } from "react";
import { Activity, BatteryCharging, Bell, CalendarDays, ChevronRight, Clock, Compass, Droplets, Gauge, Home, Play, Power, Radio, RefreshCw, Save, Square, Thermometer, Wind, Zap } from "lucide-react";
import { api, usePolledContext } from "../../apiClient";
import { findYardSensor, selectedProcessDevice } from "../../entityHelpers";
import { climateFanOptions, climateModeOptions } from "../climate/climateOptions";
import { climateDraftFromState } from "../climate/climateState";
import { powerWallMetricText, PowerWallPowerMetric, powerWallValue, switchOn } from "../powerWall/powerWallCommon";
import { solarMetricText, solarStateValue } from "../solar/solarMetrics";
import { parseSegmentList, x10ModeOptions, x10SuctionOptions, x10WaterOptions } from "../x10/x10Options";
import { roomCleanPlan, timeAfterMinutes, waitForX10CommandResult } from "../x10/x10Runtime";
import { OpeningSensorIcons, SensorSnapshotTable, roomDisplayName, roomKey, roomStatusRows } from "../../houseSensors";
import { Card, IconButton, Table, V2Page, V2SectionGrid } from "../../uiPrimitives";
import { dateText, displayEntityName, metricNumber, numberText, optionLabel, shortValue, textValue, unitValue } from "../../formatters";
import { tuyaValueText } from "../tuya/tuyaMetrics";
import {
  climateUserStatus,
  firstTimestamp,
  homeSensorSnapshot,
  irrigationUserStatus,
  metersPerSecondToKmh,
  nextActiveSchedule,
  pressureDeltaSummary,
  shortChartTime,
  shortTimeText,
  signedNumberText,
  weatherDailyMin,
  weatherDescription,
  weatherWindDegrees,
  windDirectionLabel,
  x10UserStatus,
} from "./homeDashboardUtils";

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

function HomePressureSparkline({ weatherRows = [], localRows = [] }) {
  const weather = homeChartSeries(weatherRows, "pressure_hpa");
  const local = homeChartSeries(localRows, "pressure_hpa");
  const allPoints = [...weather, ...local];
  if (weather.length < 2 && local.length < 2) return <div className="home-sparkline-empty tone-purple">No trend</div>;

  const top = 8;
  const bottom = 64;
  const left = 24;
  const right = 98;
  const values = allPoints.map((point) => point.value);
  const minRaw = Math.min(...values);
  const maxRaw = Math.max(...values);
  const padding = Math.max((maxRaw - minRaw) * 0.12, 0.2);
  const min = minRaw - padding;
  const span = Math.max(maxRaw + padding - min, 1);
  const timed = allPoints.filter((point) => Number.isFinite(point.timeMs));
  const firstMs = Math.min(...timed.map((point) => point.timeMs));
  const lastMs = Math.max(...timed.map((point) => point.timeMs));
  const timeSpan = Math.max(lastMs - firstMs, 1);
  const pathFor = (series) => series.map((point, index) => {
    const x = left + ((point.timeMs - firstMs) / timeSpan) * (right - left);
    const y = bottom - ((point.value - min) / span) * (bottom - top);
    return `${index ? "L" : "M"} ${x.toFixed(1)} ${y.toFixed(1)}`;
  }).join(" ");
  const ticks = [maxRaw, (minRaw + maxRaw) / 2, minRaw].map((value) => numberText(value, 1));

  return (
    <div className="home-sparkline home-pressure-sparkline">
      <svg viewBox="0 0 100 72" aria-hidden="true" preserveAspectRatio="none">
        <line className="home-sparkline-grid" x1={left} y1={top} x2={right} y2={top} />
        <line className="home-sparkline-grid" x1={left} y1={(top + bottom) / 2} x2={right} y2={(top + bottom) / 2} />
        <line className="home-sparkline-grid" x1={left} y1={bottom} x2={right} y2={bottom} />
        <line className="home-sparkline-axis" x1={left} y1={top} x2={left} y2={bottom} />
        {weather.length >= 2 && <path className="home-sparkline-line weather-pressure-line" d={pathFor(weather)} />}
        {local.length >= 2 && <path className="home-sparkline-line local-pressure-line" d={pathFor(local)} />}
      </svg>
      <div className="home-sparkline-y">
        {ticks.map((tick, index) => <span key={`${tick}-${index}`}>{tick}</span>)}
      </div>
      <div className="home-sparkline-x">
        <span>{shortChartTime(new Date(firstMs).toISOString())}</span>
        <span>{shortChartTime(new Date(firstMs + timeSpan / 2).toISOString())}</span>
        <span>{shortChartTime(new Date(lastMs).toISOString())}</span>
      </div>
      <div className="home-pressure-legend"><span className="weather">OWM</span><span className="local">Local</span></div>
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

const safetyLevelDetails = {
  unknown: { label: "Biztonsági állapot ismeretlen", reason: "Hiányzó vagy elavult biztonsági adat; friss értékelés szükséges.", tone: "orange" },
  idle: { label: "Nyugalmi állapot", reason: "Az elszívó nem működik.", tone: "safety" },
  green: { label: "Minden rendben", reason: "Az elszívó működik, a konyhai légutánpótlás nyitva van.", tone: "safety" },
  secondary: { label: "Távoli légutánpótlás", reason: "A konyhai ablak zárva, de egy kijelölt másik ablak nyitva van.", tone: "orange" },
  closed: { label: "Nincs légutánpótlás", reason: "Az elszívó működik, de minden kijelölt ablak zárva vagy ismeretlen állapotú.", tone: "orange" },
  co_warning: { label: "CO figyelmeztetés", reason: "A CO-szint emelkedik vagy elérte az előriasztási küszöböt.", tone: "red" },
  danger: { label: "VESZÉLY", reason: "A biztonsági rendszer veszélyt érzékelt.", tone: "red" },
  latched: { label: "Riasztás reteszelve", reason: "Egy korábbi veszélyriasztás kézi nyugtázásra vár.", tone: "red" },
};

function SafetySignalLamp({ safety, level }) {
  const [lit, setLit] = useState(false);
  const config = safety?.config || {};
  const enabled = safety?.level !== "disabled";
  const continuous = enabled && ["co_warning", "danger", "latched"].includes(level);
  const interval = level === "green" ? config.green_interval_seconds : level === "secondary" ? config.secondary_interval_seconds : config.closed_interval_seconds;
  const color = level === "green" ? config.green_color : ["secondary", "closed"].includes(level) ? config.orange_color : config.red_color;
  const brightness = level === "green" ? config.green_brightness : ["secondary", "closed"].includes(level) ? config.orange_brightness : config.red_brightness;

  useEffect(() => {
    if (!enabled || level === "idle") {
      setLit(false);
      return undefined;
    }
    if (continuous) {
      setLit(true);
      return undefined;
    }
    if (!["green", "secondary", "closed"].includes(level)) return undefined;
    const intervalMs = Math.max(Number(interval || 1), 1) * 1000;
    const pulseMs = Math.min(Math.max(Number(config.pulse_seconds || 1), 0.1) * 1000, intervalMs);
    const origin = Number(safety?.signal?.last_signal_at_epoch || 0) * 1000 || Date.now();
    const update = () => {
      const phase = ((Date.now() - origin) % intervalMs + intervalMs) % intervalMs;
      setLit(phase < pulseMs);
    };
    update();
    const timer = window.setInterval(update, 100);
    return () => window.clearInterval(timer);
  }, [enabled, level, continuous, interval, config.pulse_seconds, safety?.signal?.last_signal_at_epoch]);

  const opacity = Math.max(0.18, Math.min(Number(brightness || 0) / 254, 1));
  return (
    <span
      className={`combustion-signal-lamp ${lit ? "lit" : ""} ${enabled ? "" : "disabled"}`}
      style={{ "--signal-color": color || "#ff0000", "--signal-opacity": opacity }}
      title={enabled ? "A fizikai jelzőlámpa ritmusa" : "A védelem ki van kapcsolva"}
      aria-label={lit ? "Jelzőlámpa világít" : "Jelzőlámpa nem világít"}
    />
  );
}

function combustionSafetyReason(safety, level, fallbackReason) {
  if (safety?.stale || safety?.evaluation_error) return "A biztonsági értékelés hiányzik, elavult vagy hibás; a korábbi retesz megmarad.";
  if (level !== "danger") return fallbackReason;
  if (safety?.smoke?.alarm) return "A füstérzékelő riaszt.";
  if (safety?.co?.alarm) return "A CO-érzékelő riaszt.";
  return "A CO-szint elérte a veszély- és lekapcsolási küszöböt.";
}

function CombustionSafetyStatusCard({ safety, fallbackCo, error }) {
  const enabled = safety?.level && safety.level !== "disabled";
  const level = enabled ? safety.level : safety?.would_level || "idle";
  const details = safetyLevelDetails[level] || safetyLevelDetails.idle;
  const coValue = safety?.co?.value_ppm ?? metricNumber(fallbackCo || {}, "carbon_monoxide_value");
  const smoke = safety?.smoke;
  const reason = combustionSafetyReason(safety, level, details.reason);
  const smokeText = !smoke?.configured ? "Füst: még nincs bekötve" : smoke.alarm ? "Füst: RIASZTÁS" : "Füst: rendben";
  const powerText = safety?.power_w == null ? "Elszívó: nincs fogyasztási adat" : `Elszívó: ${numberText(safety.power_w, 0)} W`;
  return (
    <article className={`home-status-card combustion-status-card ${level !== "idle" ? "active" : ""} tone-${details.tone}`}>
      <div className="home-status-icon combustion-status-icon"><SafetySignalLamp safety={safety} level={level} /></div>
      <div>
        <span>Elszívó / CO biztonság</span>
        <strong>{coValue !== null && coValue !== undefined ? `${numberText(coValue, 0)} ppm` : details.label}</strong>
        <small className="combustion-status-label">{details.label}</small>
        <small className="combustion-status-reason">{error && !safety ? error : reason}</small>
        <em>{smokeText} | {powerText}{enabled ? "" : " | VÉDELEM KIKAPCSOLVA"}</em>
      </div>
    </article>
  );
}

function UserStatusTiles({ irrigation, coSensor }) {
  const { data: x10State, error: x10Error } = usePolledContext("/api/context/robot", { intervalMs: 5000 });
  const { data: climateState, error: climateError } = usePolledContext("/api/context/climate", { intervalMs: 5000 });
  const { data: combustionSafety, error: combustionError } = usePolledContext("/api/combustion-safety/state", { intervalMs: 1000 });
  const error = x10Error || climateError;

  const irrigationStatus = irrigationUserStatus(irrigation);
  const x10Status = x10UserStatus(x10State);
  const climateStatus = climateUserStatus(climateState);
  return (
    <section className="home-status-grid">
      <HomeStatusCard title="Irrigation" value={irrigationStatus.value} description="Timed garden valve" meta={irrigationStatus.meta} icon={Droplets} active={irrigationStatus.active} tone="green" />
      <HomeStatusCard title="Robot" value={x10Status.value} description="Xiaomi X10 cleaner" meta={error && !x10State ? error : x10Status.meta} icon={Home} active={x10Status.active} tone="orange" />
      <HomeStatusCard title="Climate" value={climateStatus.value} description={climateStatus.description} meta={error && !climateState ? error : climateStatus.meta} icon={Wind} active={climateStatus.active} tone="blue" />
      <CombustionSafetyStatusCard safety={combustionSafety} fallbackCo={coSensor} error={combustionError} />
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
  const [busy, setBusy] = useState("");
  const { data: state, loading, refresh: loadX10 } = usePolledContext("/api/context/robot", {
    intervalMs: 5000,
    onError: (err) => setToast(err.message),
  });
  const [quickClean, setQuickClean] = useState({
    delay_min: 2,
    map_id: "",
    mode: "2",
    suction: "3",
    water_level: "2",
    segments: [],
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
      const previousResultTs = Number(state?.command_result?.ts || 0);
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
      await waitForX10CommandResult(api, "schedule_clean", previousResultTs);
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
  const [draft, setDraft] = useState(() => climateDraftFromState(null));
  const [draftDirty, setDraftDirty] = useState(false);
  const [busy, setBusy] = useState("");
  const { data: state, setData: setState, loading } = usePolledContext("/api/context/climate", {
    intervalMs: 10000,
    onError: (err) => setToast(err.message),
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
      setDraft({ ...climateDraftFromState(nextState), extra_fan: payload.extra_fan || draft.extra_fan });
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
      extra_fan: draft.extra_fan,
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
        <IconButton icon={Power} className="home-primary" disabled={Boolean(busy)} onClick={() => sendClimate({ power: "on", extra_fan: draft.extra_fan }, "power_on", "Climate turned on")}>On</IconButton>
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
        <label className="home-field">
          Extra fan
          <select value={draft.extra_fan} onChange={(event) => updateDraft("extra_fan", event.target.value)}>
            <option value="on">On</option>
            <option value="off">Off</option>
          </select>
        </label>
        <IconButton icon={Save} className="home-primary" disabled={Boolean(busy)} onClick={applyDraft}>{busy === "apply" ? "Applying" : "Apply"}</IconButton>
      </div>
    </article>
  );
}

function UserPowerWallDevice({ setToast }) {
  const [busy, setBusy] = useState("");
  const [policyBusy, setPolicyBusy] = useState("");
  const [historyByEntity, setHistoryByEntity] = useState({});
  const { data: state, loading, refresh: loadPowerWall } = usePolledContext("/api/context/power_wall", {
    intervalMs: 10000,
    onError: (err) => setToast(err.message),
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

export function NyestriasztoScheduler({ setToast }) {
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
  const motionEvents = Array.isArray(motion.events) ? motion.events : [];
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

function HomeSensorCard({ title, value, meta, unit, digits = 1, icon: Icon = Activity, tone = "blue", rows = [], valueKey, chartType = "line", secondary = null, chart = null }) {
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
      {chart || (secondary?.overlayChart ? (
        <HomeDualSparkline rows={secondary.rows || rows} primaryKey={valueKey} secondaryKey={secondary.valueKey} primaryDigits={digits} secondaryDigits={secondary.digits ?? 0} />
      ) : (
        <HomeSparkline rows={rows} valueKey={valueKey} tone={tone} type={chartType} digits={digits} />
      ))}
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
  const tankLiveItem = irrigation?.live?.topics?.tank_level;
  const tankLive = tankLiveItem && typeof tankLiveItem.json === "object" && !Array.isArray(tankLiveItem.json)
    ? tankLiveItem.json
    : null;
  const storedTank = latest.find((row) => String(row.key || "").toLowerCase() === "liquid_level_percent");
  const tankLevel = tankLive?.liquid_level_percent ?? tankLive?.percent ?? tankLive?.level_percent ?? storedTank?.v_num;
  const lastSession = irrigation?.session_stats?.[0] || null;
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
  const footerMeta = `Tank ${unitValue(tankLevel, "%", 0)} | Last: ${unitValue(lastSession?.duration_minutes, "min", 1)}`;

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

function HomeSensorGrid({ irrigation, weather, localSensors = [], mobileExtras = null }) {
  const { data: pilotState, error: pilotError } = usePolledContext("/api/context/irrigation_pilot", { intervalMs: 60000 });

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
  const yardPressure = metricNumber(yardSensor, "latest_pressure_hpa");
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
      <HomeSensorCard
        title="Pressure"
        value={pressure}
        unit="hPa"
        digits={0}
        icon={Gauge}
        tone="purple"
        meta={pressureMeta}
        rows={weatherRows}
        valueKey="pressure_hpa"
        chart={<HomePressureSparkline weatherRows={weatherRows} localRows={yardRows} />}
        secondary={{ label: "Local", value: yardPressure, unit: "hPa", digits: 1, icon: Gauge, overlayChart: true }}
      />
      <HomeSensorCard title={`Wind ${windDirection}`} value={wind} unit="km/h" digits={1} icon={Compass} tone="sky" meta={windMeta} rows={weatherRowsKmh} valueKey="wind_speed_kmh" chartType="bar" />
      {mobileExtras}
    </section>
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
  const houseRows = roomStatusRows(indoorSensors, openingSensors);
  const avgTempValues = indoorSensors.map((sensor) => metricNumber(sensor, "latest_temperature")).filter((value) => value !== null);
  const avgTemp = avgTempValues.length ? avgTempValues.reduce((sum, value) => sum + value, 0) / avgTempValues.length : null;
  const openCount = openingSensors.filter((sensor) => sensor.contact === false).length;
  return (
    <article className="home-side-card home-weather-card home-thermo-card tone-blue">
      <div className="home-panel-head">
        <div className="home-panel-icon"><Home size={20} aria-hidden="true" /></div>
        <div>
          <h2>House Status</h2>
          <span>{`${houseRows.length} rooms | ${indoorSensors.length} climate sensors | ${openCount} open | avg ${unitValue(avgTemp, "C", 1)}`}</span>
        </div>
      </div>
      <div className="home-thermo-list">
        {houseRows.map(({ room, sensor, openings }) => {
          const temp = metricNumber(sensor, "latest_temperature");
          const humidity = metricNumber(sensor, "latest_humidity");
          const hasClimate = temp !== null || humidity !== null;
          return (
            <div className={`home-thermo-row ${hasClimate ? "" : "missing-climate"}`} key={room}>
              <Thermometer size={16} aria-hidden="true" />
              <strong>{roomDisplayName(room)}</strong>
              <OpeningSensorIcons sensors={openings} />
              {sensor?.samples?.length ? <InlineTempSparkline rows={sensor.samples} /> : <span className="home-inline-sparkline empty" aria-label="Nincs hőmérő görbe">-</span>}
              <span>{unitValue(temp, "C", 1)}</span>
              <small>{humidity === null ? dateText(sensor?.latest_ts) : `${unitValue(humidity, "%", 0)} | ${dateText(sensor?.latest_ts)}`}</small>
            </div>
          );
        })}
      </div>
    </article>
  );
}

function HomeRecentEvents({ irrigation }) {
  const { data: x10State } = usePolledContext("/api/context/robot", { intervalMs: 30000 });
  const { data: climateState } = usePolledContext("/api/context/climate", { intervalMs: 30000 });
  const irrigationStatus = irrigationUserStatus(irrigation);
  const latest = irrigation.latest || [];
  const newest = latest.slice().sort((a, b) => new Date(b.ts || 0) - new Date(a.ts || 0))[0];
  const nextSchedule = nextActiveSchedule(irrigation.schedules || []);
  const latestSession = (irrigation.session_stats || irrigation.sessions || [])[0] || null;
  const sessionTime = firstTimestamp(latestSession);
  const x10Plan = roomCleanPlan(x10State?.room_clean_status, Date.now());
  const climateUpdatedAt = climateState?.updated_at || climateState?.power_meter?.updated_at || climateState?.power_meter?.last_seen_ts;
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

function HomeSolarPanel({ compact = false }) {
  const { data: solar, error } = usePolledContext("/api/context/solar", { intervalMs: 30000 });

  const values = solar?.state || {};
  const charts = solar?.charts || {};
  const productionRows = charts.production_power_24h || [];
  const dailyRows = charts.production_daily_30d || [];
  const powerNow = solarStateValue(values, "output_power_w");
  const todayEnergy = solarStateValue(values, "plant_energy_today_kwh") ?? solarStateValue(values, "energy_today_kwh");
  const todayRow = dailyRows[dailyRows.length - 1] || {};
  const todayKwh = todayEnergy ?? metricNumber(todayRow, "production_kwh");
  const monthProduction = solar?.summary?.production_month_kwh ?? null;
  const updatedAt = solar?.summary?.updated_at || solar?.entity?.last_seen_ts;

  if (compact) {
    return (
      <article className="home-side-card home-solar-card home-compact-info-card tone-yellow">
        <div className="home-sensor-top">
          <div className="home-panel-icon"><Zap size={18} aria-hidden="true" /></div>
          <div className="home-solar-heading">
            <span>Solar</span>
          </div>
        </div>
        <div className="home-compact-main-row">
          <strong>{solarMetricText(powerNow, "system_power_w")}</strong>
          <small className="home-solar-updated">{error || dateText(updatedAt)}</small>
        </div>
        <HomeSparkline rows={productionRows} valueKey="avg_production_power_w" tone="yellow" type="line" digits={0} />
        <div className="home-compact-main-row home-solar-bottom-stats">
          <span>{solarMetricText(todayKwh, "energy_today_kwh")} | {solarMetricText(monthProduction, "energy_today_kwh")}</span>
        </div>
      </article>
    );
  }

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
          <span>Month</span>
          <strong>{solarMetricText(monthProduction, "energy_today_kwh")}</strong>
        </div>
      </div>
    </article>
  );
}

function HomeSecuPanel({ fallbackCo }) {
  const { data: safety, error } = usePolledContext("/api/combustion-safety/state", { intervalMs: 1000 });
  const enabled = safety?.level && safety.level !== "disabled";
  const level = enabled ? safety.level : safety?.would_level || "idle";
  const details = safetyLevelDetails[level] || safetyLevelDetails.idle;
  const coValue = safety?.co?.value_ppm ?? metricNumber(fallbackCo || {}, "carbon_monoxide_value");
  const smoke = safety?.smoke;
  const indicator = safety?.indicator;
  const reason = combustionSafetyReason(safety, level, details.reason);
  const smokeText = !smoke?.configured ? "nincs bekötve" : smoke.alarm ? "RIASZTÁS" : "rendben";
  const indicatorText = !indicator?.configured ? "nincs bekötve" : indicator.radio_online === true ? "online" : indicator.radio_online === false ? "OFFLINE" : "ismeretlen";
  const extractorPower = Number(safety?.power_w);
  const extractorStage = !safety?.fan_active
    ? "OFF"
    : !Number.isFinite(extractorPower)
      ? "ON"
      : extractorPower < 100
        ? "1. fokozat"
        : extractorPower < 175
          ? "2. fokozat"
          : "3. fokozat";

  return (
    <article className={`home-side-card home-secu-card home-compact-info-card tone-${details.tone}`}>
      <div className="home-sensor-top">
        <div className="home-panel-icon combustion-status-icon"><SafetySignalLamp safety={safety} level={level} /></div>
        <span>Home Secu</span>
      </div>
      <div className="home-compact-main-row home-secu-value">
        <strong>{coValue !== null && coValue !== undefined ? `${numberText(coValue, 0)} ppm` : details.label}</strong>
        <span>Elszívó {extractorStage}</span>
      </div>
      <div className="home-secu-system-state" title={reason}>
        {error && !safety ? error : enabled ? details.label : "VÉDELEM KIKAPCSOLVA"}
      </div>
      <small>Füst: {smokeText} | Jelző: {indicatorText}</small>
    </article>
  );
}

function useHomeWeather() {
  const { data: weather = null } = usePolledContext("/api/context/irrigation_pilot", {
    intervalMs: 5000,
    mapPayload: (payload) => payload.weather || null,
  });
  const { data: statsPayload = null } = usePolledContext("/api/context/home_statistics", {
    intervalMs: 5000,
    refreshPaths: ["/api/context/home_statistics"],
  });
  const stats = statsPayload || {};
  const localSensors = stats.temp_humidity_sensors || [];
  const openingSensors = stats.opening_sensors || [];

  return { weather, localSensors, openingSensors, coSensor: stats.co_sensor || null };
}

export function UserDashboard({ snapshot, reload, setToast, variant = "v1" }) {
  const { weather, localSensors, openingSensors, coSensor } = useHomeWeather();
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
        <UserStatusTiles irrigation={snapshot?.irrigation || {}} coSensor={coSensor} />
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
      <UserStatusTiles irrigation={snapshot?.irrigation || {}} coSensor={coSensor} />
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
  const { data: x10State, error: x10Error } = usePolledContext("/api/context/robot", { intervalMs: 10000 });
  const { data: climateState, error: climateError } = usePolledContext("/api/context/climate", { intervalMs: 10000 });
  const { data: powerWallState, error: powerWallError } = usePolledContext("/api/context/power_wall", { intervalMs: 10000 });
  const statusError = x10Error || climateError || powerWallError;

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

export function MobileDashboard({ snapshot, reload, setToast }) {
  const { weather, localSensors, openingSensors, coSensor } = useHomeWeather();
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

      <HomeSensorGrid
        irrigation={snapshot?.irrigation || {}}
        weather={weather}
        localSensors={localSensors}
        mobileExtras={(
          <>
            <HomeSolarPanel compact />
            <HomeSecuPanel fallbackCo={coSensor} />
          </>
        )}
      />

      <section className="mobile-dash-side">
        <HomeWeatherPanel localSensors={localSensors} openingSensors={openingSensors} />
      </section>
    </section>
  );
}

export function TabletDashboard({ snapshot, reload, setToast, activeTab, setActiveTab, menuItems = [] }) {
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
