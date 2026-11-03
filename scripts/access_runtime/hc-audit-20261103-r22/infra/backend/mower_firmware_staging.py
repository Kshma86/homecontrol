"""Release-verified HC retention, deliberately independent of live rover identity."""
import hashlib
import re
import struct

from mower_firmware_service import BODY_LIMIT, FirmwareError, valid_token
from mower_firmware_store import check_replay, MAX_ARTIFACTS, MAX_BYTES, MAX_JOBS


def request_token(value):
    if type(value) is not str or re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value) is None:
        raise FirmwareError("INVALID_REQUEST_ID", "Pontos HC mentésazonosító szükséges.")
    return value


def descriptor(row, *, replayed=False):
    report = row["report"]
    return {"ok": True, "scope": "HC_LOCAL_STAGING", "persisted": True, "state": row["state"],
            "hc_job_id": row["hc_job_id"], "request_id": row["request_id"], "artifact_id": row["artifact_id"],
            "release_id": row["release_id"], "metadata": report["metadata"], "elf_sha256": report["elf_sha256"],
            "elf_verified_at_staging": True, "release_verified_at_staging": True,
            "saved_at": row["saved_at"].isoformat(), "replayed": replayed,
            "update_id": None, "upload_available": False, "hardware_qualified": False, "rover_contacted": False}


class MowerFirmwareStaging:
    def __init__(self, preflight, store):
        self.preflight, self.store = preflight, store

    def stage(self, body, request_id, release_id):
        request_token(request_id)
        if not valid_token(release_id, 64):
            raise FirmwareError("RELEASE_REQUIRED", "HC-mentéshez szerveroldalon jóváhagyott kiadást kell választani.")
        if type(body) is not bytes or not 4 < len(body) <= BODY_LIMIT:
            raise FirmwareError("BAD_LENGTH", "Hibás HC firmware-csomag.")
        artifact_id = hashlib.sha256(body).hexdigest()
        previous = self.store.request(request_id)
        if previous:
            # This is retained historical evidence, not renewed release approval.
            check_replay(previous, artifact_id, release_id)
            return descriptor(previous, replayed=True)
        report = self.preflight.preflight(body, release_id)
        if report["release_verified"] is not True:
            raise FirmwareError("RELEASE_NOT_APPROVED", "Csak ellenőrzött jóváhagyott kiadás menthető.")
        length = struct.unpack_from("<I", body)[0]
        row, replayed = self.store.save(request_id, artifact_id, release_id, body[4:4 + length], body[4 + length:], report)
        return descriptor(row, replayed=replayed)

    def request_status(self, request_id):
        row = self.store.request(request_token(request_id))
        return {**descriptor(row), "found": True} if row else {
            "ok": True, "found": False, "request_id": request_id, "scope": "HC_LOCAL_STAGING",
            "persisted": False, "upload_available": False, "rover_contacted": False}

    def job(self, job_id):
        if type(job_id) is not str or re.fullmatch(r"[0-9A-F]{32}", job_id) is None or job_id == "0" * 32:
            raise FirmwareError("INVALID_JOB_ID", "Hibás HC feladatazonosító.")
        row = self.store.job(job_id)
        if not row:
            raise FirmwareError("JOB_NOT_FOUND", "A HC firmware-feladat nem található.", 404)
        return descriptor(row)

    def history(self):
        return {"ok": True, "scope": "HC_LOCAL_STAGING", "upload_available": False, "rover_contacted": False,
                "jobs": [descriptor(row) for row in self.store.history()],
                "limits": {"artifacts": MAX_ARTIFACTS, "bytes": MAX_BYTES, "jobs": MAX_JOBS}}
