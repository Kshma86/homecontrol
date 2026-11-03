"""PostgreSQL immutable HC draft revisions; atomic CAS and durable replay checks."""
from runtime_schema_contract import check_runtime_schema
import threading

from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from mower_parameters_service import DraftError, MAX_REVISION

TABLE = "hc.mower_parameter_revision"
# Keep byte-for-byte equivalent to infra/db/052_mower_parameter_drafts.sql.
SCHEMA_SQL = """-- HC-local RCP1 drafts only. Revision is not a native rover configuration revision.
CREATE TABLE IF NOT EXISTS hc.mower_parameter_revision (
    rover_key text NOT NULL CHECK (rover_key ~ '^[A-Za-z0-9_-]{1,32}$'),
    revision bigint NOT NULL CHECK (revision BETWEEN 1 AND 4294967295),
    expected_revision bigint NOT NULL CHECK (expected_revision = revision - 1),
    request_id text NOT NULL CHECK (request_id ~ '^[A-Za-z0-9_-]{1,64}$'),
    parameters jsonb NOT NULL CHECK (jsonb_typeof(parameters) = 'object'),
    draft_sha256 text NOT NULL CHECK (draft_sha256 ~ '^[0-9a-f]{64}$'),
    saved_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (rover_key, revision),
    UNIQUE (rover_key, request_id)
);
"""


class MowerParametersStore:
    def __init__(self, db_conn, execute_sql):
        self.db_conn, self.execute_sql = db_conn, execute_sql
        self._ready = False
        self._lock = threading.Lock()

    def ensure_schema(self):
        if self._ready:
            return
        with self._lock:
            if not self._ready:
                check_runtime_schema(self.execute_sql, "mower_parameters")
                self._ready = True

    def _rows(self, sql, params):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            with connection.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())

    def latest(self, key):
        rows = self._rows(f"SELECT * FROM {TABLE} WHERE rover_key=%s ORDER BY revision DESC LIMIT 1", (key,))
        return rows[0] if rows else None

    def revision(self, key, revision):
        rows = self._rows(f"SELECT * FROM {TABLE} WHERE rover_key=%s AND revision=%s", (key, revision))
        return rows[0] if rows else None

    def request(self, key, id_):
        rows = self._rows(f"SELECT * FROM {TABLE} WHERE rover_key=%s AND request_id=%s", (key, id_))
        return rows[0] if rows else None

    def history(self, key):
        return self._rows(f"SELECT * FROM {TABLE} WHERE rover_key=%s ORDER BY revision DESC LIMIT 20", (key,))

    def list_latest(self):
        return self._rows(f"SELECT DISTINCT ON (rover_key) rover_key, revision, saved_at FROM {TABLE} ORDER BY rover_key, revision DESC LIMIT 100", ())

    def save(self, key, id_, expected, parameters, sha256):
        self.ensure_schema()
        with self.db_conn(dict_row) as connection:
            with connection.cursor() as cursor:
                # Protect initial creation as well as updates; no missing-row CAS race.
                cursor.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", ("hc.mower.parameters:" + key,))
                cursor.execute(f"SELECT * FROM {TABLE} WHERE rover_key=%s AND request_id=%s", (key, id_))
                previous = cursor.fetchone()
                if previous:
                    if previous["expected_revision"] != expected or previous["draft_sha256"] != sha256 or previous["parameters"] != parameters:
                        raise DraftError("ID_CONFLICT", "Ehhez a mentésazonosítóhoz más tartalom tartozik.", 409)
                    return previous, True
                cursor.execute(f"SELECT revision FROM {TABLE} WHERE rover_key=%s ORDER BY revision DESC LIMIT 1", (key,))
                latest = cursor.fetchone()
                current = latest["revision"] if latest else 0
                if current != expected:
                    raise DraftError("REVISION_CONFLICT", "Másik szerkesztő már újabb draftot mentett. A helyi módosítások megmaradtak.", 409, current_revision=current)
                if current >= MAX_REVISION:
                    raise DraftError("REVISION_LIMIT", "A draftverzió elérte a felső határt.", 409)
                cursor.execute(f"INSERT INTO {TABLE} (rover_key, revision, expected_revision, request_id, parameters, draft_sha256) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *",
                               (key, current + 1, current, id_, Jsonb(parameters), sha256))
                return cursor.fetchone(), False
