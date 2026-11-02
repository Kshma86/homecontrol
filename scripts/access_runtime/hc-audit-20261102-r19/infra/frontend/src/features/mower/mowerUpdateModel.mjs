const PHASES = new Set(["IDLE", "QUIESCING", "READY", "RECEIVING", "ERASING", "WRITING", "VERIFYING", "TRIAL", "COMPLETE", "ABORTED", "ERROR", "EXITING"]);
const hex = (value, size) => typeof value === "string" && new RegExp(`^[0-9A-F]{${size}}$`).test(value) && !/^0+$/.test(value);
const uint = (value, max = 0xffffffff) => Number.isInteger(value) && value >= 0 && value <= max;
const hash = (value) => typeof value === "string" && /^[0-9a-f]{64}$/.test(value);
const token = (value) => typeof value === "string" && /^[A-Za-z0-9_.-]{1,48}$/.test(value);

export function validSessionIntent(intent) {
  return !!intent && Object.keys(intent).sort().join(",") === "jobId,requestId" && hex(intent.jobId, 32)
    && typeof intent.requestId === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(intent.requestId);
}

export function validSessionAttempt(attempt, intent = null) {
  if (!attempt || !validSessionIntent({ jobId: attempt.hc_job_id, requestId: attempt.request_id })
    || !["CREATE_INTENT", "UNKNOWN", "ADMITTED", "REJECTED"].includes(attempt.state) || attempt.persisted !== true
    || (attempt.closed !== undefined && typeof attempt.closed !== "boolean") || attempt.closed && attempt.state !== "ADMITTED"
    || attempt.active !== (attempt.state !== "REJECTED" && !attempt.closed) || attempt.revision !== (attempt.state === "CREATE_INTENT" ? 1 : 2)
    || !hex(attempt.esp_boot, 16) || !hex(attempt.profile_crc, 8) || typeof attempt.code !== "string" || !/^[A-Z_0-9]{1,32}$/.test(attempt.code)
    || typeof attempt.created_at !== "string" || !Number.isFinite(Date.parse(attempt.created_at))
    || typeof attempt.updated_at !== "string" || !Number.isFinite(Date.parse(attempt.updated_at))) return false;
  if (attempt.state === "ADMITTED" ? !hex(attempt.update_id, 32) || attempt.progress_path !== `/api/v3/update/${attempt.update_id}`
    : attempt.update_id !== null || attempt.progress_path !== null) return false;
  return !intent || attempt.request_id === intent.requestId && attempt.hc_job_id === intent.jobId;
}

function vgIdentity(identity) {
  return identity?.v === 3 && identity.contract === "3.1.0" && typeof identity.update_locked === "boolean"
    && identity.stm_remote_update === true && identity.update_service_abi === 2
    && identity.stm_flash_layout === "H743_1M_QSPI2" && identity.stm_image_max_bytes === 524288 && hex(identity.esp_boot, 16)
    && hex(identity.profile_crc, 8) && identity.stm_confirmed_slot === null && identity.stm_inactive_slot === null;
}

function validObservation(value, capacity) {
  if (!value || value.v !== 3 || !hex(value.esp_boot, 16) || (value.update_id !== null && !hex(value.update_id, 32))
    || ![null, "STM", "ESP"].includes(value.target) || !PHASES.has(value.phase)
    || typeof value.error !== "string" || !/^[A-Z_]{1,32}$/.test(value.error)
    || typeof value.detail !== "string" || !/^[A-Za-z0-9_.-]{0,48}$/.test(value.detail)
    || (value.stm_service_boot !== null && !hex(value.stm_service_boot, 16))
    || !["ESP", "STM_APP", "STM_LOADER", "STM_TRIAL", "NONE"].includes(value.source)) return false;
  for (const key of ["locked", "source_valid", "can_retry", "can_finish"]) if (typeof value[key] !== "boolean") return false;
  for (const key of ["can_active", "outputs_inhibited"]) if (value[key] !== null && typeof value[key] !== "boolean") return false;
  for (const key of ["source_age_ms", "stop_evidence_age_ms"]) if (value[key] !== null && !uint(value[key])) return false;
  if (!uint(value.last_phase_ms) || !uint(value.image_bytes, capacity) || !uint(value.http_received_bytes, value.image_bytes)
    || !(value.stm_written_bytes === null && value.target !== "STM" || uint(value.stm_written_bytes, value.image_bytes))
    || !(value.image_sha256 === null || hash(value.image_sha256)) || !(value.fw_id === null || token(value.fw_id))
    || !(value.bootloader_fw === null || token(value.bootloader_fw)) || !["MEASURED", "POWER_INHIBIT", "UNKNOWN"].includes(value.stop_evidence)) return false;
  if (![null, "A", "B", "NONE"].includes(value.confirmed_slot) || ![null, "A", "B"].includes(value.inactive_slot)
    || ![null, "A", "B", "NONE"].includes(value.candidate_slot)) return false;
  if (value.update_id === null && (value.target !== null || value.phase !== "IDLE" || value.locked)) return false;
  if (value.source_valid && (value.source === "NONE" || value.source_age_ms === null || value.source.startsWith("STM_") && value.stm_service_boot === null)) return false;
  return value.image_bytes === 0 ? value.image_sha256 === null && value.fw_id === null : hash(value.image_sha256) && token(value.fw_id);
}

