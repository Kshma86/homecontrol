#!/usr/bin/env bash
TS=$(date +%F_%H-%M-%S)
docker exec homecontrol-postgres pg_dump -U homecontrol -Fc -d homecontrol -f /tmp/homecontrol.dump
docker cp homecontrol-postgres:/tmp/homecontrol.dump /srv/docker/homecontrol/postgres_backup.dump
tar -czf "/srv/docker/homecontrol/backups/homecontrol_$TS.tar.gz" /srv/docker/homecontrol
