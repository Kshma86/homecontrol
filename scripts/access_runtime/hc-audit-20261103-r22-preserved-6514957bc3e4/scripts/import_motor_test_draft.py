#!/usr/bin/env python3
"""Import the shipped MOTOR_TEST proposal into HC drafts only. Never contacts rover."""
import json
import os
from pathlib import Path
import sys

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / 'infra/backend'))
import psycopg
from mower_parameters_service import MowerParametersService
from mower_parameters_store import MowerParametersStore


def main():
    def connection(row_factory):
        return psycopg.connect(os.environ['DATABASE_URL'], row_factory=row_factory)

    def execute(sql):
        with psycopg.connect(os.environ['DATABASE_URL']) as conn:
            conn.execute(sql)

    service = MowerParametersService(MowerParametersStore(connection, execute))
    key = 'rover-motor-test'
    draft = service.latest(key)
    if draft['draft_revision']:
        print(f"HC draft already exists: {key}, revision {draft['draft_revision']}; preserved, no rover writes")
        return
    parameters = json.loads((root / 'infra/backend/static/rover_motor_test.initial.json').read_text())
    draft = service.save(key, dict(request_id='hc-motor-test-import-20261012-v2', expected_revision=0, parameters=parameters))
    print(f"HC draft imported: {key}, revision {draft['draft_revision']}, CRC {draft['validation']['parameters_crc']}; NOT APPLIED")


if __name__ == '__main__':
    main()
