"""Native single-send action intents and explicit, atomic verified HC exit."""
from runtime_schema_contract import check_runtime_schema
import threading

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from mower_firmware_service import FirmwareError

TABLE = "hc.mower_firmware_operation"
EXIT_TABLE = "hc.mower_firmware_exit"
SESSION_TABLE = "hc.mower_firmware_session"
LOCK_KEY = "hc.mower.firmware.native-session"
SCHEMA_SQL = """-- One durable send intent per native session/action; explicit verified HC exit.
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS closed boolean NOT NULL DEFAULT false;
ALTER TABLE hc.mower_firmware_session ADD COLUMN IF NOT EXISTS initial_stm_boot text
    CHECK (initial_stm_boot ~ '^[0-9A-F]{16}$' AND initial_stm_boot <> repeat('0', 16));
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_active_check;
-- Migration 054's cross-column inline CHECK receives this PostgreSQL name.
ALTER TABLE hc.mower_firmware_session DROP CONSTRAINT IF EXISTS mower_firmware_session_check;
ALTER TABLE hc.mower_firmware_session ADD CONSTRAINT mower_firmware_session_active_check
    CHECK (active = (state <> 'REJECTED' AND NOT closed));
CREATE TABLE IF NOT EXISTS hc.mower_firmware_operation (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL REFERENCES hc.mower_firmware_session(request_id),
    action text NOT NULL CHECK (action IN ('IMAGE', 'ABORT', 'FINISH')),
    state text NOT NULL CHECK (state IN ('INTENT', 'UNKNOWN', 'ADMITTED', 'REJECTED')),
    code text NOT NULL CHECK (code ~ '^[A-Z_0-9]{1,32}$'),
    service_boot text NOT NULL CHECK (service_boot ~ '^[0-9A-F]{16}$' AND service_boot <> repeat('0', 16)),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (session_request_id, action)
);
CREATE TABLE IF NOT EXISTS hc.mower_firmware_exit (
    request_id text PRIMARY KEY CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    session_request_id text NOT NULL UNIQUE REFERENCES hc.mower_firmware_session(request_id),
    proof jsonb NOT NULL CHECK (jsonb_typeof(proof) = 'object'),
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


class MowerFirmwareOperationsStore:
    def __init__(self, db_conn, execute_sql, sessions):
        self.db_conn, self.execute_sql, self.sessions = db_conn, execute_sql, sessions
        self._ready, self._lock = False, threading.Lock()

    def ensure_schema(self):
        if self._ready:
            return
        with self._lock:
            if not self._ready:
                self.sessions.ensure_schema()
                check_runtime_schema(self.execute_sql, "mower_operations")
                self._ready = True

    def request(self, id_):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            return connection.execute(f"SELECT * FROM {TABLE} WHERE request_id=%s", (id_,)).fetchone()

    def history(self, session_id):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            return connection.execute(f"SELECT * FROM {TABLE} WHERE session_request_id=%s ORDER BY created_at, action", (session_id,)).fetchall()

    def reserve(self, id_, session_id, action, boot):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (LOCK_KEY,))
            previous = connection.execute(f"SELECT * FROM {TABLE} WHERE request_id=%s", (id_,)).fetchone()
            if previous:
                if (previous["session_request_id"], previous["action"]) != (session_id, action):
                    raise FirmwareError("ID_CONFLICT", "Másik művelethez tartozó kérésazonosító.", 409)
                return previous, False
            if connection.execute(f"SELECT request_id FROM {EXIT_TABLE} WHERE request_id=%s", (id_,)).fetchone():
                raise FirmwareError("ID_CONFLICT", "Visszatérési igazoláshoz tartozó azonosító.", 409)
            parent = connection.execute(f"SELECT * FROM {SESSION_TABLE} WHERE request_id=%s FOR UPDATE", (session_id,)).fetchone()
            if not parent or not parent["active"] or parent["state"] != "ADMITTED":
                raise FirmwareError("SESSION_UNBOUND", "Aktív, megőrzött natív session szükséges.", 409)
            if connection.execute(f"SELECT request_id FROM {TABLE} WHERE session_request_id=%s AND action=%s", (session_id, action)).fetchone():
                raise FirmwareError("ACTION_RECORDED", "Ez a művelet már naplózott; csak GET-egyeztetés engedélyezett.", 409)
            if connection.execute(f"SELECT count(*) AS n FROM {TABLE}").fetchone()["n"] >= 3072:
                raise FirmwareError("SESSION_QUOTA", "A HC frissítési műveletnapló megtelt.", 409)
            row = connection.execute(f"INSERT INTO {TABLE} (request_id,session_request_id,action,state,code,service_boot) VALUES (%s,%s,%s,'INTENT','SEND_INTENT',%s) RETURNING *", (id_, session_id, action, boot)).fetchone()
            return row, True

    def complete(self, id_, state, code):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            row = connection.execute(f"UPDATE {TABLE} SET state=%s, code=%s, updated_at=now() WHERE request_id=%s AND state='INTENT' RETURNING *", (state, code, id_)).fetchone()
            return row or connection.execute(f"SELECT * FROM {TABLE} WHERE request_id=%s", (id_,)).fetchone()

    def exit_request(self, id_):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            return connection.execute(f"SELECT * FROM {EXIT_TABLE} WHERE request_id=%s", (id_,)).fetchone()

    def close(self, id_, session_id, proof, check=None):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            connection.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (LOCK_KEY,))
            previous = connection.execute(f"SELECT * FROM {EXIT_TABLE} WHERE request_id=%s", (id_,)).fetchone()
            if previous:
                if previous["session_request_id"] != session_id:
                    raise FirmwareError("ID_CONFLICT", "Eltérő sessionhez tartozó visszatérési igazolás.", 409)
                return previous
            if connection.execute(f"SELECT request_id FROM {TABLE} WHERE request_id=%s", (id_,)).fetchone():
                raise FirmwareError("ID_CONFLICT", "Natív művelethez tartozó azonosító.", 409)
            parent = connection.execute(f"SELECT * FROM {SESSION_TABLE} WHERE request_id=%s FOR UPDATE", (session_id,)).fetchone()
            finish = connection.execute(f"SELECT * FROM {TABLE} WHERE session_request_id=%s AND action='FINISH'", (session_id,)).fetchone()
            if not parent or not parent["active"] or parent["state"] != "ADMITTED" or not finish or finish["state"] == "REJECTED":
                raise FirmwareError("EXIT_NOT_AUTHORIZED", "Megőrzött explicit FINISH-szándék szükséges.", 409)
            if check:
                check()
            row = connection.execute(f"INSERT INTO {EXIT_TABLE} (request_id,session_request_id,proof) VALUES (%s,%s,%s) RETURNING *", (id_, session_id, Jsonb(proof))).fetchone()
            connection.execute(f"UPDATE {SESSION_TABLE} SET active=false, closed=true, updated_at=now() WHERE request_id=%s", (session_id,))
            return row
