import ftplib
import logging
import os
import queue
import socket
import ssl
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from enum import Enum
from typing import Callable, Dict, Iterator, List, Optional, Protocol, Tuple, TypeVar
import paramiko
from filezilla_companion.filezilla.server import Server

DEFAULT_WORKERS = 16
DEFAULT_TIMEOUT = 10.0  # seconds, for each network step (connection, handshake, login)
_POLL_INTERVAL = 0.1  # seconds between two checks for Ctrl+C while check_all() waits for the tests

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

class _Failable(Protocol):
    """A result that run_all() can count."""

    @property
    def failed(self) -> bool: ...

_R = TypeVar("_R", bound=_Failable)

class Untestable(Exception):
    """Raised before any connection when the site cannot be tested; the message tells why."""

class _PartialLogin(Exception):
    """Raised when the server wants another authentication factor after the one given, so no session can start."""

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
        raise Untestable(f"protocol {server.protocol} is not supported")
    except Exception as e:
        return failure_result(e)

def failure_result(error: Exception) -> AuthResult:
    """Return the result standing for an exception raised while connecting to a server."""
    if isinstance(error, Untestable):
        return AuthResult(AuthStatus.UNTESTABLE, str(error))
    if isinstance(error, _PartialLogin):
        return AuthResult(AuthStatus.REJECTED, "another authentication factor is required")
    if isinstance(error, paramiko.BadAuthenticationType):
        return AuthResult(AuthStatus.REJECTED, f"the server only allows {', '.join(error.allowed_types)}")
    if isinstance(error, paramiko.AuthenticationException):
        return AuthResult(AuthStatus.REJECTED)
    if isinstance(error, socket.gaierror):
        return AuthResult(AuthStatus.HOST_NOT_FOUND)
    if isinstance(error, (socket.timeout, TimeoutError)):
        return AuthResult(AuthStatus.TIMEOUT)
    if isinstance(error, ConnectionRefusedError):
        return AuthResult(AuthStatus.REFUSED)
    if isinstance(error, (paramiko.SSHException, ftplib.Error, EOFError, OSError)):
        return AuthResult(AuthStatus.ERROR, str(error) or type(error).__name__)
    # A server misbehaving in a way the libraries do not anticipate must not abort the work on every other site: the
    # error is reported with the site instead.
    return AuthResult(AuthStatus.ERROR, f"{type(error).__name__}: {error}")

def check_all(
    servers: List[Server],
    workers: int,
    timeout: float,
    on_progress: Callable[[int, int], None],
) -> List[AuthResult]:
    """Test the servers in parallel with run_all() and return their results in the same order."""
    return run_all(servers, lambda server: check(server, timeout), workers, on_progress)

