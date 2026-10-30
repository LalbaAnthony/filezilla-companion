from collections.abc import Hashable
from typing import List, Optional
from filezilla_companion.auth import AuthStatus
from filezilla_companion.criteria.base import Action, Analysis, GroupCriterion, Remove
from filezilla_companion.filezilla.server import Server

class DivergentPasswordsCriterion(GroupCriterion):
    slug = "divergent-passwords"
    label = "Divergent passwords (same host, user and port)"
    keep_one = True

    def key(self, server: Server) -> Optional[Hashable]:
        # Key file sites do not log in with their password.
        if server.uses_keyfile:
            return None
        return (server.normalized_host, server.user, server.port)

    def is_group(self, servers: List[Server]) -> bool:
        return len({srv.password for srv in servers}) > 1

    def describe(self, servers: List[Server]) -> str:
        return f"{servers[0].user}@{servers[0].host}:{servers[0].port}"

    def prepare(self, servers: List[Server], analysis: Analysis) -> None:
        analysis.check_credentials(servers)

    def resolve(self, servers: List[Server], analysis: Analysis) -> List[Action]:
        """Propose to remove the sites whose login fails, checked only when another site of the group logs in."""
        results = [analysis.auth_result(srv) for srv in servers]
        # Only a mix of accepted and failed logins tells which password is outdated.
        decisive = any(result.status == AuthStatus.OK for result in results) and any(result.failed for result in results)
        return [
            Remove(srv, result.reason, checked=decisive and result.failed)
            for srv, result in zip(servers, results)
        ]
