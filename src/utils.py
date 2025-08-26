import os
import base64
import platform
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style

from server import Server
from action import Action


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

def select_actions(actions: List[Action]) -> List[Action]:
    choices = [{"name": a.name, "value": a} for a in actions]
    return inquirer.checkbox(
        message="Choose one or more actions (use `space` to select):",
        choices=choices,
        validate=lambda result: len(result) > 0,
    ).execute()

def get_sitemanager_path() -> str:
    """Determine FileZilla sitemanager.xml path for current OS."""
    if platform.system() == "Windows":
        return os.path.expandvars(r"%APPDATA%\FileZilla\sitemanager.xml")
    return os.path.expanduser("~/.config/filezilla/sitemanager.xml")
