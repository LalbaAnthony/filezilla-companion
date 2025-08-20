import os
import sys
import base64
import platform
import subprocess
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style
import pyperclip

server_default_port = 22
server_default_username = ""
server_default_protocol = 1  # 0 = FTP, 1 = SFTP


@dataclass
class Server:
    name: str
    host: str
    port: int
    protocol: int  # 0 = FTP, 1 = SFTP
    user: str
    password: Optional[str] = None
    keyfile: Optional[str] = None

    @property
    def fullhost(self) -> str:
        """Return the full host string with port if necessary."""
        assert (
            self.host and self.port
        ), "Cannot generate fullhost without host and port."
        return f"{self.host}:{self.port}"

    @property
    def fullname(self) -> str:
        """Return the full name string with user if necessary."""
        assert (
            self.host and self.user
        ), "Cannot generate fullname without host and user."
        return f"{self.user}@{self.host}"

    @property
    def label(self) -> str:
        """Return the nice label."""
        assert self.fullname, "Cannot generate label without fullname."
        if self.name:
            return f"{self.name} ({self.fullname})"
        return f"{self.fullname}"

    @property
    def command(self) -> str:
        """Return the SSH command to connect to the server."""
        assert self.can_connect, "Cannot generate command without host and user."
        cmd_parts = ["ssh"]
        if self.keyfile:
            cmd_parts += ["-i", f'"{self.keyfile}"']
        if self.user and self.host:
            cmd_parts += [f"{self.user}@{self.host}", "-p", str(self.port)]
        if self.password:
            cmd_parts += ["-o", "PasswordAuthentication=yes"]

        cmd = " ".join(cmd_parts)

        return cmd

    @property
    def is_ftp(self) -> bool:
        """Check if the server is FTP."""
        assert self.protocol in (0, 1), "Invalid protocol value"
        return self.protocol == 0 or self.port == 21 or "ftp." in self.host

    @property
    def is_sftp(self) -> bool:
        """Check if the server is SFTP."""
        assert self.protocol in (0, 1), "Invalid protocol value"
        return self.protocol == 1 or self.port == 22 or "sftp." in self.host

    @property
    def can_connect(self) -> bool:
        """Check if the server can be connected to."""
        return self.host and self.user and ((not self.is_ftp) or (self.is_sftp))

    def defaulting(self) -> List[str]:
        """Set default values for missing attributes."""

        global server_default_port, server_default_username, server_default_protocol

        updated = []

        if not self.port:
            self.port = server_default_port
            updated.append("port")

        if not self.protocol:
            self.protocol = server_default_protocol
            updated.append("protocol")

        if not self.user:
            self.user = server_default_username
            updated.append("user")

        return updated

    def open(self) -> None:
        """Open a new terminal window and initiate SSH connection."""
        assert self.can_connect, "Cannot connect to server without host and user."

        if self.password:
            pyperclip.copy(self.password)
            print(Fore.GREEN + "Password copied to clipboard." + Style.RESET_ALL)

        print(Fore.WHITE + f"Connecting to {self.label} using `{self.command}` ..." + Style.RESET_ALL)

        if platform.system() == "Windows":
            subprocess.Popen(["start", "cmd", "/k", self.command], shell=True)
        else:
            for emulator in (
                ["gnome-terminal", "--"],
                ["xterm", "-e"],
                ["konsole", "-e"],
            ):
                if shutil.which(emulator[0]):
                    subprocess.Popen(emulator + [self.command + "; exec $SHELL"])


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

    server.open()


if __name__ == "__main__":
    main()
