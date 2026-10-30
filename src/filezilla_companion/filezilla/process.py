import platform
import subprocess
from typing import Optional

def is_running() -> Optional[bool]:
    """Return whether a FileZilla process is running, or None when it cannot be determined."""
    windows = platform.system() == "Windows"
    if windows:
        # The CSV output quotes the image name whatever the system language, unlike the "no task" message.
        argv = ["tasklist", "/FI", "IMAGENAME eq filezilla.exe", "/FO", "CSV", "/NH"]
    else:
        argv = ["pgrep", "-x", "filezilla"]

    try:
        result = subprocess.run(argv, capture_output=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return None

    if windows:
        if result.returncode != 0:
            return None
        # Bytes, not text: tasklist prints in the OEM code page, which the default decoding may reject.
        return b'"filezilla.exe"' in result.stdout.lower()
    # pgrep exits with 0 when a process matches, 1 when none does, and above on error.
    if result.returncode > 1:
        return None
    return result.returncode == 0
