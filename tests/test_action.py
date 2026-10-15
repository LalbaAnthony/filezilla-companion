import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import pyperclip  # noqa: E402
from action import Action  # noqa: E402
from server import Server  # noqa: E402


def _server(password="secret") -> Server:
    return Server("prod", "example.com", 22, 1, "deploy", password)


class ActionRunTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch("action.subprocess.Popen"),
            mock.patch("action.subprocess.run"),
            mock.patch("action.pyperclip.copy"),
        ]
        self.mocks = [p.start() for p in patches]
        _, self.popen, self.run_, self.copy = self.mocks
        for p in patches:
            self.addCleanup(p.stop)

    def _platform(self, name: str):
        p = mock.patch("action.platform.system", return_value=name)
        p.start()
        self.addCleanup(p.stop)

    def test_windows_interactive_opens_cmd(self):
        self._platform("Windows")
        with mock.patch("utils.find_cmd", return_value=r"C:\Windows\System32\cmd.exe"):
            Action("ssh", "SSH", interactive=True).run(_server())

        self.popen.assert_called_once_with([r"C:\Windows\System32\cmd.exe", "/k", "ssh deploy@example.com -p 22"])
        self.copy.assert_called_once_with("secret")

    def test_windows_keeps_remote_shell_unescaped(self):
        self._platform("Windows")
        with mock.patch("utils.find_cmd", return_value="cmd.exe"):
            Action("x", "X", commands=["uptime"], interactive=True).run(_server())

        self.assertEqual(
            self.popen.call_args.args[0][2],
            'ssh deploy@example.com -p 22 "uptime ; exec $SHELL"',
        )

    def test_posix_interactive_opens_single_terminal(self):
        self._platform("Linux")
        with mock.patch("utils.find_terminal", return_value=["xterm", "-e"]):
            Action("ssh", "SSH", interactive=True).run(_server())

        self.popen.assert_called_once_with(
            ["xterm", "-e", "sh", "-c", 'ssh deploy@example.com -p 22; exec "${SHELL:-/bin/sh}"'],
            start_new_session=True,
        )
        self.run_.assert_not_called()
        self.copy.assert_called_once_with("secret")

    def test_posix_escapes_remote_shell_variable(self):
        self._platform("Linux")
        with mock.patch("utils.find_terminal", return_value=["xterm", "-e"]):
            Action("x", "X", commands=["uptime"], interactive=True).run(_server())

        script = self.popen.call_args.args[0][4]
        self.assertTrue(script.startswith(r'ssh deploy@example.com -p 22 "uptime ; exec \$SHELL"'))

    def test_posix_falls_back_to_current_terminal(self):
        self._platform("Linux")
        with mock.patch("utils.find_terminal", return_value=None):
            Action("ssh", "SSH", interactive=True).run(_server())

        self.popen.assert_not_called()
        self.run_.assert_called_once_with("ssh deploy@example.com -p 22", shell=True)

    def test_clipboard_failure_does_not_abort(self):
        self._platform("Linux")
        self.copy.side_effect = pyperclip.PyperclipException("no clipboard")
        with mock.patch("utils.find_terminal", return_value=["xterm", "-e"]):
            Action("ssh", "SSH", interactive=True).run(_server())

        self.popen.assert_called_once()
        self.assertIn("Password not copied to clipboard: no clipboard", self.mocks[0].getvalue())

    def test_no_clipboard_without_password(self):
        self._platform("Linux")
        with mock.patch("utils.find_terminal", return_value=["xterm", "-e"]):
            Action("ssh", "SSH", interactive=True).run(_server(password=None))

        self.copy.assert_not_called()

    def test_non_interactive_runs_in_place(self):
        for system in ("Windows", "Linux"):
            with self.subTest(system=system), mock.patch("action.platform.system", return_value=system):
                self.run_.reset_mock()
                Action("x", "X", commands=["a", "b"]).run(_server())
                self.run_.assert_called_once_with('ssh deploy@example.com -p 22 "a && b "', shell=True)


if __name__ == "__main__":
    unittest.main()
