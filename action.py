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
        for cmd in self.commands:
            formatted = cmd.format(
                ssh=server.command,
                user=server.user,
                host=server.host,
                port=server.port,
            )
            print(Fore.WHITE + f"Running: {formatted}" + Style.RESET_ALL)
            subprocess.run(formatted, shell=True)

        if self.interactive:
            server.open()
