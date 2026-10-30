import unittest
from unittest import mock

from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.criteria import CRITERIA
from filezilla_companion.criteria.base import Remove, Rename
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
                "Clean up the site manager (--clean)",
            ],
        )
        self.assertEqual(self.fuzzy.call_args.kwargs["message"], "Select a command:")


class CheckboxPromptsTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(prompts.inquirer, "checkbox")
        self.checkbox = patch.start()
        self.addCleanup(patch.stop)

    def _choices(self):
        return self.checkbox.call_args.kwargs["choices"]

    def test_select_criteria_checks_every_criterion_and_requires_one(self):
        self.checkbox.return_value.execute.return_value = CRITERIA[:2]

        self.assertEqual(prompts.select_criteria(CRITERIA), CRITERIA[:2])
        self.assertEqual(
            [(choice.value, choice.name, choice.enabled) for choice in self._choices()],
            [(criterion, criterion.label, True) for criterion in CRITERIA],
        )
        validate = self.checkbox.call_args.kwargs["validate"]
        self.assertFalse(validate([]))
        self.assertTrue(validate([CRITERIA[0]]))

    def test_select_actions_lists_sections_with_proposed_checks(self):
        server = Server("prod", "example.com", 22, 1, "deploy")
        remove = Remove(server, "credentials rejected", checked=True)
        rename = Rename(server, "name shared with another site", checked=False, new_name="prod (deploy@example.com)")
        self.checkbox.return_value.execute.return_value = [remove]

        self.assertEqual(prompts.select_actions([("Failed", [remove]), ("Names", [rename])]), [remove])
        choices = self._choices()
        self.assertEqual([type(choice) for choice in choices], [Separator, Choice, Separator, Choice])
        self.assertEqual(str(choices[0]), "-- Failed --")
        self.assertEqual(
            (choices[1].value, choices[1].name, choices[1].enabled),
            (remove, "Remove prod (deploy@example.com:22): credentials rejected", True),
        )
        self.assertEqual(
            (choices[3].value, choices[3].name, choices[3].enabled),
            (rename, 'Rename prod (deploy@example.com:22) to "prod (deploy@example.com)": name shared with another site', False),
        )


if __name__ == "__main__":
    unittest.main()
