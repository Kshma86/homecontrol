import { displayEntityName } from "./formatters";

export function entitySelectLabel(entity) {
  if (!entity) return "-";
  const name = displayEntityName(entity.display_name || entity.entity_name || entity.device_name || "Entity");
  const location = entity.location ? ` | ${entity.location}` : "";
  const platform = entity.platform ? ` | ${entity.platform}` : "";
  return `${name}${location}${platform}`;
}

export function processBinding(state, key) {
  return state?.process_bindings?.[key] || {};
}

export function selectedProcessDevice(state, key, fallback) {
  const binding = processBinding(state, key);
  if (binding.configuration_state === "invalid") return null;
  const selectedId = binding.selected_entity_id ?? binding.selected_entity?.entity_id;
  const devices = state?.devices || [];
  if (selectedId) {
    const selected = devices.find((item) => String(item.entity_id) === String(selectedId));
    if (selected) return selected;
  }
  if (binding.selected_entity) return binding.selected_entity;
  // An authoritative empty binding must not become a different device in UI.
  if (Object.prototype.hasOwnProperty.call(state?.process_bindings || {}, key)) return null;
  return typeof fallback === "function" ? fallback(devices) : null;
}

export function findYardSensor(localSensors = []) {
  return localSensors.find((sensor) => sensor.entity_name === "Udvar")
    || localSensors.find((sensor) => String(sensor.entity_name || sensor.device_name || "").toLowerCase().includes("udvar"));
}
