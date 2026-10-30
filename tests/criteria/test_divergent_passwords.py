import io
import unittest
from unittest import mock

from filezilla_companion import auth
from filezilla_companion.auth import AuthResult, AuthStatus
from filezilla_companion.criteria.base import Analysis, Remove
from filezilla_companion.criteria.divergent_passwords import DivergentPasswordsCriterion
from filezilla_companion.filezilla.server import Server


class DivergentPasswordsCriterionTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(auth, "check"),
        ]
        _, self.check = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _evaluate(self, servers, results):
        self.check.side_effect = lambda srv, timeout: results[srv.password]
        return DivergentPasswordsCriterion().evaluate(Analysis(servers))

    def test_tests_only_grouped_sites_and_proposes_the_failing_ones(self):
        servers = [
            Server("new", "example.com", 22, 1, "deploy", "new"),
            Server("old", "EXAMPLE.com", 22, 1, "deploy", "old"),
            Server("same", "example.com", 22, 1, "deploy", "new"),
            Server("alone", "other.example", 22, 1, "deploy", "x"),
            Server("other port", "example.com", 2222, 1, "deploy", "y"),
            Server("key", "example.com", 22, 1, "deploy", None, "key", logontype=5),
        ]

        [finding] = self._evaluate(servers, {"new": AuthResult(AuthStatus.OK), "old": AuthResult(AuthStatus.REJECTED)})

        self.assertEqual(finding.servers, servers[:3])
        self.assertEqual(self.check.call_count, 3)
        self.assertEqual(finding.actions, [
            Remove(servers[0], "credentials accepted", False),
            Remove(servers[1], "credentials rejected", True),
            Remove(servers[2], "credentials accepted", False),
        ])
        self.assertTrue(finding.keep_one)

    def test_checks_nothing_when_the_logins_do_not_tell(self):
        servers = [Server("a", "example.com", 22, 1, "deploy", "a"), Server("b", "example.com", 22, 1, "deploy", "b")]
        cases = [
            {"a": AuthResult(AuthStatus.REJECTED), "b": AuthResult(AuthStatus.TIMEOUT)},
            {"a": AuthResult(AuthStatus.OK), "b": AuthResult(AuthStatus.OK)},
        ]
        for results in cases:
            with self.subTest(results=results):
                [finding] = self._evaluate(servers, results)
                self.assertEqual([action.checked for action in finding.actions], [False, False])

    def test_same_password_is_not_divergent(self):
        servers = [Server("a", "example.com", 22, 1, "deploy", "p"), Server("b", "example.com", 22, 1, "deploy", "p")]

        self.assertEqual(self._evaluate(servers, {}), [])
        self.check.assert_not_called()


if __name__ == "__main__":
    unittest.main()
