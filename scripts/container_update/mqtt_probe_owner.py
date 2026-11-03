"""Run only the frozen isolated broker commands as their config owner."""


def broker_command(args,stage,image):
    args=list(map(str,args))
    if args[:2]!=['docker','run'] or '--entrypoint' not in args:return args
    pos=args.index('--entrypoint')
    if args[pos+1:pos+2]!=['mosquitto']:return args
    def option(name):
        if args.count(name)!=1:raise ValueError('Ambiguous isolated broker option')
        return args[args.index(name)+1]
    if (args[pos+2:pos+3]!=[image] or option('--user')!='0:0'
            or option('--network')!='none' or option('--cap-drop')!='ALL'
            or option('--security-opt')!='no-new-privileges' or '--read-only' not in args):
        raise ValueError('Unexpected isolated broker command')
    expected='type=bind,src='+str(stage/'mqtt/broker')+',dst=/mosquitto/config,readonly'
    if expected not in args:raise ValueError('Isolated broker configuration is not the new private copy')
    capabilities=[args[i+1] for i,value in enumerate(args[:-1]) if value=='--cap-add']
    if capabilities!=['SETUID','SETGID']:raise ValueError('Unexpected broker capabilities')
    result=[];index=0
    while index<len(args):
        if args[index]=='--cap-add':index+=2;continue
        if args[index]=='--user':result+=['--user','1883:1883'];index+=2;continue
        result.append(args[index]);index+=1
    return result


def install(executor):
    original=executor.private_mqtt_probe
    def probe(core,helper,stage,source):
        call=helper.call;image=core.load()['images']['mqtt']
        def owned(args,**kwargs):return call(broker_command(args,stage,image),**kwargs)
        helper.call=owned
        try:return original(core,helper,stage,source)
        finally:helper.call=call
    executor.private_mqtt_probe=probe
