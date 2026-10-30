import io
import unittest
from unittest import mock

from colorama import Fore, Style
from filezilla_companion.commands.list_servers import ListServersCommand
from filezilla_companion.filezilla.server import Server
from tests.helpers import make_context


class ListServersCommandTest(unittest.TestCase):
    def test_prints_every_server_with_its_port(self):
        servers = [
            Server("prod", "example.com", 2222, 1, "deploy", "secret"),
            Server("files", "ftp.example.com", 21, 0, "uploader"),
            Server("", "192.168.1.10", 22, 1, "dev"),
        ]

        with mock.patch("sys.stdout", new_callable=io.StringIO) as out:
            self.assertEqual(ListServersCommand().run(make_context(servers)), 0)

        self.assertEqual(
            out.getvalue(),
            "".join(
                f"{Fore.WHITE}{line}{Style.RESET_ALL}\n"
                for line in (
                    "prod (deploy@example.com:2222)",
                    "files (uploader@ftp.example.com:21)",
                    "dev@192.168.1.10:22",
                )
            ),
        )


if __name__ == "__main__":
    unittest.main()
