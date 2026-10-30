import re
import unittest

from filezilla_companion.commands import COMMANDS
from filezilla_companion.commands.connect import ConnectCommand


class RegistryTest(unittest.TestCase):
    def test_slugs_are_unique(self):
        slugs = [command.slug for command in COMMANDS]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_slugs_are_kebab_case_and_labels_set(self):
        for command in COMMANDS:
            with self.subTest(command=type(command).__name__):
                self.assertRegex(command.slug, re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"))
                self.assertTrue(command.label)

    def test_connect_is_preselected(self):
        self.assertIsInstance(COMMANDS[0], ConnectCommand)


if __name__ == "__main__":
    unittest.main()
