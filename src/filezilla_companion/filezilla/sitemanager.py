import base64
import datetime
import os
import platform
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable, List
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

@dataclass
class SiteManager:
    """
    The parsed sitemanager.xml. Changes go through its XML tree, so the settings that Server does not model are
    written back unchanged.
    """
    path: str
    tree: ET.ElementTree
    servers: List[Server]

    def remove(self, servers: Iterable[Server]) -> None:
        """Remove the servers from the tree and from `servers`."""
        # Matched by identity: copies of a site compare equal.
        removed = {id(srv) for srv in servers}
        parents = {child: parent for parent in self.tree.iter() for child in parent}
        for srv in self.servers:
            if id(srv) in removed:
                parents[srv.element].remove(srv.element)
        self.servers[:] = [srv for srv in self.servers if id(srv) not in removed]

    def rename(self, server: Server, name: str) -> None:
        """Rename the server in the tree and on the object."""
        name_elem = server.element.find("Name")
        if name_elem is None:
            name_elem = ET.SubElement(server.element, "Name")
        name_elem.text = name
        server.name = name

    def save(self) -> str:
        """
        Copy the file to a timestamped backup next to it, then write the tree to the file, and return the backup path.
        Raises OSError when the backup or the write fails; the file is then unchanged.
        """
        backup = self._backup_path()
        shutil.copy2(self.path, backup)
        # Written aside then moved over the file, so an interrupted write never leaves a truncated sitemanager.xml.
        tmp = f"{self.path}.tmp"
        try:
            self.tree.write(tmp, encoding="UTF-8", xml_declaration=True)
            os.replace(tmp, self.path)
        except OSError:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return backup

    def _backup_path(self) -> str:
        """Return an unused `sitemanager.<timestamp>.xml.bak` path next to the file."""
        stem, ext = os.path.splitext(self.path)
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        path = f"{stem}.{stamp}{ext}.bak"
        counter = 1
        while os.path.exists(path):
            counter += 1
            path = f"{stem}.{stamp}-{counter}{ext}.bak"
        return path

def get_sitemanager_path() -> str:
    """Determine FileZilla sitemanager.xml path for current OS."""
    if platform.system() == "Windows":
        return os.path.expandvars(r"%APPDATA%\FileZilla\sitemanager.xml")
    home = os.path.expanduser("~")
    xdg_config = os.environ.get("XDG_CONFIG_HOME") or os.path.join(home, ".config")
    candidates = [
        os.path.join(home, ".filezilla", "sitemanager.xml"),  # legacy, FileZilla still prefers it when present
        os.path.join(xdg_config, "filezilla", "sitemanager.xml"),
        os.path.join(home, ".var", "app", "org.filezillaproject.Filezilla", "config", "filezilla", "sitemanager.xml"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return candidates[1]

def load_sitemanager(path: str) -> SiteManager:
    """
    Parse FileZilla sitemanager.xml into a SiteManager holding its Server instances.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")

    tree = ET.parse(path)
    servers: List[Server] = []
    for node in tree.findall(".//Server"):
        name = node.findtext("Name") or "Unnamed"
        host = node.findtext("Host") or ""
        port = int(node.findtext("Port") or 22)
        protocol = int(node.findtext("Protocol") or 0)
        user = node.findtext("User") or ""
        keyfile = node.findtext("Keyfile")
        logontype = node.findtext("Logontype")

        password = None
        pass_elem = node.find("Pass")
        if pass_elem is not None and pass_elem.text:
            try:
                password = base64.b64decode(pass_elem.text).decode("utf-8")
            except Exception:
                password = pass_elem.text

        if not host or not user:
            Console.warning(f"Skipping server '{name}' due to missing host or user.")
            continue

        servers.append(Server(
            name, host, port, protocol, user, password, keyfile,
            logontype=int(logontype) if logontype else None,
            comments=node.findtext("Comments") or "",
            colour=int(node.findtext("Colour") or 0),
            remote_dir=node.findtext("RemoteDir") or "",
            local_dir=node.findtext("LocalDir") or "",
            element=node,
        ))
    return SiteManager(path, tree, servers)
