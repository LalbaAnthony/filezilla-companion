from collections.abc import Hashable
from typing import Callable, List, Optional, Set
from filezilla_companion.criteria.base import Action, Analysis, GroupCriterion, Rename
from filezilla_companion.filezilla.server import Server

def _user_at_host(server: Server) -> str:
    return f"{server.user}@{server.host}"

def _user_at_host_port(server: Server) -> str:
    return f"{server.user}@{server.host}:{server.port}"

# Name suffixes, shortest first: the port is added only when the user and host alone do not tell sites apart.
_SUFFIXES: List[Callable[[Server], str]] = [_user_at_host, _user_at_host_port]

class DuplicateNamesCriterion(GroupCriterion):
    slug = "duplicate-names"
    label = "Duplicate names (same name, different sites)"

    def key(self, server: Server) -> Optional[Hashable]:
        return server.name

    def is_group(self, servers: List[Server]) -> bool:
        # Sites with the same name and address are copies, left to the duplicates criteria.
        return len({_user_at_host_port(srv) for srv in servers}) > 1

    def describe(self, servers: List[Server]) -> str:
        return f'"{servers[0].name}"'

    def resolve(self, servers: List[Server], analysis: Analysis) -> List[Action]:
        """Propose to append its address to the name of each site of the group."""
        taken = {srv.name for srv in analysis.servers}
        actions: List[Action] = []
        for srv in servers:
            new_name = _new_name(srv, servers, taken)
            if new_name is not None:
                taken.add(new_name)
                actions.append(Rename(srv, "name shared with another site", checked=True, new_name=new_name))
        return actions

def _new_name(server: Server, group: List[Server], taken: Set[str]) -> Optional[str]:
    """Return the name with the shortest suffix that no other site of the group or of the site manager has, if any."""
    for suffix in _SUFFIXES:
        name = f"{server.name} ({suffix(server)})"
        shared = any(suffix(other) == suffix(server) for other in group if other is not server)
        if not shared and name not in taken:
            return name
    return None
