"""Explicit full-host recovery bridge. No app imports or startup threads."""
import os
from pathlib import Path
import psycopg
from psycopg.conninfo import conninfo_to_dict
from sql_lab_database import READER_CHECK
from migrate_hc07 import migrate
from migrate_hc39 import provision


def main():
    sql_dir=Path('/srv/docker/homecontrol/infra/db')
    dsn=os.environ['HC_RESTORE_ADMIN_DATABASE_URL']
    with psycopg.connect(dsn,autocommit=True) as conn:
        result=migrate(conn,sql_dir,apply=True,seed_initial=False)
        if not result['ready']: raise RuntimeError('Restored HC-07 schema is incompatible')
        provision(conn,sql_dir,apply=True,adopt_existing_roles=True,passwords={
            'hc_app':os.environ['HC_APP_DB_PASSWORD'],'hc_lab':os.environ['HC_LAB_DB_PASSWORD']})
    parameters=conninfo_to_dict(dsn)
    for user,key in (('hc_app','HC_APP_DB_PASSWORD'),('hc_lab','HC_LAB_DB_PASSWORD')):
        with psycopg.connect(**{**parameters,'user':user,'password':os.environ[key]},autocommit=True) as check:
            if check.execute('select current_user').fetchone()[0]!=user: raise RuntimeError('Runtime role authentication mismatch')
            if user=='hc_lab' and check.execute(READER_CHECK).fetchone()[0] is not True: raise RuntimeError('Unsafe reader permissions')
    print('Explicit restored schema and privilege migrations completed')


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('Restored schema/ACL prerequisites failed; runtime must remain stopped')
