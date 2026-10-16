import os
import platform
import shutil
import subprocess
import sys
from typing import List, Optional
import pyperclip
from console import Console
from server import Server

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

def connect(server: Server) -> None:
    """
    Open an interactive SSH session to the server, in a new terminal when one is available.
    Raises OSError when the terminal cannot be started.
    """
    command = server.command
    Console.info(f"Running: {command}")

    # Copy before launching: running in the current terminal blocks until the session ends.
    if server.password:
        try:
            pyperclip.copy(server.password)
            Console.success("Password copied to clipboard.")
        except pyperclip.PyperclipException as e:
            Console.warning(f"Password not copied to clipboard: {e}")

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
