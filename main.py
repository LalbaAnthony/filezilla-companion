import os
import sys
import base64
import platform
import subprocess
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Callable, Optional

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style
import pyperclip

from server import Server
from action import Action

server_default_port = 22
server_default_username = ""
server_default_protocol = 1  # 0 = FTP, 1 = SFTP

actions = [
    Action(
        key="ssh",
        name="Connect to SSH",
        interactive=True
    ),
    Action(
        key="ssh_cmd",
        name="Connect to SSH + run ls -la",
        commands=[
            "ls -la"
        ]
    ),
    Action(
        key="cancel",
        name="Cancel",
    ),
]

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
            print(
                Fore.YELLOW
                + f"Skipping server '{name}' due to missing host or user."
                + Style.RESET_ALL
            )
            continue

        servers.append(Server(name, host, port, protocol, user, password, keyfile))
    return servers


def select_server(servers: List[Server]) -> Server:
    """Prompt the user to select a server via a fuzzy search menu."""
    choices = [{"name": srv.label, "value": srv} for srv in servers]
    selected = inquirer.fuzzy(
        message="Select a server:", choices=choices, max_height="100%"
    ).execute()
    return selected

def select_action(actions: List[Action]) -> Action:
    choices = [{"name": a.name, "value": a} for a in actions]
    return inquirer.select(message="Choose action:", choices=choices).execute()

def get_sitemanager_path() -> str:
    """Determine FileZilla sitemanager.xml path for current OS."""
    if platform.system() == "Windows":
        return os.path.expandvars(r"%APPDATA%\FileZilla\sitemanager.xml")
    return os.path.expanduser("~/.config/filezilla/sitemanager.xml")

def main() -> None:
    colorama_init(autoreset=True, strip=False, convert=True)

    if not shutil.which("ssh"):
        print(
            Fore.RED
            + "SSH client is not installed or not found in PATH."
            + Style.RESET_ALL
        )
        return

    sitemanager_path = get_sitemanager_path()

    if not os.path.exists(sitemanager_path):
        print(
            Fore.RED
            + "FileZilla sitemanager.xml not found. Please ensure FileZilla is installed and has saved at least one site."
            + Style.RESET_ALL
        )
        return

    servers = parse_sitemanager(sitemanager_path)

    if not servers:
        print(
            Fore.RED
            + "No valid server found in the FileZilla site manager."
            + Style.RESET_ALL
        )
        return

    server = select_server(servers)

    defaults = server.defaulting()
    if defaults:
        print(
            Fore.YELLOW
            + f"Defaulting missing attributes: {', '.join(defaults)}"
            + Style.RESET_ALL
        )

    if server.is_ftp:
        print(
            Fore.RED
            + "Cannot connect to FTP servers. Please select an SFTP server."
            + Style.RESET_ALL
        )
        return

    if not server.can_connect:
        print(
            Fore.RED
            + "Cannot connect to the server with the provided details."
            + Style.RESET_ALL
        )
        return
    
    action = select_action(actions)

    if action == "cancel":
        print(Fore.YELLOW + "Operation cancelled." + Style.RESET_ALL)
    else:
        action.run(server)

if __name__ == "__main__":
    main()

