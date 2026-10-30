import subprocess
import unittest
from unittest import mock

from filezilla_companion.filezilla import process


def _completed(returncode: int, stdout: bytes = b"") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess([], returncode, stdout, b"")


class IsRunningTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(process.platform, "system", return_value="Windows"),
            mock.patch.object(process.subprocess, "run"),
        ]
        self.system, self.run = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def test_windows_finds_filezilla_in_tasklist(self):
        self.run.return_value = _completed(0, b'"FileZilla.exe","1234","Console","1","85 000 K"\r\n')

        self.assertTrue(process.is_running())

        argv = self.run.call_args.args[0]
        self.assertEqual(argv[0], "tasklist")
        self.assertIn("IMAGENAME eq filezilla.exe", argv)

    def test_windows_reports_absence_whatever_the_language(self):
        self.run.return_value = _completed(0, "INFO : aucune tâche en service ne correspond.\r\n".encode("cp850"))

        self.assertFalse(process.is_running())

    def test_windows_tasklist_failure_is_unknown(self):
        self.run.return_value = _completed(1)

        self.assertIsNone(process.is_running())

    def test_linux_uses_pgrep_exit_code(self):
        self.system.return_value = "Linux"
        for returncode, expected in ((0, True), (1, False), (2, None)):
            with self.subTest(returncode=returncode):
                self.run.return_value = _completed(returncode)
                self.assertIs(process.is_running(), expected)
        self.assertEqual(self.run.call_args.args[0], ["pgrep", "-x", "filezilla"])

    def test_missing_tool_is_unknown(self):
        for error in (FileNotFoundError("pgrep"), subprocess.TimeoutExpired("pgrep", 10)):
            with self.subTest(error=type(error).__name__):
                self.run.side_effect = error
                self.assertIsNone(process.is_running())


if __name__ == "__main__":
    unittest.main()
