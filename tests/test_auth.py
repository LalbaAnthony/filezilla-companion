import _thread
import ftplib
import os
import socket
import ssl
import tempfile
import threading
import time
import unittest
from unittest import mock

import paramiko
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from filezilla_companion import auth
from filezilla_companion.auth import AuthResult, AuthStatus
from filezilla_companion.filezilla.server import Server


def _server(**overrides) -> Server:
    fields = dict(name="prod", host="example.com", port=22, protocol=1, user="deploy", password="secret", logontype=1)
    fields.update(overrides)
    return Server(**fields)


def _write_key(directory: str, encryption: serialization.KeySerializationEncryption) -> str:
    path = os.path.join(directory, "id_ed25519")
    with open(path, "wb") as f:
        f.write(ed25519.Ed25519PrivateKey.generate().private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.OpenSSH, encryption,
        ))
    return path


class AuthResultTest(unittest.TestCase):
    def test_only_attempted_logins_can_fail(self):
        self.assertFalse(AuthResult(AuthStatus.OK).failed)
        self.assertFalse(AuthResult(AuthStatus.UNTESTABLE, "no password saved").failed)
        for status in (AuthStatus.REJECTED, AuthStatus.HOST_NOT_FOUND, AuthStatus.TIMEOUT, AuthStatus.REFUSED, AuthStatus.ERROR):
            with self.subTest(status=status):
                self.assertTrue(AuthResult(status).failed)

    def test_reason_appends_the_detail(self):
        self.assertEqual(AuthResult(AuthStatus.TIMEOUT).reason, "timed out")
        self.assertEqual(AuthResult(AuthStatus.ERROR, "reset").reason, "connection failed: reset")


class UntestableTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name
        patches = [
            mock.patch.object(auth.socket, "create_connection"),
            mock.patch.object(auth.ftplib, "FTP_TLS"),
            mock.patch.object(auth.ftplib, "FTP"),
        ]
        self.connections = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _assert_untestable(self, server: Server, detail: str) -> None:
        self.assertEqual(auth.check(server, 10.0), AuthResult(AuthStatus.UNTESTABLE, detail))
        for connection in self.connections:
            connection.assert_not_called()

    def test_unsupported_protocol(self):
        self._assert_untestable(_server(protocol=2, port=80), "protocol 2 is not supported")

    def test_logon_types_without_saved_password(self):
        cases = [
            (2, "the site asks for the password at login"),
            (3, "the site uses interactive login"),
            (4, "the site logs in with an account"),
            (6, "logon type 6 is not supported"),
        ]
        for logontype, detail in cases:
            with self.subTest(logontype=logontype):
                self._assert_untestable(_server(logontype=logontype), detail)

    def test_no_password(self):
        self._assert_untestable(_server(password=None), "no password saved")

    def test_anonymous_sftp(self):
        self._assert_untestable(_server(logontype=0, password=None), "anonymous logon is FTP only")

    def test_key_logon_over_ftp(self):
        self._assert_untestable(_server(protocol=0, port=21, logontype=5, keyfile="key"), "key file logon is SFTP only")

    def test_missing_key_file(self):
        self._assert_untestable(
            _server(logontype=5, password=None, keyfile=os.path.join(self.tmp, "gone")), "key file not found",
        )

    def test_putty_key(self):
        path = os.path.join(self.tmp, "key.ppk")
        with open(path, "w", encoding="utf-8") as f:
            f.write("PuTTY-User-Key-File-3: ssh-ed25519\nEncryption: none\n")

        self._assert_untestable(_server(logontype=5, keyfile=path), "the key file format is not supported")

    def test_key_with_passphrase(self):
        path = _write_key(self.tmp, serialization.BestAvailableEncryption(b"passphrase"))

        self._assert_untestable(_server(logontype=5, keyfile=path), "the key file is protected by a passphrase")


class SftpTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(auth.socket, "create_connection"),
            mock.patch.object(auth.paramiko, "Transport"),
        ]
        self.create_connection, transport_class = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.transport = transport_class.return_value
        self.transport.is_authenticated.return_value = True

    def test_logs_in_with_the_password(self):
        self.assertEqual(auth.check(_server(port=2222), 7.0), AuthResult(AuthStatus.OK))

        self.create_connection.assert_called_once_with(("example.com", 2222), 7.0)
        self.transport.start_client.assert_called_once_with(timeout=7.0)
        self.assertEqual((self.transport.banner_timeout, self.transport.auth_timeout), (7.0, 7.0))
        self.transport.auth_password.assert_called_once_with("deploy", "secret")
        self.transport.close.assert_called_once()

    def test_logs_in_with_the_key_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = _write_key(tmp, serialization.NoEncryption())

            self.assertEqual(auth.check(_server(logontype=5, password=None, keyfile=path), 10.0).status, AuthStatus.OK)

        user, key = self.transport.auth_publickey.call_args.args
        self.assertEqual(user, "deploy")
        self.assertIsInstance(key, paramiko.Ed25519Key)
        self.transport.auth_password.assert_not_called()

    def test_partial_authentication_accepts_the_credentials(self):
        self.transport.is_authenticated.return_value = False

        self.assertEqual(
            auth.check(_server(), 10.0),
            AuthResult(AuthStatus.OK, "another authentication factor is required"),
        )

    def test_maps_connection_errors(self):
        cases = [
            (socket.gaierror(11001, "getaddrinfo failed"), AuthResult(AuthStatus.HOST_NOT_FOUND)),
            (socket.timeout("timed out"), AuthResult(AuthStatus.TIMEOUT)),
            (TimeoutError(10060, "no answer"), AuthResult(AuthStatus.TIMEOUT)),
            (ConnectionRefusedError(10061, "refused"), AuthResult(AuthStatus.REFUSED)),
            (OSError("network unreachable"), AuthResult(AuthStatus.ERROR, "network unreachable")),
        ]
        for error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.create_connection.side_effect = error
                self.assertEqual(auth.check(_server(), 10.0), expected)

    def test_maps_ssh_errors_and_closes_the_transport(self):
        cases = [
            ("auth_password", paramiko.AuthenticationException("Authentication failed."), AuthResult(AuthStatus.REJECTED)),
            (
                "auth_password",
                paramiko.BadAuthenticationType("Bad authentication type", ["publickey"]),
                AuthResult(AuthStatus.REJECTED, "the server only allows publickey"),
            ),
            (
                "start_client",
                paramiko.SSHException("Error reading SSH protocol banner"),
                AuthResult(AuthStatus.ERROR, "Error reading SSH protocol banner"),
            ),
            ("start_client", EOFError(), AuthResult(AuthStatus.ERROR, "EOFError")),
            ("start_client", RuntimeError("boom"), AuthResult(AuthStatus.ERROR, "RuntimeError: boom")),
        ]
        for method, error, expected in cases:
            with self.subTest(error=type(error).__name__):
                self.transport.reset_mock()
                self.transport.start_client.side_effect = None
                self.transport.auth_password.side_effect = None
                getattr(self.transport, method).side_effect = error

                self.assertEqual(auth.check(_server(), 10.0), expected)
                self.transport.close.assert_called_once()


class FtpTest(unittest.TestCase):
    def setUp(self):
        patches = [
            mock.patch.object(auth.ftplib, "FTP_TLS"),
            mock.patch.object(auth.ftplib, "FTP"),
            mock.patch.object(auth, "_ImplicitFTPTLS"),
        ]
        self.ftp_tls, self.ftp, self.implicit = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _check(self, **overrides) -> AuthResult:
        fields = dict(protocol=0, port=21)
        fields.update(overrides)
        return auth.check(_server(**fields), 10.0)

    def test_tls_if_available_logs_in_over_tls_without_checking_the_certificate(self):
        self.assertEqual(self._check(), AuthResult(AuthStatus.OK))

        context = self.ftp_tls.call_args.kwargs["context"]
        self.assertEqual((context.check_hostname, context.verify_mode), (False, ssl.CERT_NONE))
        self.assertEqual(self.ftp_tls.call_args.kwargs["timeout"], 10.0)
        session = self.ftp_tls.return_value
        session.connect.assert_called_once_with("example.com", 21)
        session.auth.assert_called_once()
        session.login.assert_called_once_with("deploy", "secret", secure=False)
        session.close.assert_called_once()

    def test_tls_if_available_falls_back_to_plain_ftp(self):
        session = self.ftp_tls.return_value
        session.auth.side_effect = ftplib.error_perm("500 AUTH not understood")

        self.assertEqual(self._check(), AuthResult(AuthStatus.OK))

        session.login.assert_called_once_with("deploy", "secret", secure=False)

    def test_required_tls_refused_is_an_error(self):
        session = self.ftp_tls.return_value
        session.auth.side_effect = ftplib.error_perm("500 AUTH not understood")

        self.assertEqual(self._check(protocol=4), AuthResult(AuthStatus.ERROR, "the server refused TLS"))

        session.login.assert_not_called()
        session.close.assert_called_once()

    def test_plain_ftp(self):
        self.assertEqual(self._check(protocol=6), AuthResult(AuthStatus.OK))

        self.ftp.assert_called_once_with(timeout=10.0)
        self.ftp.return_value.login.assert_called_once_with("deploy", "secret")
        self.ftp_tls.assert_not_called()

    def test_implicit_tls(self):
        self.assertEqual(self._check(protocol=3, port=990), AuthResult(AuthStatus.OK))

        session = self.implicit.return_value
        session.connect.assert_called_once_with("example.com", 990)
        session.auth.assert_not_called()
        session.login.assert_called_once_with("deploy", "secret", secure=False)

    def test_rejected_login(self):
        self.ftp_tls.return_value.login.side_effect = ftplib.error_perm("530 Login incorrect.")

        self.assertEqual(self._check(), AuthResult(AuthStatus.REJECTED))

    def test_anonymous_logon(self):
        self.assertEqual(self._check(logontype=0, password=None), AuthResult(AuthStatus.OK))

        self.ftp_tls.return_value.login.assert_called_once_with("anonymous", "anonymous@example.com", secure=False)

    def test_server_error_reply(self):
        self.ftp_tls.return_value.connect.side_effect = ftplib.error_temp("421 Too many connections")

        self.assertEqual(self._check(), AuthResult(AuthStatus.ERROR, "421 Too many connections"))


