"""HC-09 observation checks. MQTT receipt time alone is never a device sample."""
import math
import re


WEEKLY_TASK_IDS = (12, 13, 14, 17, 15, 16, 11)


def number(value):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return float(value)


def fence(snapshot, wall, monotonic):
    return {'wall': wall, 'monotonic': monotonic, 'monitor_epoch': snapshot.get('observation_epoch')}


def fresh_frame(snapshot, topic, boundary, max_age, wall, monotonic, *, source=None):
    frame = snapshot.get('topics', {}).get(topic)
    if snapshot.get('mqtt_connected') is not True or not isinstance(frame, dict):
        return None, {'fresh': False, 'reason': 'monitor_offline_or_sample_missing'}
    if (frame.get('retain') is not False or not isinstance(snapshot.get('observation_epoch'), str)
            or frame.get('connection_generation') != snapshot.get('connection_generation')):
        return None, {'fresh': False, 'reason': 'retained_or_old_connection'}
    payload = frame.get('json')
    sample = source(payload) if source and isinstance(payload, dict) else payload
    sampled = number(sample.get('sampled_at')) if isinstance(sample, dict) else None
    receipt, received_mono = number(frame.get('timestamp')), number(frame.get('received_monotonic'))
    if (sampled is None or receipt is None or received_mono is None or sampled <= 0
            or not sampled <= receipt <= wall or received_mono > monotonic
            or wall - sampled > max_age
            or receipt - sampled + monotonic - received_mono > max_age):
        return None, {'fresh': False, 'reason': 'invalid_future_or_stale_source_sample'}
    if boundary:
        start = number(boundary.get('wall'))
        if start is None or sampled <= start or receipt < start:
            return None, {'fresh': False, 'reason': 'sample_precedes_intent'}
        if boundary.get('monitor_epoch') == snapshot.get('observation_epoch'):
            start_mono = number(boundary.get('monotonic'))
            if start_mono is None or received_mono < start_mono:
                return None, {'fresh': False, 'reason': 'receipt_precedes_intent'}
    return payload, {'fresh': True, 'sampled_at': sampled, 'source_age_seconds': max(wall - sampled, receipt - sampled + monotonic - received_mono),
                     'received_at': receipt, 'scope': 'device_observation'}


def climate_matches(command, state):
    fields = ('power', 'mode', 'target_temperature', 'fan_speed', 'light')
    checks = {}
    if not isinstance(state, dict) or state.get('ok') is not True:
        return False, checks
    for name in fields:
        if name not in command or command[name] is None or command[name] == 'keep':
            continue
        wanted, observed = command[name], state.get(name)
        if name == 'target_temperature':
            checks[name] = number(wanted) is not None and number(observed) == number(wanted)
        else:
            checks[name] = (isinstance(wanted, str) and isinstance(observed, str)
                            and wanted.lower() == observed.lower() and bool(wanted.strip()))
    return bool(checks) and all(checks.values()), checks


def climate_observation(snapshot, command, boundary, max_age, wall, monotonic):
    accepted = None
    result, reply_evidence = fresh_frame(snapshot, 'command_result', boundary, max_age, wall, monotonic,
                                        source=lambda p: {'sampled_at': p.get('reported_at')})
    if (result and command.get('hc_execution_id') and isinstance(result.get('command'), dict)
            and result['command'].get('hc_execution_id') == command['hc_execution_id']):
        accepted = result.get('ok') if type(result.get('ok')) is bool else None
    candidates = [('state', None), ('command_result', lambda p: p.get('state'))]
    last = {'fresh': False, 'reason': 'sample_missing'}
    for topic, source in candidates:
        payload, evidence = fresh_frame(snapshot, topic, boundary, max_age, wall, monotonic, source=source)
        if payload is None:
            last = evidence
            continue
        if topic == 'command_result':
            if (accepted is not True or not isinstance(payload.get('command'), dict)
                    or payload['command'].get('hc_execution_id') != command.get('hc_execution_id')):
                continue
            state = payload.get('state')
        else:
            state = payload
        matches, checks = climate_matches(command, state)
        evidence = {**evidence, 'checks': checks, 'topic': topic, 'accepted': accepted,
                    'confirmed': matches, 'confirmation_scope': 'climate_device_state',
                    'reason': 'fresh_device_state_matches' if matches else 'fresh_device_state_mismatch'}
        if matches:
            return evidence
        last = evidence
    return {**last, 'accepted': accepted, 'confirmed': False, 'confirmation_scope': 'climate_device_state'}


