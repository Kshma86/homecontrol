"""OID/owner/data-independent HC catalog, compared at the r1/058 baseline boundary."""

# A separate baseline journal is excluded from the reference catalog. Future
# migrations intentionally change the catalog; this is not a runtime health check.
QUERIES = {
    'relations': """select c.relname,c.relkind,c.relpersistence,c.relrowsecurity,c.relforcerowsecurity,
      coalesce(c.reloptions,array[]::text[]),a.amname
      from pg_class c join pg_namespace n on n.oid=c.relnamespace
      left join pg_am a on a.oid=c.relam
      where n.nspname='hc' and c.relkind in ('r','p','v','m','S','f')
      and c.relname<>'schema_baseline' order by 1""",
    'columns': """select c.relname,a.attname,a.attnum,format_type(a.atttypid,a.atttypmod),
      a.attnotnull,a.attidentity,a.attgenerated,pg_get_expr(d.adbin,d.adrelid)
      from pg_class c join pg_namespace n on n.oid=c.relnamespace
      join pg_attribute a on a.attrelid=c.oid and a.attnum>0 and not a.attisdropped
      left join pg_attrdef d on d.adrelid=c.oid and d.adnum=a.attnum
      where n.nspname='hc' and c.relkind in ('r','p','v','m','f')
      and c.relname<>'schema_baseline' order by 1,3""",
    'constraints': """select c.relname,x.conname,pg_get_constraintdef(x.oid),x.convalidated
      from pg_constraint x join pg_class c on c.oid=x.conrelid
      join pg_namespace n on n.oid=c.relnamespace where n.nspname='hc'
      and c.relname<>'schema_baseline' order by 1,2""",
    'indexes': """select t.relname,c.relname as indexname,pg_get_indexdef(i.indexrelid),
      i.indisvalid,i.indisready,i.indisunique
      from pg_index i join pg_class c on c.oid=i.indexrelid
      join pg_class t on t.oid=i.indrelid join pg_namespace n on n.oid=t.relnamespace
      where n.nspname='hc' and t.relname<>'schema_baseline' order by 1,2""",
    'enums': """select t.typname,e.enumlabel,e.enumsortorder::text
      from pg_type t join pg_namespace n on n.oid=t.typnamespace
      join pg_enum e on e.enumtypid=t.oid where n.nspname='hc' order by t.typname,e.enumsortorder""",
    'functions': """select p.proname,pg_get_function_identity_arguments(p.oid),pg_get_functiondef(p.oid)
      from pg_proc p join pg_namespace n on n.oid=p.pronamespace
      where n.nspname='hc' order by 1,2""",
    'triggers': """select c.relname,t.tgname,t.tgenabled,pg_get_triggerdef(t.oid)
      from pg_trigger t join pg_class c on c.oid=t.tgrelid
      join pg_namespace n on n.oid=c.relnamespace where n.nspname='hc'
      and not t.tgisinternal order by 1,2""",
    'views': """select c.relname,pg_get_viewdef(c.oid)
      from pg_class c join pg_namespace n on n.oid=c.relnamespace
      where n.nspname='hc' and c.relkind in ('v','m') order by 1""",
    'sequences': """select c.relname,format_type(s.seqtypid,null),s.seqstart::text,
      s.seqincrement::text,s.seqmax::text,s.seqmin::text,s.seqcache::text,s.seqcycle,
      t.relname as owned_table,a.attname,d.deptype
      from pg_sequence s join pg_class c on c.oid=s.seqrelid
      join pg_namespace n on n.oid=c.relnamespace
      left join pg_depend d on d.classid='pg_class'::regclass and d.objid=c.oid
        and d.refclassid='pg_class'::regclass and d.deptype in ('a','i')
      left join pg_class t on t.oid=d.refobjid
      left join pg_attribute a on a.attrelid=t.oid and a.attnum=d.refobjsubid
      where n.nspname='hc' order by 1""",
}


def normalize(snapshot):
    # pg_dump -> parser flattens this historical nested AND into one AND list.
    # Canonicalize only this exact, known equivalent expression, never arbitrary
    # parentheses (which could change OR/AND precedence or conceal real drift).
    grouped = 'CHECK ((((octet_length(image) >= 1280) AND (octet_length(image) <= 524288)) AND ((octet_length(image) % 32) = 0)))'
    flat = 'CHECK (((octet_length(image) >= 1280) AND (octet_length(image) <= 524288) AND ((octet_length(image) % 32) = 0)))'
    for row in snapshot['constraints']:
        if row[:2] == ['mower_firmware_artifact', 'mower_firmware_artifact_image_check'] and row[2] == grouped:
            row[2] = flat
    return snapshot


def catalog(conn):
    # Call inside a transaction so this setting cannot leak into the caller.
    conn.execute("select set_config('search_path','pg_catalog',true)")
    return normalize({key: [list(row) for row in conn.execute(sql).fetchall()]
                      for key, sql in QUERIES.items()})


def differences(actual, expected):
    return {key: {'added': [r for r in actual[key] if r not in expected[key]],
                  'removed': [r for r in expected[key] if r not in actual[key]]}
            for key in expected if actual[key] != expected[key]}
