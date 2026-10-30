import io
import os
import stat
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
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


class LoadSitemanagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sitemanager.xml")
        stdout = mock.patch("sys.stdout", new_callable=io.StringIO)
        self.stdout = stdout.start()
        self.addCleanup(stdout.stop)

    def test_reads_cleanup_settings_and_keeps_the_element(self):
        _touch(self.path, """<FileZilla3>
    <Servers>
        <Server>
            <Host>example.com</Host>
            <Protocol>1</Protocol>
            <Logontype>5</Logontype>
            <User>deploy</User>
            <Keyfile>C:\\keys\\id_ed25519</Keyfile>
            <Colour>2</Colour>
            <Comments>production</Comments>
            <LocalDir>C:\\www</LocalDir>
            <RemoteDir>1 0 3 var 3 www</RemoteDir>
            <Name>prod</Name>
        </Server>
    </Servers>
</FileZilla3>""")

        sitemanager_ = sitemanager.load_sitemanager(self.path)

        [server] = sitemanager_.servers
        self.assertEqual(
            (server.logontype, server.colour, server.comments, server.local_dir, server.remote_dir),
            (5, 2, "production", "C:\\www", "1 0 3 var 3 www"),
        )
        self.assertIs(server.element, sitemanager_.tree.find(".//Server"))
        self.assertEqual(sitemanager_.path, self.path)

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
            sitemanager.load_sitemanager(self.path).servers,
            [
                Server("prod", "example.com", 2222, 1, "deploy", "secret"),
                Server("lan", "192.168.1.10", 22, 1, "dev", None, "/home/dev/.ssh/id_ed25519"),
            ],
        )
        self.assertIn("Skipping server 'broken' due to missing host or user.", self.stdout.getvalue())

    def test_missing_file_raises(self):
        with self.assertRaises(FileNotFoundError):
            sitemanager.load_sitemanager(self.path)


_CLEANUP_XML = """<?xml version="1.0"?>
<FileZilla3 version="3.69.1" platform="windows">
    <Servers>
        <Server>
            <Host>example.com</Host>
            <User>deploy</User>
            <Pass encoding="base64">c2VjcmV0</Pass>
            <Name>prod</Name>
        </Server>
        <Server>
            <Host>example.com</Host>
            <User>deploy</User>
            <Pass encoding="base64">c2VjcmV0</Pass>
            <Name>prod</Name>
        </Server>
        <Folder expanded="1">clients
            <Server>
                <Host>acme.example</Host>
                <User>acme</User>
                <Name>acme</Name>
                <Comments>keep me</Comments>
            </Server>
        </Folder>
    </Servers>
</FileZilla3>"""


class SiteManagerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sitemanager.xml")
        _touch(self.path, _CLEANUP_XML)
        self.sitemanager = sitemanager.load_sitemanager(self.path)

    def _reload(self) -> sitemanager.SiteManager:
        return sitemanager.load_sitemanager(self.path)

    def test_remove_matches_copies_by_identity(self):
        first, second, acme = self.sitemanager.servers
        self.assertEqual(first, second)

        self.sitemanager.remove([second, acme])

        self.assertEqual(len(self.sitemanager.servers), 1)
        self.assertIs(self.sitemanager.servers[0], first)
        self.assertEqual(len(self.sitemanager.tree.findall(".//Server")), 1)
        self.assertIs(self.sitemanager.tree.find(".//Server"), first.element)
        # The folder stays, even empty.
        self.assertIsNotNone(self.sitemanager.tree.find(".//Folder"))

    def test_rename_updates_the_element_and_the_server(self):
        acme = self.sitemanager.servers[2]

        self.sitemanager.rename(acme, "acme (acme@acme.example)")

        self.assertEqual(acme.name, "acme (acme@acme.example)")
        self.assertEqual(acme.element.findtext("Name"), "acme (acme@acme.example)")

    def test_rename_adds_a_missing_name(self):
        acme = self.sitemanager.servers[2]
        acme.element.remove(acme.element.find("Name"))

        self.sitemanager.rename(acme, "acme")

        self.assertEqual(acme.element.findtext("Name"), "acme")

    def test_save_backs_up_then_writes_every_untouched_setting(self):
        first, second, acme = self.sitemanager.servers
        self.sitemanager.remove([second])
        self.sitemanager.rename(acme, "acme (renamed)")

        with mock.patch.object(sitemanager.datetime, "datetime") as datetime_:
            datetime_.now.return_value.strftime.return_value = "20261030-143205"
            backup = self.sitemanager.save()

        self.assertEqual(backup, os.path.join(self.tmp.name, "sitemanager.20261030-143205.xml.bak"))
        with open(backup, encoding="utf-8") as f:
            self.assertEqual(f.read(), _CLEANUP_XML)
        self.assertFalse(os.path.exists(f"{self.path}.tmp"))

        with mock.patch("sys.stdout", new_callable=io.StringIO):
            reloaded = self._reload()
        self.assertEqual(reloaded.servers, [first, acme])
        self.assertEqual(reloaded.servers[1].comments, "keep me")
        root = reloaded.tree.getroot()
        self.assertEqual(root.attrib, {"version": "3.69.1", "platform": "windows"})
        self.assertEqual(root.find(".//Folder").attrib, {"expanded": "1"})

    def test_save_never_overwrites_an_existing_backup(self):
        taken = os.path.join(self.tmp.name, "sitemanager.20261030-143205.xml.bak")
        _touch(taken, "older backup")

        with mock.patch.object(sitemanager.datetime, "datetime") as datetime_:
            datetime_.now.return_value.strftime.return_value = "20261030-143205"
            backup = self.sitemanager.save()

        self.assertEqual(backup, os.path.join(self.tmp.name, "sitemanager.20261030-143205-2.xml.bak"))
        with open(taken, encoding="utf-8") as f:
            self.assertEqual(f.read(), "older backup")

    def test_failed_write_leaves_the_file_unchanged(self):
        self.sitemanager.remove(self.sitemanager.servers)

        def write_partially(file, **kwargs):
            file.write(b"<FileZilla3>")
            raise OSError("disk full")

        with mock.patch.object(self.sitemanager.tree, "write", side_effect=write_partially), \
                self.assertRaises(OSError):
            self.sitemanager.save()

        with open(self.path, encoding="utf-8") as f:
            self.assertEqual(f.read(), _CLEANUP_XML)
        self.assertFalse(os.path.exists(f"{self.path}.tmp"))

    @unittest.skipIf(sys.platform == "win32", "POSIX permissions")
    def test_save_keeps_the_mode_of_the_replaced_file(self):
        os.chmod(self.path, 0o640)

        self.sitemanager.save()

        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o640)


