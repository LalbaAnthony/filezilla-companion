import re
import unittest

from filezilla_companion.criteria import CRITERIA
from filezilla_companion.criteria.divergent_passwords import DivergentPasswordsCriterion
from filezilla_companion.criteria.failed_connection import FailedConnectionCriterion


def _index(criterion_type: type) -> int:
    return next(i for i, criterion in enumerate(CRITERIA) if isinstance(criterion, criterion_type))


class RegistryTest(unittest.TestCase):
    def test_slugs_are_unique(self):
        slugs = [criterion.slug for criterion in CRITERIA]
        self.assertEqual(len(slugs), len(set(slugs)))

    def test_slugs_are_kebab_case_and_labels_set(self):
        for criterion in CRITERIA:
            with self.subTest(criterion=type(criterion).__name__):
                self.assertRegex(criterion.slug, re.compile(r"^[a-z][a-z0-9]*(-[a-z0-9]+)*$"))
                self.assertTrue(criterion.label)

    def test_failed_connection_runs_before_divergent_passwords(self):
        # Divergent passwords then reuse the credential tests instead of running a second pass.
        self.assertLess(_index(FailedConnectionCriterion), _index(DivergentPasswordsCriterion))


if __name__ == "__main__":
    unittest.main()
