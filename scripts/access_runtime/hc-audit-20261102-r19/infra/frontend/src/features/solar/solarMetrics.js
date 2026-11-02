import { numberText, unitValue } from "../../formatters";

export const solarMetricLabels = {
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

export function solarStateValue(state, key) {
  return state?.[key]?.value ?? null;
}

export function solarMetricText(value, key) {
  const [, unit = "", digits = 1] = solarMetricLabels[key] || [key, "", 1];
  if (value === null || value === undefined || value === "") return "-";
  if (typeof value === "number" || Number.isFinite(Number(value))) {
    return unit ? unitValue(Number(value), unit, digits) : numberText(Number(value), digits);
  }
  return String(value);
}
