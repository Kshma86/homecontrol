export const MANUAL_PROTOCOL = "homecontrol.mower.manual.v3";
export const TERMINAL_RESULTS = new Set(["APPLIED", "REJECTED"]);

export function validCommandResult(result, record) {
  if (!result || result.request_id !== record.request_id || result.command !== record.command
      || !["PENDING", "UNKNOWN", "APPLIED", "REJECTED"].includes(result.result)) return false;
  if (result.result !== "APPLIED") return true;
  return result.code === "OK" && /^[0-9A-F]{16}$/.test(result.stm_boot) && result.stm_boot !== "0000000000000000"
    && (!record.stm_boot || record.stm_boot === result.stm_boot)
    && Number.isInteger(result.control_epoch) && result.control_epoch > 0 && result.control_epoch <= 0xffffffff
    && Number.isInteger(result.state_seq) && result.state_seq > 0 && result.state_seq <= 0xffffffff
    && ["DISARMED", "IDLE", "MANUAL", "AUTO", "PAUSED", "FAULT", "MAINTENANCE"].includes(result.state);
}

export function manualStateInvalid(state, lease) {
  const delta = (state.control_epoch - lease.control_epoch) >>> 0;
  // Older pre-claim snapshots are allowed until the lease epoch is observed.
  return delta > 0 && delta < 0x80000000 || delta === 0 && (state.state !== "MANUAL" || state.manual_lease_id !== lease.lease_id);
}

export function newRequestId() {
  return `hc3-${globalThis.crypto?.randomUUID?.() || `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`}`;
}

export function commandPayload(command, value, identity, state, requestId) {
  if (command === "stop") return { v: 3, request_id: requestId };
  if (!identity?.esp_boot || !identity?.stm_boot || !Number.isInteger(state?.control_epoch)) throw new Error("Nincs friss roverazonosság.");
  return { v: 3, request_id: requestId, esp_boot: identity.esp_boot,
    stm_boot: identity.stm_boot, control_epoch: state.control_epoch, command, value };
}

export function fullSetpoint(lease, seq, intent, held) {
  if (!validLease(lease) || typeof held !== "boolean" || !Number.isInteger(seq) || seq < 1 || seq > 0xffffffff) throw new Error("Érvénytelen kézi lease.");
  if (lease.drive_mode === "ERPM") {
    const targets = [intent.left ?? 0, intent.right ?? 0, intent.thirdEnabled ? intent.third ?? 0 : 0];
    if (!targets.every((value, index) => Number.isInteger(value) && Math.abs(value) <= lease.motor_erpm_limits[index])) throw new Error("Érvénytelen eRPM célérték.");
    return { type: "drive_erpm", lease_id: lease.lease_id, control_epoch: lease.control_epoch, seq,
      left_erpm: held ? targets[0] : 0, right_erpm: held ? targets[1] : 0, third_erpm: held ? targets[2] : 0, deadman: held };
  }
  if (!Number.isInteger(intent.linear) || !Number.isInteger(intent.yaw)
    || Math.abs(intent.linear) > lease.max_linear_mm_s || Math.abs(intent.yaw) > lease.max_yaw_mdeg_s) throw new Error("Érvénytelen kézi sebesség.");
  return { type: "drive", lease_id: lease.lease_id, control_epoch: lease.control_epoch,
    seq, linear_mm_s: held ? intent.linear : 0, yaw_mdeg_s: held ? intent.yaw : 0,
    blade_rpm: 0, deadman: held === true };
}

export function validLease(frame) {
  return frame?.type === "claimed" && Number.isInteger(frame.lease_id) && frame.lease_id > 0
    && frame.lease_id <= 0xffffffff && Number.isInteger(frame.control_epoch) && frame.control_epoch > 0 && frame.control_epoch <= 0xffffffff
    && frame.lease_ms === 350 && (frame.drive_mode === "ERPM"
      ? frame.max_linear_mm_s === 0 && frame.max_yaw_mdeg_s === 0 && Array.isArray(frame.motor_erpm_limits)
        && frame.motor_erpm_limits.length === 3 && frame.motor_erpm_limits.every((v, i) => Number.isInteger(v) && v >= (i < 2 ? 1 : 0) && v <= (i < 2 ? 6000 : 25000))
      : (frame.drive_mode === undefined || frame.drive_mode === "METRIC") && Number.isInteger(frame.max_linear_mm_s) && frame.max_linear_mm_s > 0
    && frame.max_linear_mm_s <= 65535 && Number.isInteger(frame.max_yaw_mdeg_s) && frame.max_yaw_mdeg_s > 0 && frame.max_yaw_mdeg_s <= 360000);
}

export function commandLabel(command) {
  return ({ stop: "STOP", arm: "Élesítés", disarm: "Hatástalanítás", pause: "Szünet",
    start: "Küldetés indítása", resume: "Folytatás", reset_fault: "Hiba törlése", heading_set: "Északi referencia" })[command] || command;
}

export function canClaimManual(snapshot, state) {
  const identity = snapshot?.identity;
  const direct = identity?.mode === "MOTOR_TEST" && identity.manual_claim_from_disarmed === true && identity.test_manual_control === true;
  return snapshot?.capabilities?.manual === true && !["RECEIVING", "VALIDATING"].includes(state?.store)
    && (direct ? ["DISARMED", "IDLE"].includes(state?.state) : state?.state === "IDLE" && state?.stopped === true);
}
