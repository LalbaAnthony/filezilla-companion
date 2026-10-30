import base64
import os
import platform
import xml.etree.ElementTree as ET
from typing import List
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

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

def parse_sitemanager(path: str) -> List[Server]:
    """
    Parse FileZilla sitemanager.xml into Server instances.
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

        servers.append(Server(name, host, port, protocol, user, password, keyfile))
    return servers
