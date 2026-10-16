import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pyperclip  # noqa: E402
import ssh  # noqa: E402
from server import Server  # noqa: E402


def _server(password="secret") -> Server:
    return Server("prod", "example.com", 22, 1, "deploy", password)


class ConnectTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("ssh.subprocess.Popen"),
            mock.patch("ssh.subprocess.run"),
            mock.patch("ssh.pyperclip.copy"),
        ]
        self.stdout, self.popen, self.run_, self.copy = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _platform(self, name: str):
        p = mock.patch("ssh.platform.system", return_value=name)
        p.start()
        self.addCleanup(p.stop)

    def test_windows_opens_cmd(self):
        self._platform("Windows")
        with mock.patch("ssh.find_cmd", return_value=r"C:\Windows\System32\cmd.exe"):
            ssh.connect(_server())

        self.popen.assert_called_once_with([r"C:\Windows\System32\cmd.exe", "/k", "ssh deploy@example.com -p 22"])
        self.run_.assert_not_called()
        self.copy.assert_called_once_with("secret")

    def test_windows_without_cmd_raises(self):
        self._platform("Windows")
        with mock.patch("ssh.find_cmd", return_value=None), self.assertRaises(FileNotFoundError):
            ssh.connect(_server())

        self.popen.assert_not_called()

    def test_posix_opens_single_terminal(self):
        self._platform("Linux")
        with mock.patch("ssh.find_terminal", return_value=["xterm", "-e"]):
            ssh.connect(_server())

        self.popen.assert_called_once_with(
            ["xterm", "-e", "sh", "-c", 'ssh deploy@example.com -p 22; exec "${SHELL:-/bin/sh}"'],
            start_new_session=True,
        )
        self.run_.assert_not_called()
        self.copy.assert_called_once_with("secret")

    def test_posix_falls_back_to_current_terminal(self):
        self._platform("Linux")
        with mock.patch("ssh.find_terminal", return_value=None):
            ssh.connect(_server())

        self.popen.assert_not_called()
        self.run_.assert_called_once_with("ssh deploy@example.com -p 22", shell=True)
        self.assertIn("No graphical terminal available", self.stdout.getvalue())

    def test_clipboard_failure_does_not_abort(self):
        self._platform("Linux")
        self.copy.side_effect = pyperclip.PyperclipException("no clipboard")
        with mock.patch("ssh.find_terminal", return_value=["xterm", "-e"]):
            ssh.connect(_server())

        self.popen.assert_called_once()
        self.assertIn("Password not copied to clipboard: no clipboard", self.stdout.getvalue())

    def test_no_clipboard_without_password(self):
        self._platform("Linux")
        with mock.patch("ssh.find_terminal", return_value=["xterm", "-e"]):
            ssh.connect(_server(password=None))

        self.copy.assert_not_called()


class FindTerminalTest(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(os.environ, {"DISPLAY": ":0"})
        self.env_patch.start()
        os.environ.pop("WAYLAND_DISPLAY", None)

    def tearDown(self):
        self.env_patch.stop()

    def test_none_without_display(self):
        os.environ.pop("DISPLAY")
        with mock.patch("ssh.shutil.which", return_value="/usr/bin/xterm"):
            self.assertIsNone(ssh.find_terminal())

    def test_wayland_display_is_enough(self):
        os.environ.pop("DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        with mock.patch("ssh.shutil.which", side_effect=lambda name: name == "gnome-terminal" or None):
            self.assertEqual(ssh.find_terminal(), ["gnome-terminal", "--"])

    def test_prefers_debian_default_terminal(self):
        with mock.patch("ssh.shutil.which", return_value="/usr/bin/found"):
            self.assertEqual(ssh.find_terminal(), ["x-terminal-emulator", "-e"])

    def test_falls_back_to_installed_emulator(self):
        with mock.patch("ssh.shutil.which", side_effect=lambda name: name == "xterm" or None):
            self.assertEqual(ssh.find_terminal(), ["xterm", "-e"])

    def test_none_when_no_emulator_installed(self):
        with mock.patch("ssh.shutil.which", return_value=None):
            self.assertIsNone(ssh.find_terminal())

    def test_returns_a_copy(self):
        with mock.patch("ssh.shutil.which", return_value="/usr/bin/found"):
            ssh.find_terminal().append("mutated")
            self.assertEqual(ssh.find_terminal(), ["x-terminal-emulator", "-e"])


if __name__ == "__main__":
    unittest.main()
