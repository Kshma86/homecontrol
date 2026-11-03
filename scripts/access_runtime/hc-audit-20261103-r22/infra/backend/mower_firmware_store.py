"""Atomic, immutable HC staging; no native update session or transport."""
from runtime_schema_contract import check_runtime_schema
import threading
import uuid

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from mower_firmware_service import FirmwareError

ARTIFACT_TABLE = "hc.mower_firmware_artifact"
JOB_TABLE = "hc.mower_firmware_job"
LOCK_KEY = "hc.mower.firmware.staging"
MAX_ARTIFACTS, MAX_BYTES, MAX_JOBS = 32, 256 * 1024 * 1024, 1024
# Keep byte-for-byte equivalent to infra/db/053_mower_firmware_staging.sql.
SCHEMA_SQL = """-- HC-local retained firmware only. HC_STAGED is NOT a native update session.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_artifact (
    artifact_id text PRIMARY KEY CHECK (artifact_id ~ '^[0-9a-f]{64}$'),
    image bytea NOT NULL CHECK (octet_length(image) BETWEEN 1280 AND 524288 AND octet_length(image) % 32 = 0),
    elf bytea NOT NULL CHECK (octet_length(elf) BETWEEN 52 AND 16777216),
    saved_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_job (
    hc_job_id text PRIMARY KEY CHECK (hc_job_id ~ '^[0-9A-F]{32}$' AND hc_job_id <> repeat('0', 32)),
    request_id text NOT NULL UNIQUE CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    artifact_id text NOT NULL REFERENCES hc.mower_firmware_artifact(artifact_id),
    release_id text NOT NULL CHECK (release_id ~ '^[A-Za-z0-9_.-]{1,64}$'),
    state text NOT NULL CHECK (state = 'HC_STAGED'),
    report jsonb NOT NULL CHECK (jsonb_typeof(report) = 'object'),
    saved_at timestamptz NOT NULL DEFAULT now()
);
"""


def check_replay(row, artifact_id, release_id):
    if row["artifact_id"] != artifact_id or row["release_id"] != release_id:
        raise FirmwareError("ID_CONFLICT", "Ehhez a mentésazonosítóhoz más fájlpár vagy kiadás tartozik.", 409)


class MowerFirmwareStore:
    def __init__(self, db_conn, execute_sql):
        self.db_conn, self.execute_sql = db_conn, execute_sql
        self._ready, self._lock = False, threading.Lock()

    def ensure_schema(self):
        if self._ready:
            return
        with self._lock:
            if not self._ready:
                check_runtime_schema(self.execute_sql, "mower_staging")
                self._ready = True

    def _rows(self, sql, params=()):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            return list(connection.execute(sql, params).fetchall())

    def request(self, request_id):
        rows = self._rows(f"SELECT * FROM {JOB_TABLE} WHERE request_id=%s", (request_id,))
        return rows[0] if rows else None

    def job(self, job_id):
        rows = self._rows(f"SELECT * FROM {JOB_TABLE} WHERE hc_job_id=%s", (job_id,))
        return rows[0] if rows else None

    def history(self):
        return self._rows(f"SELECT * FROM {JOB_TABLE} ORDER BY saved_at DESC, hc_job_id DESC LIMIT 20")

    def artifact(self, artifact_id):
        rows = self._rows(f"SELECT image, elf FROM {ARTIFACT_TABLE} WHERE artifact_id=%s", (artifact_id,))
        if not rows:
            raise FirmwareError("ARTIFACT_NOT_FOUND", "A HC-ban őrzött firmware-fájlpár nem található.", 409)
        return bytes(rows[0]["image"]), bytes(rows[0]["elf"])

    def save(self, request_id, artifact_id, release_id, image, elf, report):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            # Global lock makes quota checks and dedup atomic across HC workers.
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (LOCK_KEY,))
            previous = connection.execute(f"SELECT * FROM {JOB_TABLE} WHERE request_id=%s", (request_id,)).fetchone()
            if previous:
                check_replay(previous, artifact_id, release_id)
                return previous, True
            jobs = connection.execute(f"SELECT count(*) AS n FROM {JOB_TABLE}").fetchone()["n"]
            if jobs >= MAX_JOBS:
                raise FirmwareError("STORAGE_QUOTA", "A HC firmware-feladattároló megtelt; adminisztrátori karbantartás szükséges.", 409)
            retained = connection.execute(f"SELECT artifact_id FROM {ARTIFACT_TABLE} WHERE artifact_id=%s", (artifact_id,)).fetchone()
            if not retained:
                usage = connection.execute(f"SELECT count(*) AS n, COALESCE(sum(octet_length(image) + octet_length(elf)), 0) AS bytes FROM {ARTIFACT_TABLE}").fetchone()
                if usage["n"] >= MAX_ARTIFACTS or usage["bytes"] + len(image) + len(elf) > MAX_BYTES:
                    raise FirmwareError("STORAGE_QUOTA", "A HC firmware-fájltároló megtelt; adminisztrátori karbantartás szükséges.", 409)
                connection.execute(f"INSERT INTO {ARTIFACT_TABLE} (artifact_id, image, elf) VALUES (%s,%s,%s)", (artifact_id, image, elf))
            row = connection.execute(f"INSERT INTO {JOB_TABLE} (hc_job_id, request_id, artifact_id, release_id, state, report) VALUES (%s,%s,%s,%s,'HC_STAGED',%s) RETURNING *",
                                     (uuid.uuid4().hex.upper(), request_id, artifact_id, release_id, Jsonb(report))).fetchone()
            return row, False
