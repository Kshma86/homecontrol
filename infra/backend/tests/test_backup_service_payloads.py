import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backup_service import BackupService


class BackupServicePayloadTest(unittest.TestCase):
    def service(self):
        service = BackupService(lambda *args: (b"{}", 200), lambda *args: b"")
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        root = Path(tempdir.name)
        service.backup_root = root / "backups"
        service.settings_file = service.backup_root / "settings.json"
        service.ai_backup_lock_file = service.backup_root / "ai-backup.lock"
        service.ai_backup_state_file = service.backup_root / "ai-backup-state.json"
        service.ai_shutdown_request_file = service.backup_root / "ai-shutdown-after-backup.request"
        service.timer_file = root / "timer"
        service.service_file = root / "service"
        return service

    def test_update_settings_payload_includes_context(self):
        service = self.service()

        payload, status = service.update_settings_payload(
            {"schedule_enabled": False, "retention_days": 3},
            lambda *sections: {"invalidated": list(sections)},
        )

        self.assertEqual(status, 200)
        self.assertFalse(payload["settings"]["schedule_enabled"])
        self.assertEqual(payload["context"]["invalidated"], ["backup"])

    def test_compare_payload_requires_path(self):
        payload, status = self.service().compare_payload("missing.tar.gz", "")

        self.assertEqual(status, 400)
        self.assertEqual(payload["error"], "path is required")

    def test_payload_includes_git_and_restic_plan(self):
        payload = self.service().payload()

        self.assertIn("plan", payload)
        self.assertIn("activity", payload)
        self.assertTrue(payload["plan"]["git"]["enabled"])
        self.assertFalse(payload["plan"]["restic"]["enabled"])
        self.assertEqual(payload["settings"]["restic_repository"], "sftp:a@192.168.1.2:/mnt/hc-backup/restic/homecontrol")
        self.assertEqual(payload["plan"]["restic"]["remote"]["mount"], "/mnt/hc-backup")
        self.assertEqual(payload["plan"]["restic"]["retention"]["daily"], 14)

    def test_activity_reads_recent_backup_log_markers(self):
        service = self.service()
        service.backup_root.mkdir(parents=True)
        (service.backup_root / "backup.log").write_text(
            "\n".join(
                [
                    "[2026-07-29 02:15:01] == Backup kész: /tmp/homecontrol.tar.gz (10M) ==",
                    "[2026-07-29 03:00:00] Config sync kész",
                    "[2026-07-29 04:30:00] == Restic check kész ==",
                ]
            ),
            encoding="utf-8",
        )

        activity = service.activity()

        self.assertIsNone(activity["latest_backup"])
        self.assertIn("Backup kész", activity["legacy_backup_log"])
        self.assertIn("Config sync kész", activity["latest_gitea_sync"])
        self.assertIn("Restic check kész", activity["latest_restic_check"])

    def test_unverified_log_success_cannot_clear_an_unrelated_error(self):
        service = self.service()
        service.backup_root.mkdir(parents=True)
        (service.backup_root / "backup.log").write_text(
            "\n".join(
                [
                    "[2026-07-29 22:33:55] HIBA: AI szerver nem lett elérhető SSH-n 900 másodperc alatt",
                    "[2026-07-30 02:15:33] == Backup kész restic nélkül: /tmp/homecontrol.tar.gz ==",
                ]
            ),
            encoding="utf-8",
        )

        activity = service.activity()

        self.assertIn("HIBA:", activity["latest_error"])
        self.assertIsNone(activity["latest_backup"])

    def test_full_ai_backup_payload_writes_request_file(self):
        service = self.service()

        payload, status = service.full_ai_backup_payload(lambda *sections: {"invalidated": list(sections)})

        self.assertEqual(status, 202)
        self.assertTrue((service.backup_root / "requests" / (payload["run_id"]+".json")).exists())
        self.assertEqual(payload["mode"], "full_ai_backup")
        self.assertEqual(payload["context"]["invalidated"], ["backup"])

    def test_legacy_request_file_does_not_masquerade_as_a_new_job(self):
        service = self.service()
        service.backup_root.mkdir(parents=True)
        request_file = service.backup_root / "full-ai-backup.request"
        request_file.write_text("recent\n", encoding="utf-8")

        payload, status = service.full_ai_backup_payload(lambda *sections: {"invalidated": list(sections)})

        self.assertEqual(status, 202)
        self.assertEqual(payload["request"]["state"], "queued")

    def test_full_ai_backup_can_run_after_recent_success(self):
        from datetime import datetime

        service = self.service()
        service.latest_log_timestamp = lambda marker: datetime.now()

        payload, status = service.full_ai_backup_payload(lambda *sections: {})

        self.assertEqual(status, 202)
        self.assertTrue((service.backup_root / "requests" / (payload["run_id"]+".json")).exists())
        self.assertIn("queued", payload["message"])

    def test_gitea_status_payload_runs_status_script(self):
        service = self.service()
        calls = []
        service.run_gitea_script = lambda script, args=(), timeout=120: calls.append((script, list(args), timeout)) or {"ok": True, "returncode": 0, "stdout": "clean", "stderr": ""}

        payload, status = service.gitea_status_payload()

        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "gitea_status")
        self.assertEqual(calls[0][0], "gitea_config_status_f1.sh")

    def test_gitea_commit_payload_passes_message(self):
        service = self.service()
        calls = []
        service.run_gitea_script = lambda script, args=(), timeout=120: calls.append((script, list(args), timeout)) or {"ok": True, "returncode": 0, "stdout": "pushed", "stderr": ""}

        payload, status = service.gitea_commit_payload({"message": "Manual save"}, lambda *sections: {"invalidated": list(sections)})

        self.assertEqual(status, 202)
        self.assertEqual(payload["mode"], "gitea_commit")
        self.assertEqual(payload["request"]["message"], "Manual save")
        self.assertFalse(calls)
        self.assertEqual(payload["context"]["invalidated"], ["backup"])

    def test_gitea_restore_payload_uses_staging_ref(self):
        service = self.service()
        calls = []
        service.run_gitea_script = lambda script, args=(), timeout=120: calls.append((script, list(args), timeout)) or {"ok": True, "returncode": 0, "stdout": "staged", "stderr": ""}

        payload, status = service.gitea_restore_payload({"ref": "main"})

        self.assertEqual(status, 200)
        self.assertEqual(payload["mode"], "gitea_restore")
        self.assertEqual(calls[0][0], "gitea_config_restore.sh")
        self.assertEqual(calls[0][1], ["main"])

    def test_gitea_environment_includes_offsite_settings(self):
        service = self.service()
        service.backup_root.mkdir(parents=True)
        service.settings_file.write_text(
            '{"git_offsite_enabled": true, "git_offsite_remote": "https://github.com/user/homecontrol.git", "git_offsite_branch": "main"}',
            encoding="utf-8",
        )

        env = service.gitea_environment()

        self.assertEqual(env["GIT_OFFSITE_ENABLED"], "true")
        self.assertEqual(env["GIT_OFFSITE_REMOTE"], "https://github.com/user/homecontrol.git")
        self.assertEqual(env["GIT_OFFSITE_BRANCH"], "main")


if __name__ == "__main__":
    unittest.main()
