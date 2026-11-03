export function dateText(value) {
  if (!value) return "-";
  return new Date(value).toLocaleString("en-GB", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

export function timestampLabel(value) {
  if (!value) return "-";
  return new Date(value).toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit", hour12: false });
}

export function dayLabel(value) {
  if (!value) return "-";
  return new Date(value).toLocaleDateString("en-GB", { month: "2-digit", day: "2-digit" });
}

export function metricNumber(row, key) {
  const value = row?.[key];
  if (value === undefined || value === null || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

export function displayEntityName(name) {
  const labels = {
    "Nyestriasztó": "Marten Deterrent",
  };
  return labels[name] || name;
}

export function textValue(value) {
  if (typeof value === "string" && ["none", "null", "undefined", "unknown_none", "unknown_null"].includes(value.trim().toLowerCase())) return "-";
  if (value === undefined || value === null || value === "") return "-";
  return String(value);
}

export function optionLabel(options, value) {
  const option = options.find((item) => String(item.value) === String(value));
  return option ? option.label : textValue(value);
}

export function numberText(value, digits = 1) {
  if (typeof value === "string" && ["none", "null", "undefined", "unknown_none", "unknown_null"].includes(value.trim().toLowerCase())) return "-";
  if (value === undefined || value === null || value === "") return "-";
  const number = Number(value);
  if (!Number.isFinite(number)) return String(value);
  return Number.isInteger(number) ? String(number) : number.toFixed(digits);
}

export function unitValue(value, unit, digits = 1) {
  const text = numberText(value, digits);
  return text === "-" ? "-" : `${text} ${unit}`;
}

export function byteText(value) {
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

export function uptimeText(seconds) {
  const total = Number(seconds);
  if (!Number.isFinite(total) || total < 0) return "-";
  const days = Math.floor(total / 86400);
  const hours = Math.floor((total % 86400) / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  if (days > 0) return `${days}d ${hours}h`;
  if (hours > 0) return `${hours}h ${minutes}m`;
  return `${minutes}m`;
}

export function ageText(item) {
  return item ? `${item.age_sec} s` : "-";
}

export function shortValue(value, max = 140) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (!text) return "-";
  return text.length > max ? `${text.slice(0, max - 3)}...` : text;
}

export function jsonText(value) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

export function statusTone(ok, warn = false) {
  if (ok) return "ok";
  return warn ? "warn" : "bad";
}

export function boolText(value) {
  return value ? "Running" : "Stopped";
}

export function valueText(row) {
  if (!row) return "-";
  if (row.v_num !== null && row.v_num !== undefined) return Number(row.v_num).toLocaleString("en-GB");
  if (row.v_bool !== null && row.v_bool !== undefined) return row.v_bool ? "true" : "false";
  if (row.v_text !== null && row.v_text !== undefined) return row.v_text;
  return "-";
}
