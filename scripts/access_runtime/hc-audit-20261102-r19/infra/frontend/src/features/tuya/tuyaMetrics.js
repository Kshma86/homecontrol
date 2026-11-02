export function tuyaStateValue(device, key) {
  const item = device?.state?.[key];
  return item ? item.value : undefined;
}

export function tuyaValueText(value, digits = 1) {
  if (value === undefined || value === null || value === "") return "-";
  if (typeof value === "boolean") return value ? "on" : "off";
  const number = Number(value);
  if (Number.isFinite(number)) return number.toLocaleString("en-GB", { maximumFractionDigits: digits });
  return String(value);
}

export function tuyaMetric(device, key, suffix = "", digits = 1) {
  const value = tuyaStateValue(device, key);
  const text = tuyaValueText(value, digits);
  return text === "-" ? text : `${text}${suffix}`;
}
