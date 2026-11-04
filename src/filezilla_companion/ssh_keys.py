import base64
import os
import stat
import struct
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple
import paramiko
from filezilla_companion import auth
from filezilla_companion.auth import AuthStatus
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

# The names ssh-keygen gives by default, in the order they are preferred.
_STANDARD_NAMES = ("id_ed25519", "id_ecdsa", "id_rsa")
# Prefixes of the key types, in the order they are preferred.
_ALGORITHMS = ("ssh-ed25519", "ecdsa-sha2-", "ssh-rsa")
_PUBLIC_SUFFIX = ".pub"

# Relative to the directory an SFTP session starts in, the account's home on a standard server.
_REMOTE_DIR = ".ssh"
_REMOTE_FILE = ".ssh/authorized_keys"
_REMOTE_TMP = ".ssh/authorized_keys.filezilla-companion.tmp"

# So callers can name the type of a loaded private key without importing paramiko.
PrivateKey = paramiko.PKey

class KeyUnavailable(Exception):
    """Raised when the private key of a pair cannot be used to test it; the message tells why."""

@dataclass
class PublicKey:
    """A public key file, and what the commands need from its content."""
    path: str
    algorithm: str
    blob: str  # base64, as written in authorized_keys
    comment: str = ""

    @property
    def name(self) -> str:
        """Return the file name."""
        return os.path.basename(self.path)

    @property
    def private_path(self) -> str:
        """Return the path of the private key of the pair, which may not exist."""
        return self.path[:-len(_PUBLIC_SUFFIX)]

    @property
    def line(self) -> str:
        """Return the key as written in authorized_keys."""
        return f"{self.algorithm} {self.blob} {self.comment}".rstrip()

    @property
    def label(self) -> str:
        """Return the text shown in the selection menu."""
        details = f"{self.algorithm}, {self.comment}" if self.comment else self.algorithm
        return f"{self.name} ({details})"

@dataclass
class DeployResult:
    """The outcome of deploying a key to a site."""
    detail: str
    failed: bool = False
    # Whether a login with the key alone succeeded, so the site can switch to it.
    verified: bool = False

@dataclass
class _Added:
    """What _add_key() created on the server, for _remove_key()."""
    line: bool = False
    file: bool = False
    directory: bool = False

def ssh_dir() -> str:
    """Return the local directory holding the user's SSH keys."""
    return os.path.expanduser(os.path.join("~", ".ssh"))

