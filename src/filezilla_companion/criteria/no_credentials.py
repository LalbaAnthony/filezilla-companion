from typing import Optional
from filezilla_companion.criteria.base import Analysis, SiteCriterion
from filezilla_companion.filezilla.server import Server

class NoCredentialsCriterion(SiteCriterion):
    slug = "no-credentials"
    label = "No credentials (normal logon without password or key file)"

    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        # The other logon types do without a saved password on purpose (anonymous, ask for password, interactive...).
        if server.logontype not in (None, 1) or server.password or server.uses_keyfile:
            return None
        return "no password or key file saved"
