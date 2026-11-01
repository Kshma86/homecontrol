"""Explicit HC-39 admin provisioning. Default plan is read-only; no app import."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re

import psycopg
from psycopg import sql

from migrate_hc07 import recorded
from db_privilege_manifest import RELATIONS
from sql_lab_database import READER_CHECK


FILENAME = '061_hc39_runtime_schema.sql'
CHECKSUM = 'de18c28193b50b54c45c13f427ede0d401e3ad04b0bdfe0466c327b688513549'
POLICY = 'hc39-v1'
ROLES = ('hc_app', 'hc_lab')
JOURNALS = ('schema_baseline', 'startup_schema_migration', 'db_privilege_migration')


class PrivilegeError(RuntimeError):
    pass


def preserve_public(conn, kind, name, privileges, old_logins):
    """Remove inherited PUBLIC access while preserving existing login consumers."""
    for privilege in privileges:
        for role in old_logins:
            conn.execute(sql.SQL('grant {} on {} {} to {}').format(
                sql.SQL(privilege), sql.SQL(kind), name, sql.Identifier(role)))
    conn.execute(sql.SQL('revoke {} on {} {} from public').format(
        sql.SQL(','.join(privileges)), sql.SQL(kind), name))


def provision(conn, sql_dir, *, apply=False, passwords=None, adopt_existing_roles=False):
    body = (Path(sql_dir) / FILENAME).read_bytes()
    if hashlib.sha256(body).hexdigest() != CHECKSUM:
        raise PrivilegeError('HC-39 SQL checksum mismatch')
    with conn.transaction():
        if not apply:
            conn.execute('set transaction read only')
        else:
            conn.execute("set local lock_timeout='5s'")
            conn.execute("set local statement_timeout='60s'")
            conn.execute('select pg_advisory_xact_lock(721950039)')
        if not {'059', '060'} <= set(recorded(conn)):
            raise PrivilegeError('HC-07 explicit 059/060 migrations are required first')
        journal = conn.execute("select to_regclass('hc.db_privilege_migration')").fetchone()[0]
        rows = conn.execute('select version,checksum,policy from hc.db_privilege_migration').fetchall() if journal else []
        if rows and rows != [('061', CHECKSUM, POLICY)]:
            raise PrivilegeError('Unknown HC-39 journal/checksum/policy')
        old_logins = [r[0] for r in conn.execute('select rolname from pg_roles where rolcanlogin and not(rolname=any(%s))', (list(ROLES),))]
        existing = {}
        for role in ROLES:
            row = conn.execute('''select oid,rolsuper or rolcreatedb or rolcreaterole or rolreplication
                or rolbypassrls or rolinherit or not rolcanlogin from pg_roles where rolname=%s''', (role,)).fetchone()
            if row:
                if (not rows and not adopt_existing_roles) or row[1] or conn.execute('select 1 from pg_auth_members where member=%s', (row[0],)).fetchone():
                    raise PrivilegeError('Existing HC-39 role is untracked or privileged; manual review required')
                if conn.execute('''select 1 from pg_class where relowner=%s
                    union all select 1 from pg_namespace where nspowner=%s
                    union all select 1 from pg_database where datdba=%s limit 1''', (row[0],)*3).fetchone():
                    raise PrivilegeError('Runtime/reader role must not own database objects')
                existing[role] = row[0]
        if not apply:
            return dict(applied=False, pending=not bool(rows), roles=list(ROLES), policy=POLICY,
                        admin_role=conn.execute('select current_user').fetchone()[0],
                        public_acl_existing_logins_preserved=old_logins)
        if not conn.execute('select rolsuper from pg_roles where rolname=current_user').fetchone()[0]:
            raise PrivilegeError('Provisioning requires a separate admin connection')
        # Fixed role names, separate random URL-safe passwords; never command-line arguments.
        for role in ROLES:
            if role not in existing:
                password = (passwords or {}).get(role, '')
                if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', password):
                    raise PrivilegeError('New HC-39 roles require distinct 32–128 character URL-safe passwords')
        if passwords and passwords.get('hc_app') and passwords.get('hc_app') == passwords.get('hc_lab'):
            raise PrivilegeError('Application and reader passwords must differ')
        for role in ROLES:
            if role not in existing:
                conn.execute(sql.SQL('create role {} login noinherit nosuperuser nocreatedb nocreaterole noreplication nobypassrls password {}').format(
                    sql.Identifier(role), sql.Literal(passwords[role])))
        if not rows:
            conn.execute(body.decode(), prepare=False)
            conn.execute('''create table hc.db_privilege_migration(
                version text primary key, checksum text not null, policy text not null,
                applied_at timestamptz not null default now(), applied_by text not null default current_user)''')
            conn.execute('insert into hc.db_privilege_migration(version,checksum,policy) values(%s,%s,%s)', ('061', CHECKSUM, POLICY))

        database = conn.execute('select current_database()').fetchone()[0]
        # PostgreSQL has no negative per-role ACL. PUBLIC grants must be removed;
        # preserve every pre-existing login's effective access explicitly first.
        for (privilege,) in conn.execute('''select privilege_type from pg_database,
            lateral aclexplode(coalesce(datacl,acldefault('d',datdba))) a
            where datname=current_database() and grantee=0 and privilege_type in ('CREATE','TEMPORARY')'''):
            preserve_public(conn, 'database', sql.Identifier(database), [privilege], old_logins)
        for name, privilege in conn.execute('''select nspname,privilege_type from pg_namespace,
            lateral aclexplode(coalesce(nspacl,acldefault('n',nspowner))) a
            where nspname !~ '^pg_' and grantee=0 and privilege_type='CREATE' '''):
            preserve_public(conn, 'schema', sql.Identifier(name), [privilege], old_logins)
        for schema, name, kind, privilege in conn.execute('''select n.nspname,c.relname,c.relkind,a.privilege_type
            from pg_class c join pg_namespace n on n.oid=c.relnamespace,
            lateral aclexplode(coalesce(c.relacl,acldefault(case when c.relkind='S' then 'S'::"char" else 'r'::"char" end,c.relowner))) a
            where n.nspname !~ '^pg_' and n.nspname<>'information_schema'
            and c.relkind in ('r','p','v','m','f','S') and a.grantee=0'''):
            preserve_public(conn, 'sequence' if kind == 'S' else 'table', sql.Identifier(schema, name), [privilege], old_logins)
        for schema, name, args, function_oid in conn.execute('''select n.nspname,p.proname,pg_get_function_identity_arguments(p.oid),p.oid
            from pg_proc p join pg_namespace n on n.oid=p.pronamespace
            where n.nspname='hc' or (n.nspname !~ '^pg_' and p.prosecdef)'''):
            function = sql.SQL('{}.{}({})').format(sql.Identifier(schema), sql.Identifier(name), sql.SQL(args))
            public_execute = conn.execute('''select exists(select 1 from pg_proc p,
                lateral aclexplode(coalesce(p.proacl,acldefault('f',p.proowner))) a
                where p.oid=%s and a.grantee=0 and a.privilege_type='EXECUTE')''',
                (function_oid,)).fetchone()[0]
            preserve_public(conn, 'function', function, ['EXECUTE'], old_logins if public_execute else [])
        owners = conn.execute("select distinct pg_get_userbyid(proowner) from pg_proc p join pg_namespace n on n.oid=p.pronamespace where n.nspname='hc'").fetchall()
        for (owner,) in owners:
            conn.execute(sql.SQL('alter default privileges for role {} in schema hc revoke execute on functions from public').format(sql.Identifier(owner)))
        for role in ROLES:
            conn.execute(sql.SQL('grant connect on database {} to {}').format(sql.Identifier(database), sql.Identifier(role)))
            conn.execute(sql.SQL('grant usage on schema hc to {}').format(sql.Identifier(role)))
            conn.execute(sql.SQL("alter role {} in database {} set search_path=pg_catalog,hc").format(sql.Identifier(role), sql.Identifier(database)))
        relations = conn.execute("select relname,relkind from pg_class c join pg_namespace n on n.oid=c.relnamespace where n.nspname='hc' and relkind in ('r','p','v','m','S')").fetchall()
        # A full legacy dump legitimately has no HC-38 fresh-install journal.
        expected = {k:v for k,v in RELATIONS.items()
                    if k != 'schema_baseline' or k in dict(relations)}
        if dict(relations) != expected:
            raise PrivilegeError('HC-39 relation inventory differs from the reviewed grant manifest')
        for name, kind in relations:
            target = sql.Identifier('hc', name)
            if kind == 'S':
                conn.execute(sql.SQL('grant usage on sequence {} to hc_app').format(target))
            else:
                conn.execute(sql.SQL('grant select on table {} to hc_app,hc_lab').format(target))
                if kind in ('r','p') and name not in JOURNALS:
                    conn.execute(sql.SQL('grant insert,update,delete on table {} to hc_app').format(target))
        conn.execute(sql.SQL('alter role hc_lab in database {} set default_transaction_read_only=on').format(sql.Identifier(database)))
        conn.execute(sql.SQL("alter role hc_lab in database {} set statement_timeout='7s'").format(sql.Identifier(database)))
        conn.execute(sql.SQL("alter role hc_lab in database {} set idle_in_transaction_session_timeout='10s'").format(sql.Identifier(database)))
        # Check effective ACLs, including PUBLIC and any existing direct grants,
        # before committing. Provisioning must not report success for an unsafe role.
        conn.execute('set local role hc_lab')
        safe = conn.execute(READER_CHECK.replace(" and session_user = 'hc_lab'", '')).fetchone()
        conn.execute('set local role none')
        if not safe or safe[0] is not True:
            raise PrivilegeError('Effective SQL Lab permissions remain unsafe; review existing direct/column grants')
        return dict(applied=not bool(rows), pending=False, roles=list(ROLES), policy=POLICY,
                    granted_relations=len(relations), public_acl_existing_logins_preserved=old_logins)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--plan', action='store_true')
    mode.add_argument('--apply', action='store_true')
    parser.add_argument('--adopt-existing-roles', action='store_true', help='Explicitly reuse reviewed cluster roles when restoring into a second database')
    parser.add_argument('--sql-dir', type=Path, default=Path(__file__).resolve().parents[1] / 'db')
    args = parser.parse_args()
    dsn = os.environ.get('HC39_ADMIN_DATABASE_URL', '')
    if not dsn:
        parser.exit(2, 'HC39_ADMIN_DATABASE_URL is required; runtime DATABASE_URL is never used.\n')
    try:
        with psycopg.connect(dsn, autocommit=True) as connection:
            result = provision(connection, args.sql_dir, apply=args.apply, adopt_existing_roles=args.adopt_existing_roles, passwords={
                'hc_app': os.environ.get('HC_APP_DB_PASSWORD', ''), 'hc_lab': os.environ.get('HC_LAB_DB_PASSWORD', '')})
        print(json.dumps(result, indent=2))
    except PrivilegeError as exc:
        parser.exit(1, 'HC-39 provisioning refused; transaction rolled back: ' + str(exc) + '\n')
    except Exception:
        parser.exit(1, 'HC-39 provisioning failed; transaction rolled back. Check prerequisites, role policy and credentials privately.\n')


if __name__ == '__main__':
    main()
