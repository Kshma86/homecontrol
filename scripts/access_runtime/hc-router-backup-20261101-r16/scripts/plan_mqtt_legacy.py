#!/usr/bin/env python3
"""HC-41 legacy IP restriction review plan. Never executes firewall commands."""
import argparse
import ipaddress
import json


def plan(esp_ip, broker_ip):
    esp = ipaddress.IPv4Address(esp_ip)
    broker = ipaddress.IPv4Address(broker_ip)
    if any(v.is_unspecified or v.is_loopback or v.is_multicast for v in (esp, broker)):
        raise ValueError('Explicit unicast ESP and broker container IPv4 addresses required')
    # The destination is post-DNAT. Matching only the host's published address
    # would miss direct bridge-to-broker connections from other containers.
    commands = [
        ['iptables', '-N', 'HC41_LEGACY'],
        ['iptables', '-A', 'HC41_LEGACY', '-s', str(esp), '-j', 'ACCEPT'],
        ['iptables', '-A', 'HC41_LEGACY', '-j', 'DROP'],
        ['iptables', '-I', 'DOCKER-USER', '1', '-p', 'tcp', '-d', str(broker), '--dport', '1883', '-j', 'HC41_LEGACY'],
        ['iptables', '-I', 'OUTPUT', '1', '-p', 'tcp', '-d', str(broker), '--dport', '1883', '-j', 'DROP'],
        ['ip6tables', '-I', 'INPUT', '1', '-p', 'tcp', '--dport', '1883', '-j', 'DROP'],
        ['ip6tables', '-I', 'DOCKER-USER', '1', '-p', 'tcp', '--dport', '1883', '-j', 'DROP'],
    ]
    return dict(applied=False,ready_to_apply=False,esp_ip=str(esp),broker_container_ip=str(broker),
        commands_for_review_only=commands,
        requirements=['Confirm ESP identity and DHCP reservation',
            'Verify iptables backend, bridge netfilter and IPv6/proxy paths on the actual host',
            'Verify broker container address after recreation; regenerate rules on IP change',
            'Install persistent idempotent owner rules and exact inverse rollback; do not flush other rules',
            'Prove unrelated LAN, IPv6, host and Docker peers cannot access legacy MQTT',
            'Preserve the original ESP source address; NAT/proxy masking must fail closed',
            'Keep legacy access closed until rules and supervised STOP/ack route are verified'])


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--esp-ip',required=True)
    parser.add_argument('--broker-ip',required=True)
    args=parser.parse_args()
    print(json.dumps(plan(args.esp_ip,args.broker_ip),indent=2))
