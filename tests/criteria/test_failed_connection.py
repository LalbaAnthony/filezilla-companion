import io
import unittest
from unittest import mock

from filezilla_companion import auth
from filezilla_companion.auth import AuthResult, AuthStatus
from filezilla_companion.criteria.base import Analysis, Remove
from filezilla_companion.criteria.failed_connection import FailedConnectionCriterion
from filezilla_companion.filezilla.server import Server


class FailedConnectionCriterionTest(unittest.TestCase):
    def setUp(self):
        stdout = mock.patch("sys.stdout", new_callable=io.StringIO)
        stdout.start()
        self.addCleanup(stdout.stop)

    def test_proposes_failures_and_reports_untestable_sites(self):
        servers = [
            Server("ok", "ok.example", 22, 1, "u", "p"),
            Server("rejected", "rejected.example", 22, 1, "u", "p"),
            Server("lan", "192.168.1.10", 22, 1, "u", "p"),
            Server("ask", "ask.example", 22, 1, "u", logontype=2),
            Server("gone", "gone.example", 22, 1, "u", "p"),
        ]
        results = {
            "ok": AuthResult(AuthStatus.OK),
            "rejected": AuthResult(AuthStatus.REJECTED),
            "lan": AuthResult(AuthStatus.TIMEOUT),
            "ask": AuthResult(AuthStatus.UNTESTABLE, "the site asks for the password at login"),
            "gone": AuthResult(AuthStatus.REJECTED),
        }

        with mock.patch.object(auth, "check", side_effect=lambda srv, timeout: results[srv.name]) as check:
            findings = FailedConnectionCriterion().evaluate(Analysis(servers))

        self.assertEqual(check.call_count, len(servers))
        self.assertEqual(
            [(finding.title, finding.servers, finding.actions) for finding in findings],
            [
                (
                    "credentials rejected",
                    [servers[1], servers[4]],
                    [Remove(servers[1], "credentials rejected", True), Remove(servers[4], "credentials rejected", True)],
                ),
                ("timed out", [servers[2]], [Remove(servers[2], "timed out (private address)", False)]),
                ("not testable: the site asks for the password at login", [servers[3]], []),
            ],
        )


if __name__ == "__main__":
    unittest.main()
