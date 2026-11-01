#!/usr/bin/env python3
"""Owned nft bridge/inet filtering. Default is a read-only plan, never global flush."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess

TABLE='hc41_r10'


def rules(policy):
    esp=ipaddress.IPv4Address(policy['esp_ip']);broker=ipaddress.IPv4Address(policy['broker_ip'])
    if any(a.is_unspecified or a.is_loopback or a.is_multicast for a in (esp,broker)):raise ValueError('Invalid source/destination')
    sources=[str(esp)]
    if policy.get('mode')=='rollback':
        sources += [str(ipaddress.IPv4Network(policy['docker_subnet'])),str(ipaddress.IPv4Address(policy['dashboard_ip']))]
    elif policy.get('mode')!='authenticated':raise ValueError('Invalid mode')
    match='ether type ip ip daddr '+str(broker)+' tcp dport 1883 ip saddr != { '+', '.join(sources)+' } counter drop'
    # Native bridge hooks include direct Docker peers AND routed/host output.
    # No br_netfilter module or global sysctl change is required.
    text='add table bridge '+TABLE+'\n'
    for hook in ('forward','output'):
        text+='add chain bridge '+TABLE+' '+hook+' { type filter hook '+hook+' priority -5; policy accept; }\n'
        text+='add rule bridge '+TABLE+' '+hook+' '+match+'\n'
    text+='add table inet '+TABLE+'\n'
    text+='add chain inet '+TABLE+' input { type filter hook input priority -5; policy accept; }\n'
    text+='add rule inet '+TABLE+' input meta nfproto ipv6 tcp dport 1883 counter drop\n'
    return text


def execute(policy,run=subprocess.run):
    text=rules(policy);prefix=''
    for family in ('bridge','inet'):
        result=run(['nft','list','table',family,TABLE],capture_output=True,text=True)
        if result.returncode==0:
            if not policy.get('owned_chain'):raise RuntimeError('Existing unowned access table; reconcile before adopting')
            prefix+='delete table '+family+' '+TABLE+'\n'
        elif result.returncode!=1:raise RuntimeError('Cannot inspect nftables ownership')
    result=run(['nft','-f','-'],input=prefix+text,capture_output=True,text=True)
    if result.returncode:raise RuntimeError('Atomic access firewall transaction failed')
    return dict(applied=True,table=TABLE,mode=policy['mode'])


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--policy',type=Path,required=True);parser.add_argument('--apply',action='store_true')
    args=parser.parse_args();policy=json.loads(args.policy.read_text())
    if args.apply:
        if os.geteuid()!=0:raise SystemExit('Firewall installation requires root')
        result=execute(policy);policy['owned_chain']=True
        from common import write_json
        write_json(args.policy,policy);print(json.dumps(result))
    else:print(rules(policy))
