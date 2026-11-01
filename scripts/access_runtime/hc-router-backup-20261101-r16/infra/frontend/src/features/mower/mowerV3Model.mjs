export const STATE_TIMEOUT_MS = 1500;

export function currentState(snapshot, receivedAt, now) {
  const age = snapshot?.freshness?.effective_age_ms;
  const elapsed = receivedAt === null ? 0 : Math.max(0, now - receivedAt);
  const effectiveAge = Number.isInteger(age) ? age + elapsed : null;
  const fresh = snapshot?.freshness?.fresh === true
    && snapshot?.connection?.status === "LIVE"
    && (snapshot?.identity?.update_locked === false || snapshot?.simple_control === true || snapshot?.identity?.mode === "MOTOR_TEST")
    && receivedAt !== null
    && effectiveAge !== null && effectiveAge <= STATE_TIMEOUT_MS;
  return { fresh, effectiveAge, state: fresh ? snapshot.state : null };
}

export function displayBoolean(value, yes, no) {
  return value === true ? yes : value === false ? no : "Ismeretlen";
}

export function displayMask(value) {
  return Number.isInteger(value) ? `0x${value.toString(16).padStart(8, "0").toUpperCase()}` : "Ismeretlen";
}
