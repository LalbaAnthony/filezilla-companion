import io
import os
import unittest
from unittest import mock

from filezilla_companion import terminal

_COMMAND = "ssh deploy@example.com -p 22"


class OpenInTerminalTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(terminal.subprocess, "Popen"),
            mock.patch.object(terminal.subprocess, "run"),
        ]
        self.stdout, self.popen, self.run_ = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _platform(self, name: str):
        p = mock.patch.object(terminal.platform, "system", return_value=name)
        p.start()
        self.addCleanup(p.stop)

    def test_windows_opens_cmd(self):
        self._platform("Windows")
        with mock.patch.object(terminal, "find_cmd", return_value=r"C:\Windows\System32\cmd.exe"):
            terminal.open_in_terminal(_COMMAND)

        self.popen.assert_called_once_with([r"C:\Windows\System32\cmd.exe", "/k", _COMMAND])
        self.run_.assert_not_called()

    def test_windows_without_cmd_raises(self):
        self._platform("Windows")
        with mock.patch.object(terminal, "find_cmd", return_value=None), self.assertRaises(FileNotFoundError):
            terminal.open_in_terminal(_COMMAND)

        self.popen.assert_not_called()

    def test_posix_opens_single_terminal(self):
        self._platform("Linux")
        with mock.patch.object(terminal, "find_terminal", return_value=["xterm", "-e"]):
            terminal.open_in_terminal(_COMMAND)

        self.popen.assert_called_once_with(
            ["xterm", "-e", "sh", "-c", f'{_COMMAND}; exec "${{SHELL:-/bin/sh}}"'],
            start_new_session=True,
        )
        self.run_.assert_not_called()

    def test_posix_falls_back_to_current_terminal(self):
        self._platform("Linux")
        with mock.patch.object(terminal, "find_terminal", return_value=None):
            terminal.open_in_terminal(_COMMAND)

        self.popen.assert_not_called()
        self.run_.assert_called_once_with(_COMMAND, shell=True)
        self.assertIn("No graphical terminal available", self.stdout.getvalue())


class FindTerminalTest(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(os.environ, {"DISPLAY": ":0"})
        self.env_patch.start()
        os.environ.pop("WAYLAND_DISPLAY", None)

    def tearDown(self):
        self.env_patch.stop()

    def test_none_without_display(self):
        os.environ.pop("DISPLAY")
        with mock.patch.object(terminal.shutil, "which", return_value="/usr/bin/xterm"):
            self.assertIsNone(terminal.find_terminal())

    def test_wayland_display_is_enough(self):
        os.environ.pop("DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        with mock.patch.object(terminal.shutil, "which", side_effect=lambda name: name == "gnome-terminal" or None):
            self.assertEqual(terminal.find_terminal(), ["gnome-terminal", "--"])

    def test_prefers_debian_default_terminal(self):
        with mock.patch.object(terminal.shutil, "which", return_value="/usr/bin/found"):
            self.assertEqual(terminal.find_terminal(), ["x-terminal-emulator", "-e"])

    def test_falls_back_to_installed_emulator(self):
        with mock.patch.object(terminal.shutil, "which", side_effect=lambda name: name == "xterm" or None):
            self.assertEqual(terminal.find_terminal(), ["xterm", "-e"])

    def test_none_when_no_emulator_installed(self):
        with mock.patch.object(terminal.shutil, "which", return_value=None):
            self.assertIsNone(terminal.find_terminal())

    def test_returns_a_copy(self):
        with mock.patch.object(terminal.shutil, "which", return_value="/usr/bin/found"):
            terminal.find_terminal().append("mutated")
            self.assertEqual(terminal.find_terminal(), ["x-terminal-emulator", "-e"])


if __name__ == "__main__":
    unittest.main()
