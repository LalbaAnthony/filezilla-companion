import unittest
from unittest import mock

from InquirerPy.prompts.checkbox import InquirerPyCheckboxControl
from InquirerPy.prompts.fuzzy import InquirerPyFuzzyControl
from InquirerPy.separator import Separator
from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.criteria import CRITERIA
from filezilla_companion.criteria.base import Remove, Rename
from filezilla_companion.filezilla.server import Server
from filezilla_companion.ssh_keys import PublicKey


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
                "Deploy an SSH key to servers (--deploy-key)",
                "List servers (--list)",
                "Clean up the site manager (--clean)",
                "Import sites from Bitwarden (--import-bitwarden)",
            ],
        )
        self.assertEqual(self.fuzzy.call_args.kwargs["message"], "Select a command:")

    def test_select_key_lists_labels_and_returns_the_pick(self):
        keys = [
            PublicKey("/home/me/.ssh/id_ed25519.pub", "ssh-ed25519", "AAAA", "me@laptop"),
            PublicKey("/home/me/.ssh/id_rsa.pub", "ssh-rsa", "BBBB"),
        ]
        self.fuzzy.return_value.execute.return_value = keys[1]

        self.assertIs(prompts.select_key(keys), keys[1])
        self.assertEqual(
            [choice["name"] for choice in self._choices()],
            ["id_ed25519.pub (ssh-ed25519, me@laptop)", "id_rsa.pub (ssh-rsa)"],
        )
        self.assertEqual(self.fuzzy.call_args.kwargs["message"], "Select a public key:")

    def test_select_servers_is_a_multiselect_keeping_the_server_objects(self):
        servers = [Server("prod", "example.com", 22, 1, "deploy"), Server("prod", "example.com", 22, 1, "deploy")]
        self.fuzzy.return_value.execute.return_value = [servers[1]]

        self.assertEqual(prompts.select_servers(servers), [servers[1]])

        kwargs = self.fuzzy.call_args.kwargs
        self.assertTrue(kwargs["multiselect"])
        # A validator would refuse `enter` on the current line: InquirerPy validates the toggled lines only.
        self.assertNotIn("validate", kwargs)
        control = InquirerPyFuzzyControl(
            choices=kwargs["choices"],
            pointer=">",
            marker="x",
            current_text=lambda: "",
            max_lines=10,
            session_result=None,
            multiselect=True,
            marker_pl=" ",
            match_exact=False,
        )
        # Identity, not equality: copies of a site compare equal, and the command must get the sites it listed.
        for choice, server in zip(control.choices, servers):
            self.assertIs(choice["value"], server)
            self.assertEqual(choice["name"], "prod (deploy@example.com)")
            self.assertFalse(choice["enabled"])


class CheckboxPromptsTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(prompts.inquirer, "checkbox")
        self.checkbox = patch.start()
        self.addCleanup(patch.stop)

    def _processed_choices(self):
        """Run the choices given to the prompt through InquirerPy's own processing, as the real prompt does."""
        control = InquirerPyCheckboxControl(
            choices=self.checkbox.call_args.kwargs["choices"],
            default=None,
            pointer=">",
            enabled_symbol="x",
            disabled_symbol="o",
            session_result=None,
        )
        return control.choices

    def test_select_criteria_checks_every_criterion_and_requires_one(self):
        self.checkbox.return_value.execute.return_value = CRITERIA[:2]

        self.assertEqual(prompts.select_criteria(CRITERIA), CRITERIA[:2])
        choices = self._processed_choices()
        self.assertEqual([choice["name"] for choice in choices], [criterion.label for criterion in CRITERIA])
        self.assertTrue(all(choice["enabled"] for choice in choices))
        for choice, criterion in zip(choices, CRITERIA):
            self.assertIs(choice["value"], criterion)
        validate = self.checkbox.call_args.kwargs["validate"]
        self.assertFalse(validate([]))
        self.assertTrue(validate([CRITERIA[0]]))

    def test_select_actions_keeps_the_action_objects_as_values(self):
        server = Server("prod", "example.com", 22, 1, "deploy")
        remove = Remove(server, "credentials rejected", checked=True)
        rename = Rename(server, "name shared with another site", checked=False, new_name="prod (deploy@example.com)")
        self.checkbox.return_value.execute.return_value = [remove]

        self.assertEqual(prompts.select_actions([("Failed", [remove]), ("Names", [rename])]), [remove])

        separator, remove_choice, _, rename_choice = self._processed_choices()
        self.assertIsInstance(separator["value"], Separator)
        self.assertEqual(separator["name"], "-- Failed --")
        # Identity, not equality: InquirerPy's Choice handling used to return dict copies of these dataclasses.
        self.assertIs(remove_choice["value"], remove)
        self.assertIs(rename_choice["value"], rename)
        self.assertEqual(
            (remove_choice["name"], remove_choice["enabled"]),
            ("Remove prod (deploy@example.com:22): credentials rejected", True),
        )
        self.assertEqual(
            (rename_choice["name"], rename_choice["enabled"]),
            ('Rename prod (deploy@example.com:22) to "prod (deploy@example.com)": name shared with another site', False),
        )


if __name__ == "__main__":
    unittest.main()
