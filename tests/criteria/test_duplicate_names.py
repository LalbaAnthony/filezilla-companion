import unittest

from filezilla_companion.criteria.base import Analysis, Rename
from filezilla_companion.criteria.duplicate_names import DuplicateNamesCriterion
from filezilla_companion.filezilla.server import Server


def _renames(findings):
    return [(action.server.host, action.server.port, action.new_name) for finding in findings for action in finding.actions]


class DuplicateNamesCriterionTest(unittest.TestCase):
    def test_appends_user_and_host_to_each_name(self):
        servers = [
            Server("prod", "a.example", 22, 1, "deploy"),
            Server("prod", "b.example", 22, 1, "deploy"),
            Server("staging", "a.example", 22, 1, "deploy"),
        ]

        findings = DuplicateNamesCriterion().evaluate(Analysis(servers))

        self.assertEqual([(finding.title, finding.servers) for finding in findings], [('"prod"', servers[:2])])
        self.assertEqual(findings[0].actions[0], Rename(servers[0], "name shared with another site", True, "prod (deploy@a.example)"))
        self.assertEqual(_renames(findings), [("a.example", 22, "prod (deploy@a.example)"), ("b.example", 22, "prod (deploy@b.example)")])

    def test_adds_the_port_only_where_needed(self):
        servers = [
            Server("prod", "a.example", 22, 1, "deploy"),
            Server("prod", "a.example", 2222, 1, "deploy"),
            Server("prod", "b.example", 22, 1, "deploy"),
        ]

        findings = DuplicateNamesCriterion().evaluate(Analysis(servers))

        self.assertEqual(_renames(findings), [
            ("a.example", 22, "prod (deploy@a.example:22)"),
            ("a.example", 2222, "prod (deploy@a.example:2222)"),
            ("b.example", 22, "prod (deploy@b.example)"),
        ])

    def test_avoids_names_already_taken(self):
        servers = [
            Server("prod", "a.example", 22, 1, "deploy"),
            Server("prod", "b.example", 22, 1, "deploy"),
            Server("prod (deploy@a.example)", "c.example", 22, 1, "deploy"),
        ]

        findings = DuplicateNamesCriterion().evaluate(Analysis(servers))

        self.assertEqual(_renames(findings), [
            ("a.example", 22, "prod (deploy@a.example:22)"),
            ("b.example", 22, "prod (deploy@b.example)"),
        ])

    def test_leaves_copies_to_the_duplicates_criteria(self):
        copies = [Server("prod", "a.example", 22, 1, "deploy"), Server("prod", "a.example", 22, 1, "deploy")]
        self.assertEqual(DuplicateNamesCriterion().evaluate(Analysis(copies)), [])

        servers = copies + [Server("prod", "b.example", 22, 1, "deploy")]
        findings = DuplicateNamesCriterion().evaluate(Analysis(servers))
        # The copies cannot be told apart by their address: only the third site is renamed.
        self.assertEqual(_renames(findings), [("b.example", 22, "prod (deploy@b.example)")])


if __name__ == "__main__":
    unittest.main()