def integer(value):
    if isinstance(value, bool):
        return None
    try:
        numeric = float(value)
        return int(numeric) if math.isfinite(numeric) and numeric.is_integer() else None
    except (ValueError, TypeError, OverflowError):
        return None


def minute(value):
    text = str(value or '')
    if re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d(?::00(?:\.0+)?)?', text):
        return text[:5]
    return None


def first(row, *names):
    return next((row[name] for name in names if row.get(name) is not None), None)


def entry_values(row):
    segments = row.get('segments')
    if not isinstance(segments, list):
        segments = str(segments or '').split(',')
    values = dict(time=minute(first(row, 'start_time', 'time')), days=row.get('days'),
                  enabled=integer(row.get('enabled')), map_id=integer(row.get('map_id')),
                  mode=integer(first(row, 'mode', 'clean_mode', 'flag')),
                  suction=integer(row.get('suction')), water=integer(first(row, 'water_level', 'clean_param')),
                  segments=[integer(v) for v in segments])
    valid = (all(v is not None for v in values.values()) and values['enabled'] in (0, 1)
             and isinstance(values['days'], str) and re.fullmatch('[01]{7}', values['days'])
             and bool(values['segments']) and all(v is not None for v in values['segments']))
    return values, bool(valid)


def entry_matches(command, entry):
    wanted, wanted_ok = entry_values(command)
    observed, observed_ok = entry_values(entry)
    return wanted_ok and observed_ok and wanted == observed


def weekly_commands(scheduler, desired):
    commands = []
    for item in desired:
        day = integer(item.get('day_index'))
        if day is None or not 0 <= day <= 6:
            raise ValueError('Invalid weekly schedule day')
        days = ['0'] * 7
        days[scheduler.x10_day_mask_index_by_hc_day()[day]] = '1'
        commands.append({**item, 'start_time': minute(item.get('start_time')), 'days': ''.join(days),
                         'enabled': integer(item.get('enabled')), 'task_id': str(WEEKLY_TASK_IDS[day]),
                         'mode': first(item, 'mode', 'clean_mode'),
                         'water_level': first(item, 'water_level', 'clean_param')})
    if not commands or any(not entry_values(c)[1] for c in commands):
        raise ValueError('Incomplete weekly schedule cannot be confirmed')
    return commands


def weekly_observation(snapshot, commands, boundary, max_age, wall, monotonic):
    payload, evidence = fresh_frame(snapshot, 'scheduler/observation', boundary, max_age, wall, monotonic)
    if not isinstance(payload, dict) or not isinstance(payload.get('entries'), list):
        return {**evidence, 'confirmed': False, 'reason': evidence.get('reason', 'invalid_scheduler_entries')}
    entries = payload['entries']
    if any(not isinstance(e, dict) for e in entries):
        return {**evidence, 'confirmed': False, 'reason': 'invalid_scheduler_entries'}
    wanted_ids = {c['task_id'] for c in commands}
    matches = [len([e for e in entries if str(e.get('task_id')) == c['task_id']]) == 1
               and any(str(e.get('task_id')) == c['task_id'] and entry_matches(c, e) for e in entries)
               for c in commands]
    unexpected = any(integer(e.get('task_id')) in WEEKLY_TASK_IDS and str(e.get('task_id')) not in wanted_ids
                     and integer(e.get('enabled')) != 0 for e in entries)
    return {**evidence, 'confirmed': all(matches) and not unexpected, 'matches': matches,
            'unexpected_enabled_weekly_slot': unexpected,
            'reason': 'fresh_robot_schedule_matches' if all(matches) and not unexpected else 'fresh_robot_schedule_mismatch',
            'confirmation_scope': 'robot_weekly_schedule_not_cleaning_completion'}
