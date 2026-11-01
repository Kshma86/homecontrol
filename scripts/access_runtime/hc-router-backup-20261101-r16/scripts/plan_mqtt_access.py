#!/usr/bin/env python3
"""HC-41 read-only network plan. Never changes broker, passwords or firewall."""
import argparse,ipaddress,json,subprocess


def plan(bindings,host_ips=(),allowed_clients=()):
    addresses=[ipaddress.ip_address(v) for v in host_ips]
    clients=[ipaddress.ip_address(v) for v in allowed_clients]
    if any(v.is_unspecified or v.is_multicast or v.is_loopback for v in clients):
        raise ValueError('Remote clients must be explicit unicast host addresses')
    blockers=[];commands=[];configured=set()
    if not clients:blockers.append('approved_remote_client_inventory_missing')
    ports=bindings.get('1883/tcp',[])
    for item in ports:
        bind=item.get('HostIp') or '0.0.0.0';port=int(item['HostPort'])
        address=ipaddress.ip_address(bind)
        destinations=[address] if not address.is_unspecified else [v for v in addresses if v.version==address.version and not v.is_loopback]
        if not destinations:blockers.append('all_published_host_addresses_must_be_inventoried')
        for destination in destinations:
            binary='iptables' if destination.version==4 else 'ip6tables'
            chain='HC41_MQTT'
            if binary not in configured:
                configured.add(binary)
                commands.append([binary,'-N',chain])
                for client in clients:
                    if client.version==destination.version:commands.append([binary,'-A',chain,'-s',str(client),'-j','ACCEPT'])
                commands.append([binary,'-A',chain,'-j','DROP'])
            commands.append([binary,'-I','DOCKER-USER','1','-p','tcp','-m','conntrack','--ctdir','ORIGINAL','--ctorigdst',str(destination),'--ctorigdstport',str(port),'-j',chain])
    return dict(finding='HC-41',full_finding_fixed=False,authentication='deferred_by_user',
        broker_changed=False,passwords_changed=False,firewall_changed=False,
        network_plan_ready=not blockers,blockers=sorted(set(blockers)),commands_for_review_only=commands,
        limits=['Requires verified Docker iptables backend and both IP families',
                'Review order/idempotency and every local bind address before applying',
                'IP filtering does not authenticate clients or provide topic ACLs'])


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--bindings-file');p.add_argument('--live',action='store_true')
    p.add_argument('--host-ip',action='append',default=[]);p.add_argument('--allow-client',action='append',default=[])
    args=p.parse_args()
    if args.live:
        bindings=json.loads(subprocess.check_output(['docker','inspect','--format','{{json .HostConfig.PortBindings}}','homecontrol-mqtt']))
    elif args.bindings_file:bindings=json.load(open(args.bindings_file))
    else:bindings={'1883/tcp':[{'HostIp':'0.0.0.0','HostPort':'1883'},{'HostIp':'::','HostPort':'1883'}]}
    print(json.dumps(plan(bindings,args.host_ip,args.allow_client),indent=2))


if __name__=='__main__':main()
