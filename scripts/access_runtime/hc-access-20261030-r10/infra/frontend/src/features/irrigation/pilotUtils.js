import { numberText, unitValue } from "../../formatters";

export const pilotFields = [
  ["rain_24h_threshold_mm", "Rain threshold", "mm", 0.1],
  ["forecast_rain_threshold_mm", "Forecast rain threshold", "mm", 0.1],
  ["pop_threshold_percent", "POP threshold", "%", 1],
  ["heat_threshold_c", "Heat starts", "C", 0.1],
  ["heat_step_c", "Heat step", "C", 0.1],
  ["heat_multiplier_step", "Heat multiplier step", "x", 0.01],
  ["cold_threshold_c", "Cool weather starts", "C", 0.1],
  ["cold_step_c", "Cool weather step", "C", 0.1],
  ["cold_multiplier_step", "Cool multiplier step", "x", 0.01],
  ["soil_wet_skip_threshold_percent", "Wet soil skip", "%", 1],
  ["soil_wet_adjust_threshold_percent", "Moisture reduce from", "%", 1],
  ["soil_wet_multiplier_delta", "Wet moisture multiplier", "x", 0.01],
  ["soil_dry_threshold_percent", "Dry soil threshold", "%", 1],
  ["soil_dry_multiplier_delta", "Dry soil multiplier", "x", 0.01],
  ["soil_sample_max_age_hours", "Soil max age", "h", 1],
  ["min_duration_multiplier", "Minimum multiplier", "x", 0.01],
  ["max_duration_multiplier", "Maximum multiplier", "x", 0.01],
];

export function ruleText(rules = []) {
  if (!Array.isArray(rules) || !rules.length) return "-";
  return rules.join(", ");
}

export function decisionStatusText(row = {}) {
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

export function signedMultiplierText(value) {
  const number = Number(value);
  if (!Number.isFinite(number)) return "-";
  const text = Math.abs(number).toFixed(2);
  if (number > 0) return `+${text}`;
  if (number < 0) return `-${text}`;
  return "0.00";
}

export function pilotTermLabel(term = {}) {
  const labels = {
    base: "Base multiplier",
    heat_increase: "Heat",
    cold_decrease: "Cool weather",
    soil_wet_reduce: "Moisture",
    soil_dry_increase: "Dry soil",
    multiplier_clamped: "Limit",
  };
  return labels[term.rule] || term.rule || "Rule";
}

export function pilotTermMeta(term = {}) {
  if (term.rule === "base") return "default";
  if (term.rule === "heat_increase" || term.rule === "cold_decrease") {
    const source = term.source === "local_sensor" ? "local sensor" : term.source || "weather";
    return `${unitValue(term.temperature_c, "C", 1)} | ${term.steps || 1} step(s) | ${source}`;
  }
  if (term.rule === "soil_wet_reduce" || term.rule === "soil_dry_increase") {
    return `${unitValue(term.soil_moisture_percent, "%", 0)} | threshold ${unitValue(term.threshold_percent, "%", 0)}`;
  }
  if (term.rule === "multiplier_clamped") {
    return `${numberText(term.raw_multiplier, 2)}x -> ${numberText(term.multiplier, 2)}x`;
  }
  return "";
}
