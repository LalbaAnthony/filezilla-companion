import io
import unittest
from unittest import mock

from filezilla_companion import prompts, ssh
from filezilla_companion.commands.base import Context
from filezilla_companion.commands.connect import ConnectCommand
from filezilla_companion.filezilla.server import Server


def _server() -> Server:
    return Server("prod", "example.com", 22, 1, "deploy", "secret")


class ConnectCommandTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(ssh, "find_ssh", return_value="/usr/bin/ssh"),
            mock.patch.object(ssh, "ssh_is_functional", return_value=True),
            mock.patch.object(ssh, "connect"),
            mock.patch.object(prompts, "select_server"),
        ]
        self.stdout, self.find_ssh, self.ssh_is_functional, self.connect, self.select_server = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _run(self, server: Server) -> int:
        self.select_server.return_value = server
        return ConnectCommand().run(Context([server]))

    def test_connects_to_the_selected_server(self):
        server = _server()

        self.assertEqual(self._run(server), 0)

        self.select_server.assert_called_once_with([server])
        self.connect.assert_called_once_with(server)

    def test_missing_ssh_aborts_before_the_menu(self):
        self.find_ssh.return_value = None

        self.assertEqual(self._run(_server()), 1)

        self.select_server.assert_not_called()
        self.assertIn("SSH client is not installed or not found in PATH.", self.stdout.getvalue())

    def test_broken_ssh_aborts_before_the_menu(self):
        self.ssh_is_functional.return_value = False

        self.assertEqual(self._run(_server()), 1)

        self.select_server.assert_not_called()
        self.assertIn("SSH client is not installed or not found in PATH.", self.stdout.getvalue())

    def test_defaults_missing_attributes(self):
        server = Server("prod", "example.com", 0, 0, "deploy")

        self.assertEqual(self._run(server), 0)

        self.assertIn("Defaulting missing attributes: port, protocol", self.stdout.getvalue())
        self.assertEqual((server.port, server.protocol), (22, 1))
        self.connect.assert_called_once_with(server)

    def test_rejects_ftp_server(self):
        self.assertEqual(self._run(Server("files", "example.com", 21, 1, "deploy")), 1)

        self.assertIn("Cannot connect to FTP servers.", self.stdout.getvalue())
        self.connect.assert_not_called()

    def test_rejects_server_without_user(self):
        self.assertEqual(self._run(Server("prod", "example.com", 22, 1, "")), 1)

        self.assertIn("Cannot connect to the server with the provided details.", self.stdout.getvalue())
        self.connect.assert_not_called()

    def test_session_launch_failure_is_reported(self):
        self.connect.side_effect = FileNotFoundError("cmd.exe not found.")

        self.assertEqual(self._run(_server()), 1)

        self.assertIn("Cannot open the SSH session: cmd.exe not found.", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
