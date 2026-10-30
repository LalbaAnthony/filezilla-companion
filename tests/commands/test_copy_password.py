import io
import unittest
from unittest import mock

from filezilla_companion import clipboard, prompts
from filezilla_companion.commands.copy_password import CopyPasswordCommand
from filezilla_companion.filezilla.server import Server
from tests.helpers import make_context


class CopyPasswordCommandTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(prompts, "select_server"),
            mock.patch.object(clipboard, "copy"),
        ]
        self.stdout, self.select_server, self.copy = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.sftp = Server("prod", "example.com", 22, 1, "deploy", "secret")
        self.ftp = Server("files", "ftp.example.com", 21, 0, "uploader", "ftp-secret")
        self.no_password = Server("lan", "192.168.1.10", 22, 1, "dev")

    def test_offers_only_servers_with_password_ftp_included(self):
        self.select_server.return_value = self.ftp

        self.assertEqual(CopyPasswordCommand().run(make_context([self.sftp, self.no_password, self.ftp])), 0)

        self.select_server.assert_called_once_with([self.sftp, self.ftp])
        self.copy.assert_called_once_with("ftp-secret")
        self.assertIn("Password of files (uploader@ftp.example.com) copied to clipboard.", self.stdout.getvalue())

    def test_no_server_with_password_aborts_before_the_menu(self):
        self.assertEqual(CopyPasswordCommand().run(make_context([self.no_password])), 1)

        self.select_server.assert_not_called()
        self.assertIn("No server with a saved password", self.stdout.getvalue())

    def test_clipboard_failure_is_an_error(self):
        self.select_server.return_value = self.sftp
        self.copy.side_effect = clipboard.ClipboardError("no clipboard")

        self.assertEqual(CopyPasswordCommand().run(make_context([self.sftp])), 1)

        self.assertIn("Cannot copy the password to the clipboard: no clipboard", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
