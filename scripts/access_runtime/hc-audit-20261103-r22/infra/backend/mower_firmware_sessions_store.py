"""Durable admission intent before HTTP; atomic transition, no automatic replay/unlock."""
from runtime_schema_contract import check_runtime_schema
import threading

from psycopg.rows import dict_row
from mower_firmware_service import FirmwareError

TABLE = "hc.mower_firmware_session"
LOCK_KEY = "hc.mower.firmware.native-session"
# Keep byte-for-byte equivalent to infra/db/054_mower_firmware_sessions.sql.
SCHEMA_SQL = """-- Durable single-send create intent. Active UNKNOWN is not cleared by observation.
CREATE TABLE IF NOT EXISTS hc.mower_firmware_session (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    hc_job_id text NOT NULL REFERENCES hc.mower_firmware_job(hc_job_id),
    connection_key text NOT NULL CHECK (connection_key ~ '^[0-9a-f]{64}$'),
    esp_boot text NOT NULL CHECK (esp_boot ~ '^[0-9A-F]{16}$' AND esp_boot <> repeat('0', 16)),
    profile_crc text NOT NULL CHECK (profile_crc ~ '^[0-9A-F]{8}$' AND profile_crc <> '00000000'),
    state text NOT NULL CHECK (state IN ('CREATE_INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    update_id text UNIQUE CHECK (update_id ~ '^[0-9A-F]{32}$' AND update_id <> repeat('0', 32)),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    revision integer NOT NULL CHECK (revision BETWEEN 1 AND 2),
    active boolean NOT NULL CHECK (active = (state <> 'REJECTED')),
    singleton boolean NOT NULL DEFAULT true CHECK (singleton),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK ((state = 'ADMITTED') = (update_id IS NOT NULL)),
    CHECK ((state = 'CREATE_INTENT') = (revision = 1))
);
CREATE UNIQUE INDEX IF NOT EXISTS mower_firmware_one_active_session
    ON hc.mower_firmware_session(singleton) WHERE active;
"""


class MowerFirmwareSessionsStore:
    def __init__(self, db_conn, execute_sql, staging):
        self.db_conn, self.execute_sql, self.staging = db_conn, execute_sql, staging
        self._ready, self._lock = False, threading.Lock()

    def ensure_schema(self):
        if self._ready:
            return
        with self._lock:
            if not self._ready:
                self.staging.ensure_schema()
                check_runtime_schema(self.execute_sql, "mower_sessions")
                self._ready = True

    def _one(self, sql, params=()):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            return connection.execute(sql, params).fetchone()

    def request(self, id_):
        return self._one(f"SELECT * FROM {TABLE} WHERE request_id=%s", (id_,))

    def active(self):
        return self._one(f"SELECT * FROM {TABLE} WHERE active")

    def reserve(self, id_, job_id, connection_key, esp_boot, profile_crc, initial_stm_boot=None):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (LOCK_KEY,))
            row = connection.execute(f"SELECT * FROM {TABLE} WHERE request_id=%s", (id_,)).fetchone()
            if row:
                if row["hc_job_id"] != job_id:
                    raise FirmwareError("ID_CONFLICT", "A session kérésazonosítójához más HC-feladat tartozik.", 409)
                return row, False
            if connection.execute(f"SELECT request_id FROM {TABLE} WHERE active").fetchone():
                raise FirmwareError("HC_UPDATE_PENDING", "Korábbi frissítési szándék/session egyeztetése szükséges.", 409)
            count = connection.execute(f"SELECT count(*) AS n FROM {TABLE}").fetchone()["n"]
            if count >= 1024:
                raise FirmwareError("SESSION_QUOTA", "A HC session-napló megtelt; adminisztrátori karbantartás szükséges.", 409)
            extra_column = ", initial_stm_boot" if initial_stm_boot is not None else ""
            extra_value = ", %s" if initial_stm_boot is not None else ""
            params = (id_, job_id, connection_key, esp_boot, profile_crc) + ((initial_stm_boot,) if initial_stm_boot is not None else ())
            row = connection.execute(f"INSERT INTO {TABLE} (request_id, hc_job_id, connection_key, esp_boot, profile_crc, state, code, revision, active{extra_column}) VALUES (%s,%s,%s,%s,%s,'CREATE_INTENT','SEND_INTENT',1,true{extra_value}) RETURNING *", params).fetchone()
            return row, True

    def complete(self, id_, state, code, update_id=None):
        # Only the original sender can advance revision 1; polling never changes it.
        row = self._one(f"UPDATE {TABLE} SET state=%s, code=%s, update_id=%s, active=%s, revision=2, updated_at=now() WHERE request_id=%s AND revision=1 RETURNING *",
                        (state, code, update_id, state != "REJECTED", id_))
        return row if row else self.request(id_)
