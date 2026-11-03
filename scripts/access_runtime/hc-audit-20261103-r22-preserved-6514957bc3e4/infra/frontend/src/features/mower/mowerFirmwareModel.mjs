export const IMAGE_LIMIT = 524288, ELF_LIMIT = 16 * 1024 * 1024;

export function stageRequestId(crypto) {
  if (typeof crypto?.getRandomValues !== "function") throw new Error("Biztonságos mentésazonosító nem generálható.");
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return Array.from(bytes, (value) => value.toString(16).padStart(2, "0")).join("").toUpperCase();
}

export function fileProblem(image, elf) {
  if (!image || !elf) return "Válassz RFU2 .bin fájlt és a hozzá tartozó ELF-et.";
  if (!Number.isInteger(image.size) || image.size < 1280 || image.size > IMAGE_LIMIT || image.size % 32)
    return "Az RFU2 1280–524288 bájt, 32 bájtra igazítva.";
  if (!Number.isInteger(elf.size) || elf.size < 52 || elf.size > ELF_LIMIT) return "Az ELF mérete 52 bájt és 16 MiB között lehet.";
  return null;
}

export function preflightBody(image, elf) {
  const problem = fileProblem(image, elf);
  if (problem) throw new Error(problem);
  const prefix = new ArrayBuffer(4);
  new DataView(prefix).setUint32(0, image.size, true);
  return new Blob([prefix, image, elf], { type: "application/octet-stream" });
}

export function validReport(report, releaseId) {
  const metadata = report?.metadata;
  return report?.ok === true && report.scope === "HC_LOCAL_PREFLIGHT" && report.elf_verified === true
    && report.upload_available === false && report.persisted === false && report.hardware_qualified === false && report.rover_contacted === false
    && report.release_id === (releaseId || null) && report.release_verified === !!releaseId
    && metadata?.layout === "H743_1M_QSPI_REC2" && metadata.slot === "APP" && metadata.target === "STM32H743VG"
    && metadata.service_abi === 2 && metadata.link_address === "08100000"
    && Number.isInteger(metadata.image_bytes) && metadata.image_bytes >= 1280 && metadata.image_bytes <= IMAGE_LIMIT && metadata.image_bytes % 32 === 0
    && typeof metadata.image_sha256 === "string" && /^[0-9a-f]{64}$/.test(metadata.image_sha256)
    && typeof report.elf_sha256 === "string" && /^[0-9a-f]{64}$/.test(report.elf_sha256)
    && typeof metadata.profile_crc === "string" && /^[0-9A-F]{8}$/.test(metadata.profile_crc) && metadata.profile_crc !== "00000000"
    && typeof metadata.fw_id === "string" && /^[A-Za-z0-9_.-]{1,48}$/.test(metadata.fw_id);
}

export function validStaged(job, intent = null) {
  if (job?.ok !== true || job.scope !== "HC_LOCAL_STAGING" || job.state !== "HC_STAGED" || job.persisted !== true
    || job.update_id !== null || job.upload_available !== false || job.rover_contacted !== false || job.hardware_qualified !== false
    || job.elf_verified_at_staging !== true || job.release_verified_at_staging !== true
    || typeof job.hc_job_id !== "string" || !/^[0-9A-F]{32}$/.test(job.hc_job_id) || /^0+$/.test(job.hc_job_id)
    || typeof job.request_id !== "string" || !/^[A-Za-z0-9_-]{1,64}$/.test(job.request_id)
    || typeof job.artifact_id !== "string" || !/^[0-9a-f]{64}$/.test(job.artifact_id)
    || typeof job.release_id !== "string" || !/^[A-Za-z0-9_.-]{1,64}$/.test(job.release_id)
    || typeof job.saved_at !== "string" || !Number.isFinite(Date.parse(job.saved_at))) return false;
  // Reuse the exact image metadata checks without treating historical review as current approval.
  if (!validReport({ ...job, scope: "HC_LOCAL_PREFLIGHT", persisted: false, elf_verified: true, release_verified: true }, job.release_id)) return false;
  return !intent || job.request_id === intent.requestId && job.release_id === intent.releaseId
    && job.metadata.image_sha256 === intent.imageHash && job.elf_sha256 === intent.elfHash && job.metadata.image_bytes === intent.imageBytes;
}

export function validStageIntent(intent) {
  return intent && Object.keys(intent).sort().join(",") === "elfHash,imageBytes,imageHash,releaseId,requestId"
    && typeof intent.requestId === "string" && /^[A-Za-z0-9_-]{1,64}$/.test(intent.requestId)
    && typeof intent.releaseId === "string" && /^[A-Za-z0-9_.-]{1,64}$/.test(intent.releaseId)
    && typeof intent.imageHash === "string" && /^[0-9a-f]{64}$/.test(intent.imageHash)
    && typeof intent.elfHash === "string" && /^[0-9a-f]{64}$/.test(intent.elfHash)
    && Number.isInteger(intent.imageBytes) && intent.imageBytes >= 1280 && intent.imageBytes <= IMAGE_LIMIT && intent.imageBytes % 32 === 0;
}
