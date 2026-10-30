import ftplib
import logging
import os
import socket
import ssl
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, List, Optional, Tuple
import paramiko
from filezilla_companion.filezilla.server import Server

DEFAULT_WORKERS = 16
DEFAULT_TIMEOUT = 10.0  # seconds, for each network step (connection, handshake, login)

# paramiko logs transport errors (e.g. an unreadable banner) from its own threads. Without a handler, Python prints
# them on stderr, across the progress line, although they are already reported in the results.
logging.getLogger("paramiko").addHandler(logging.NullHandler())

# FileZilla protocols: 1 = SFTP; over FTP, 0 = TLS when the server offers it, 3 = implicit TLS, 4 = explicit TLS
# required, 6 = plain. Others (HTTP, S3, cloud storage...) are not tested.
_SFTP = 1
_FTP_TLS_IF_AVAILABLE = 0
_FTP_IMPLICIT_TLS = 3
_FTP_EXPLICIT_TLS = 4
_FTP_PLAIN = 6
_FTP_PROTOCOLS = (_FTP_TLS_IF_AVAILABLE, _FTP_IMPLICIT_TLS, _FTP_EXPLICIT_TLS, _FTP_PLAIN)

_LOGONTYPE_ANONYMOUS = 0
_LOGONTYPE_NORMAL = 1
_UNSUPPORTED_LOGONTYPES = {
    2: "asks for the password at login",
    3: "uses interactive login",
    4: "logs in with an account",
}
# Credentials FileZilla sends for an anonymous logon.
_ANONYMOUS = ("anonymous", "anonymous@example.com")

class AuthStatus(Enum):
    OK = "credentials accepted"
    REJECTED = "credentials rejected"
    HOST_NOT_FOUND = "host not found"
    TIMEOUT = "timed out"
    REFUSED = "connection refused"
    ERROR = "connection failed"
    UNTESTABLE = "not testable"

@dataclass
class AuthResult:
    status: AuthStatus
    detail: str = ""

    @property
    def failed(self) -> bool:
        """Check if the test ran and did not log in."""
        return self.status not in (AuthStatus.OK, AuthStatus.UNTESTABLE)

    @property
    def reason(self) -> str:
        """Return the status with its detail, for display."""
        return f"{self.status.value}: {self.detail}" if self.detail else self.status.value

class _Untestable(Exception):
    """Raised before any connection when the site cannot be tested; the message tells why."""

class _ImplicitFTPTLS(ftplib.FTP_TLS):
    """FTP_TLS for implicit TLS (FileZilla protocol 3), where TLS starts with the connection, not after AUTH TLS."""

    _sock: Optional[socket.socket] = None

    @property
    def sock(self) -> Optional[socket.socket]:
        return self._sock

    @sock.setter
    def sock(self, value: Optional[socket.socket]) -> None:
        # FTP.connect assigns the plain socket, then reads the welcome message through it: wrap it in between.
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=self.host)
        self._sock = value

def check(server: Server, timeout: float) -> AuthResult:
    """Log in to the server with its saved credentials, disconnect, and return the outcome."""
    try:
        if server.protocol == _SFTP:
            return _check_sftp(server, timeout)
        if server.protocol in _FTP_PROTOCOLS:
            return _check_ftp(server, timeout)
        raise _Untestable(f"protocol {server.protocol} is not supported")
    except _Untestable as e:
        return AuthResult(AuthStatus.UNTESTABLE, str(e))
    except paramiko.BadAuthenticationType as e:
        return AuthResult(AuthStatus.REJECTED, f"the server only allows {', '.join(e.allowed_types)}")
    except paramiko.AuthenticationException:
        return AuthResult(AuthStatus.REJECTED)
    except socket.gaierror:
        return AuthResult(AuthStatus.HOST_NOT_FOUND)
    except (socket.timeout, TimeoutError):
        return AuthResult(AuthStatus.TIMEOUT)
    except ConnectionRefusedError:
        return AuthResult(AuthStatus.REFUSED)
    except (paramiko.SSHException, ftplib.Error, EOFError, OSError) as e:
        return AuthResult(AuthStatus.ERROR, str(e) or type(e).__name__)
    except Exception as e:
        # A server misbehaving in a way the libraries do not anticipate must not abort the tests of every other
        # site: the error is reported with the site instead.
        return AuthResult(AuthStatus.ERROR, f"{type(e).__name__}: {e}")

