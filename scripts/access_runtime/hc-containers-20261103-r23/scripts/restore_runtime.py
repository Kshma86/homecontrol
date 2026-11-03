#!/usr/bin/env python3
"""Explicit full-restore HC-07/39 dependency preparation, never runtime startup."""
import argparse
import os
from pathlib import Path
import re
import secrets
import shlex
import subprocess
from urllib.parse import quote

BASE = Path('/srv/docker/homecontrol')


def read_environment(path):
    data = {}
    for line in path.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'): continue
        key, separator, value = line.partition('=')
        if not separator or not re.fullmatch(r'[A-Z][A-Z0-9_]*', key.strip()):
            raise ValueError('Unsupported environment file syntax')
        values = shlex.split(value, comments=True)
        if len(values)>1: raise ValueError('Quote environment values containing spaces')
        data[key.strip()] = values[0] if values else ''
    return data


def environment(base=BASE):
    path = base/'infra/.env'; data = read_environment(path)
    for key in ('HC_APP_DB_PASSWORD','HC_LAB_DB_PASSWORD'):
        if not data.get(key): data[key] = secrets.token_urlsafe(36)
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', data[key]):
            raise ValueError('HC-39 requires URL-safe application/reader passwords')
    if data['HC_APP_DB_PASSWORD']==data['HC_LAB_DB_PASSWORD']: raise ValueError('Reader/application credentials must differ')
    database = data.get('POSTGRES_DB','homecontrol')
    data['SQL_LAB_DATABASE_URL'] = 'postgresql://hc_lab:'+data['HC_LAB_DB_PASSWORD']+'@postgres:5432/'+quote(database,safe='')
    # Preserve original text/order/comments; append explicit reviewed overrides.
    keys = ('HC_APP_DB_PASSWORD','HC_LAB_DB_PASSWORD','SQL_LAB_DATABASE_URL')
    text = '\n'.join(line for line in path.read_text().splitlines() if line.partition('=')[0].strip() not in keys)+'\n'
    text += '\n'.join(key+'='+data[key] for key in keys)+'\n'
    temporary=path.with_name('.env.restore-prepared')
    with temporary.open('x') as stream:
        os.fchmod(stream.fileno(),0o600);stream.write(text);stream.flush();os.fsync(stream.fileno())
    os.replace(temporary,path)
    return data


def roles(data, run=subprocess.run):
    # Names are fixed. Values are restricted URL-safe tokens, sent on stdin.
    sql = ''
    for role,key in (('hc_app','HC_APP_DB_PASSWORD'),('hc_lab','HC_LAB_DB_PASSWORD')):
        password=data[key]
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}',password): raise ValueError('Unsafe role credential')
        sql += "DO $$ BEGIN IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='"+role+"') THEN CREATE ROLE "+role+" LOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS; ELSIF EXISTS(SELECT FROM pg_roles WHERE rolname='"+role+"' AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR rolbypassrls OR rolinherit OR NOT rolcanlogin)) THEN RAISE EXCEPTION 'Unsafe existing runtime role'; END IF; END $$;\n"
        sql += "ALTER ROLE "+role+" PASSWORD '"+password+"';\n"
    run(['docker','exec','-i','homecontrol-postgres','sh','-c',
         'exec psql -U "$POSTGRES_USER" -d postgres -v ON_ERROR_STOP=1'], input=sql, text=True, check=True,
        stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)


def migrate(data, base=BASE, run=subprocess.run):
    user=data.get('POSTGRES_USER','homecontrol');database=data.get('POSTGRES_DB','homecontrol')
    admin='postgresql://'+quote(user,safe='')+':'+quote(data['POSTGRES_PASSWORD'],safe='')+'@postgres:5432/'+quote(database,safe='')
    env={**os.environ,'HC_RESTORE_ADMIN_DATABASE_URL':admin,
         'HC_APP_DB_PASSWORD':data['HC_APP_DB_PASSWORD'],'HC_LAB_DB_PASSWORD':data['HC_LAB_DB_PASSWORD']}
    run(['docker','compose','run','--rm','--no-deps','--pull','never','--entrypoint','python',
         '-e','HC_RESTORE_ADMIN_DATABASE_URL','-e','HC_APP_DB_PASSWORD','-e','HC_LAB_DB_PASSWORD',
         'backend','/app/restore_runtime_schema.py'],cwd=base/'infra',env=env,check=True)


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('step',choices=('environment','roles','migrate'))
    args=parser.parse_args()
    if args.step=='environment': environment()
    else:
        data=read_environment(BASE/'infra/.env')
        if args.step=='roles': roles(data)
        else: migrate(data)
    print('Restore runtime dependency step completed: '+args.step)


if __name__=='__main__':
    try: main()
    except Exception: raise SystemExit('Restore runtime dependency failed; inspect the private restore environment and migration prerequisites')
