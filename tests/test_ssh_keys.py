import base64
import io
import os
import stat
import struct
import tempfile
import unittest
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from typing import Dict, List, Optional
from unittest import mock

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519
from filezilla_companion import auth, ssh_keys
from filezilla_companion.auth import AuthResult, AuthStatus
from filezilla_companion.filezilla.server import Server
from filezilla_companion.ssh_keys import DeployResult, PublicKey


def _blob(algorithm: str) -> str:
    """Return a base64 blob that starts with the key type, like a real key's."""
    name = algorithm.encode("ascii")
    return base64.b64encode(struct.pack(">I", len(name)) + name + b"key-data").decode("ascii")


def _key(path: str = "/home/me/.ssh/id_ed25519.pub", comment: str = "me@laptop") -> PublicKey:
    return PublicKey(path, "ssh-ed25519", _blob("ssh-ed25519"), comment)


def _server(**overrides) -> Server:
    fields = dict(name="prod", host="example.com", port=22, protocol=1, user="deploy", password="secret", logontype=1)
    fields.update(overrides)
    return Server(**fields)


class _FakeHome(unittest.TestCase):
    """A fake home directory, so tests never read the real ~/.ssh."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.home = tmp.name
        self.ssh = os.path.join(self.home, ".ssh")
        patches = [
            mock.patch.dict(os.environ, {"HOME": self.home, "USERPROFILE": self.home}),
            mock.patch("sys.stdout", new_callable=io.StringIO),
        ]
        _, self.stdout = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _write(self, name: str, text: str, age: int = 0) -> str:
        os.makedirs(self.ssh, exist_ok=True)
        path = os.path.join(self.ssh, name)
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        if age:
            modified = os.path.getmtime(path) - age
            os.utime(path, (modified, modified))
        return path

    def _write_pub(self, name: str, algorithm: str = "ssh-ed25519", age: int = 0) -> str:
        return self._write(name, f"{algorithm} {_blob(algorithm)} comment\n", age)

    def _write_pair(self, name: str, encryption=None) -> PublicKey:
        """Write a real key pair, and return its public key."""
        private = ed25519.Ed25519PrivateKey.generate()
        path = os.path.join(self.ssh, name)
        os.makedirs(self.ssh, exist_ok=True)
        with open(path, "wb") as f:
            f.write(private.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.OpenSSH,
                encryption or serialization.NoEncryption(),
            ))
        public = private.public_key().public_bytes(serialization.Encoding.OpenSSH, serialization.PublicFormat.OpenSSH)
        with open(f"{path}.pub", "wb") as f:
            f.write(public + b" me@laptop\n")
        return next(key for key in ssh_keys.list_public_keys() if key.name == f"{name}.pub")


class ListPublicKeysTest(_FakeHome):
    def test_missing_directory_gives_no_key(self):
        self.assertEqual(ssh_keys.list_public_keys(), [])

    def test_prefers_standard_names_then_algorithm_then_most_recent(self):
        self._write_pub("zz_other.pub", "sk-ssh-ed25519@openssh.com")
        self._write_pub("custom_rsa.pub", "ssh-rsa")
        self._write_pub("custom_ecdsa.pub", "ecdsa-sha2-nistp256")
        self._write_pub("old_ed25519.pub", "ssh-ed25519", age=1000)
        self._write_pub("new_ed25519.pub", "ssh-ed25519")
        self._write_pub("id_rsa.pub", "ssh-rsa", age=5000)
        self._write_pub("id_ecdsa.pub", "ecdsa-sha2-nistp256", age=5000)
        self._write_pub("id_ed25519.pub", "ssh-ed25519", age=5000)

        self.assertEqual(
            [key.name for key in ssh_keys.list_public_keys()],
            [
                "id_ed25519.pub",
                "id_ecdsa.pub",
                "id_rsa.pub",
                "new_ed25519.pub",
                "old_ed25519.pub",
                "custom_ecdsa.pub",
                "custom_rsa.pub",
                "zz_other.pub",
            ],
        )

    def test_a_standard_name_wins_over_a_newer_and_more_modern_key(self):
        self._write_pub("id_rsa.pub", "ssh-rsa", age=5000)
        self._write_pub("work.pub", "ssh-ed25519")

        self.assertEqual([key.name for key in ssh_keys.list_public_keys()], ["id_rsa.pub", "work.pub"])

    def test_a_key_without_its_private_file_is_listed(self):
        self._write_pub("id_ed25519.pub")

        self.assertEqual([key.name for key in ssh_keys.list_public_keys()], ["id_ed25519.pub"])

    def test_skips_invalid_files_with_a_warning(self):
        self._write("empty.pub", "")
        self._write("one_word.pub", "ssh-ed25519\n")
        self._write("putty.pub", "---- BEGIN SSH2 PUBLIC KEY ----\nAAAA\n---- END SSH2 PUBLIC KEY ----\n")
        self._write("bad_base64.pub", "ssh-ed25519 not*base64 comment\n")
        self._write("short.pub", "ssh-ed25519 AAAA comment\n")
        self._write("wrong_type.pub", f"ssh-ed25519 {_blob('ssh-rsa')} comment\n")

        self.assertEqual(ssh_keys.list_public_keys(), [])

        output = self.stdout.getvalue()
        for name in ("empty", "one_word", "putty", "bad_base64", "short", "wrong_type"):
            self.assertIn(f"Skipping {name}.pub: not an OpenSSH public key.", output)

    def test_skips_a_file_that_is_not_text(self):
        os.makedirs(self.ssh)
        with open(os.path.join(self.ssh, "binary.pub"), "wb") as f:
            f.write(b"\xff\xfe\x00")

        self.assertEqual(ssh_keys.list_public_keys(), [])

        self.assertIn("Skipping binary.pub:", self.stdout.getvalue())

    def test_ignores_other_files_and_directories(self):
        self._write("known_hosts", "x")
        self._write("id_ed25519", "private")
        os.makedirs(os.path.join(self.ssh, "folder.pub"))

        self.assertEqual(ssh_keys.list_public_keys(), [])
        self.assertEqual(self.stdout.getvalue(), "")


class PublicKeyTest(unittest.TestCase):
    def test_line_keeps_a_comment_with_spaces(self):
        self.assertEqual(_key(comment="my laptop key").line, f"ssh-ed25519 {_blob('ssh-ed25519')} my laptop key")

    def test_line_without_comment_has_no_trailing_space(self):
        self.assertEqual(_key(comment="").line, f"ssh-ed25519 {_blob('ssh-ed25519')}")

    def test_label_shows_the_name_algorithm_and_comment(self):
        self.assertEqual(_key().label, "id_ed25519.pub (ssh-ed25519, me@laptop)")
        self.assertEqual(_key(comment="").label, "id_ed25519.pub (ssh-ed25519)")

    def test_private_path_drops_the_suffix(self):
        self.assertEqual(_key().private_path, "/home/me/.ssh/id_ed25519")


class LoadPrivateKeyTest(_FakeHome):
    def test_returns_the_key_of_the_pair(self):
        key = self._write_pair("id_ed25519")

        private = ssh_keys.load_private_key(key)

        self.assertEqual(private.asbytes(), base64.b64decode(key.blob))

    def test_missing_private_file(self):
        self._write_pub("id_ed25519.pub")
        key = ssh_keys.list_public_keys()[0]

        with self.assertRaisesRegex(ssh_keys.KeyUnavailable, "key file not found"):
            ssh_keys.load_private_key(key)

    def test_private_key_of_another_pair(self):
        key = self._write_pair("id_ed25519")
        self._write_pair("other")
        os.replace(os.path.join(self.ssh, "other"), key.private_path)

        with self.assertRaisesRegex(ssh_keys.KeyUnavailable, "does not match"):
            ssh_keys.load_private_key(key)

    def test_key_protected_by_a_passphrase(self):
        key = self._write_pair("id_ed25519", serialization.BestAvailableEncryption(b"passphrase"))

        # Not the message: which exception reports the passphrase depends on the cryptography version.
        with self.assertRaises(ssh_keys.KeyUnavailable):
            ssh_keys.load_private_key(key)


class CanDeployTest(_FakeHome):
    def test_sftp_site_with_a_password(self):
        self.assertTrue(ssh_keys.can_deploy(_server(), _key()))

    def test_ftp_site(self):
        self.assertFalse(ssh_keys.can_deploy(_server(protocol=0, port=21), _key()))

    def test_site_without_usable_credentials(self):
        for overrides in ({"password": None}, {"logontype": 2}, {"logontype": 0}):
            with self.subTest(overrides=overrides):
                self.assertFalse(ssh_keys.can_deploy(_server(**overrides), _key()))

    def test_site_using_another_readable_key(self):
        other = self._write_pair("other")

        self.assertTrue(ssh_keys.can_deploy(_server(logontype=5, password=None, keyfile=other.private_path), _key()))

    def test_site_using_a_key_that_cannot_be_read(self):
        site = _server(logontype=5, password=None, keyfile=os.path.join(self.ssh, "gone"))

        self.assertFalse(ssh_keys.can_deploy(site, _key()))

    def test_site_already_using_this_key(self):
        key = self._write_pair("id_ed25519")
        unnormalized = os.path.join(self.ssh, "..", ".ssh", "id_ed25519")

        self.assertFalse(ssh_keys.can_deploy(_server(logontype=5, password=None, keyfile=unnormalized), key))

    def test_keyfile_ignored_by_a_password_logon_does_not_count_as_using_it(self):
        key = self._write_pair("id_ed25519")

        self.assertTrue(ssh_keys.can_deploy(_server(logontype=1, keyfile=key.private_path), key))

    def test_password_encrypted_by_the_master_password(self):
        element = ET.fromstring('<Server><Pass encoding="crypt" pubkey="abc">ZZZ</Pass></Server>')

        self.assertFalse(ssh_keys.can_deploy(_server(element=element), _key()))

    def test_password_in_base64(self):
        element = ET.fromstring('<Server><Pass encoding="base64">c2VjcmV0</Pass></Server>')

        self.assertTrue(ssh_keys.can_deploy(_server(element=element), _key()))


class _FakeFile:
    def __init__(self, sftp: "_FakeSftp", path: str) -> None:
        self.sftp = sftp
        self.path = path

    def __enter__(self) -> "_FakeFile":
        return self

    def __exit__(self, *exc_info) -> None:
        pass

    def read(self) -> bytes:
        return self.sftp.files[self.path]

    def write(self, data: bytes) -> None:
        self.sftp.calls.append(f"write {self.path}")
        self.sftp.files[self.path] += data

    def chmod(self, mode: int) -> None:
        self.sftp.calls.append(f"chmod {self.path} {mode:o}")
        self.sftp.modes[self.path] = mode


class _FakeSftp:
    """An in-memory stand-in for paramiko.SFTPClient, raising what it raises for a missing path."""

    def __init__(self, files: Optional[Dict[str, bytes]] = None, modes: Optional[Dict[str, int]] = None) -> None:
        self.files = dict(files or {})
        self.modes = dict(modes or {})
        self.dirs = {os.path.dirname(path) for path in self.files}
        self.calls: List[str] = []
        self.rename_error: Optional[Exception] = None
        self.remove_error: Optional[Exception] = None

    def stat(self, path: str) -> mock.Mock:
        if path in self.dirs:
            return mock.Mock(st_mode=stat.S_IFDIR | self.modes.get(path, 0o755))
        if path in self.files:
            return mock.Mock(st_mode=stat.S_IFREG | self.modes.get(path, 0o644))
        raise FileNotFoundError(2, "No such file")

    def mkdir(self, path: str, mode: int) -> None:
        self.calls.append(f"mkdir {path} {mode:o}")
        self.dirs.add(path)
        self.modes[path] = mode

    def rmdir(self, path: str) -> None:
        self.calls.append(f"rmdir {path}")
        self.dirs.remove(path)

    def remove(self, path: str) -> None:
        self.calls.append(f"remove {path}")
        if self.remove_error:
            raise self.remove_error
        del self.files[path]

    def open(self, path: str, mode: str) -> _FakeFile:
        if mode == "r" and path not in self.files:
            raise FileNotFoundError(2, "No such file")
        if mode == "w" or path not in self.files:
            self.files[path] = b""
        return _FakeFile(self, path)

    def posix_rename(self, source: str, target: str) -> None:
        self.calls.append(f"rename {source} {target}")
        if self.rename_error:
            raise self.rename_error
        self.files[target] = self.files.pop(source)
        self.modes[target] = self.modes.pop(source)


_DIR = ".ssh"
_FILE = ".ssh/authorized_keys"
_TMP = ".ssh/authorized_keys.filezilla-companion.tmp"
_PRIVATE = object()


class DeployTest(unittest.TestCase):
    def setUp(self):
        self.key = _key()
        self.line = self.key.line.encode("ascii")
        self.server = _server()

    def _deploy(
        self,
        sftp: _FakeSftp,
        login: AuthResult = AuthResult(AuthStatus.OK),
        private: object = _PRIVATE,
    ) -> DeployResult:
        @contextmanager
        def session(server, timeout):
            self.assertIs(server, self.server)
            self.assertEqual(timeout, 7.0)
            yield sftp

        with mock.patch.object(auth, "sftp_session", session), \
                mock.patch.object(auth, "check_key", return_value=login) as self.check_key:
            return ssh_keys.deploy(self.server, self.key, private, 7.0)

    def test_creates_the_directory_and_the_file_private(self):
        sftp = _FakeSftp()

        result = self._deploy(sftp)

        self.assertEqual(result, DeployResult("key added, key login verified", verified=True))
        self.assertEqual(sftp.files[_FILE], self.line + b"\n")
        self.assertEqual(sftp.calls, [f"mkdir {_DIR} 700", f"chmod {_FILE} 600", f"write {_FILE}"])
        self.check_key.assert_called_once_with(self.server, _PRIVATE, 7.0)

    def test_creates_the_file_in_an_existing_directory(self):
        sftp = _FakeSftp()
        sftp.dirs.add(_DIR)

        self.assertTrue(self._deploy(sftp).verified)

        self.assertEqual(sftp.calls, [f"chmod {_FILE} 600", f"write {_FILE}"])

    def test_appends_after_a_final_newline_and_keeps_the_modes(self):
        sftp = _FakeSftp({_FILE: b"ssh-rsa OTHER other\n"}, {_FILE: 0o640, _DIR: 0o750})

        self.assertTrue(self._deploy(sftp).verified)

        self.assertEqual(sftp.files[_FILE], b"ssh-rsa OTHER other\n" + self.line + b"\n")
        self.assertEqual(sftp.calls, [f"write {_FILE}"])
        self.assertEqual((sftp.modes[_FILE], sftp.modes[_DIR]), (0o640, 0o750))

    def test_appends_on_a_new_line_without_a_final_newline(self):
        sftp = _FakeSftp({_FILE: b"ssh-rsa OTHER other"})

        self._deploy(sftp)

        self.assertEqual(sftp.files[_FILE], b"ssh-rsa OTHER other\n" + self.line + b"\n")

    def test_finds_the_key_whatever_its_comment_and_options(self):
        cases = {
            "same line": self.line + b"\n",
            "other comment": f"ssh-ed25519 {self.key.blob} someone-else\n".encode("ascii"),
            "options": f'no-pty,from="10.0.0.1" ssh-ed25519 {self.key.blob}\n'.encode("ascii"),
            "windows line ending": self.line + b"\r\n",
        }
        for label, content in cases.items():
            with self.subTest(label):
                sftp = _FakeSftp({_FILE: content})

                result = self._deploy(sftp)

                self.assertEqual(result, DeployResult("key already present, key login verified", verified=True))
                self.assertEqual(sftp.files[_FILE], content)
                self.assertEqual(sftp.calls, [])

    def test_a_commented_out_key_does_not_count(self):
        content = b"# " + self.line + b"\n"
        sftp = _FakeSftp({_FILE: content})

        self.assertEqual(self._deploy(sftp).detail, "key added, key login verified")

        self.assertEqual(sftp.files[_FILE], content + self.line + b"\n")

    def test_without_private_key_deploys_without_testing(self):
        sftp = _FakeSftp()

        result = self._deploy(sftp, private=None)

        self.assertEqual(result, DeployResult("key added, not verified"))
        self.assertEqual(sftp.files[_FILE], self.line + b"\n")
        self.check_key.assert_not_called()

    def test_without_private_key_on_a_key_already_present(self):
        result = self._deploy(_FakeSftp({_FILE: self.line + b"\n"}), private=None)

        self.assertEqual(result, DeployResult("key already present, not verified"))

    def test_failed_login_removes_the_added_line_and_keeps_the_rest(self):
        original = b"# keep me\r\nssh-rsa OTHER other\n\nlast line without newline"
        sftp = _FakeSftp({_FILE: original}, {_FILE: 0o640})

        result = self._deploy(sftp, login=AuthResult(AuthStatus.REJECTED))

        self.assertEqual(result, DeployResult("key login failed: credentials rejected. The key was removed", failed=True))
        self.assertEqual(sftp.files[_FILE], original + b"\n")
        self.assertEqual(sftp.modes[_FILE], 0o640)
        self.assertNotIn(_TMP, sftp.files)
        self.assertEqual(sftp.calls[-1], f"rename {_TMP} {_FILE}")

    def test_failed_login_removes_what_was_created(self):
        sftp = _FakeSftp()

        result = self._deploy(sftp, login=AuthResult(AuthStatus.TIMEOUT))

        self.assertEqual(result, DeployResult("key login failed: timed out. The key was removed", failed=True))
        self.assertEqual(sftp.files, {})
        self.assertEqual(sftp.dirs, set())

    def test_failed_login_keeps_a_directory_that_existed(self):
        sftp = _FakeSftp()
        sftp.dirs.add(_DIR)

        self._deploy(sftp, login=AuthResult(AuthStatus.REJECTED))

        self.assertEqual(sftp.files, {})
        self.assertEqual(sftp.dirs, {_DIR})

    def test_failed_login_never_removes_a_key_already_present(self):
        content = self.line + b"\n"
        sftp = _FakeSftp({_FILE: content})

        result = self._deploy(sftp, login=AuthResult(AuthStatus.REJECTED))

        self.assertEqual(
            result,
            DeployResult("key already present, but the key login failed: credentials rejected", failed=True),
        )
        self.assertEqual(sftp.files[_FILE], content)
        self.assertEqual(sftp.calls, [])

    def test_failed_removal_leaves_the_file_whole_and_says_so(self):
        original = b"ssh-rsa OTHER other\n"
        sftp = _FakeSftp({_FILE: original})
        sftp.rename_error = OSError("rename not supported")

        result = self._deploy(sftp, login=AuthResult(AuthStatus.REJECTED))

        self.assertTrue(result.failed)
        self.assertFalse(result.verified)
        self.assertEqual(
            result.detail,
            "key login failed: credentials rejected. The key stays in authorized_keys, its removal failed: "
            "connection failed: rename not supported",
        )
        self.assertEqual(sftp.files[_FILE], original + self.line + b"\n")
        self.assertNotIn(_TMP, sftp.files)

    def test_failed_removal_reports_a_temporary_file_left_behind(self):
        sftp = _FakeSftp({_FILE: b"ssh-rsa OTHER other\n"})
        sftp.rename_error = OSError("rename not supported")
        sftp.remove_error = OSError("connection lost")

        result = self._deploy(sftp, login=AuthResult(AuthStatus.REJECTED))

        self.assertIn(f"rename not supported; {_TMP} also stays on the server: connection lost", result.detail)

    def test_login_failure_on_the_saved_credentials_changes_nothing(self):
        @contextmanager
        def session(server, timeout):
            raise auth.paramiko.AuthenticationException("Authentication failed.")
            yield

        with mock.patch.object(auth, "sftp_session", session):
            result = ssh_keys.deploy(self.server, self.key, _PRIVATE, 7.0)

        self.assertEqual(result, DeployResult("credentials rejected", failed=True))

    def test_write_failure_is_reported(self):
        sftp = _FakeSftp()
        sftp.mkdir = mock.Mock(side_effect=PermissionError(13, "Permission denied"))

        result = self._deploy(sftp)

        self.assertTrue(result.failed)
        self.assertIn("Permission denied", result.detail)
        self.check_key.assert_not_called()


class DeployAllTest(unittest.TestCase):
    def test_returns_the_results_in_order_and_reports_progress(self):
        servers = [_server(host="a.example"), _server(host="b.example"), _server(host="c.example")]
        results = {
            "a.example": DeployResult("a", verified=True),
            "b.example": DeployResult("b", failed=True),
            "c.example": DeployResult("c"),
        }
        progress = []

        with mock.patch.object(ssh_keys, "deploy", side_effect=lambda srv, *_: results[srv.host]) as deploy:
            self.assertEqual(
                ssh_keys.deploy_all(servers, _key(), _PRIVATE, lambda done, failed: progress.append((done, failed))),
                [results["a.example"], results["b.example"], results["c.example"]],
            )

        self.assertEqual(len(progress), 3)
        self.assertEqual(progress[-1], (3, 1))
        deploy.assert_any_call(servers[0], mock.ANY, _PRIVATE, auth.DEFAULT_TIMEOUT)


if __name__ == "__main__":
    unittest.main()
