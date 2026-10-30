import os
from typing import Optional
from filezilla_companion.criteria.base import Analysis, SiteCriterion
from filezilla_companion.filezilla.server import Server

class MissingKeyfileCriterion(SiteCriterion):
    slug = "missing-keyfile"
    label = "Missing key file"

    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        if not server.uses_keyfile:
            return None
        if not server.keyfile:
            return "no key file set"
        if not os.path.isfile(server.keyfile):
            return "key file not found"
        return None
