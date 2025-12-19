import subprocess
from dataclasses import dataclass, field
from typing import List
from server import Server
import platform
import shutil
import pyperclip
from colorama import Fore, Style


@dataclass
class Action:
    key: str
    name: str
    commands: List[str] = field(default_factory=list)
    interactive: bool = False

    def run(self, server: "Server") -> None:
        """Execute this action using the server object."""
        command = server.command

        if self.commands:
            interactive=""
            if self.interactive:
                interactive="; exec $SHELL"

            command = f'{command} "{" && ".join(self.commands)} {interactive}"'
            # command = f'{command} "/bin/sh -c \'{ " && ".join(self.commands) }{interactive}\'"'
            # command = f'{command} "bash --noprofile --norc -c \'{ " && ".join(self.commands) }{interactive}\'"'

        print(Fore.WHITE + f"Running: {command}" + Style.RESET_ALL)

        if self.interactive:
            if platform.system() == "Windows":
                subprocess.Popen(["start", "cmd", "/k", command], shell=True)
            else:
                for emulator in (
                    ["gnome-terminal", "--"],
                    ["xterm", "-e"],
                    ["konsole", "-e"],
                ):
                    if shutil.which(emulator[0]):
                        subprocess.Popen(emulator + [command])

            if server.password:
                pyperclip.copy(server.password)
                print(Fore.GREEN + "Password copied to clipboard." + Style.RESET_ALL)
        else:
            subprocess.run(command, shell=True)
