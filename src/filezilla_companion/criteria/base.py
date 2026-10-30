from abc import ABC, abstractmethod
from collections.abc import Hashable
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from filezilla_companion import auth
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

def site_label(server: Server) -> str:
    """Return the site name with its full address, port included, to tell apart sites that share a name or a host."""
    address = f"{server.user}@{server.host}:{server.port}"
    return f"{server.name} ({address})" if server.name else address

@dataclass
class Action(ABC):
    """A change proposed for a site, applied only if it is checked in the selection menu."""
    server: Server
    reason: str
    checked: bool

    @property
    @abstractmethod
    def label(self) -> str:
        """Return the text shown in the selection menu."""

@dataclass
class Remove(Action):
    @property
    def label(self) -> str:
        return f"Remove {site_label(self.server)}: {self.reason}"

@dataclass
class Rename(Action):
    new_name: str

    @property
    def label(self) -> str:
        return f'Rename {site_label(self.server)} to "{self.new_name}": {self.reason}'

@dataclass
class Finding:
    """Sites matched by a criterion for the same reason, and the changes proposed for them."""
    title: str
    servers: List[Server]
    actions: List[Action] = field(default_factory=list)
    # Whether removing every site of the finding deserves a warning, e.g. all the copies of a site.
    keep_one: bool = False

class Analysis:
    """The sites under analysis, and the results that criteria share, like the slow credential tests."""

    def __init__(
        self,
        servers: List[Server],
        auth_workers: int = auth.DEFAULT_WORKERS,
        auth_timeout: float = auth.DEFAULT_TIMEOUT,
    ) -> None:
        self.servers = servers
        self.auth_workers = auth_workers
        self.auth_timeout = auth_timeout
        # Keyed by id(): Server is unhashable, and copies of a site compare equal.
        self._auth: Dict[int, auth.AuthResult] = {}

    def check_credentials(self, servers: List[Server]) -> None:
        """Test the credentials of the servers not tested yet, in parallel, showing the progress."""
        pending = [srv for srv in servers if id(srv) not in self._auth]
        if not pending:
            return
        total = len(pending)

        def show(done: int, failed: int) -> None:
            Console.progress(f"Testing credentials: {done}/{total} ({failed} failed)", done == total)

        show(0, 0)
        results = auth.check_all(pending, self.auth_workers, self.auth_timeout, show)
        for srv, result in zip(pending, results):
            self._auth[id(srv)] = result

    def auth_result(self, server: Server) -> auth.AuthResult:
        """Return the credential test result of the server, testing it now if it was not."""
        self.check_credentials([server])
        return self._auth[id(server)]

class Criterion(ABC):
    """A rule that finds sites to report, and proposes changes for them."""

    slug: str
    label: str

    @abstractmethod
    def evaluate(self, analysis: Analysis) -> List[Finding]:
        """Return the findings over the analyzed sites, in site manager order."""

    @abstractmethod
    def summary(self, findings: List[Finding]) -> str:
        """Return the count shown in the report heading, e.g. `3 groups`."""

class GroupCriterion(Criterion):
    """A criterion over groups of sites sharing a key, e.g. duplicates."""

    # Whether removing every site of a group deserves a warning.
    keep_one = False

    @abstractmethod
    def key(self, server: Server) -> Optional[Hashable]:
        """Return the grouping key of the site, or None to leave the site out."""

    def is_group(self, servers: List[Server]) -> bool:
        """Check if sites sharing a key make a finding. By default, any key shared by several sites does."""
        return len(servers) > 1

    @abstractmethod
    def describe(self, servers: List[Server]) -> str:
        """Return the title of the finding made by the group."""

    def prepare(self, servers: List[Server], analysis: Analysis) -> None:
        """Compute at once what resolve() needs for every grouped site, e.g. credential tests. Nothing by default."""

    @abstractmethod
    def resolve(self, servers: List[Server], analysis: Analysis) -> List[Action]:
        """Return the changes proposed for the group."""

    def evaluate(self, analysis: Analysis) -> List[Finding]:
        groups: Dict[Hashable, List[Server]] = {}
        for srv in analysis.servers:
            key = self.key(srv)
            if key is not None:
                groups.setdefault(key, []).append(srv)
        matched = [group for group in groups.values() if self.is_group(group)]
        self.prepare([srv for group in matched for srv in group], analysis)
        return [
            Finding(self.describe(group), group, self.resolve(group, analysis), self.keep_one)
            for group in matched
        ]

    def summary(self, findings: List[Finding]) -> str:
        return _count(len(findings), "group")

class SiteCriterion(Criterion):
    """A criterion checking each site on its own, e.g. a missing key file. Matched sites are grouped by reason."""

    def prepare(self, analysis: Analysis) -> None:
        """Compute at once what check() needs for every site, e.g. credential tests. Nothing by default."""

    @abstractmethod
    def check(self, server: Server, analysis: Analysis) -> Optional[str]:
        """Return why the site matches, or None when it does not."""

    def propose(self, server: Server, reason: str, analysis: Analysis) -> Optional[Action]:
        """Return the change proposed for a matched site, or None to only report it. By default, its removal."""
        return Remove(server, reason, checked=True)

    def evaluate(self, analysis: Analysis) -> List[Finding]:
        self.prepare(analysis)
        findings: Dict[str, Finding] = {}
        for srv in analysis.servers:
            reason = self.check(srv, analysis)
            if reason is None:
                continue
            finding = findings.setdefault(reason, Finding(reason, []))
            finding.servers.append(srv)
            action = self.propose(srv, reason, analysis)
            if action is not None:
                finding.actions.append(action)
        return list(findings.values())

    def summary(self, findings: List[Finding]) -> str:
        return _count(sum(len(finding.servers) for finding in findings), "site")

def _count(count: int, noun: str) -> str:
    return f"{count} {noun}" if count == 1 else f"{count} {noun}s"
