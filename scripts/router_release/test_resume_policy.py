import unittest
from resume_policy import resume_weekly


class ResumePolicyTest(unittest.TestCase):
    def setUp(self):
        self.current = {'restic_enabled': False, 'ai_weekly_backup_enabled': False}
        self.receipt = {'before': {'restic_enabled': True, 'ai_weekly_backup_enabled': True},
                        'after': dict(self.current)}

    def test_restores_only_incident_suspended_weekly_flag(self):
        candidate = {'restic_enabled': True, 'ai_weekly_backup_enabled': False,
                     'git_offsite_remote': 'git@example:unchanged', 'schedule_time': '04:25'}
        result = resume_weekly(self.current, candidate, self.receipt)
        self.assertTrue(result['ai_weekly_backup_enabled'])
        self.assertFalse(candidate['ai_weekly_backup_enabled'])
        self.assertEqual(result['git_offsite_remote'], candidate['git_offsite_remote'])
        self.assertEqual(result['schedule_time'], '04:25')

    def test_refuses_to_replace_a_different_current_preference(self):
        with self.assertRaises(ValueError):
            resume_weekly({**self.current, 'ai_weekly_backup_enabled': True}, {}, self.receipt)

    def test_refuses_to_enable_a_schedule_that_was_already_disabled(self):
        self.receipt['before']['ai_weekly_backup_enabled'] = False
        with self.assertRaises(ValueError):
            resume_weekly(self.current, {}, self.receipt)
