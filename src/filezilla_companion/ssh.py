import os
import shutil
import subprocess
import sys
from typing import Optional
from filezilla_companion import clipboard, terminal
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

_WINDOWS_SSH_PATHS = [
    r"C:\Windows\Sysnative\OpenSSH\ssh.exe",
    r"C:\Windows\System32\OpenSSH\ssh.exe",
    r"C:\Program Files\Git\usr\bin\ssh.exe",
    r"C:\Program Files\OpenSSH\ssh.exe",
]

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
            clipboard.copy(server.password)
            Console.success("Password copied to clipboard.")
        except clipboard.ClipboardError as e:
            Console.warning(f"Password not copied to clipboard: {e}")

    terminal.open_in_terminal(command)