export function validUpdateSession(result, intent = null) {
  if (result?.ok !== true || result.scope !== "HC_NATIVE_SESSION" || typeof result.configured !== "boolean"
    || typeof result.upload_available !== "boolean" || typeof result.abort_available !== "boolean" || typeof result.finish_available !== "boolean"
    || result.hardware_qualified !== false || result.normal_mode_verified !== false || typeof result.bound !== "boolean"
    || typeof result.can_create !== "boolean" || typeof result.ordinary_blocked !== "boolean"
    || typeof result.ready !== "boolean" || typeof result.installation_confirmed !== "boolean"
    || typeof result.connection?.status !== "string" || !/^[A-Z_0-9]{1,32}$/.test(result.connection.status)
    || result.freshness?.timeout_ms !== 2000 || typeof result.freshness.fresh !== "boolean"
    || !(result.freshness.effective_age_ms === null || uint(result.freshness.effective_age_ms, Number.MAX_SAFE_INTEGER))) return false;
  if (!result.configured && (result.bound || result.can_create || result.ready || result.installation_confirmed || result.freshness.fresh)) return false;
  if (result.attempt !== null && !validSessionAttempt(result.attempt, intent)) return false;
  if (intent && result.attempt === null && result.found !== false) return false;
  const observed = result.observation, identity = result.identity, age = result.freshness.effective_age_ms;
  if (observed !== null && (!identity || !validObservation(observed, observed.target === "STM" ? identity.stm_image_max_bytes : Math.max(identity.stm_image_max_bytes, identity.esp_ota_max_bytes))
    || observed.esp_boot !== identity.esp_boot)) return false;
  if (age !== null && (!observed || observed.source_age_ms === null || age < observed.source_age_ms)) return false;
  if (result.freshness.fresh && (!["LIVE", "UNBOUND"].includes(result.connection.status)
    || !observed?.source_valid || !observed.source.startsWith("STM_") || age === null || age > 2000)) return false;
  if (result.bound && (!result.attempt?.update_id || observed?.update_id !== result.attempt.update_id || observed.target !== "STM"
    || identity?.esp_boot !== result.attempt.esp_boot || identity.profile_crc !== result.attempt.profile_crc || !vgIdentity(identity)
    || [observed.confirmed_slot, observed.inactive_slot, observed.candidate_slot].some((value) => value !== null))) return false;
  const loader = result.bound && result.freshness.fresh && observed.source === "STM_LOADER" && observed.locked
    && observed.can_active === false && observed.outputs_inhibited === true && observed.error === "NONE";
  if (result.ready && (!loader || observed.phase !== "READY")) return false;
  if (result.installation_confirmed && (!loader || observed.phase !== "COMPLETE" || !observed.image_bytes)) return false;
  if (!result.ordinary_blocked && (result.attempt?.active || observed?.locked || identity?.update_locked)) return false;
  if (result.can_create && (result.attempt !== null || result.ordinary_blocked || !vgIdentity(identity) || observed?.phase !== "IDLE" || observed.locked)) return false;
  const operations = result.operations ?? [];
  if ((result.upload_available || result.abort_available || result.finish_available || result.exit_check_available) && !Array.isArray(result.operations)) return false;
  if (!Array.isArray(operations) || operations.length > 3 || operations.some((op) => !validOperation(op)
    || op.session_request_id !== result.attempt?.request_id) || new Set(operations.map((op) => op.action)).size !== operations.length) return false;
  const recorded = new Set(operations.map((op) => op.action));
  const active = result.attempt?.active === true && result.bound && result.ordinary_blocked;
  if (result.upload_available && (!active || !result.ready || observed.image_bytes !== 0 || recorded.has("IMAGE"))) return false;
  if (result.abort_available && (!active || !result.freshness.fresh || !observed.locked || recorded.has("ABORT")
    || !["QUIESCING","READY","RECEIVING","ERASING","WRITING","VERIFYING","TRIAL"].includes(observed.phase))) return false;
  if (result.finish_available && (!active || !result.freshness.fresh || observed.source !== "STM_LOADER" || !observed.locked
    || observed.can_active !== false || observed.outputs_inhibited !== true || !observed.can_finish || recorded.has("FINISH")
    || !["COMPLETE","ABORTED","ERROR"].includes(observed.phase))) return false;
  if (result.exit_check_available !== undefined && typeof result.exit_check_available !== "boolean") return false;
  if (result.exit_check_available && (!result.attempt?.active || !operations.some((op) => op.action === "FINISH" && op.state !== "REJECTED"))) return false;
  return true;
}

