import json
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

TIMEOUT = 120  # seconds per bw call: a sync over a slow network or of a large vault takes a while

_LOGIN = 1  # item type of a Login, as opposed to secure notes, cards, identities and SSH keys

class BitwardenError(Exception):
    """Raised when the Bitwarden CLI cannot be run, fails, or prints something unexpected."""

@dataclass
class Login:
    """A Login item of the vault, reduced to what the import reads."""
    id: str
    name: str
    created: str  # ISO 8601 UTC creation date, as bw prints it, so it sorts chronologically as text
    username: str = ""
    password: str = ""
    uris: List[str] = field(default_factory=list)
    # Custom fields by lowercased name, empty ones left out. The first field of a name wins.
    fields: Dict[str, str] = field(default_factory=dict)

def find_bw() -> Optional[str]:
    """Return the path to the bw executable, or None if not found."""
    return shutil.which("bw")

def status(bw: str) -> str:
    """Return the vault status: `unauthenticated`, `locked`, or `unlocked` when BW_SESSION holds a valid session."""
    data = _run_json(bw, "status")
    if not isinstance(data, dict) or not isinstance(data.get("status"), str):
        raise BitwardenError("bw status printed an unexpected result.")
    return data["status"]

def sync(bw: str) -> None:
    """Pull the vault from the server into the CLI's local copy."""
    _run(bw, "sync")

def list_logins(bw: str) -> List[Login]:
    """Return the Login items of the vault, trash excluded, in the order bw prints them."""
    items = _run_json(bw, "list", "items")
    if not isinstance(items, list):
        raise BitwardenError("bw list items printed an unexpected result.")
    try:
        return [_login(item) for item in items if item.get("type") == _LOGIN]
    except (AttributeError, TypeError) as e:
        raise BitwardenError(f"bw list items printed an unexpected item: {e}") from e

def _login(item: Dict[str, Any]) -> Login:
    login = item.get("login") or {}
    fields: Dict[str, str] = {}
    for custom in item.get("fields") or []:
        name = (custom.get("name") or "").strip().lower()
        value = (custom.get("value") or "").strip()
        if name and value:
            fields.setdefault(name, value)
    return Login(
        id=item.get("id") or "",
        name=item.get("name") or "",
        created=item.get("creationDate") or "",
        username=login.get("username") or "",
        password=login.get("password") or "",
        uris=[uri["uri"].strip() for uri in login.get("uris") or [] if uri.get("uri")],
        fields=fields,
    )

def _run(bw: str, *args: str) -> str:
    """Run a bw command and return its output. Raises BitwardenError when it cannot run or fails."""
    command = " ".join(args)
    try:
        # bw prints UTF-8 whatever the locale. Without a valid session, --nointeraction makes it fail instead of
        # prompting for the master password on a terminal it does not own.
        result = subprocess.run(
            [bw, "--nointeraction", *args],
            capture_output=True,
            encoding="utf-8",
            timeout=TIMEOUT,
        )
    except subprocess.TimeoutExpired as e:
        raise BitwardenError(f"bw {command} timed out after {TIMEOUT} seconds.") from e
    except (OSError, UnicodeDecodeError) as e:
        raise BitwardenError(f"Cannot run bw {command}: {e}") from e
    if result.returncode != 0:
        detail = result.stderr.strip() or f"exit code {result.returncode}"
        raise BitwardenError(f"bw {command} failed: {detail}")
    return result.stdout

def _run_json(bw: str, *args: str) -> Any:
    output = _run(bw, *args)
    try:
        return json.loads(output)
    except ValueError as e:
        raise BitwardenError(f"bw {' '.join(args)} printed invalid JSON: {e}") from e