def check_all(
    servers: List[Server],
    workers: int,
    timeout: float,
    on_progress: Callable[[int, int], None],
) -> List[AuthResult]:
    """
    Test the servers in parallel and return their results in the same order. The sites of a host are tested one
    at a time, so hosts serving many sites do not see a burst of logins (fail2ban, account lockout).
    `on_progress(done, failed)` is called after each result.
    """
    by_host: Dict[str, List[int]] = {}
    for index, srv in enumerate(servers):
        by_host.setdefault(srv.normalized_host, []).append(index)

    results: Dict[int, AuthResult] = {}
    lock = threading.Lock()
    stop = threading.Event()
    done = 0
    failed = 0

    def test_host(indexes: List[int]) -> None:
        nonlocal done, failed
        for index in indexes:
            if stop.is_set():
                return
            result = check(servers[index], timeout)
            with lock:
                results[index] = result
                done += 1
                failed += result.failed
                on_progress(done, failed)

    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        for future in [pool.submit(test_host, indexes) for indexes in by_host.values()]:
            future.result()
    except BaseException:
        # On Ctrl+C or a failing callback, stop starting tests instead of waiting for every remaining host.
        stop.set()
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown()
    return [results[index] for index in range(len(servers))]

def _password_credentials(server: Server) -> Tuple[str, str]:
    """Return the user and password to log in with. Raises _Untestable when the site does not save them."""
    if server.logontype == _LOGONTYPE_ANONYMOUS:
        if server.protocol == _SFTP:
            raise _Untestable("anonymous logon is FTP only")
        return _ANONYMOUS
    if server.logontype in _UNSUPPORTED_LOGONTYPES:
        raise _Untestable(f"the site {_UNSUPPORTED_LOGONTYPES[server.logontype]}")
    if server.logontype not in (None, _LOGONTYPE_NORMAL):
        raise _Untestable(f"logon type {server.logontype} is not supported")
    if not server.password:
        raise _Untestable("no password saved")
    return server.user, server.password

def _load_key(path: Optional[str]) -> paramiko.PKey:
    """Load the private key file. Raises _Untestable when it is missing or unreadable by paramiko."""
    if not path or not os.path.isfile(path):
        raise _Untestable("key file not found")
    try:
        return paramiko.PKey.from_path(path)
    except TypeError as e:
        # cryptography raises TypeError for an encrypted key loaded without its passphrase.
        raise _Untestable("the key file is protected by a passphrase") from e
    except (ValueError, paramiko.UnknownKeyType, paramiko.SSHException) as e:
        # Includes PuTTY .ppk keys, which paramiko cannot read.
        raise _Untestable("the key file format is not supported") from e
    except OSError as e:
        raise _Untestable(f"cannot read the key file: {e}") from e

def _check_sftp(server: Server, timeout: float) -> AuthResult:
    key = _load_key(server.keyfile) if server.uses_keyfile else None
    credentials = None if key else _password_credentials(server)

    transport = paramiko.Transport(socket.create_connection((server.host, server.port), timeout))
    try:
        transport.banner_timeout = timeout
        transport.auth_timeout = timeout
        # No host key check: only whether the saved credentials log in matters, and nothing is sent but them.
        transport.start_client(timeout=timeout)
        if key:
            transport.auth_publickey(server.user, key)
        else:
            # Falls back to keyboard-interactive, which many servers use for passwords.
            transport.auth_password(*credentials)
        if not transport.is_authenticated():
            return AuthResult(AuthStatus.OK, "another authentication factor is required")
        return AuthResult(AuthStatus.OK)
    finally:
        transport.close()

def _check_ftp(server: Server, timeout: float) -> AuthResult:
    if server.uses_keyfile:
        raise _Untestable("key file logon is SFTP only")
    user, password = _password_credentials(server)

    if server.protocol == _FTP_IMPLICIT_TLS:
        ftp = _ImplicitFTPTLS(context=_tls_context(), timeout=timeout)
    elif server.protocol == _FTP_PLAIN:
        ftp = ftplib.FTP(timeout=timeout)
    else:
        ftp = ftplib.FTP_TLS(context=_tls_context(), timeout=timeout)

    try:
        ftp.connect(server.host, server.port)
        if server.protocol in (_FTP_TLS_IF_AVAILABLE, _FTP_EXPLICIT_TLS):
            try:
                ftp.auth()
            except ftplib.error_perm:
                # Like FileZilla, protocol 0 goes on in plain FTP when the server refuses TLS.
                if server.protocol == _FTP_EXPLICIT_TLS:
                    return AuthResult(AuthStatus.ERROR, "the server refused TLS")
        try:
            if server.protocol == _FTP_PLAIN:
                ftp.login(user, password)
            else:
                # secure=False: FTP_TLS.login would otherwise send AUTH TLS itself, again or after a plain fallback.
                ftp.login(user, password, secure=False)
        except ftplib.error_perm:
            return AuthResult(AuthStatus.REJECTED)
        return AuthResult(AuthStatus.OK)
    finally:
        ftp.close()

def _tls_context() -> ssl.SSLContext:
    """Return a TLS context that skips certificate checks: FTP servers often use self-signed certificates."""
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context
