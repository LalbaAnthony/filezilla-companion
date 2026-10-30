import unittest
from unittest import mock

from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.filezilla.server import Server


class PromptsTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(prompts.inquirer, "fuzzy")
        self.fuzzy = patch.start()
        self.addCleanup(patch.stop)

    def _choices(self):
        return self.fuzzy.call_args.kwargs["choices"]

    def test_select_server_lists_labels_and_returns_the_pick(self):
        servers = [Server("prod", "example.com", 22, 1, "deploy"), Server("", "192.168.1.10", 22, 1, "dev")]
        self.fuzzy.return_value.execute.return_value = servers[1]

        self.assertIs(prompts.select_server(servers), servers[1])
        self.assertEqual(
            self._choices(),
            [
                {"name": "prod (deploy@example.com)", "value": servers[0]},
                {"name": "dev@192.168.1.10", "value": servers[1]},
            ],
        )
        self.assertEqual(self.fuzzy.call_args.kwargs["message"], "Select a server:")

    def test_select_command_shows_flags_in_registry_order(self):
        self.fuzzy.return_value.execute.return_value = COMMANDS[0]

        self.assertIs(prompts.select_command(COMMANDS), COMMANDS[0])
        self.assertEqual(
            [choice["name"] for choice in self._choices()],
            [
                "Connect to a server (--connect)",
                "Copy a server password (--copy-password)",
                "List servers (--list)",
            ],
        )
        self.assertEqual(self.fuzzy.call_args.kwargs["message"], "Select a command:")


if __name__ == "__main__":
    unittest.main()
