import io
import unittest
from collections.abc import Hashable
from typing import List, Optional
from unittest import mock

from filezilla_companion import auth
from filezilla_companion.auth import AuthResult, AuthStatus
from filezilla_companion.console import Console
from filezilla_companion.criteria.base import (
    Action, Analysis, Finding, GroupCriterion, Remove, Rename, SiteCriterion, site_label,
)
from filezilla_companion.filezilla.server import Server


class _SameHost(GroupCriterion):
    slug = "same-host"
    label = "Same host"

    def key(self, server: Server) -> Optional[Hashable]:
        return None if server.host == "ignored.example" else server.host

    def describe(self, servers: List[Server]) -> str:
        return servers[0].host

    def resolve(self, servers: List[Server], analysis: Analysis) -> List[Action]:
        return [Remove(srv, "same host", checked=True) for srv in servers[1:]]


class _NoPassword(SiteCriterion):
    slug = "no-password"
    label = "No password"

    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        return None if server.password else f"no password on port {server.port}"


class SiteLabelTest(unittest.TestCase):
    def test_includes_the_port(self):
        self.assertEqual(site_label(Server("prod", "example.com", 2222, 1, "deploy")), "prod (deploy@example.com:2222)")
        self.assertEqual(site_label(Server("", "example.com", 22, 1, "deploy")), "deploy@example.com:22")


class GroupCriterionTest(unittest.TestCase):
    def test_groups_sites_sharing_a_key_in_file_order(self):
        servers = [
            Server("a", "one.example", 22, 1, "u"),
            Server("b", "two.example", 22, 1, "u"),
            Server("c", "one.example", 22, 1, "v"),
            Server("d", "ignored.example", 22, 1, "u"),
            Server("e", "ignored.example", 22, 1, "v"),
        ]

        findings = _SameHost().evaluate(Analysis(servers))

        self.assertEqual(findings, [Finding("one.example", [servers[0], servers[2]], [Remove(servers[2], "same host", True)])])
        self.assertEqual(_SameHost().summary(findings), "1 group")


class SiteCriterionTest(unittest.TestCase):
    def test_groups_matched_sites_by_reason_and_proposes_their_removal(self):
        servers = [
            Server("a", "one.example", 22, 1, "u"),
            Server("b", "two.example", 22, 1, "u", "secret"),
            Server("c", "three.example", 2222, 1, "u"),
            Server("d", "four.example", 22, 1, "u"),
        ]

        findings = _NoPassword().evaluate(Analysis(servers))

        self.assertEqual(
            [(finding.title, finding.servers) for finding in findings],
            [("no password on port 22", [servers[0], servers[3]]), ("no password on port 2222", [servers[2]])],
        )
        self.assertEqual(findings[0].actions, [
            Remove(servers[0], "no password on port 22", True),
            Remove(servers[3], "no password on port 22", True),
        ])
        self.assertEqual(_NoPassword().summary(findings), "3 sites")


class ActionLabelTest(unittest.TestCase):
    def test_labels(self):
        server = Server("prod", "example.com", 22, 1, "deploy")
        self.assertEqual(Remove(server, "timed out", True).label, "Remove prod (deploy@example.com:22): timed out")
        self.assertEqual(
            Rename(server, "shared name", True, "prod (deploy@example.com)").label,
            'Rename prod (deploy@example.com:22) to "prod (deploy@example.com)": shared name',
        )


class AnalysisTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(auth, "check", return_value=AuthResult(AuthStatus.REJECTED)),
            # Progress lines are throttled since the last one printed, possibly by another test.
            mock.patch.object(Console, "_last_progress", 0.0),
        ]
        self.stdout, self.check, _ = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        # Equal on purpose: results must follow the objects, not their value.
        self.servers = [Server("prod", "example.com", 22, 1, "deploy"), Server("prod", "example.com", 22, 1, "deploy")]

    def test_tests_each_site_once_and_shows_progress(self):
        analysis = Analysis(self.servers, auth_workers=3, auth_timeout=4.0)

        analysis.check_credentials(self.servers[:1])
        analysis.check_credentials(self.servers)

        self.assertEqual(self.check.call_count, 2)
        self.assertEqual(self.check.call_args.args[1], 4.0)
        self.assertIn("Testing credentials: 0/1 (0 failed)", self.stdout.getvalue())
        self.assertIn("Testing credentials: 1/1 (1 failed)", self.stdout.getvalue())

    def test_auth_result_tests_an_untested_site(self):
        analysis = Analysis(self.servers)

        self.assertEqual(analysis.auth_result(self.servers[1]), AuthResult(AuthStatus.REJECTED))
        self.assertEqual(analysis.auth_result(self.servers[1]), AuthResult(AuthStatus.REJECTED))

        self.check.assert_called_once()
        self.assertIs(self.check.call_args.args[0], self.servers[1])


if __name__ == "__main__":
    unittest.main()
