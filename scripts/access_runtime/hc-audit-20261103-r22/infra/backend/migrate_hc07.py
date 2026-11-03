"""Explicit HC-07 migrations only. Default/--plan is read-only; never imports app/workers."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

import psycopg
from psycopg.rows import dict_row

from startup_schema_contract import StartupSchemaError, check_domain
from startup_schema_manifest import DOMAIN_TABLES, MIGRATIONS


LOCK_KEY = 721950007
JOURNAL_SQL = '''create table if not exists hc.startup_schema_migration (
  version text primary key, checksum text not null check(length(checksum)=64),
  applied_at timestamptz not null default now(), applied_by text not null default current_user
)'''


def load_files(sql_dir):
    scripts = {}
    for version, filename, checksum in MIGRATIONS:
        try:
            data = (Path(sql_dir) / filename).read_bytes()
        except OSError as exc:
            raise StartupSchemaError('Missing/unreadable HC-07 SQL file: ' + filename) from exc
        if hashlib.sha256(data).hexdigest() != checksum:
            raise StartupSchemaError('SQL file checksum differs from backend manifest: ' + filename)
        body = data.decode('utf-8')
        commands = re.sub(r'--[^\n]*', '', body)
        if re.search(r'\bCONCURRENTLY\b|(?:^|;)\s*(?:BEGIN|COMMIT|ROLLBACK)\b', commands, re.I):
            raise StartupSchemaError('Only allowlisted transactional SQL is supported; 042/CONCURRENTLY is excluded')
        scripts[version] = body
    return scripts


def recorded(conn):
    exists = conn.execute("select to_regclass('hc.startup_schema_migration')").fetchone()[0]
    rows = conn.execute('select version,checksum from hc.startup_schema_migration').fetchall() if exists else []
    applied = dict(rows)
    known = {version: checksum for version, _, checksum in MIGRATIONS}
    for version, checksum in applied.items():
        if version not in known or known[version] != checksum:
            raise StartupSchemaError('Unknown/changed recorded HC-07 migration; refusing to overwrite journal')
    return applied


def core_prerequisites(conn):
    for name in ('device', 'entity', 'metric', 'entity_metric'):
        if conn.execute('select to_regclass(%s)', ('hc.' + name,)).fetchone()[0] is None:
            raise StartupSchemaError('Missing core table hc.' + name + '; restore a compatible core baseline/dump first (HC-38). No core bootstrap is performed.')


def readiness(conn):
    def fetch_one(query, params=()):
        with conn.cursor(row_factory=dict_row) as cur:
            return cur.execute(query, params).fetchone()
    errors = {}
    for domain in DOMAIN_TABLES:
        try:
            with conn.transaction():
                check_domain(fetch_one, domain)
        except StartupSchemaError as exc:
            errors[domain] = str(exc)
    return errors


def apply_one(conn, version, body, checksum):
    conn.execute(body, prepare=False)
    conn.execute('insert into hc.startup_schema_migration(version,checksum) values(%s,%s)', (version, checksum))


def migrate(conn, sql_dir, *, apply=False, seed_initial=False):
    scripts = load_files(sql_dir)
    with conn.transaction():
        if not apply:
            conn.execute('set transaction read only')
        else:
            conn.execute("set local lock_timeout='5s'")
            conn.execute("set local statement_timeout='60s'")
            conn.execute('select pg_advisory_xact_lock(%s)', (LOCK_KEY,))
        core_prerequisites(conn)
        applied = recorded(conn)
        selected = MIGRATIONS if seed_initial else MIGRATIONS[:2]
        pending = [version for version, _, _ in selected if version not in applied]
        if seed_initial and MIGRATIONS[2][0] not in applied:
            for table in ('irrigation_pilot_config', 'irrigation_solar_pump_config', 'scheduler_config',
                          'climate_schedule_rule', 'domain_season_active'):
                if conn.execute('select to_regclass(%s)', ('hc.' + table,)).fetchone()[0]:
                    if conn.execute('select 1 from hc.' + table + ' limit 1').fetchone():
                        raise StartupSchemaError('Initial seed refused for an existing installation; restore missing configuration explicitly instead.')
        if apply:
            conn.execute(JOURNAL_SQL)
            for version, _, checksum in selected:
                if version not in applied:
                    apply_one(conn, version, scripts[version], checksum)
        errors = readiness(conn)
        return dict(action='apply' if apply else 'plan', applied=pending if apply else [], pending=[] if apply else pending,
                    initial_seed_requested=seed_initial, ready=not errors, readiness_errors=errors)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--seed-initial', action='store_true', help='Explicit once-only insert-only first-install defaults')
    parser.add_argument('--sql-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'db')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL', '')
    if not url:
        parser.error('DATABASE_URL is required; never pass credentials on the command line')
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            result = migrate(conn, args.sql_dir, apply=args.apply, seed_initial=args.seed_initial)
        print(json.dumps(result, indent=2))
        return 0 if result['ready'] else 2
    except StartupSchemaError as exc:
        print(json.dumps(dict(error=str(exc))))
        return 1
    except psycopg.Error as exc:
        # A DSN/connection exception can contain credentials. Report SQLSTATE only.
        print(json.dumps(dict(error='Migration failed or commit outcome is uncertain. Check the journal before retrying; review connectivity/privileges/schema.', sqlstate=exc.sqlstate)))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
