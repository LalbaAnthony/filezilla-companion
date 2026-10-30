from typing import List
from filezilla_companion.criteria.base import Criterion
from filezilla_companion.criteria.divergent_passwords import DivergentPasswordsCriterion
from filezilla_companion.criteria.duplicate_names import DuplicateNamesCriterion
from filezilla_companion.criteria.duplicates import DuplicatesCriterion
from filezilla_companion.criteria.failed_connection import FailedConnectionCriterion
from filezilla_companion.criteria.missing_keyfile import MissingKeyfileCriterion
from filezilla_companion.criteria.no_credentials import NoCredentialsCriterion
from filezilla_companion.criteria.private_host import PrivateHostCriterion

# Order of the criteria menu, of the report and of the change list, where a change proposed by several criteria is
# listed under the first one. The failed connection criterion comes before the divergent passwords one, which then
# reuses its credential tests instead of running its own.
CRITERIA: List[Criterion] = [
    DuplicatesCriterion(),
    FailedConnectionCriterion(),
    DivergentPasswordsCriterion(),
    MissingKeyfileCriterion(),
    NoCredentialsCriterion(),
    DuplicateNamesCriterion(),
    PrivateHostCriterion(),
]