const requestToken = (value) => typeof value === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(value);
export function validActionIntent(intent) {
  return !!intent && Object.keys(intent).sort().join(",") === "action,requestId,sessionId" && requestToken(intent.requestId)
    && requestToken(intent.sessionId) && ["IMAGE","ABORT","FINISH","VERIFY_EXIT"].includes(intent.action);
}
function validOperation(op) {
  return !!op && requestToken(op.request_id) && requestToken(op.session_request_id) && ["IMAGE","ABORT","FINISH"].includes(op.action)
    && ["INTENT","UNKNOWN","ADMITTED","REJECTED"].includes(op.state) && op.persisted === true && hex(op.service_boot,16)
    && typeof op.code === "string" && /^[A-Z_0-9]{1,32}$/.test(op.code)
    && Number.isFinite(Date.parse(op.created_at)) && Number.isFinite(Date.parse(op.updated_at));
}
export function validActionResult(result, intent) {
  if (result?.ok !== true || result.scope !== "HC_UPDATE_ACTION" || typeof result.found !== "boolean" || !validActionIntent(intent)) return false;
  if (!result.found) return result.operation == null && result.exit == null;
  if (intent.action !== "VERIFY_EXIT") return result.exit === null && validOperation(result.operation)
    && result.operation.request_id === intent.requestId && result.operation.session_request_id === intent.sessionId && result.operation.action === intent.action;
  const exit = result.exit, proof = exit?.proof;
  return result.operation === null && exit?.request_id === intent.requestId && exit.session_request_id === intent.sessionId && exit.persisted === true
    && Number.isFinite(Date.parse(exit.created_at)) && hex(proof?.esp_boot,16) && hex(proof.stm_boot,16) && hex(proof.profile_crc,8)
    && uint(proof.control_epoch) && proof.control_epoch > 0 && proof.store === "EMPTY"
    && (proof.state === "DISARMED" && proof.fault_mask === 0 || proof.state === "FAULT" && uint(proof.fault_mask,7) && proof.fault_mask > 0)
    && proof.zero_targets_authority === "NATIVE_IDLE_RESTART_BARRIER";
}

export function updateView(result, receivedAt, now, error = "") {
  const elapsed = receivedAt === null ? Infinity : Math.max(0, now - receivedAt);
  const age = result?.freshness?.effective_age_ms;
  const effectiveAge = Number.isInteger(age) && receivedAt !== null ? age + elapsed : null;
  const fresh = !error && result?.freshness?.fresh === true && effectiveAge !== null && effectiveAge <= 2000;
  return { fresh, effectiveAge, ready: fresh && result?.ready === true, installed: fresh && result?.installation_confirmed === true,
    canCreate: !error && elapsed <= 2000 && result?.can_create === true,
    canUpload: fresh && result?.upload_available === true, canAbort: fresh && result?.abort_available === true,
    canFinish: fresh && result?.finish_available === true, canVerifyExit: result?.exit_check_available === true };
}
