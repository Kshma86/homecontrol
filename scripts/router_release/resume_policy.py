"""Restore only the weekly flag suspended by the documented router incident."""


def resume_weekly(current, candidate, containment):
    before, after = containment['before'], containment['after']
    for key in ('restic_enabled', 'ai_weekly_backup_enabled'):
        if before.get(key) is not True or after.get(key) is not False or current.get(key) is not False:
            raise ValueError('Incident suspension settings changed; do not guess the intended schedule')
    return {**candidate, 'ai_weekly_backup_enabled': before['ai_weekly_backup_enabled']}
