from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
from filezilla_companion.filezilla.server import Server
from filezilla_companion.filezilla.sitemanager import SiteManager

@dataclass
class Context:
    """State loaded once before any command runs, so commands share it without reloading it."""
    sitemanager: SiteManager

    @property
    def servers(self) -> List[Server]:
        return self.sitemanager.servers

class Command(ABC):
    """A behavior offered in the startup menu and selectable with the `--<slug>` flag."""

    slug: str
    label: str

    @abstractmethod
    def run(self, context: Context) -> int:
        """Execute the command and return the process exit code."""