_TABBED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<FileZilla3>
\t<Servers>
\t\t<Folder expanded="1">clients
\t\t\t<Server>
\t\t\t\t<Host>acme.example</Host>
\t\t\t\t<User>acme</User>
\t\t\t\t<Pass encoding="crypt" pubkey="abc">xyz</Pass>
\t\t\t\t<Name>acme</Name>
\t\t\t\t<Colour>2</Colour>
\t\t\t\t<Keyfile>/keys/id</Keyfile>
\t\t\t</Server>
\t\t</Folder>
\t</Servers>
</FileZilla3>"""


class AddUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "sitemanager.xml")
        stdout = mock.patch("sys.stdout", new_callable=io.StringIO)
        stdout.start()
        self.addCleanup(stdout.stop)
        self.new = Server(
            "new", "new.example", 2222, 1, "deploy", "s3cret", logontype=1,
            comments="bitwarden-id: abc", remote_dir="1 0 3 var 3 www",
        )

    def _file(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def test_add_appends_the_site_at_the_top_level_indented_like_the_file(self):
        _touch(self.path, _TABBED_XML)
        sitemanager_ = sitemanager.load_sitemanager(self.path)

        sitemanager_.add(self.new)
        sitemanager_.save()

        self.assertIs(sitemanager_.servers[-1], self.new)
        self.assertIs(sitemanager_.tree.find("Servers/Server"), self.new.element)
        self.assertEqual(self._file(), "\n".join([
            "<?xml version='1.0' encoding='UTF-8'?>",
            "<FileZilla3>",
            "\t<Servers>",
            *_TABBED_XML.splitlines()[3:13],  # the folder, unchanged
            "\t\t<Server>",
            "\t\t\t<Host>new.example</Host>",
            "\t\t\t<Port>2222</Port>",
            "\t\t\t<Protocol>1</Protocol>",
            "\t\t\t<User>deploy</User>",
            '\t\t\t<Pass encoding="base64">czNjcmV0</Pass>',
            "\t\t\t<Logontype>1</Logontype>",
            "\t\t\t<Name>new</Name>",
            "\t\t\t<Comments>bitwarden-id: abc</Comments>",
            "\t\t\t<RemoteDir>1 0 3 var 3 www</RemoteDir>",
            "\t\t</Server>",
            "\t</Servers>",
            "</FileZilla3>",
        ]))
        self.assertEqual(sitemanager.load_sitemanager(self.path).servers[-1], self.new)

    def test_add_creates_the_servers_element_of_an_unindented_file(self):
        _touch(self.path, "<FileZilla3/>")
        sitemanager_ = sitemanager.load_sitemanager(self.path)

        sitemanager_.add(self.new)
        sitemanager_.save()

        self.assertEqual(sitemanager.load_sitemanager(self.path).servers, [self.new])
        self.assertIn("<FileZilla3><Servers><Server><Host>new.example</Host>", self._file())

    def test_update_sets_adds_and_removes_settings(self):
        _touch(self.path, _TABBED_XML)
        sitemanager_ = sitemanager.load_sitemanager(self.path)
        [acme] = sitemanager_.servers

        sitemanager_.update(acme, {"keyfile": None, "port": 2222, "password": "new"})

        self.assertEqual((acme.keyfile, acme.port, acme.password), (None, 2222, "new"))
        self.assertEqual(ET.tostring(acme.element, encoding="unicode"), "\n".join([
            "<Server>",
            "\t\t\t\t<Host>acme.example</Host>",
            "\t\t\t\t<User>acme</User>",
            '\t\t\t\t<Pass encoding="base64">bmV3</Pass>',
            "\t\t\t\t<Name>acme</Name>",
            "\t\t\t\t<Colour>2</Colour>",
            "\t\t\t\t<Port>2222</Port>",
            "\t\t\t</Server>",
            "\t\t",
        ]))

    def test_save_creates_a_missing_file_and_folder_without_backup(self):
        path = os.path.join(self.tmp.name, "FileZilla", "sitemanager.xml")
        sitemanager_ = sitemanager.empty_sitemanager(path)
        sitemanager_.add(Server("new", "new.example", 22, 1, "deploy"))

        self.assertIsNone(sitemanager_.save())

        with open(path, encoding="utf-8") as f:
            self.assertEqual(f.read(), "\n".join([
                "<?xml version='1.0' encoding='UTF-8'?>",
                "<FileZilla3>",
                "\t<Servers>",
                "\t\t<Server>",
                "\t\t\t<Host>new.example</Host>",
                "\t\t\t<Port>22</Port>",
                "\t\t\t<Protocol>1</Protocol>",
                "\t\t\t<User>deploy</User>",
                "\t\t\t<Name>new</Name>",
                "\t\t</Server>",
                "\t</Servers>",
                "</FileZilla3>",
            ]))
        self.assertEqual(os.listdir(os.path.dirname(path)), ["sitemanager.xml"])

    @unittest.skipIf(sys.platform == "win32", "POSIX permissions")
    def test_save_creates_a_private_file(self):
        sitemanager.empty_sitemanager(self.path).save()

        self.assertEqual(stat.S_IMODE(os.stat(self.path).st_mode), 0o600)


class RemoteDirTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(sitemanager.platform, "system", return_value="Linux")
        self.system = patch.start()
        self.addCleanup(patch.stop)

    def test_encodes_unix_paths(self):
        for path, expected in (("/var/www/", "1 0 3 var 3 www"), ("/", "1 0"), ("/my dir//x", "1 0 6 my dir 1 x")):
            with self.subTest(path=path):
                self.assertEqual(sitemanager.encode_remote_dir(path), expected)

    def test_counts_utf16_units_on_windows(self):
        self.assertEqual(sitemanager.encode_remote_dir("/\U0001F600"), "1 0 1 \U0001F600")
        self.system.return_value = "Windows"
        self.assertEqual(sitemanager.encode_remote_dir("/\U0001F600"), "1 0 2 \U0001F600")

    def test_decodes_unix_paths_only(self):
        for value, expected in (
            ("1 0 3 var 3 www", "/var/www"),
            ("1 0", "/"),
            ("1 0 6 my dir 1 x", "/my dir/x"),
            ("3 2 C: 3 www", None),  # a DOS path
            ("1 0 9 var", None),
            ("1 0 x", None),
        ):
            with self.subTest(value=value):
                self.assertEqual(sitemanager.decode_remote_dir(value), expected)


if __name__ == "__main__":
    unittest.main()
