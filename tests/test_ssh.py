import io
import unittest
from unittest import mock

from filezilla_companion import clipboard, ssh, terminal
from filezilla_companion.filezilla.server import Server


def _server(password="secret") -> Server:
    return Server("prod", "example.com", 22, 1, "deploy", password)


class ConnectTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(terminal, "open_in_terminal"),
            mock.patch.object(clipboard, "copy"),
        ]
        self.stdout, self.open_in_terminal, self.copy = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def test_copies_password_before_opening_terminal(self):
        calls = mock.Mock()
        calls.attach_mock(self.copy, "copy")
        calls.attach_mock(self.open_in_terminal, "open_in_terminal")

        ssh.connect(_server())

        self.assertEqual(
            calls.mock_calls,
            [mock.call.copy("secret"), mock.call.open_in_terminal("ssh deploy@example.com -p 22")],
        )
        self.assertIn("Running: ssh deploy@example.com -p 22", self.stdout.getvalue())
        self.assertIn("Password copied to clipboard.", self.stdout.getvalue())

    def test_clipboard_failure_does_not_abort(self):
        self.copy.side_effect = clipboard.ClipboardError("no clipboard")

        ssh.connect(_server())

        self.open_in_terminal.assert_called_once()
        self.assertIn("Password not copied to clipboard: no clipboard", self.stdout.getvalue())

    def test_no_clipboard_without_password(self):
        ssh.connect(_server(password=None))

        self.copy.assert_not_called()
        self.open_in_terminal.assert_called_once()

    def test_terminal_failure_propagates(self):
        self.open_in_terminal.side_effect = FileNotFoundError("cmd.exe not found.")

        with self.assertRaises(FileNotFoundError):
            ssh.connect(_server())


if __name__ == "__main__":
    unittest.main()
