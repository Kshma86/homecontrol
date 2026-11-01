"""Release-scoped AI isolation, shared by the backend and host backup runner.

The restricted package bakes in a mandatory JSON policy beside this module.
There is deliberately no environment variable or settings API to turn it off.
The normal development tree has no policy file and keeps its existing behavior.
"""
import json
from pathlib import Path

POLICY_REQUIRED = True  # Set True only in the frozen restricted package.
POLICY_FILE = Path(__file__).with_suffix('.json')
MESSAGE = 'Az AI-szerver SSD-probléma miatt ideiglenesen ki van hagyva; csak helyi mentés érhető el.'
RESTORE_MESSAGE = 'Korlátozott kiadásban csak staging visszaállítás használható; az éles fájlok visszaírása le van tiltva.'
REMOTE_MODES = frozenset(('weekly', 'git', 'check'))
REMOTE_SETTINGS = ('git_enabled', 'git_offsite_enabled', 'restic_enabled',
                   'restic_required', 'ai_weekly_backup_enabled',
                   'ai_weekly_shutdown_after', 'include_gitea')


def load_policy(path=None, required=None):
    path = Path(path) if path is not None else POLICY_FILE
    required = POLICY_REQUIRED if required is None else required
    try:
        if path.stat().st_size > 16384:
            raise ValueError('Oversized policy')
        data = json.loads(path.read_text())
        if (not isinstance(data, dict) or data.get('version') != 1
                or data.get('profile') != 'ai-offline'
                or not isinstance(data.get('blocked_entity_ids'), list)
                or not data['blocked_entity_ids']
                or not all(isinstance(x, int) and not isinstance(x, bool) and x > 0 for x in data['blocked_entity_ids'])
                or not isinstance(data.get('blocked_command_topics'), list)
                or not data['blocked_command_topics']
                or not all(isinstance(x, str) and x and not any(c in x for c in ('#', '+', '\x00'))
                           for x in data['blocked_command_topics'])):
            raise ValueError('Invalid restricted policy')
        return {**data, 'restricted': True, 'valid': True}
    except FileNotFoundError:
        if not required:
            return {'restricted': False, 'valid': True, 'profile': 'standard'}
    except (OSError, ValueError, TypeError):
        pass
    # Missing/unreadable/corrupt mandatory policy cannot authorize an actuator.
    return {'restricted': True, 'valid': False, 'profile': 'ai-offline'}


def policy():
    return load_policy()


def ai_disabled():
    return policy()['restricted']


def unavailable():
    return {'ok': False, 'disabled': True, 'code': 'deployment_restricted', 'error': MESSAGE}


def public_status():
    current = policy()
    return {'profile': current['profile'], 'restricted': current['restricted'],
            'policy_valid': current['valid'],
            'message': MESSAGE if current['restricted'] else '',
            'ai_enabled': not current['restricted'],
            'remote_backup_enabled': not current['restricted'],
            'restore_in_place_enabled': not current['restricted'],
            'local_backup_only': current['restricted']}


def effective_backup_settings(settings):
    result = dict(settings)
    if ai_disabled():
        result.update({key: False for key in REMOTE_SETTINGS})
    return result


def backup_mode_allowed(mode):
    return not (ai_disabled() and mode in REMOTE_MODES)


def entity_blocked(row):
    current = policy()
    if not current['restricted']:
        return False
    if not current['valid']:
        return True
    return str((row or {}).get('entity_id', '')) in {str(x) for x in current['blocked_entity_ids']}


def command_blocked(topic, payload=None):
    current = policy()
    if not current['restricted']:
        return False
    if not current['valid']:
        return True
    if isinstance(payload, dict) and entity_blocked(payload):
        return True
    return any(topic == prefix or str(topic).startswith(prefix + '/')
               for prefix in current['blocked_command_topics'])


def tuya_device_blocked(name, device_id):
    current = policy()
    if not current['restricted']:
        return False
    return (not current['valid'] or str(device_id) in current.get('blocked_tuya_device_ids', [])
            or command_blocked('homecontrol/cmd/tuya/'+str(name)+'/switch'))


def install_routes(app):
    from flask import jsonify, request
    if not policy()['valid']:
        raise RuntimeError('Mandatory deployment policy is missing or invalid; startup refused')

    @app.get('/api/deployment/status')
    def deployment_status():
        return jsonify(public_status())

    @app.before_request
    def enforce_deployment_policy():
        if not ai_disabled():
            return None
        path = request.path
        blocked = ((path == '/api/ai' or path.startswith('/api/ai/'))
                   and path not in ('/api/ai/status', '/api/ai/node/status'))
        blocked = blocked or path == '/api/context/ai/summary'
        blocked = blocked or path == '/api/admin/containers/ai/restart'
        blocked = blocked or path == '/api/backup/full-ai' or path.startswith('/api/backup/gitea/')
        if path in ('/api/backup/restore', '/api/backup/restore/recover') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            body = request.get_json(silent=True) or {}
            if path.endswith('/recover') or not isinstance(body, dict) or body.get('mode', 'staging') != 'staging':
                return jsonify({**unavailable(), 'error': RESTORE_MESSAGE}), 503
        blocked = blocked or (path == '/api/process-bindings/ai_node_power_plug'
                              and request.method not in ('GET', 'HEAD', 'OPTIONS'))
        if path.startswith(('/api/power-wall/', '/api/tuya/')) and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            body = request.get_json(silent=True)
            blocked = blocked or (isinstance(body, dict) and entity_blocked(body))
        if blocked:
            return jsonify(unavailable()), 503
