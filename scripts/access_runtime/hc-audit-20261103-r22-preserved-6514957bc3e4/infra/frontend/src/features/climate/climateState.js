export function climateDraftFromState(state) {
  return {
    power: state?.power || "off",
    mode: state?.mode && state.mode !== "unknown" ? state.mode : "auto",
    target_temperature: state?.target_temperature ?? 23,
    fan_speed: state?.fan_speed && state.fan_speed !== "unknown" ? state.fan_speed : "auto",
    extra_fan: "on",
    light: state?.light || "off",
  };
}
