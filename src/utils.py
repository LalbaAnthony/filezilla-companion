import json
import os
import base64
import platform
import xml.etree.ElementTree as ET
from typing import List, Optional
from InquirerPy import inquirer
from colorama import Fore, Style
from server import Server
from action import Action
import shutil
import subprocess
import sys

_WINDOWS_SSH_PATHS = [
    r"C:\Windows\Sysnative\OpenSSH\ssh.exe",
    r"C:\Windows\System32\OpenSSH\ssh.exe",
    r"C:\Program Files\Git\usr\bin\ssh.exe",
    r"C:\Program Files\OpenSSH\ssh.exe",
]

# Ordered by preference, each entry is the argv prefix that runs the remaining args as a command.
_POSIX_TERMINALS = [
    ["x-terminal-emulator", "-e"],  # Debian alternatives entry for the desktop's default terminal
    ["gnome-terminal", "--"],
    ["konsole", "-e"],
    ["xfce4-terminal", "-x"],
    ["xterm", "-e"],
]

def find_cmd() -> Optional[str]:
    """Return the path to the cmd executable on Windows, or None if not found."""
    found = shutil.which("cmd") or shutil.which("cmd.exe")
    if found:
        return found
    if sys.platform == "win32":
        for path in [r"C:\Windows\System32\cmd.exe", r"C:\Windows\Sysnative\cmd.exe"]:
            if os.path.isfile(path):
                return path
    return None

def find_terminal() -> Optional[List[str]]:
    """Return the argv prefix of a graphical terminal emulator on POSIX, or None if unavailable."""
    if not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return None
    for emulator in _POSIX_TERMINALS:
        if shutil.which(emulator[0]):
            return list(emulator)
    return None

def find_ssh() -> Optional[str]:
    """Return the path to the ssh executable, or None if not found."""
    found = shutil.which("ssh") or shutil.which("ssh.exe")
    if found:
        return found
    if sys.platform == "win32":
        for path in _WINDOWS_SSH_PATHS:
            if os.path.isfile(path):
                return path
    return None

def ssh_is_functional(ssh_path: str) -> bool:
    """Verify the binary actually runs (guards against broken installs)."""
    try:
        result = subprocess.run(
            [ssh_path, "-V"],
            capture_output=True,
            timeout=5,
        )
        return result.returncode == 0 or b"OpenSSH" in result.stderr
    except Exception:
        return False

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
        message="Select a server:",
        instruction="(use arrows to scroll and `enter` to confirm)",
        invalid_message="please select a server",
        choices=choices,
        validate=lambda result: result is not None,
        max_height="100%"
    ).execute()
    return selected

def load_actions(path: str) -> list[Action]:
    with open(path, "r", encoding="utf-8") as f:
        raw = json.load(f)
    return [Action(**item) for item in raw]

def select_actions(actions: List[Action]) -> List[Action]:
    choices = [
        {"name": a.name, "value": a, "enabled": a.default} for a in actions
    ]
    return inquirer.checkbox(
        message="Choose one or more actions:",
        instruction="(use `space` to select and `enter` to confirm)",
        invalid_message="please select at least one action",
        choices=choices,
        validate=lambda result: len(result) > 0,
        max_height="100%"
    ).execute()


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
