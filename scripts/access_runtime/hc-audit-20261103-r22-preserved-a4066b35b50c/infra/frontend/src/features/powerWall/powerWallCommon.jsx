import React from "react";
import { displayEntityName, metricNumber, timestampLabel, unitValue } from "../../formatters";
import { tuyaStateValue, tuyaValueText } from "../tuya/tuyaMetrics";

export function powerWallValue(device, keys) {
  for (const key of keys) {
    const value = tuyaStateValue(device, key);
    if (value !== undefined && value !== null && value !== "") return value;
  }
  return undefined;
}

export function powerWallMetricText(value, suffix = "", digits = 1) {
  const text = tuyaValueText(value, digits);
  return text === "-" ? text : `${text}${suffix}`;
}

export function switchOn(value) {
  if (value === true) return true;
  if (value === false) return false;
  const text = String(value ?? "").trim().toUpperCase();
  if (text === "ON" || text === "TRUE" || text === "1") return true;
  if (text === "OFF" || text === "FALSE" || text === "0") return false;
  return null;
}

export function powerWallDisplayName(device = {}) {
  return displayEntityName(device.display_name || device.entity_name || device.device_name);
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

export function PowerWallPowerMetric({ device, value, history, loadHistory }) {
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