def list_public_keys() -> List[PublicKey]:
    """
    Return the valid public keys of ssh_dir(), the most logical default first. Unusable files are skipped with a
    warning. Raises OSError when the directory exists but cannot be read.
    """
    directory = ssh_dir()
    try:
        names = os.listdir(directory)
    except FileNotFoundError:
        return []

    ranked: List[Tuple[Tuple[int, int, float, str], PublicKey]] = []
    for name in names:
        if not name.endswith(_PUBLIC_SUFFIX):
            continue
        path = os.path.join(directory, name)
        if not os.path.isfile(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                key = _parse_public_key(path, f.read())
            modified = os.path.getmtime(path)
        except (OSError, UnicodeDecodeError) as e:
            Console.warning(f"Skipping {name}: {e}")
            continue
        if key is None:
            Console.warning(f"Skipping {name}: not an OpenSSH public key.")
            continue
        ranked.append((_preference(key, modified), key))
    ranked.sort(key=lambda item: item[0])
    return [key for _, key in ranked]

def _preference(key: PublicKey, modified: float) -> Tuple[int, int, float, str]:
    """Return the sort key: standard names, then the most modern algorithm, then the most recent file."""
    stem = os.path.basename(key.private_path)
    name_rank = _STANDARD_NAMES.index(stem) if stem in _STANDARD_NAMES else len(_STANDARD_NAMES)
    algorithm_rank = next(
        (rank for rank, prefix in enumerate(_ALGORITHMS) if key.algorithm.startswith(prefix)),
        len(_ALGORITHMS),
    )
    return name_rank, algorithm_rank, -modified, key.name

def _parse_public_key(path: str, text: str) -> Optional[PublicKey]:
    """Return the key held in the content of a .pub file, or None when it does not hold a valid one."""
    lines = text.strip().splitlines()
    parts = lines[0].split(None, 2) if lines else []
    if len(parts) < 2:
        return None
    algorithm, blob = parts[:2]
    try:
        data = base64.b64decode(blob, validate=True)
        length = struct.unpack(">I", data[:4])[0]
    except (ValueError, struct.error):
        # binascii.Error, for bad base64, is a ValueError.
        return None
    # The blob starts with the key type: this rejects anything that only looks like a key before it reaches a server.
    if data[4:4 + length] != algorithm.encode("utf-8"):
        return None
    return PublicKey(path, algorithm, blob, parts[2].strip() if len(parts) > 2 else "")

def load_private_key(key: PublicKey) -> PrivateKey:
    """Return the private key of the pair. Raises KeyUnavailable when it is unusable or belongs to another key."""
    try:
        private = auth.load_key(key.private_path)
    except auth.Untestable as e:
        raise KeyUnavailable(str(e)) from e
    if private.asbytes() != base64.b64decode(key.blob):
        raise KeyUnavailable("the private key does not match the public key")
    return private

def can_deploy(server: Server, key: PublicKey) -> bool:
    """Check if the key can be deployed with what the site saves, and would change something."""
    if server.uses_keyfile and server.keyfile and _same_file(server.keyfile, key.private_path):
        return False
    return not _password_is_encrypted(server) and auth.sftp_login_problem(server) is None

def _same_file(first: str, second: str) -> bool:
    return _canonical_path(first) == _canonical_path(second)

def _canonical_path(path: str) -> str:
    return os.path.normcase(os.path.abspath(os.path.expanduser(path)))

def _password_is_encrypted(server: Server) -> bool:
    """Check if the site logs in with a password encrypted by FileZilla's master password, which cannot be read."""
    if server.element is None or server.uses_keyfile:
        return False
    element = server.element.find("Pass")
    return element is not None and element.get("encoding") == "crypt"

def deploy_all(
    servers: List[Server],
    key: PublicKey,
    private: Optional[PrivateKey],
    on_progress: Callable[[int, int], None],
    workers: int = auth.DEFAULT_WORKERS,
    timeout: float = auth.DEFAULT_TIMEOUT,
) -> List[DeployResult]:
    """Deploy the key to the servers in parallel with auth.run_all() and return the results in the same order."""
    return auth.run_all(servers, lambda server: deploy(server, key, private, timeout), workers, on_progress)

def deploy(server: Server, key: PublicKey, private: Optional[PrivateKey], timeout: float) -> DeployResult:
    """
    Add the key to the site's authorized_keys, logging in with its saved credentials, then test a login with the
    private key when there is one. A line added for a login that then fails is removed.
    """
    try:
        with auth.sftp_session(server, timeout) as sftp:
            added = _add_key(sftp, key)
            state = "key added" if added.line else "key already present"
            if private is None:
                return DeployResult(f"{state}, not verified")
            login = auth.check_key(server, private, timeout)
            if login.status == AuthStatus.OK:
                return DeployResult(f"{state}, key login verified", verified=True)
            if not added.line:
                return DeployResult(f"{state}, but the key login failed: {login.reason}", failed=True)
            try:
                _remove_key(sftp, key, added)
            except Exception as e:
                reason = auth.failure_result(e).reason
                return DeployResult(
                    f"key login failed: {login.reason}. The key stays in authorized_keys, its removal failed: {reason}",
                    failed=True,
                )
            return DeployResult(f"key login failed: {login.reason}. The key was removed", failed=True)
    except Exception as e:
        return DeployResult(auth.failure_result(e).reason, failed=True)

def _add_key(sftp: paramiko.SFTPClient, key: PublicKey) -> _Added:
    """Append the key to authorized_keys unless it holds it, creating what is missing, and return what changed."""
    added = _Added()
    try:
        sftp.stat(_REMOTE_DIR)
    except FileNotFoundError:
        sftp.mkdir(_REMOTE_DIR, 0o700)
        added.directory = True

    try:
        content = _read(sftp, _REMOTE_FILE)
    except FileNotFoundError:
        content = b""
        added.file = True

    if _holds_key(content, key):
        return added

    separator = b"" if not content or content.endswith(b"\n") else b"\n"
    with sftp.open(_REMOTE_FILE, "a") as f:
        # Only on a file created here: changing the mode of an existing one could break a deliberate setup.
        if added.file:
            f.chmod(0o600)
        f.write(separator + key.line.encode("utf-8") + b"\n")
    added.line = True
    return added

def _read(sftp: paramiko.SFTPClient, path: str) -> bytes:
    with sftp.open(path, "r") as f:
        return f.read()

def _holds_key(content: bytes, key: PublicKey) -> bool:
    """Check if authorized_keys holds the key, whatever the comment or the options of its line."""
    blob = key.blob.encode("ascii")
    return any(
        blob in line.split()
        for line in content.splitlines()
        if not line.lstrip().startswith(b"#")
    )

def _remove_key(sftp: paramiko.SFTPClient, key: PublicKey, added: _Added) -> None:
    """Undo _add_key(). The file is replaced by a rename, so a lost connection cannot leave it truncated."""
    if added.file:
        sftp.remove(_REMOTE_FILE)
        if added.directory:
            sftp.rmdir(_REMOTE_DIR)
        return

    line = key.line.encode("utf-8")
    kept = [row for row in _read(sftp, _REMOTE_FILE).splitlines(keepends=True) if row.strip() != line]
    mode = stat.S_IMODE(sftp.stat(_REMOTE_FILE).st_mode)
    try:
        with sftp.open(_REMOTE_TMP, "w") as f:
            f.chmod(mode)
            f.write(b"".join(kept))
        sftp.posix_rename(_REMOTE_TMP, _REMOTE_FILE)
    except Exception as e:
        try:
            sftp.remove(_REMOTE_TMP)
        except Exception as leftover:
            raise OSError(f"{e}; {_REMOTE_TMP} also stays on the server: {leftover}") from e
        raise
