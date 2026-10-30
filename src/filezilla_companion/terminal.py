import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional
from filezilla_companion.console import Console

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

def open_in_terminal(command: str) -> None:
    """
    Run a shell command in a new terminal window that stays open once the command exits.
    Without a graphical session on POSIX, runs it in the current terminal and blocks until it exits.
    Raises OSError when the terminal cannot be started.
    """
    if platform.system() == "Windows":
        cmd = find_cmd()
        if not cmd:
            raise FileNotFoundError("cmd.exe not found.")
        subprocess.Popen([cmd, "/k", command])
        return

    terminal = find_terminal()
    if not terminal:
        Console.warning("No graphical terminal available, running in the current terminal.")
        subprocess.run(command, shell=True)
        return

    # Mirror `cmd /k`: keep the window open on a local shell once the command exits.
    subprocess.Popen(
        terminal + ["sh", "-c", f'{command}; exec "${{SHELL:-/bin/sh}}"'],
        start_new_session=True,
    )
