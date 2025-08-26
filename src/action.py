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

        if self.commands:
            # join with && so it stops on first error
            joined = " && ".join(self.commands)
            formatted = f'{server.command} "{joined}"'

            print(Fore.WHITE + "Running: " + Fore.YELLOW + formatted + Style.RESET_ALL)
            subprocess.run(formatted, shell=True)
