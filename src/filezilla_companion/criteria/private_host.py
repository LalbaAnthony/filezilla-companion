import ipaddress
from typing import Optional
from filezilla_companion.criteria.base import Action, Analysis, SiteCriterion
from filezilla_companion.filezilla.server import Server

def is_private_host(host: str) -> bool:
    """Check if the host is localhost or a private, loopback or link-local IP address."""
    host = host.strip().lower()
    if host == "localhost":
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        # A host name: telling would take a DNS lookup per site.
        return False
    return address.is_private or address.is_loopback or address.is_link_local

class PrivateHostCriterion(SiteCriterion):
    slug = "private-host"
    label = "Private addresses (report only)"

    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        return "private address" if is_private_host(server.host) else None

    def propose(self, server: Server, reason: str, analysis: Analysis) -> Optional[Action]:
        return None
