from collections.abc import Hashable
from typing import List, Optional
from filezilla_companion.criteria.base import Action, Analysis, GroupCriterion, Remove
from filezilla_companion.filezilla.server import Server

class DuplicatesCriterion(GroupCriterion):
    slug = "duplicates"
    label = "Duplicates (same host, user, password, port and key file)"
    keep_one = True

    def key(self, server: Server) -> Optional[Hashable]:
        return (server.normalized_host, server.user, server.password, server.port, server.keyfile)

    def describe(self, servers: List[Server]) -> str:
        return f"{servers[0].user}@{servers[0].host}:{servers[0].port}"

    def resolve(self, servers: List[Server], analysis: Analysis) -> List[Action]:
        """Keep the most complete copy, the first one on a tie, and propose to remove the others."""
        kept = max(servers, key=_completeness)
        return [
            Remove(srv, "most complete copy, kept", checked=False)
            if srv is kept
            else Remove(srv, f'copy of "{kept.name}"', checked=True)
            for srv in servers
        ]

def _completeness(server: Server) -> int:
    """Count the optional settings the site fills in."""
    return sum(bool(value) for value in (
        server.name, server.comments, server.remote_dir, server.local_dir, server.keyfile, server.colour,
    ))
