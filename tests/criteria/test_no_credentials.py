import unittest

from filezilla_companion.criteria.base import Analysis, Remove
from filezilla_companion.criteria.no_credentials import NoCredentialsCriterion
from filezilla_companion.filezilla.server import Server


class NoCredentialsCriterionTest(unittest.TestCase):
    def test_flags_normal_logons_without_password_or_key_file(self):
        servers = [
            Server("empty", "example.com", 22, 1, "u", logontype=1),
            Server("password", "example.com", 22, 1, "u", "p", logontype=1),
            Server("key", "example.com", 22, 1, "u", keyfile="key", logontype=5),
            Server("ignored key", "example.com", 22, 1, "u", keyfile="key", logontype=1),
            Server("ask", "example.com", 22, 1, "u", logontype=2),
            Server("anonymous", "example.com", 21, 0, "anonymous", logontype=0),
            Server("no logon type", "example.com", 22, 1, "u"),
        ]

        [finding] = NoCredentialsCriterion().evaluate(Analysis(servers))

        self.assertEqual(finding.servers, [servers[0], servers[3], servers[6]])
        self.assertEqual(finding.actions[0], Remove(servers[0], "no password or key file saved", True))


if __name__ == "__main__":
    unittest.main()
