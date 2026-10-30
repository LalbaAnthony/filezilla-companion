import unittest

from filezilla_companion.criteria.base import Analysis, Remove
from filezilla_companion.criteria.duplicates import DuplicatesCriterion
from filezilla_companion.filezilla.server import Server


class DuplicatesCriterionTest(unittest.TestCase):
    def test_groups_same_host_user_password_port_and_key_file(self):
        servers = [
            Server("a", "Example.com ", 22, 1, "deploy", "secret"),
            Server("b", "example.com", 22, 0, "deploy", "secret"),
            Server("other port", "example.com", 2222, 1, "deploy", "secret"),
            Server("other password", "example.com", 22, 1, "deploy", "other"),
            Server("other user", "example.com", 22, 1, "root", "secret"),
            Server("other key", "example.com", 22, 1, "deploy", "secret", "key"),
        ]

        findings = DuplicatesCriterion().evaluate(Analysis(servers))

        self.assertEqual([finding.servers for finding in findings], [servers[:2]])
        self.assertEqual(findings[0].title, "deploy@Example.com :22")
        self.assertTrue(findings[0].keep_one)

    def test_keeps_the_most_complete_copy(self):
        servers = [
            Server("a", "example.com", 22, 1, "deploy", "secret"),
            Server("b", "example.com", 22, 1, "deploy", "secret", comments="prod", remote_dir="1 0 3 var"),
            Server("c", "example.com", 22, 1, "deploy", "secret", colour=1),
        ]

        [finding] = DuplicatesCriterion().evaluate(Analysis(servers))

        self.assertEqual(finding.actions, [
            Remove(servers[0], 'copy of "b"', checked=True),
            Remove(servers[1], "most complete copy, kept", checked=False),
            Remove(servers[2], 'copy of "b"', checked=True),
        ])

    def test_keeps_the_first_copy_on_a_tie(self):
        servers = [Server("a", "example.com", 22, 1, "deploy"), Server("b", "example.com", 22, 1, "deploy")]

        [finding] = DuplicatesCriterion().evaluate(Analysis(servers))

        self.assertEqual([action.checked for action in finding.actions], [False, True])


if __name__ == "__main__":
    unittest.main()
