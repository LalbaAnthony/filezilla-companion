import subprocess
from dataclasses import dataclass, field
from typing import List
from server import Server

from colorama import init as colorama_init, Fore, Style


@dataclass
class Action:
    key: str
    name: str
    commands: List[str] = field(default_factory=list)
    interactive: bool = False

    def run(self, server: "Server") -> None:
        """Execute this action using the server object."""
        if self.interactive:
            server.open()
            return

        for cmd in self.commands:
            # prepend ssh if not already part of command
            if "{ssh}" in cmd:
                formatted = cmd.format(
                    ssh=server.command,
                    user=server.user,
                    host=server.host,
                    port=server.port,
                )
            else:
                formatted = f"{server.command} {cmd}"

            print(Fore.WHITE + f"Running: " + Fore.YELLOW + formatted + Style.RESET_ALL)
            subprocess.run(formatted, shell=True)
