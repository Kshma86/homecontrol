export function validApplyCorrelation(value) {
  return value && Object.keys(value).sort().join() === ["request_id", "esp_boot", "stm_boot", "expected_revision", "parameters_crc"].sort().join()
    && /^[A-Za-z0-9_-]{1,64}$/.test(value.request_id) && Number.isInteger(value.expected_revision)
    && value.expected_revision > 0 && value.expected_revision <= 0xffffffff
    && [value.esp_boot, value.stm_boot].every((boot) => typeof boot === "string" && /^[0-9A-F]{16}$/.test(boot) && !/^0+$/.test(boot))
    && typeof value.parameters_crc === "string" && /^[0-9A-F]{8}$/.test(value.parameters_crc);
}

export function confirmedApplyOutcome(result, attempt) {
  if (!validApplyCorrelation(attempt) || result?.request_id !== attempt.request_id) return false;
  const snapshot = result.snapshot, config = snapshot?.parameters, identity = snapshot?.identity, state = snapshot?.state;
  const healthy = snapshot?.freshness?.fresh === true && snapshot.connection?.status === "LIVE"
    && identity?.mode === "MOTOR_TEST" && config?.storage === "ACTIVE" && config.applied === true && config.busy === false
    && config.available === true && config.source_valid === true && Number.isInteger(config.source_age_ms) && config.source_age_ms <= 1500
    && config.parameters && config.esp_boot === identity.esp_boot && config.stm_boot === identity.stm_boot && config.control_epoch === state?.control_epoch;
  if (!healthy) return false;
  if (result.result === "APPLIED") return config.request_id === attempt.request_id && config.revision === attempt.expected_revision && config.parameters_crc === attempt.parameters_crc;
  if (result.result === "CANCELLED") return result.code === "BOOT_CHANGED" && (identity.esp_boot !== attempt.esp_boot || identity.stm_boot !== attempt.stm_boot)
    && config.request_id !== attempt.request_id && config.revision < attempt.expected_revision && config.can_apply === true && identity.runtime_parameters === true
    && state.state === "DISARMED" && state.armed === false && state.stopped === true && [null, 0].includes(state.manual_lease_id);
  return false;
}
