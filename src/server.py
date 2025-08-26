import platform
import subprocess
import shutil
from dataclasses import dataclass, field
from typing import List, Optional

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style
import pyperclip


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

        print(
            Fore.WHITE
            + f"Connecting to {self.label} using `{self.command}` ..."
            + Style.RESET_ALL
        )

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
