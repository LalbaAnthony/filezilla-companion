import io
import os
import sys
import tempfile
import unittest
from unittest import mock

from filezilla_companion.filezilla import sitemanager
from filezilla_companion.filezilla.server import Server


def _touch(path: str, content: str = "<FileZilla3/>") -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


class GetSitemanagerPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        # expanduser reads HOME on POSIX and USERPROFILE on Windows.
        env = {"HOME": self.home, "USERPROFILE": self.home}
        self.env_patch = mock.patch.dict(os.environ, env)
        self.env_patch.start()
        os.environ.pop("XDG_CONFIG_HOME", None)
        self.platform_patch = mock.patch.object(sitemanager.platform, "system", return_value="Linux")
        self.platform_patch.start()

    def tearDown(self):
        self.platform_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    @unittest.skipUnless(sys.platform == "win32", "%VAR% expansion is only supported by ntpath")
    def test_windows_uses_appdata(self):
        with mock.patch.object(sitemanager.platform, "system", return_value="Windows"), \
                mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(
                sitemanager.get_sitemanager_path(),
                r"C:\Users\me\AppData\Roaming\FileZilla\sitemanager.xml",
            )

    def test_defaults_to_xdg_path_when_nothing_exists(self):
        expected = os.path.join(self.home, ".config", "filezilla", "sitemanager.xml")
        self.assertEqual(sitemanager.get_sitemanager_path(), expected)

    def test_honors_xdg_config_home(self):
        xdg = os.path.join(self.home, "custom-config")
        expected = os.path.join(xdg, "filezilla", "sitemanager.xml")
        _touch(expected)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": xdg}):
            self.assertEqual(sitemanager.get_sitemanager_path(), expected)

    def test_prefers_legacy_dir_over_xdg(self):
        legacy = os.path.join(self.home, ".filezilla", "sitemanager.xml")
        _touch(legacy)
        _touch(os.path.join(self.home, ".config", "filezilla", "sitemanager.xml"))
        self.assertEqual(sitemanager.get_sitemanager_path(), legacy)

    def test_finds_flatpak_config(self):
        flatpak = os.path.join(
            self.home, ".var", "app", "org.filezillaproject.Filezilla", "config", "filezilla", "sitemanager.xml"
        )
        _touch(flatpak)
        self.assertEqual(sitemanager.get_sitemanager_path(), flatpak)


class ParseSitemanagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sitemanager.xml")
        stdout = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = stdout.start()
        self.addCleanup(stdout.stop)

    def test_reads_servers_in_folders_and_skips_incomplete_ones(self):
        _touch(self.path, """<?xml version="1.0" encoding="UTF-8"?>
<FileZilla3>
    <Servers>
        <Server>
            <Host>example.com</Host>
            <Port>2222</Port>
            <Protocol>1</Protocol>
            <User>deploy</User>
            <Pass encoding="base64">c2VjcmV0</Pass>
            <Name>prod</Name>
        </Server>
        <Folder>
            <Server>
                <Host>192.168.1.10</Host>
                <Protocol>1</Protocol>
                <User>dev</User>
                <Keyfile>/home/dev/.ssh/id_ed25519</Keyfile>
                <Name>lan</Name>
            </Server>
        </Folder>
        <Server>
            <Host></Host>
            <User>nobody</User>
            <Name>broken</Name>
        </Server>
    </Servers>
</FileZilla3>""")

        self.assertEqual(
            sitemanager.parse_sitemanager(self.path),
            [
                Server("prod", "example.com", 2222, 1, "deploy", "secret"),
                Server("lan", "192.168.1.10", 22, 1, "dev", None, "/home/dev/.ssh/id_ed25519"),
            ],
        )
        self.assertIn("Skipping server 'broken' due to missing host or user.", self.stdout.getvalue())

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            sitemanager.parse_sitemanager(self.path)


if __name__ == "__main__":
    unittest.main()
