from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import List
from filezilla_companion.console import Console
from filezilla_companion.filezilla import process
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
    # Whether the command needs saved sites. Without any (no sitemanager.xml, or no valid site in it), only the
    # commands that do not are offered.
    requires_servers = True

    @abstractmethod
    def run(self, context: Context) -> int:
        """Execute the command and return the process exit code."""

def confirm_write() -> bool:
    """Ask whether to write the changes to sitemanager.xml, after warning when FileZilla may overwrite them."""
    running = process.is_running()
    if running:
        Console.warning("FileZilla is running: its Site Manager may overwrite sitemanager.xml and undo these changes. Close it first.")
    elif running is None:
        Console.warning("Cannot tell whether FileZilla is running. If it is, close it first: its Site Manager may overwrite sitemanager.xml.")
    return Console.confirm("Write the changes to sitemanager.xml?")
