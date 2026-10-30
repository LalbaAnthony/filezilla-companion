import unittest

from filezilla_companion.criteria.base import Analysis
from filezilla_companion.criteria.private_host import PrivateHostCriterion, is_private_host
from filezilla_companion.filezilla.server import Server


class IsPrivateHostTest(unittest.TestCase):
    def test_private_addresses(self):
        for host in ("10.0.0.1", "172.16.4.2", "192.168.1.10", "127.0.0.1", "169.254.1.1", "::1", "fd00::1", "localhost", " LocalHost "):
            with self.subTest(host=host):
                self.assertTrue(is_private_host(host))

    def test_public_addresses_and_host_names(self):
        for host in ("8.8.8.8", "172.32.0.1", "2001:4860::8888", "example.com", "intranet.local"):
            with self.subTest(host=host):
                self.assertFalse(is_private_host(host))


class PrivateHostCriterionTest(unittest.TestCase):
    def test_reports_without_proposing_changes(self):
        servers = [Server("lan", "192.168.1.10", 22, 1, "u"), Server("prod", "example.com", 22, 1, "u")]

        [finding] = PrivateHostCriterion().evaluate(Analysis(servers))

        self.assertEqual((finding.title, finding.servers, finding.actions), ("private address", servers[:1], []))


if __name__ == "__main__":
    unittest.main()
