import os
import tempfile
import unittest

from filezilla_companion.criteria.base import Analysis, Remove
from filezilla_companion.criteria.missing_keyfile import MissingKeyfileCriterion
from filezilla_companion.filezilla.server import Server


class MissingKeyfileCriterionTest(unittest.TestCase):
    def test_flags_key_logons_whose_file_is_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            present = os.path.join(tmp, "id_ed25519")
            with open(present, "w", encoding="utf-8"):
                pass
            servers = [
                Server("present", "example.com", 22, 1, "u", keyfile=present, logontype=5),
                Server("gone", "example.com", 22, 1, "u", keyfile=os.path.join(tmp, "gone"), logontype=5),
                Server("unset", "example.com", 22, 1, "u", logontype=5),
                Server("ignored", "example.com", 22, 1, "u", "p", os.path.join(tmp, "gone"), logontype=1),
            ]

            findings = MissingKeyfileCriterion().evaluate(Analysis(servers))

        self.assertEqual(
            [(finding.title, finding.actions) for finding in findings],
            [
                ("key file not found", [Remove(servers[1], "key file not found", True)]),
                ("no key file set", [Remove(servers[2], "no key file set", True)]),
            ],
        )


if __name__ == "__main__":
    unittest.main()
