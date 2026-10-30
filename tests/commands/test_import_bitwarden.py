import io
import os
import tempfile
import unittest
from typing import List
from unittest import mock

from filezilla_companion import bitwarden, prompts
from filezilla_companion.commands import import_bitwarden
from filezilla_companion.commands.base import Context
from filezilla_companion.commands.import_bitwarden import ImportBitwardenCommand
from filezilla_companion.filezilla import process, sitemanager
from filezilla_companion.filezilla.server import Server
from filezilla_companion.filezilla.sitemanager import SiteManager

_SITEMANAGER = """<?xml version="1.0" encoding="UTF-8"?>
<FileZilla3>
    <Servers>
        <Server>
            <Host>prod.example.com</Host>
            <Port>22</Port>
            <Protocol>1</Protocol>
            <User>deploy</User>
            <Pass encoding="base64">b2xk</Pass>
            <Logontype>1</Logontype>
            <Name>prod</Name>
            <Comments>handmade</Comments>
            <Colour>2</Colour>
            <LocalDir>C:\\www</LocalDir>
        </Server>
        <Folder expanded="1">clients
            <Server>
                <Host>acme.example</Host>
                <Port>21</Port>
                <Protocol>0</Protocol>
                <User>acme</User>
                <Pass encoding="base64">YWNtZS1vbGQ=</Pass>
                <Logontype>1</Logontype>
                <Name>acme</Name>
                <Comments>bitwarden-id: acme-id</Comments>
                <RemoteDir>1 0 3 srv</RemoteDir>
            </Server>
        </Folder>
    </Servers>
</FileZilla3>"""


def _login(
    item_id: str,
    name: str,
    *uris: str,
    username: str = "deploy",
    password: str = "secret",
    created: str = "2024-01-01T00:00:00.000Z",
    **fields: str,
) -> bitwarden.Login:
    return bitwarden.Login(item_id, name, created, username, password, list(uris), fields)


# The login of the acme site, matching it exactly.
_ACME = _login("acme-id", "acme", "ftp://acme.example/srv", username="acme", password="acme-old")


class ImportBitwardenCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, "sitemanager.xml")
        self._write(_SITEMANAGER)

        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(bitwarden, "find_bw", return_value="bw"),
            mock.patch.object(bitwarden, "status", return_value="unlocked"),
            mock.patch.object(bitwarden, "sync"),
            mock.patch.object(bitwarden, "list_logins", return_value=[]),
            mock.patch.object(prompts, "select_actions"),
            mock.patch.object(process, "is_running", return_value=False),
            mock.patch("builtins.input", return_value="y"),
        ]
        (self.stdout, self.find_bw, self.status, self.sync, self.list_logins, self.select_actions, _,
         self.input) = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.select_actions.side_effect = self._select_all

    def _write(self, content: str) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)
        self.sitemanager = sitemanager.load_sitemanager(self.path)

    def _run(self, *logins: bitwarden.Login, context: Context = None) -> int:
        self.list_logins.return_value = list(logins)
        return ImportBitwardenCommand().run(context or Context(self.sitemanager))

    def _file(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def _reloaded(self) -> SiteManager:
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            return sitemanager.load_sitemanager(self.path)

    def _select_all(self, sections: List[tuple]) -> list:
        """Keep every proposed change, which are all checked, recording the menu as the user sees it."""
        self.menu = [(title, [action.label for action in actions]) for title, actions in sections]
        return [action for _, actions in sections for action in actions]

    def _sections(self) -> List[tuple]:
        """Return the titles and labels of the change menu, as shown before the changes are applied."""
        self.select_actions.assert_called_once()
        return self.menu

    def _backups(self) -> List[str]:
        return [name for name in os.listdir(self.dir) if name.endswith(".bak")]

    def test_missing_bw_is_an_error(self):
        self.find_bw.return_value = None

        self.assertEqual(self._run(), 1)

        self.assertIn("Bitwarden CLI (bw) not found in PATH.", self.stdout.getvalue())
        self.list_logins.assert_not_called()

    def test_vault_must_be_unlocked(self):
        for status, message in (("locked", "run `bw unlock`"), ("unauthenticated", "run `bw login`"), ("odd", "status: odd")):
            with self.subTest(status=status):
                self.status.return_value = status
                self.assertEqual(self._run(), 1)
                self.assertIn(message, self.stdout.getvalue())
        self.sync.assert_not_called()
        self.list_logins.assert_not_called()

    def test_sync_failure_only_warns(self):
        self.sync.side_effect = bitwarden.BitwardenError("bw sync failed: offline")

        self.assertEqual(self._run(_ACME), 0)

        self.assertIn("Cannot sync the Bitwarden vault, using its local copy: bw sync failed: offline", self.stdout.getvalue())
        self.list_logins.assert_called_once_with("bw")

    def test_vault_read_failure_is_an_error(self):
        self.list_logins.side_effect = bitwarden.BitwardenError("bw list items failed: boom")

        self.assertEqual(self._run(), 1)

        self.assertIn("Cannot read the Bitwarden vault: bw list items failed: boom", self.stdout.getvalue())

    def test_no_ftp_login_is_nothing_to_do(self):
        self.assertEqual(self._run(_login("w1", "web", "https://example.com", protocol="sftp")), 0)

        output = self.stdout.getvalue()
        self.assertIn("No FTP/SFTP login to import in the Bitwarden vault.", output)
        self.assertNotIn("Skipping", output)
        self.select_actions.assert_not_called()

    def test_up_to_date_sites_need_nothing(self):
        self.assertEqual(self._run(_ACME), 0)

        self.assertIn("1 site(s) up to date.", self.stdout.getvalue())
        self.assertIn("Nothing to import.", self.stdout.getvalue())
        self.select_actions.assert_not_called()
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_adds_a_new_site_at_the_top_level_after_a_backup(self):
        login = _login("new-id", "new", "https://panel.example", "sftp://New.Example:2222/var/www/", "ftp://other.example")

        self.assertEqual(self._run(login, _ACME), 0)

        self.assertEqual(self._sections(), [("Add", ["Add new (deploy@new.example:2222)"])])
        reloaded = self._reloaded()
        self.assertEqual(reloaded.servers[-1], Server(
            "new", "new.example", 2222, 1, "deploy", "secret", logontype=1,
            comments="bitwarden-id: new-id", remote_dir="1 0 3 var 3 www",
        ))
        self.assertIs(reloaded.tree.find("Servers/Server[Name='new']"), reloaded.servers[-1].element)
        [backup] = self._backups()
        output = self.stdout.getvalue()
        self.assertIn("1 site(s) to add, 0 to update.", output)
        self.assertIn(f"1 site(s) added, 0 updated. Backup: {os.path.join(self.dir, backup)}", output)

    def test_updates_a_marked_site_in_place_showing_old_and_new_values(self):
        login = _login("acme-id", "acme", "ftpes://acme.example:2121/var/www", username="acme", password="acme-new")

        self.assertEqual(self._run(login), 0)

        self.assertEqual(self._sections(), [("Update", [
            'Update acme (acme@acme.example:21): port 21 → 2121, protocol ftp → ftpes, password, '
            'remote dir "/srv" → "/var/www"',
        ])])
        reloaded = self._reloaded()
        acme = reloaded.servers[1]
        self.assertEqual(
            (acme.port, acme.protocol, acme.password, acme.remote_dir, acme.comments),
            (2121, 4, "acme-new", "1 0 3 var 3 www", "bitwarden-id: acme-id"),
        )
        self.assertIs(reloaded.tree.find("Servers/Folder/Server"), acme.element)
        self.assertEqual(reloaded.servers[0], self.sitemanager.servers[0])

    def test_adopts_the_unmarked_site_at_its_address_and_keeps_its_other_settings(self):
        login = _login("prod-id", "production", "sftp://prod.example.com", password="new")

        self.assertEqual(self._run(login, _ACME), 0)

        self.assertEqual(self._sections(), [("Update", [
            'Update prod (deploy@prod.example.com:22): name "prod" → "production", password, link to Bitwarden',
        ])])
        prod = self._reloaded().servers[0]
        self.assertEqual(
            (prod.name, prod.password, prod.comments, prod.colour, prod.local_dir),
            ("production", "new", "handmade\n\nbitwarden-id: prod-id", 2, "C:\\www"),
        )

    def test_updates_every_site_it_matches(self):
        self._write("""<FileZilla3>
    <Servers>
        <Server><Host>prod.example.com</Host><User>deploy</User><Name>prod</Name></Server>
        <Server><Host>PROD.example.com</Host><User>deploy</User><Name>prod</Name><Comments>bitwarden-id: gone-id</Comments></Server>
    </Servers>
</FileZilla3>""")

        self.assertEqual(self._run(_login("prod-id", "prod", "sftp://prod.example.com")), 0)

        label = 'protocol ftp → sftp, password, logon type unset → normal, link to Bitwarden'
        self.assertEqual(self._sections(), [("Update", [
            f"Update prod (deploy@prod.example.com:22): {label}",
            f"Update prod (deploy@PROD.example.com:22): {label}",
        ])])
        self.assertEqual(
            [(srv.host, srv.password, srv.comments) for srv in self._reloaded().servers],
            [
                ("prod.example.com", "secret", "bitwarden-id: prod-id"),
                ("PROD.example.com", "secret", "bitwarden-id: prod-id"),
            ],
        )

    def test_a_login_with_a_marked_site_leaves_unmarked_copies_alone(self):
        self._write("""<FileZilla3>
    <Servers>
        <Server><Host>prod.example.com</Host><Protocol>1</Protocol><User>deploy</User><Pass encoding="base64">b2xk</Pass><Logontype>1</Logontype><Name>prod</Name><Comments>bitwarden-id: prod-id</Comments></Server>
        <Server><Host>prod.example.com</Host><Protocol>1</Protocol><User>deploy</User><Pass encoding="base64">b2xk</Pass><Logontype>1</Logontype><Name>copy</Name></Server>
    </Servers>
</FileZilla3>""")

        self.assertEqual(self._run(_login("prod-id", "prod", "sftp://prod.example.com", password="new")), 0)

        self.assertEqual(self._sections(), [("Update", ["Update prod (deploy@prod.example.com:22): password"])])
        self.assertEqual([srv.password for srv in self._reloaded().servers], ["new", "old"])

    def test_the_oldest_login_adopts_a_site_and_the_others_are_skipped(self):
        newer = _login("copy-id", "copy", "sftp://prod.example.com", created="2025-01-01T00:00:00.000Z")
        older = _login("prod-id", "prod", "sftp://prod.example.com", password="old", created="2023-01-01T00:00:00.000Z")

        self.assertEqual(self._run(newer, older), 0)

        self.assertIn('Skipping "copy": deploy@prod.example.com:22 already comes from "prod".', self.stdout.getvalue())
        self.assertEqual(self._sections(), [("Update", ["Update prod (deploy@prod.example.com:22): link to Bitwarden"])])

    def test_two_new_logins_at_one_address_add_one_site(self):
        first = _login("a-id", "first", "sftp://new.example", created="2023-01-01T00:00:00.000Z")
        second = _login("b-id", "second", "sftp://new.example", created="2024-01-01T00:00:00.000Z")

        self.assertEqual(self._run(second, first), 0)

        self.assertIn('Skipping "second": deploy@new.example:22 already comes from "first".', self.stdout.getvalue())
        self.assertEqual(self._sections(), [("Add", ["Add first (deploy@new.example:22)"])])

    def test_a_login_without_site_skips_an_address_another_login_owns(self):
        older = _login("old-id", "older", "ftp://acme.example", username="acme", created="2020-01-01T00:00:00.000Z")
        owner = _login("acme-id", "acme", "ftp://acme.example/srv", username="acme", password="acme-old", created="2025-01-01T00:00:00.000Z")

        self.assertEqual(self._run(older, owner), 0)

        self.assertIn('Skipping "older": acme@acme.example:21 already comes from "acme".', self.stdout.getvalue())
        self.assertIn("Nothing to import.", self.stdout.getvalue())

    def test_a_site_whose_login_is_skipped_can_be_adopted(self):
        broken = _login("acme-id", "acme", "ftp://acme.example", username="")
        other = _login("other-id", "acme", "ftp://acme.example/srv", username="acme", password="acme-old")

        self.assertEqual(self._run(broken, other), 0)

        self.assertIn('Skipping "acme": no username.', self.stdout.getvalue())
        self.assertEqual(self._sections(), [("Update", ["Update acme (acme@acme.example:21): link to Bitwarden"])])
        self.assertEqual(self._reloaded().servers[1].comments, "bitwarden-id: other-id")

    def test_unselected_changes_write_nothing(self):
        self.select_actions.side_effect = None
        self.select_actions.return_value = []

        self.assertEqual(self._run(_login("new-id", "new", "sftp://new.example")), 0)

        self.assertIn("No change selected, sitemanager.xml left unchanged.", self.stdout.getvalue())
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_declined_confirmation_writes_nothing(self):
        self.input.return_value = "n"

        self.assertEqual(self._run(_login("new-id", "new", "sftp://new.example")), 0)

        self.assertIn("sitemanager.xml left unchanged.", self.stdout.getvalue())
        self.assertEqual(self._file(), _SITEMANAGER)
        self.assertEqual(self._backups(), [])

    def test_write_failure_is_an_error(self):
        with mock.patch.object(SiteManager, "save", side_effect=OSError("disk full")):
            self.assertEqual(self._run(_login("new-id", "new", "sftp://new.example")), 1)

        self.assertIn("Cannot write sitemanager.xml: disk full", self.stdout.getvalue())

    def test_creates_the_site_manager_on_a_fresh_install(self):
        path = os.path.join(self.dir, "FileZilla", "sitemanager.xml")

        context = Context(sitemanager.empty_sitemanager(path))
        self.assertEqual(self._run(_login("new-id", "new", "sftp://new.example"), context=context), 0)

        self.assertIn(f"1 site(s) added, 0 updated. Created {path}", self.stdout.getvalue())
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            self.assertEqual([srv.name for srv in sitemanager.load_sitemanager(path).servers], ["new"])
        self.assertEqual(os.listdir(os.path.dirname(path)), ["sitemanager.xml"])


class ToSiteTest(unittest.TestCase):
    def _site(self, *uris: str, **kwargs) -> Server:
        return import_bitwarden._to_site(_login("id", "site", *uris, **kwargs))

    def _skip_reason(self, *uris: str, **kwargs) -> str:
        with self.assertRaises(import_bitwarden._Skip) as raised:
            self._site(*uris, **kwargs)
        return str(raised.exception)

    def test_maps_schemes_and_protocol_field_to_protocol_and_default_port(self):
        for uri, fields, expected in (
            ("sftp://h", {}, (1, 22)),
            ("ssh://h", {}, (1, 22)),
            ("ftp://h", {}, (0, 21)),
            ("ftps://h", {}, (3, 990)),
            ("ftpes://h", {}, (4, 21)),
            ("SFTP://h:2200", {}, (1, 2200)),
            ("ftp://h", {"protocol": "ftps"}, (3, 990)),
            ("ftp://h:2121", {"protocol": "FTPES"}, (4, 2121)),
        ):
            with self.subTest(uri=uri, fields=fields):
                site = self._site(uri, **fields)
                self.assertEqual((site.protocol, site.port), expected)

    def test_ignores_logins_without_ftp_uri(self):
        for uris in ((), ("https://example.com",), ("example.com",), ("sftp://[::1",)):
            with self.subTest(uris=uris):
                self.assertIsNone(self._site(*uris, protocol="sftp"))

    def test_uri_user_is_a_fallback_for_the_username(self):
        self.assertEqual(self._site("sftp://root@h", username="").user, "root")
        self.assertEqual(self._site("sftp://root@h").user, "deploy")

    def test_key_file_logon_keeps_the_password(self):
        home = os.path.join(os.sep, "home", "me")
        with mock.patch.dict(os.environ, {"HOME": home, "USERPROFILE": home, "KEYS": "/keys"}):
            site = self._site("sftp://h", keyfile="~/.ssh/id_ed25519")
            self.assertEqual(self._site("sftp://h", keyfile="$KEYS/id").keyfile, "/keys/id")

        # expanduser keeps the rest of the path as written.
        self.assertEqual((site.keyfile, site.logontype, site.password), (home + "/.ssh/id_ed25519", 5, "secret"))
        self.assertIsNone(self._site("sftp://h", password="", keyfile="/k").password)

    def test_remote_dir_comes_from_the_path_except_the_root(self):
        for uri, expected in (
            ("sftp://h", ""),
            ("sftp://h/", ""),
            ("sftp://h/var/my%20www/", "1 0 3 var 6 my www"),
        ):
            with self.subTest(uri=uri):
                self.assertEqual(self._site(uri).remote_dir, expected)

    def test_skips_logins_that_cannot_be_imported(self):
        for uri, kwargs, reason in (
            ("sftp://h", {"username": ""}, "no username"),
            ("sftp://h", {"password": ""}, "no password or key file"),
            ("ftp://h", {"keyfile": "/k"}, "key file on a ftp site, only SFTP logs in with one"),
            ("sftp://h", {"protocol": "scp"}, 'unknown protocol "scp"'),
            ("sftp://h:99999", {}, "invalid port in its URI"),
            ("sftp:///var/www", {}, "no host in its URI"),
        ):
            with self.subTest(reason=reason):
                self.assertEqual(self._skip_reason(uri, **kwargs), reason)


class MarkerTest(unittest.TestCase):
    def test_reads_the_marker_line_only(self):
        self.assertEqual(import_bitwarden._marker("notes\nbitwarden-id:  abc \nmore"), "abc")
        self.assertEqual(import_bitwarden._marker("bitwarden-id: abc\r\n"), "abc")
        self.assertIsNone(import_bitwarden._marker("see bitwarden-id: abc"))

    def test_replaces_or_appends_the_marker(self):
        for comments, expected in (
            ("", "bitwarden-id: new"),
            ("notes\n", "notes\n\nbitwarden-id: new"),
            ("notes\r\nbitwarden-id: old\r\nmore", "notes\r\nbitwarden-id: new\r\nmore"),
        ):
            with self.subTest(comments=comments):
                self.assertEqual(import_bitwarden._with_marker(comments, "new"), expected)


if __name__ == "__main__":
    unittest.main()
