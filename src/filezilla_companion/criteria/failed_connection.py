from typing import Optional
from filezilla_companion.auth import AuthStatus
from filezilla_companion.criteria.base import Action, Analysis, Remove, SiteCriterion
from filezilla_companion.criteria.private_host import is_private_host
from filezilla_companion.filezilla.server import Server

class FailedConnectionCriterion(SiteCriterion):
    slug = "failed-connection"
    label = "Failed connection (logs in with the saved credentials)"

    def prepare(self, analysis: Analysis) -> None:
        analysis.check_credentials(analysis.servers)

    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        result = analysis.auth_result(server)
        return None if result.status == AuthStatus.OK else result.reason

    def propose(self, server: Server, reason: str, analysis: Analysis) -> Optional[Action]:
        if not analysis.auth_result(server).failed:
            # Not testable: reported, but nothing proves the site is broken.
            return None
        if is_private_host(server.host):
            # Such hosts are often only reachable from a given network, so failing from here proves little.
            return Remove(server, f"{reason} (private address)", checked=False)
        return Remove(server, reason, checked=True)
