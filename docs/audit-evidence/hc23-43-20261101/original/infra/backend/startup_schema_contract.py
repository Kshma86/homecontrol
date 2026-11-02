"""Read-only HC-07 compatibility checks. Never seed, migrate, or repair on startup."""
from startup_schema_manifest import DOMAIN_TABLES, MIGRATIONS, REQUIRED_COLUMNS, SUPPORTED_SCHEDULER_MODES


class StartupSchemaError(RuntimeError):
    pass


HELP = 'Run migrate_hc07.py --plan / --apply explicitly before starting this backend; restore the core schema first (HC-38).'


def check_journal(fetch_one):
    if fetch_one is None:
        raise StartupSchemaError('Schema checks require a read connection. ' + HELP)
    try:
        exists = fetch_one("select to_regclass('hc.startup_schema_migration') is not null as present")
        if not exists or not exists.get('present'):
            raise StartupSchemaError('HC-07 migration journal is missing. ' + HELP)
        known = tuple(row[0] for row in MIGRATIONS)
        unknown = fetch_one('select version from hc.startup_schema_migration where not(version=any(%s)) limit 1', (list(known),))
        if unknown:
            raise StartupSchemaError('Unknown HC-07 schema version; use its matching backend. ' + HELP)
        required = {m[0] for m in MIGRATIONS[:2]}
        for version, _, checksum in MIGRATIONS:
            row = fetch_one('select checksum from hc.startup_schema_migration where version=%s', (version,))
            if (not row and version in required) or (row and row.get('checksum') != checksum):
                raise StartupSchemaError('HC-07 migration ' + version + ' is missing or has a different checksum. ' + HELP)
    except StartupSchemaError:
        raise
    except Exception as exc:
        raise StartupSchemaError('HC-07 schema journal could not be read. ' + HELP) from exc


def column_check_sql(domain):
    values = ','.join("('%s','%s','%s')" % (table, column, typename)
                      for table in DOMAIN_TABLES[domain] for column, typename in REQUIRED_COLUMNS[table].items())
    return '''with expected(relation,column_name,type_name) as (values ''' + values + ''')
      select coalesce(json_agg(e.relation||'.'||e.column_name||':'||e.type_name)
        filter(where a.attname is null or a.atttypid<>to_regtype(e.type_name)), '[]'::json) as missing
      from expected e
      left join pg_namespace n on n.nspname='hc'
      left join pg_class c on c.relnamespace=n.oid and c.relname=e.relation and c.relkind in ('r','p')
      left join pg_attribute a on a.attrelid=c.oid and a.attname=e.column_name and a.attnum>0 and not a.attisdropped'''


def check_domain(fetch_one, domain):
    if domain not in DOMAIN_TABLES:
        raise ValueError('Unknown startup schema domain')
    check_journal(fetch_one)
    try:
        shape = fetch_one(column_check_sql(domain))
        if not shape or shape.get('missing') != []:
            raise StartupSchemaError('Incompatible ' + domain + ' schema columns/types. ' + HELP)
        if domain == 'pilot':
            for table in ('irrigation_pilot_config', 'irrigation_solar_pump_config'):
                if not fetch_one('select id from hc.' + table + ' where id=1'):
                    raise StartupSchemaError('Missing ' + table + ' configuration; restore it or explicitly seed a new installation. ' + HELP)
        elif domain == 'scheduler':
            config = fetch_one('select mode from hc.scheduler_config where id=1')
            if not config or config.get('mode') not in SUPPORTED_SCHEDULER_MODES:
                raise StartupSchemaError('Scheduler mode missing or unsupported; review and choose a supported mode explicitly. No automatic mode conversion. ' + HELP)
            index = fetch_one("""select i.indisunique and i.indisvalid and i.indisready as valid
              from pg_index i where i.indexrelid=to_regclass('hc.ux_scheduler_run_idempotency')""")
            if not index or index.get('valid') is not True:
                raise StartupSchemaError('Scheduler idempotency index missing or invalid. ' + HELP)
        elif domain == 'season':
            for name in ('irrigation', 'climate'):
                if not fetch_one('''select a.profile from hc.domain_season_active a
                     join hc.domain_season_profile p using(domain,profile) where a.domain=%s''', (name,)):
                    raise StartupSchemaError('Missing active season configuration; restore or explicitly seed. ' + HELP)
    except StartupSchemaError:
        raise
    except Exception as exc:
        raise StartupSchemaError('Cannot validate ' + domain + ' schema. ' + HELP) from exc