def run_all(
    servers: List[Server],
    task: Callable[[Server], _R],
    workers: int,
    on_progress: Callable[[int, int], None],
) -> List[_R]:
    """
    Run the task on the servers in parallel and return its results in the same order. The sites of a host are handled
    one at a time, so hosts serving many sites do not see a burst of logins (fail2ban, account lockout).
    `on_progress(done, failed)` is called after each result. On Ctrl+C or a failing callback, the exception is raised
    without waiting for the tasks in progress, which then end in the background without reporting.
    """
    by_host: Dict[str, List[int]] = {}
    for index, srv in enumerate(servers):
        by_host.setdefault(srv.normalized_host, []).append(index)
    hosts: "queue.SimpleQueue[List[int]]" = queue.SimpleQueue()
    for indexes in by_host.values():
        hosts.put(indexes)

    results: Dict[int, _R] = {}
    errors: List[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()
    ended = threading.Semaphore(0)  # released by each thread on its way out
    done = 0
    failed = 0

    def run_hosts() -> None:
        nonlocal done, failed
        try:
            while True:
                try:
                    indexes = hosts.get_nowait()
                except queue.Empty:
                    return
                for index in indexes:
                    if stop.is_set():
                        return
                    result = task(servers[index])
                    with lock:
                        # Checked again: run_all() may have given up during the task.
                        if stop.is_set():
                            return
                        results[index] = result
                        done += 1
                        failed += result.failed
                        on_progress(done, failed)
        except BaseException as e:
            # Raised again by run_all(), in the caller's thread.
            errors.append(e)
            stop.set()
        finally:
            ended.release()

    # Daemon threads, unlike ThreadPoolExecutor's: Python exits without waiting for the tasks in progress, which
    # can each last several timeouts (connection, handshake, login).
    threads = [threading.Thread(target=run_hosts, daemon=True) for _ in range(min(workers, len(by_host)))]
    try:
        for thread in threads:
            thread.start()
        for _ in threads:
            # Timed waits: on Windows, Ctrl+C does not interrupt a wait without timeout. Not Thread.join(): on some
            # Python versions (3.10 at least), interrupting it marks the thread as stopped while it still runs.
            while not ended.acquire(timeout=_POLL_INTERVAL):
                pass
            if errors:
                break
    except BaseException:
        # Under the lock, so no progress line is printed once the caller handles the exception.
        with lock:
            stop.set()
        raise
    if errors:
        raise errors[0]
    return [results[index] for index in range(len(servers))]

def _password_credentials(server: Server) -> Tuple[str, str]:
    """Return the user and password to log in with. Raises Untestable when the site does not save them."""
    if server.logontype == _LOGONTYPE_ANONYMOUS:
        if server.protocol == _SFTP:
            raise Untestable("anonymous logon is FTP only")
        return _ANONYMOUS
    if server.logontype in _UNSUPPORTED_LOGONTYPES:
        raise Untestable(f"the site {_UNSUPPORTED_LOGONTYPES[server.logontype]}")
    if server.logontype not in (None, _LOGONTYPE_NORMAL):
        raise Untestable(f"logon type {server.logontype} is not supported")
    if not server.password:
        raise Untestable("no password saved")
    return server.user, server.password

def load_key(path: Optional[str]) -> paramiko.PKey:
    """Load the private key file. Raises Untestable when it is missing or unreadable by paramiko."""
    if not path or not os.path.isfile(path):
        raise Untestable("key file not found")
    try:
        return paramiko.PKey.from_path(path)
    except TypeError as e:
        # cryptography raises TypeError for an encrypted key loaded without its passphrase.
        raise Untestable("the key file is protected by a passphrase") from e
    except (ValueError, paramiko.UnknownKeyType, paramiko.SSHException) as e:
        # Includes PuTTY .ppk keys, which paramiko cannot read.
        raise Untestable("the key file format is not supported") from e
    except OSError as e:
        raise Untestable(f"cannot read the key file: {e}") from e

def _sftp_credentials(server: Server) -> Tuple[Optional[paramiko.PKey], Optional[Tuple[str, str]]]:
    """Return the key, or else the user and password, to log in with. Raises Untestable when neither is usable."""
    key = load_key(server.keyfile) if server.uses_keyfile else None
    return key, None if key else _password_credentials(server)

@contextmanager
def _connected_transport(server: Server, timeout: float) -> Iterator[paramiko.Transport]:
    """Yield a transport connected to the server and not logged in yet, and close it afterwards."""
    transport = paramiko.Transport(socket.create_connection((server.host, server.port), timeout))
    try:
        transport.banner_timeout = timeout
        transport.auth_timeout = timeout
        transport.channel_timeout = timeout
        # No host key check: the saved credentials go to whatever answers at the address.
        transport.start_client(timeout=timeout)
        yield transport
    finally:
        transport.close()

def _log_in(
    transport: paramiko.Transport,
    server: Server,
    key: Optional[paramiko.PKey],
    credentials: Optional[Tuple[str, str]],
) -> None:
    if key:
        transport.auth_publickey(server.user, key)
    else:
        # Falls back to keyboard-interactive, which many servers use for passwords.
        transport.auth_password(*credentials)

def _check_sftp(server: Server, timeout: float) -> AuthResult:
    key, credentials = _sftp_credentials(server)
    with _connected_transport(server, timeout) as transport:
        _log_in(transport, server, key, credentials)
        if not transport.is_authenticated():
            return AuthResult(AuthStatus.OK, "another authentication factor is required")
        return AuthResult(AuthStatus.OK)

def sftp_login_problem(server: Server) -> Optional[str]:
    """Return why sftp_session() cannot log in to the site with what it saves, or None when it can try."""
    if server.protocol != _SFTP:
        return f"protocol {server.protocol} is not SFTP"
    try:
        _sftp_credentials(server)
    except Untestable as e:
        return str(e)
    return None

@contextmanager
def sftp_session(server: Server, timeout: float) -> Iterator[paramiko.SFTPClient]:
    """
    Log in to the site with its saved credentials and yield an SFTP client, then disconnect. Raises the exceptions
    that failure_result() handles.
    """
    key, credentials = _sftp_credentials(server)
    with _connected_transport(server, timeout) as transport:
        _log_in(transport, server, key, credentials)
        if not transport.is_authenticated():
            raise _PartialLogin()
        client = paramiko.SFTPClient.from_transport(transport)
        # Without a timeout, a server that stops answering would block its worker thread forever.
        client.get_channel().settimeout(timeout)
        yield client

def check_key(server: Server, key: paramiko.PKey, timeout: float) -> AuthResult:
    """Log in to the site with the key alone, whatever it saves, disconnect, and return the outcome."""
    try:
        with _connected_transport(server, timeout) as transport:
            transport.auth_publickey(server.user, key)
            if not transport.is_authenticated():
                raise _PartialLogin()
            return AuthResult(AuthStatus.OK)
    except Exception as e:
        return failure_result(e)

def _check_ftp(server: Server, timeout: float) -> AuthResult:
    if server.uses_keyfile:
        raise Untestable("key file logon is SFTP only")
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