class ImplicitFtpTlsTest(unittest.TestCase):
    def test_wraps_the_socket_as_soon_as_it_is_set(self):
        context = mock.Mock()
        ftp = auth._ImplicitFTPTLS(context=context)
        ftp.host = "example.com"
        raw = mock.Mock()

        ftp.sock = raw

        context.wrap_socket.assert_called_once_with(raw, server_hostname="example.com")
        self.assertIs(ftp.sock, context.wrap_socket.return_value)
        ftp.sock = None
        self.assertIsNone(ftp.sock)


class CheckAllTest(unittest.TestCase):
    def test_returns_results_in_order_and_reports_progress(self):
        servers = [_server(name=str(i), host=f"host{i}.example") for i in range(4)]
        results = {
            "0": AuthResult(AuthStatus.OK),
            "1": AuthResult(AuthStatus.REJECTED),
            "2": AuthResult(AuthStatus.UNTESTABLE, "no password saved"),
            "3": AuthResult(AuthStatus.TIMEOUT),
        }
        progress = []

        with mock.patch.object(auth, "check", side_effect=lambda srv, timeout: results[srv.name]):
            self.assertEqual(
                auth.check_all(servers, 2, 10.0, lambda done, failed: progress.append((done, failed))),
                [results[srv.name] for srv in servers],
            )

        self.assertEqual([done for done, _ in progress], [1, 2, 3, 4])
        self.assertEqual(progress[-1], (4, 2))

    def test_tests_the_sites_of_a_host_one_at_a_time(self):
        servers = [_server(host=host) for host in ("a.example", "A.example ", "a.example", "b.example", "b.example")]
        lock = threading.Lock()
        active = {}
        peaks = {}

        def check(srv, timeout):
            with lock:
                active[srv.normalized_host] = active.get(srv.normalized_host, 0) + 1
                peaks[srv.normalized_host] = max(peaks.get(srv.normalized_host, 0), active[srv.normalized_host])
            time.sleep(0.02)
            with lock:
                active[srv.normalized_host] -= 1
            return AuthResult(AuthStatus.OK)

        with mock.patch.object(auth, "check", side_effect=check):
            auth.check_all(servers, 5, 10.0, lambda done, failed: None)

        self.assertEqual(peaks, {"a.example": 1, "b.example": 1})

    def test_callback_failure_propagates(self):
        with mock.patch.object(auth, "check", return_value=AuthResult(AuthStatus.OK)), \
                self.assertRaises(RuntimeError):
            auth.check_all([_server()], 1, 10.0, mock.Mock(side_effect=RuntimeError("stop")))

    def test_ctrl_c_raises_without_waiting_for_the_test_in_progress(self):
        servers = [_server(name=str(i), host=f"host{i}.example") for i in range(2)]
        release = threading.Event()
        returned = threading.Event()
        workers = []
        progress = mock.Mock()

        def check(srv, timeout):
            workers.append(threading.current_thread())
            # Once check_all() waits for the tests: an earlier interrupt would not exercise that wait.
            time.sleep(0.2)
            # What Ctrl+C does to the main thread.
            _thread.interrupt_main()
            # Bounded, so a check_all() that waits for this test fails the assertions below instead of hanging.
            release.wait(5)
            returned.set()
            return AuthResult(AuthStatus.OK)

        with mock.patch.object(auth, "check", side_effect=check) as check_:
            with self.assertRaises(KeyboardInterrupt):
                auth.check_all(servers, 1, 10.0, progress)
            self.assertFalse(returned.is_set())
            release.set()
            workers[0].join(5)
            self.assertFalse(workers[0].is_alive())

        # Daemon, so Python exits without waiting for it; the queued host is never tested.
        self.assertTrue(workers[0].daemon)
        self.assertEqual(check_.call_count, 1)
        progress.assert_not_called()


if __name__ == "__main__":
    unittest.main()
