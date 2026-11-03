"""Explicit HC-38 fresh-install baseline. Default plan and --verify are read-only."""
import argparse
import hashlib
import json
import os
from pathlib import Path

import psycopg

from baseline_contract import catalog, differences


VERSION = 'hc-r1-058-v1'
SQL_FILE = 'baselines/hc_r1_058_v1.sql'
CATALOG_FILE = 'baselines/hc_r1_058_v1.catalog.json'
SQL_SHA256 = '8e532cf2d5a5b8b642a9b17cf1bdd8f41859430aa012f1caca266d74f45d220c'
CATALOG_SHA256 = '1fd380c3f9dc0b64d37da604f6afb3336397b1dae2a17fc78afd0c66bf74ee2b'
LOCK_KEY = 721950007  # Same serialization boundary as the HC-07 runner.
JOURNAL_SQL = '''create table hc.schema_baseline (
  singleton boolean primary key default true check(singleton),
  version text not null, checksum text not null check(length(checksum)=64),
  applied_at timestamptz not null default now(), applied_by text not null default current_user
)'''


class BaselineError(RuntimeError):
    pass


def load_files(sql_dir):
    result = []
    for filename, checksum in [(SQL_FILE, SQL_SHA256), (CATALOG_FILE, CATALOG_SHA256)]:
        try:
            data = (Path(sql_dir) / filename).read_bytes()
        except OSError as exc:
            raise BaselineError('Missing/unreadable baseline file: ' + filename) from exc
        if hashlib.sha256(data).hexdigest() != checksum:
            raise BaselineError('Baseline checksum mismatch: ' + filename)
        result.append(data.decode('utf-8'))
    return result[0], json.loads(result[1])


def install(conn, sql_dir, *, apply=False, verify=False):
    if apply and verify:
        raise BaselineError('Apply and verify are mutually exclusive')
    body, expected = load_files(sql_dir)
    with conn.transaction():
        if not apply:
            conn.execute('set transaction isolation level repeatable read, read only')
        else:
            conn.execute("set local lock_timeout='5s'")
            conn.execute("set local statement_timeout='60s'")
            conn.execute('select pg_advisory_xact_lock(%s)', (LOCK_KEY,))
        if conn.info.server_version // 10000 != 16:
            raise BaselineError('This baseline is validated for PostgreSQL 16 only')
        exists = conn.execute("select to_regnamespace('hc') is not null").fetchone()[0]
        if exists:
            # Never adopt an existing installation or modify its journal/data.
            journal = conn.execute("select to_regclass('hc.schema_baseline')").fetchone()[0]
            if journal:
                rows = conn.execute('select version,checksum from hc.schema_baseline').fetchall()
                if rows != [(VERSION, SQL_SHA256)]:
                    raise BaselineError('Unknown/changed baseline journal; refusing to overwrite')
            diff = differences(catalog(conn), expected)
            if apply and (not journal or diff):
                raise BaselineError('Existing HC schema refused: use restore/explicit upgrades, never a fresh baseline')
            return dict(action='verify' if verify else ('apply' if apply else 'plan'),
                        version=VERSION, state='recorded' if journal else 'unversioned',
                        matched=not diff, applied=False, pending=False,
                        fresh_install_allowed=False, differences=diff)
        # Deliberately require a fresh database, not just a missing hc namespace
        # in a shared/live installation. Extension-owned objects are allowed.
        foreign_objects = conn.execute("""select 1 from pg_class c
          join pg_namespace n on n.oid=c.relnamespace
          where n.nspname not like 'pg_%' and n.nspname<>'information_schema'
          and c.relkind in ('r','p','v','m','S','f','c')
          and not exists(select 1 from pg_depend d where d.classid='pg_class'::regclass
            and d.objid=c.oid and d.deptype='e')
          union all select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
          where n.nspname not like 'pg_%' and n.nspname<>'information_schema'
          and not exists(select 1 from pg_depend d where d.classid='pg_proc'::regclass
            and d.objid=p.oid and d.deptype='e')
          union all select 1 from pg_type t join pg_namespace n on n.oid=t.typnamespace
          where n.nspname not like 'pg_%' and n.nspname<>'information_schema'
          and t.typtype in ('d','e','r')
          and not exists(select 1 from pg_depend d where d.classid='pg_type'::regclass
            and d.objid=t.oid and d.deptype='e') limit 1""").fetchone()
        if foreign_objects:
            raise BaselineError('Fresh baseline requires an empty database; existing user objects found')
        if apply:
            conn.execute(body, prepare=False)
            if differences(catalog(conn), expected):
                raise BaselineError('Created baseline differs from reference catalog; transaction aborted')
            conn.execute(JOURNAL_SQL)
            conn.execute('insert into hc.schema_baseline(version,checksum) values(%s,%s)', (VERSION, SQL_SHA256))
        return dict(action='verify' if verify else ('apply' if apply else 'plan'),
                    version=VERSION, state='created' if apply else 'empty', matched=bool(apply),
                    applied=bool(apply), pending=not apply, fresh_install_allowed=True, differences={})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--apply', action='store_true')
    mode.add_argument('--verify', action='store_true', help='Read-only structural comparison at baseline boundary')
    parser.add_argument('--sql-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'db')
    args = parser.parse_args()
    url = os.environ.get('DATABASE_URL')
    if not url:
        parser.error('DATABASE_URL is required; never pass credentials on the command line')
    try:
        with psycopg.connect(url, autocommit=True) as conn:
            result = install(conn, args.sql_dir, apply=args.apply, verify=args.verify)
        print(json.dumps(result, indent=2))
        return 0 if result['matched'] or (not args.verify and result['state'] == 'empty') else 2
    except BaselineError as exc:
        print(json.dumps({'error': str(exc)}))
        return 1
    except psycopg.Error as exc:
        print(json.dumps({'error': 'Baseline failed or commit outcome is uncertain. Inspect schema/journal before retrying.',
                          'sqlstate': exc.sqlstate}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
