import subprocess
from dataclasses import dataclass, field
from typing import List
from server import Server
import platform
import pyperclip
from colorama import Fore, Style


@dataclass
class Action:
    key: str
    name: str
    commands: List[str] = field(default_factory=list)
    interactive: bool = False
    default: bool = False

    def run(self, server: "Server") -> None:
        """Execute this action using the server object."""
        command = server.command
        is_windows = platform.system() == "Windows"

        if self.commands:
            interactive=""
            if self.interactive:
                # On POSIX the command goes through a local `sh`, escape `$` so the remote shell expands it.
                interactive="; exec $SHELL" if is_windows else r"; exec \$SHELL"

            command = f'{command} "{" && ".join(self.commands)} {interactive}"'
            # command = f'{command} "/bin/sh -c \'{ " && ".join(self.commands) }{interactive}\'"'
            # command = f'{command} "bash --noprofile --norc -c \'{ " && ".join(self.commands) }{interactive}\'"'

        print(Fore.WHITE + f"Running: {command}" + Style.RESET_ALL)

        if self.interactive:
            # Copy before launching: the POSIX fallback below blocks until the session ends.
            if server.password:
                try:
                    pyperclip.copy(server.password)
                    print(Fore.GREEN + "Password copied to clipboard." + Style.RESET_ALL)
                except pyperclip.PyperclipException as e:
                    print(Fore.YELLOW + f"Password not copied to clipboard: {e}" + Style.RESET_ALL)

            if is_windows:
                from utils import find_cmd
                cmd = find_cmd()
                subprocess.Popen([cmd, "/k", command])
            else:
                from utils import find_terminal
                terminal = find_terminal()
                if terminal:
                    # Mirror `cmd /k`: keep the window open on a local shell once the command exits.
                    subprocess.Popen(
                        terminal + ["sh", "-c", f'{command}; exec "${{SHELL:-/bin/sh}}"'],
                        start_new_session=True,
                    )
                else:
                    print(
                        Fore.YELLOW
                        + "No graphical terminal available, running in the current terminal."
                        + Style.RESET_ALL
                    )
                    subprocess.run(command, shell=True)
        else:
            subprocess.run(command, shell=True)
