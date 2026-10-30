import base64
import datetime
import os
import platform
import re
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

# Server attributes that add() writes and update() changes, with their element, in the order FileZilla writes them.
_SETTINGS: Dict[str, str] = {
    "host": "Host",
    "port": "Port",
    "protocol": "Protocol",
    "user": "User",
    "password": "Pass",
    "keyfile": "Keyfile",
    "logontype": "Logontype",
    "name": "Name",
    "comments": "Comments",
    "remote_dir": "RemoteDir",
}

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

    def add(self, server: Server) -> None:
        """Add the server at the top level of the site manager, and to `servers`."""
        root = self.tree.getroot()
        parent = root.find("Servers")
        if parent is None:
            parent = ET.Element("Servers")
            self._append(root, parent)
        element = ET.Element("Server")
        for attr, tag in _SETTINGS.items():
            value = getattr(server, attr)
            if not _is_unset(value):
                _write_setting(ET.SubElement(element, tag), attr, value)
        self._append(parent, element)
        server.element = element
        self.servers.append(server)

    def update(self, server: Server, changes: Dict[str, Any]) -> None:
        """
        Set the server's attributes, among those add() writes, on the object and in its element. An empty value
        removes the setting.
        """
        for attr, value in changes.items():
            tag = _SETTINGS[attr]
            setattr(server, attr, value)
            child = server.element.find(tag)
            if _is_unset(value):
                if child is not None:
                    _detach(server.element, child)
                continue
            if child is None:
                child = ET.Element(tag)
                self._append(server.element, child)
            _write_setting(child, attr, value)

    def save(self) -> Optional[str]:
        """
        Write the tree to the file, after copying the file to a timestamped backup next to it when it exists, and
        return the backup path, or None when the file did not exist. Raises OSError when the backup or the write
        fails; the file is then unchanged.
        """
        existed = os.path.exists(self.path)
        backup = None
        if existed:
            backup = self._backup_path()
            shutil.copy2(self.path, backup)
        else:
            directory = os.path.dirname(self.path)
            if directory:
                os.makedirs(directory, exist_ok=True)
        # Written aside then moved over the file, so an interrupted write never leaves a truncated sitemanager.xml.
        tmp = f"{self.path}.tmp"
        try:
            # A leftover would keep its mode: the new file is created private, since it holds passwords.
            if os.path.exists(tmp):
                os.remove(tmp)
            fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "wb") as f:
                self.tree.write(f, encoding="UTF-8", xml_declaration=True)
            # A replaced file keeps its own mode. Windows files take the folder's permissions instead.
            if existed and platform.system() != "Windows":
                shutil.copymode(self.path, tmp)
            os.replace(tmp, self.path)
        except OSError:
            if os.path.exists(tmp):
                os.remove(tmp)
            raise
        return backup

    def _append(self, parent: ET.Element, child: ET.Element) -> None:
        """
        Append the child, indented like the rest of the file when it is: ElementTree writes the whitespace as parsed,
        so a new element would otherwise sit on the line of the previous one.
        """
        unit = self._indent_unit()
        inline = len(parent) > 0 and "\n" not in (parent[-1].tail or "")
        if unit is None or inline:
            parent.append(child)
            return
        level = self._depth(parent) + 1
        ET.indent(child, space=unit, level=level)
        if len(parent):
            child.tail = parent[-1].tail
            parent[-1].tail = "\n" + unit * level
        else:
            parent.text = "\n" + unit * level
            child.tail = "\n" + unit * (level - 1)
        parent.append(child)

    def _indent_unit(self) -> Optional[str]:
        """Return the indentation of one level, read before the root's first child, or None if the file has none."""
        text = self.tree.getroot().text
        if not text or text.strip() or "\n" not in text:
            return None
        return text.rsplit("\n", 1)[1]

    def _depth(self, element: ET.Element) -> int:
        parents = {child: parent for parent in self.tree.iter() for child in parent}
        depth = 0
        while element in parents:
            element = parents[element]
            depth += 1
        return depth

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

def _is_unset(value: Any) -> bool:
    return value is None or value == ""

def _write_setting(element: ET.Element, attr: str, value: Any) -> None:
    """Write the value in the setting's element, encoded like FileZilla does."""
    if attr == "password":
        # Replaces any other encoding, e.g. `crypt` (FileZilla's master password) and its pubkey attribute.
        element.attrib.clear()
        element.set("encoding", "base64")
        element.text = base64.b64encode(value.encode("utf-8")).decode("ascii")
    else:
        element.text = str(value)

def _detach(parent: ET.Element, child: ET.Element) -> None:
    """Remove the child. When it is the last one, the previous one takes its tail, which indents the closing tag."""
    children = list(parent)
    index = children.index(child)
    if index > 0 and index == len(children) - 1:
        children[index - 1].tail = child.tail
    parent.remove(child)

def encode_remote_dir(path: str) -> str:
    """
    Return the Unix path in FileZilla's RemoteDir format: server type 1 (Unix), an empty prefix (0), then each segment
    preceded by its length. `/var/www` gives `1 0 3 var 3 www`, and `/` gives `1 0`.
    """
    segments = [segment for segment in path.split("/") if segment]
    return "1 0" + "".join(f" {_wchar_len(segment)} {segment}" for segment in segments)

def decode_remote_dir(value: str) -> Optional[str]:
    """Return the Unix path held in a FileZilla RemoteDir, or None for another kind of path."""
    if not value.startswith("1 0"):
        return None
    segments: List[str] = []
    rest = value[3:]
    while rest:
        match = re.match(r" (\d+) ", rest)
        if match is None:
            return None
        end = match.end() + int(match.group(1))
        segments.append(rest[match.end():end])
        rest = rest[end:]
    path = "/" + "/".join(segments)
    # Segments are sliced by code point: a value counted otherwise (UTF-16 on Windows) does not survive the round trip.
    return path if encode_remote_dir(path) == value else None

def _wchar_len(text: str) -> int:
    """Return the length FileZilla counts: its strings are wchar_t, which is UTF-16 on Windows."""
    if platform.system() == "Windows":
        return len(text.encode("utf-16-le")) // 2
    return len(text)

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

def empty_sitemanager(path: str) -> SiteManager:
    """Return a SiteManager without any site, for a sitemanager.xml that does not exist yet. save() creates it."""
    root = ET.Element("FileZilla3")
    ET.SubElement(root, "Servers")
    # Indented, so the sites added later are too.
    ET.indent(root, space="\t")
    return SiteManager(path, ET.ElementTree(root), [])

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
