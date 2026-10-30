import json
import subprocess
import unittest
from unittest import mock

from filezilla_companion import bitwarden


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


class BitwardenTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(bitwarden.subprocess, "run")
        self.run = patch.start()
        self.addCleanup(patch.stop)

    def test_find_bw_looks_in_path(self):
        with mock.patch.object(bitwarden.shutil, "which", return_value="/usr/bin/bw") as which:
            self.assertEqual(bitwarden.find_bw(), "/usr/bin/bw")

        which.assert_called_once_with("bw")

    def test_status_runs_bw_without_prompts(self):
        self.run.return_value = _completed('{"serverUrl": null, "status": "unlocked"}')

        self.assertEqual(bitwarden.status("bw"), "unlocked")

        self.run.assert_called_once_with(
            ["bw", "--nointeraction", "status"],
            capture_output=True,
            encoding="utf-8",
            timeout=bitwarden.TIMEOUT,
        )

    def test_status_rejects_unexpected_output(self):
        for stdout, message in (("[]", "unexpected result"), ("? Master password:", "invalid JSON")):
            with self.subTest(stdout=stdout):
                self.run.return_value = _completed(stdout)
                with self.assertRaisesRegex(bitwarden.BitwardenError, message):
                    bitwarden.status("bw")

    def test_sync(self):
        self.run.return_value = _completed("Syncing complete.")

        bitwarden.sync("bw")

        self.assertEqual(self.run.call_args.args[0], ["bw", "--nointeraction", "sync"])

    def test_failure_reports_stderr_or_exit_code(self):
        for stderr, message in (("You are not logged in.\n", "bw sync failed: You are not logged in."), ("", "bw sync failed: exit code 1")):
            with self.subTest(stderr=stderr):
                self.run.return_value = _completed(returncode=1, stderr=stderr)
                with self.assertRaises(bitwarden.BitwardenError) as raised:
                    bitwarden.sync("bw")
                self.assertEqual(str(raised.exception), message)

    def test_run_errors_are_wrapped(self):
        for error in (
            subprocess.TimeoutExpired("bw", bitwarden.TIMEOUT),
            FileNotFoundError("bw"),
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
        ):
            with self.subTest(error=type(error).__name__):
                self.run.side_effect = error
                with self.assertRaises(bitwarden.BitwardenError) as raised:
                    bitwarden.sync("bw")
                self.assertIs(raised.exception.__cause__, error)

    def test_list_logins_reads_login_items_only(self):
        self.run.return_value = _completed(json.dumps([
            {
                "id": "a1",
                "type": 1,
                "name": "prod",
                "creationDate": "2024-05-13T08:46:30.123Z",
                "fields": [
                    {"name": " KeyFile ", "value": " ~/.ssh/id ", "type": 0},
                    {"name": "keyfile", "value": "/other", "type": 0},
                    {"name": "protocol", "value": "", "type": 0},
                    {"name": "linked", "value": None, "type": 3},
                ],
                "login": {
                    "username": "deploy",
                    "password": " p@ss ",
                    "uris": [{"match": None, "uri": " sftp://example.com "}, {"match": None, "uri": None}],
                },
            },
            {"id": "n1", "type": 2, "name": "note", "secureNote": {"type": 0}},
            {"id": "b2", "type": 1, "name": "empty", "login": None},
        ]))

        self.assertEqual(bitwarden.list_logins("bw"), [
            bitwarden.Login(
                "a1", "prod", "2024-05-13T08:46:30.123Z", "deploy", " p@ss ", ["sftp://example.com"],
                {"keyfile": "~/.ssh/id"},
            ),
            bitwarden.Login("b2", "empty", ""),
        ])
        self.assertEqual(self.run.call_args.args[0], ["bw", "--nointeraction", "list", "items"])

    def test_list_logins_rejects_unexpected_output(self):
        for stdout in ('{"object": "list"}', "[1]", '[{"type": 1, "login": "deploy"}]'):
            with self.subTest(stdout=stdout):
                self.run.return_value = _completed(stdout)
                with self.assertRaises(bitwarden.BitwardenError):
                    bitwarden.list_logins("bw")


if __name__ == "__main__":
    unittest.main()
