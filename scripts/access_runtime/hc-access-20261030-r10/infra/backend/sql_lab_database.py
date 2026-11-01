"""A separate, fail-closed SQL Lab connection; never fall back to runtime/admin."""
import psycopg

from database_service import DatabaseService


READER_CHECK = """
select current_user = 'hc_lab' and session_user = 'hc_lab'
 and not (r.rolsuper or r.rolcreatedb or r.rolcreaterole or r.rolreplication
          or r.rolbypassrls or r.rolinherit)
 and not exists(select 1 from pg_auth_members where member=r.oid)
 and not exists(select 1 from pg_database where datdba=r.oid)
 and not has_database_privilege(current_database(),'CREATE')
 and not has_database_privilege(current_database(),'TEMP')
 and not exists(select 1 from pg_namespace where nspowner=r.oid
     or (nspname !~ '^pg_' and has_schema_privilege(oid,'CREATE')))
 and not exists(select 1 from pg_class where relowner=r.oid)
 and not exists(select 1 from pg_proc where proowner=r.oid)
 and not exists(select 1 from pg_largeobject_metadata where lomowner=r.oid)
 and not has_table_privilege('pg_catalog.pg_authid','SELECT')
 and not exists(
   select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace
   where n.nspname !~ '^pg_' and n.nspname <> 'information_schema'
    and ((c.relkind in ('r','p','v','m','f') and
       (has_table_privilege(c.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
        or has_any_column_privilege(c.oid,'INSERT,UPDATE,REFERENCES')
        or (n.nspname<>'hc' and (has_table_privilege(c.oid,'SELECT')
            or has_any_column_privilege(c.oid,'SELECT')))))
      or (c.relkind='S' and has_sequence_privilege(c.oid,'USAGE,UPDATE'))))
 and not exists(
   select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace
   where n.nspname !~ '^pg_' and n.nspname <> 'information_schema'
    and has_schema_privilege(n.oid,'USAGE') and has_function_privilege(p.oid,'EXECUTE')
    and (p.prosecdef or n.nspname='hc'))
 and not exists(select 1 from pg_proc p join pg_namespace n on n.oid=p.pronamespace,
     lateral aclexplode(p.proacl) a where n.nspname='pg_catalog' and a.grantee=r.oid)
 and not exists(select 1 from pg_class c join pg_namespace n on n.oid=c.relnamespace,
     lateral aclexplode(c.relacl) a where n.nspname='pg_catalog' and a.grantee=r.oid) as safe
from pg_roles r where r.rolname=current_user
"""


class SqlLabUnavailable(RuntimeError):
    pass


class SqlLabDatabase(DatabaseService):
    def conn(self, row_factory=None):
        if not self.database_url.strip():
            raise SqlLabUnavailable('SQL Lab is disabled: SQL_LAB_DATABASE_URL is required.')
        connection = None
        try:
            connection = psycopg.connect(self.database_url, row_factory=row_factory, connect_timeout=5)
            connection.read_only = True
            # Validate every new connection, including reconnects and metadata reads.
            # Use a tuple cursor regardless of the caller's row factory.
            with connection.transaction():
                with connection.cursor(row_factory=psycopg.rows.tuple_row) as cursor:
                    cursor.execute("set local statement_timeout='7s'")
                    cursor.execute("set local search_path=pg_catalog,hc")
                    cursor.execute(READER_CHECK)
                    row = cursor.fetchone()
                    if not row or row[0] is not True:
                        raise RuntimeError('Unsafe SQL Lab role')
            return connection
        except Exception:
            if connection is not None:
                connection.close()
            # Connection errors can contain a DSN/password; never return them.
            raise SqlLabUnavailable('SQL Lab reader connection is unavailable or has unsafe privileges.') from None
