#!/usr/bin/env python3
"""HC-41 staged MQTT configuration. Writes a NEW private package, never applies it."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import re
import secrets

ROLES = ('backend', 'ingest', 'tuya', 'x10', 'x10_api', 'climate', 'growatt', 'grott', 'dashboard', 'explorer')
PYTHON_SERVICES = {
    'backend': 'backend', 'hc_ingest': 'ingest',
    'homecontrol-tuya-poller': 'tuya', 'homecontrol-xiaomi-x10': 'x10',
    'homecontrol-gree-climate': 'climate', 'homecontrol-ha-growatt-poller': 'growatt',
}


def access_rules(device):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', device):
        raise ValueError('Invalid irrigation device identity')
    tele = f'homecontrol/tele/irrigation/{device}/#'
    stat = f'homecontrol/stat/irrigation/{device}/#'
    cmd = f'homecontrol/cmd/irrigation/{device}/#'
    rules = {
        'backend': [('read', 'zigbee/#'), ('read', 'homecontrol/#'),
            ('write', 'zigbee/+/set'), ('write', 'zigbee/+/get'),
            ('write', 'zigbee/bridge/request/#'), ('write', cmd),
            ('write', 'homecontrol/cmd/tuya/+/switch'),
            ('write', 'homecontrol/xiaomi_x10/command/#'),
            ('write', 'homecontrol/gree_climate/command'),
            ('write', 'homecontrol/mower/cmd/#')],
        'ingest': [('read', t) for t in ('zigbee/#', 'homecontrol/tele/tuya/#',
            'homecontrol/tele/growatt/#', 'homecontrol/tele/irrigation/+/pump_metrics',
            'homecontrol/tele/irrigation/+/solar', 'homecontrol/stat/irrigation/+/availability',
            'homecontrol/xiaomi_x10/#', 'homecontrol/gree_climate/#')],
        'tuya': [('read', 'homecontrol/cmd/tuya/+/switch'), ('write', 'homecontrol/tele/tuya/#')],
        'x10': [('read', 'homecontrol/xiaomi_x10/command/#'), ('write', 'homecontrol/xiaomi_x10/#')],
        'x10_api': [('read', 'homecontrol/xiaomi_x10/#'), ('write', 'homecontrol/xiaomi_x10/command/#')],
        'climate': [('read', 'homecontrol/gree_climate/command')] + [('write', 'homecontrol/gree_climate/' + t)
            for t in ('availability', 'state', 'error', 'command_result')],
        'growatt': [('write', 'homecontrol/tele/growatt/cloud/#')],
        'grott': [('write', 'homecontrol/tele/growatt/inverter/#')],
        'dashboard': [('read', tele), ('read', stat), ('write', cmd)],
        'explorer': [('read', 'homecontrol/#'), ('read', 'zigbee/#'), ('read', '$SYS/broker/#')],
        'zigbee2mqtt': [('readwrite', 'zigbee/#')],
    }
    legacy = [('write', tele), ('write', stat), ('read', cmd)]
    return rules, legacy


def prepare(root, *, device='esp-irrigation-1', esp_ip=None, ip_confirmed=False):
    root = Path(root).resolve()
    project = Path(__file__).resolve().parents[1]
    if any(root.is_relative_to(project / name) for name in ('infra', 'apps', 'scripts', 'homeassistant', 'docs')):
        raise ValueError('Credential packages must remain outside exported source/configuration trees')
    rules, legacy = access_rules(device)
    if esp_ip:
        address = ipaddress.ip_address(esp_ip)
        if address.is_unspecified or address.is_multicast or address.is_loopback:
            raise ValueError('ESP address must be an explicit unicast address')
    root.mkdir(mode=0o700)  # Refuse overwrite or reuse of an existing package.
    root.chmod(0o700)
    credential_dir = root / 'credentials'
    credential_dir.mkdir(mode=0o700)
    passwords = {role: secrets.token_urlsafe(36) for role in (*ROLES, 'zigbee2mqtt')}
    def write(path, value, mode=0o600):
        path.write_text(value, encoding='utf-8');path.chmod(mode)
    # The parent is private. Individual bind-mounted secret files are readable by
    # each container's unprivileged UID, without exposing the other role files.
    for role, password in passwords.items():
        write(credential_dir / (role + '.password'), password + '\n', 0o444)
    write(credential_dir / 'passwords', ''.join('hc_' + role + ':' + password + '\n' for role, password in passwords.items()))
    acl = ''.join('user hc_' + role + '\n' + ''.join('topic ' + access + ' ' + topic + '\n' for access, topic in entries) + '\n'
        for role, entries in rules.items())
    write(root / 'authenticated.acl', acl, 0o444)
    write(root / 'legacy.acl', ''.join('topic ' + access + ' ' + topic + '\n' for access, topic in legacy), 0o444)
    write(root / 'mosquitto.conf', '''# HC-41 candidate; deploy only after password hashing and network verification.
per_listener_settings true
persistence true
persistence_location /mosquitto/data/
log_dest stdout
log_type error
log_type warning
log_type notice

listener 1884 0.0.0.0
allow_anonymous false
password_file /mosquitto/config/credentials/passwords
acl_file /mosquitto/config/authenticated.acl

listener 1883 0.0.0.0
allow_anonymous true
acl_file /mosquitto/config/legacy.acl
''', 0o444)
    services = {'mqtt': {'volumes': [str(root) + ':/mosquitto/config:ro'],
        'ports': ['127.0.0.1:1884:1884']}}
    for service, role in PYTHON_SERVICES.items():
        target = '/run/secrets/hc-mqtt.password'
        environment = dict(MQTT_USERNAME='hc_' + role, MQTT_PASSWORD_FILE=target, MQTT_AUTH_REQUIRED='1')
        if role == 'x10':
            environment.update(X10_MQTT_HOST='mqtt', X10_MQTT_PORT='1884')
        else:
            environment.update(MQTT_HOST='127.0.0.1' if role in ('climate', 'growatt') else 'mqtt', MQTT_PORT='1884')
        services[service] = {'environment': environment,
            'volumes': [str(credential_dir / (role + '.password')) + ':' + target + ':ro']}
    env = root / 'zigbee2mqtt.env'
    write(env, 'ZIGBEE2MQTT_CONFIG_MQTT_SERVER=mqtt://mqtt:1884\n'
        'ZIGBEE2MQTT_CONFIG_MQTT_USER=hc_zigbee2mqtt\n'
        'ZIGBEE2MQTT_CONFIG_MQTT_PASSWORD=' + passwords['zigbee2mqtt'] + '\n')
    services['zigbee2mqtt'] = {'env_file': [str(env)]}
    write(root / 'dashboard-client.env', '# Generic client template; adapt to the dashboard configuration schema.\n'
        'MQTT_HOST=127.0.0.1\nMQTT_PORT=21884\nMQTT_USERNAME=hc_dashboard\n'
        'MQTT_PASSWORD=' + passwords['dashboard'] + '\n')
    # Field reference for manual entry, not an application-specific import format.
    write(root / 'mqtt-explorer.connection.json', json.dumps(dict(
        name='HC – megfigyelés (SSH)', protocol='mqtt', host='127.0.0.1', port=21884,
        username='hc_explorer', password=passwords['explorer'],
        suggested_mqtt_version='5.0', subscriptions=['homecontrol/#', 'zigbee/#', '$SYS/broker/#'],
        permissions='read_only', active=False, format='manual_connection_field_reference'),
        indent=2, ensure_ascii=False) + '\n')
    # Optional profile is not enabled. Upstream verbose logs may expose secrets.
    write(root / 'grott.optional.env', 'gmqttport=1884\ngmqttauth=True\ngmqttuser=hc_grott\n'
        'gmqttpassword=' + passwords['grott'] + '\ngverbose=False\n')
    write(root / 'compose.override.json', json.dumps({'services': services}, indent=2) + '\n')
    manifest = dict(finding='HC-41', applied=False, state='prepared_not_deployed',
        device=device, esp_ip=esp_ip, esp_ip_confirmed=ip_confirmed,
        passwords_need_hashing=True, authenticated_port=1884, legacy_port=1883,
        roles=list(passwords),
        blockers=['Password database must be hashed with mosquitto_passwd -U in an isolated helper',
            'Review immutable release/images and merge with the active frozen Compose',
            'Apply and verify ESP-only IPv4/IPv6 network restriction before opening the legacy listener',
            'Configure and verify the approved dev-PC dashboard credentials over SSH tunnel; confirm fixed ESP address/DHCP reservation',
            'Install the authenticated post-boot probe adapter with the release',
            'Verify broker UID ownership/readability of the private config/password database',
            'Include new MQTT secrets in the encrypted restore bundle, never in config Git exports',
            'Supervised telemetry/STOP/ack/reconnect validation and rollback required'],
        network_applied=False, broker_restarted=False,
        later_phase='Move ESP to authenticated 1884, remove anonymous listener and its publication/rules')
    if not ip_confirmed:manifest['blockers'].append('ESP IP/DHCP identity is not confirmed')
    write(root / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--device', default='esp-irrigation-1')
    parser.add_argument('--esp-ip')
    parser.add_argument('--esp-ip-confirmed', action='store_true')
    args = parser.parse_args()
    # The summary deliberately contains no passwords or environment values.
    print(json.dumps(prepare(args.output, device=args.device, esp_ip=args.esp_ip, ip_confirmed=args.esp_ip_confirmed), indent=2))


if __name__ == '__main__':main()
