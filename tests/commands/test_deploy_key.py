import base64
import io
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from typing import List
from unittest import mock

from filezilla_companion import prompts, ssh_keys
from filezilla_companion.commands.base import Context
from filezilla_companion.commands.deploy_key import DeployKeyCommand
from filezilla_companion.filezilla import process, sitemanager
from filezilla_companion.ssh_keys import DeployResult, PublicKey

_PASSWORD = base64.b64encode(b"secret").decode("ascii")
_SITEMANAGER = f"""<?xml version="1.0"?>
<FileZilla3>
    <Servers>
        <Server><Host>a.example</Host><Protocol>1</Protocol><User>u</User><Logontype>1</Logontype><Pass encoding="base64">{_PASSWORD}</Pass><Name>alpha</Name></Server>
        <Server><Host>b.example</Host><Protocol>1</Protocol><User>u</User><Logontype>1</Logontype><Pass encoding="base64">{_PASSWORD}</Pass><Name>bravo</Name></Server>
        <Server><Host>ftp.example</Host><Protocol>0</Protocol><Port>21</Port><User>u</User><Logontype>1</Logontype><Pass encoding="base64">{_PASSWORD}</Pass><Name>files</Name></Server>
    </Servers>
</FileZilla3>"""

_PRIVATE = object()


class DeployKeyCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, "sitemanager.xml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(_SITEMANAGER)
        self.sitemanager = sitemanager.load_sitemanager(self.path)
        self.alpha, self.bravo, self.ftp = self.sitemanager.servers
        self.key = PublicKey(os.path.join(self.dir, "id_ed25519.pub"), "ssh-ed25519", "AAAA", "me@laptop")

        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(ssh_keys, "list_public_keys", return_value=[self.key]),
            mock.patch.object(ssh_keys, "load_private_key", return_value=_PRIVATE),
            mock.patch.object(ssh_keys, "deploy_all"),
            mock.patch.object(prompts, "select_key", return_value=self.key),
            mock.patch.object(prompts, "select_servers"),
            mock.patch.object(process, "is_running", return_value=False),
            mock.patch("builtins.input", return_value="y"),
        ]
        (
            self.stdout, self.list_public_keys, self.load_private_key, self.deploy_all,
            self.select_key, self.select_servers, self.is_running, self.input,
        ) = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)
        self.select_servers.return_value = [self.alpha, self.bravo]
        self.deploy_all.return_value = [
            DeployResult("key added, key login verified", verified=True),
            DeployResult("key already present, key login verified", verified=True),
        ]

    def _run(self) -> int:
        return DeployKeyCommand().run(Context(self.sitemanager))

    def _file(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def _sites(self) -> List[ET.Element]:
        return ET.fromstring(self._file()).findall(".//Server")

    def _backups(self) -> List[str]:
        return [name for name in os.listdir(self.dir) if name.endswith(".bak")]

    def test_switches_the_verified_sites_to_the_key(self):
        self.assertEqual(self._run(), 0)

        alpha, bravo, ftp = self._sites()
        for site in (alpha, bravo):
            self.assertEqual(site.findtext("Logontype"), "5")
            self.assertEqual(site.findtext("Keyfile"), self.key.private_path)
            self.assertIsNone(site.find("Pass"))
        self.assertEqual(ftp.findtext("Logontype"), "1")
        self.assertIsNone(ftp.find("Keyfile"))
        self.assertEqual(ftp.findtext("Pass"), _PASSWORD)
        self.assertEqual(len(self._backups()), 1)
        self.assertEqual(self.alpha.logontype, 5)
        self.assertEqual(self.alpha.keyfile, self.key.private_path)
        self.assertIsNone(self.alpha.password)
        self.assertIn("2 site(s) switched to the key. Backup:", self.stdout.getvalue())

    def test_asks_before_the_servers_and_before_the_file(self):
        self._run()

        questions = [call.args[0] for call in self.input.call_args_list]
        self.assertEqual(len(questions), 2)
        self.assertIn("Add id_ed25519.pub to authorized_keys on these 2 server(s)?", questions[0])
        self.assertIn("Write the changes to sitemanager.xml?", questions[1])

    def test_lists_the_selected_sites_before_asking(self):
        output_at_question = []
        self.input.side_effect = lambda question: output_at_question.append(self.stdout.getvalue()) or "n"

        self._run()

        self.assertIn("alpha (u@a.example:22)", output_at_question[0])
        self.assertIn("bravo (u@b.example:22)", output_at_question[0])

    def test_passes_the_key_and_the_selection_to_the_deployment(self):
        self._run()

        servers, key, private, _ = self.deploy_all.call_args.args
        self.assertEqual([id(srv) for srv in servers], [id(self.alpha), id(self.bravo)])
        self.assertIs(key, self.key)
        self.assertIs(private, _PRIVATE)

    def test_no_public_key_aborts_before_any_menu(self):
        self.list_public_keys.return_value = []

        self.assertEqual(self._run(), 1)

        self.assertIn("No public key found", self.stdout.getvalue())
        self.select_key.assert_not_called()

    def test_unreadable_ssh_directory_aborts(self):
        self.list_public_keys.side_effect = PermissionError(13, "Permission denied")

        self.assertEqual(self._run(), 1)

        self.assertIn("Cannot read", self.stdout.getvalue())
        self.select_key.assert_not_called()

    def test_offers_only_the_sites_that_can_take_the_key(self):
        self._run()

        self.select_key.assert_called_once_with([self.key])
        offered = self.select_servers.call_args.args[0]
        self.assertEqual([id(srv) for srv in offered], [id(self.alpha), id(self.bravo)])
        self.assertIn("1 site(s) not offered", self.stdout.getvalue())

    def test_no_site_to_offer_aborts(self):
        self.sitemanager.remove([self.alpha, self.bravo])

        self.assertEqual(self._run(), 1)

        self.assertIn("No site to deploy this key to.", self.stdout.getvalue())
        self.select_servers.assert_not_called()

    def test_empty_selection_changes_nothing(self):
        self.select_servers.return_value = []

        self.assertEqual(self._run(), 0)

        self.input.assert_not_called()
        self.deploy_all.assert_not_called()
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_declining_the_deployment_changes_nothing(self):
        self.input.return_value = "n"

        self.assertEqual(self._run(), 0)

        self.deploy_all.assert_not_called()
        self.assertEqual(self._file(), _SITEMANAGER)
        self.assertEqual(self._backups(), [])

    def test_declining_the_write_leaves_the_file(self):
        self.input.side_effect = ["y", "n"]

        self.assertEqual(self._run(), 0)

        self.deploy_all.assert_called_once()
        self.assertEqual(self._file(), _SITEMANAGER)
        self.assertEqual(self._backups(), [])
        self.assertEqual(self.alpha.logontype, 1)
        self.assertIn("sitemanager.xml left unchanged. The key stays on the servers.", self.stdout.getvalue())

    def test_warns_about_the_password_before_the_write(self):
        self._run()

        self.assertIn("their saved password will be removed", self.stdout.getvalue())

    def test_warns_when_filezilla_is_running(self):
        self.is_running.return_value = True

        self._run()

        self.assertIn("FileZilla is running", self.stdout.getvalue())

    def test_partial_failure_switches_the_others_and_exits_with_an_error(self):
        self.deploy_all.return_value = [
            DeployResult("credentials rejected", failed=True),
            DeployResult("key added, key login verified", verified=True),
        ]

        self.assertEqual(self._run(), 1)

        alpha, bravo, _ = self._sites()
        self.assertEqual(alpha.findtext("Logontype"), "1")
        self.assertEqual(alpha.findtext("Pass"), _PASSWORD)
        self.assertEqual(bravo.findtext("Logontype"), "5")
        output = self.stdout.getvalue()
        self.assertIn("alpha (u@a.example:22): credentials rejected", output)
        self.assertIn("bravo (u@b.example:22): key added, key login verified", output)

    def test_every_failure_exits_without_asking_to_write(self):
        self.deploy_all.return_value = [
            DeployResult("timed out", failed=True),
            DeployResult("credentials rejected", failed=True),
        ]

        self.assertEqual(self._run(), 1)

        self.assertEqual(self.input.call_count, 1)
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_unusable_private_key_deploys_without_switching(self):
        self.load_private_key.side_effect = ssh_keys.KeyUnavailable("the key file is protected by a passphrase")
        self.deploy_all.return_value = [
            DeployResult("key added, not verified"),
            DeployResult("key already present, not verified"),
        ]

        self.assertEqual(self._run(), 0)

        self.assertIsNone(self.deploy_all.call_args.args[2])
        self.assertEqual(self.input.call_count, 1)
        self.assertEqual(self._file(), _SITEMANAGER)
        output = self.stdout.getvalue()
        self.assertIn("Cannot test logins with id_ed25519.pub: the key file is protected by a passphrase.", output)
        self.assertIn("alpha (u@a.example:22): key added, not verified", output)

    def test_write_failure_exits_with_an_error(self):
        with mock.patch.object(sitemanager.shutil, "copy2", side_effect=OSError("disk full")):
            self.assertEqual(self._run(), 1)

        self.assertIn("Cannot write sitemanager.xml: disk full", self.stdout.getvalue())
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_site_on_another_key_moves_to_this_one(self):
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(
                '<FileZilla3><Servers><Server><Host>k.example</Host><Protocol>1</Protocol><User>u</User>'
                '<Logontype>5</Logontype><Keyfile>old_key</Keyfile><Name>keyed</Name></Server></Servers></FileZilla3>'
            )
        self.sitemanager = sitemanager.load_sitemanager(self.path)
        keyed = self.sitemanager.servers[0]
        self.select_servers.return_value = [keyed]
        self.deploy_all.return_value = [DeployResult("key added, key login verified", verified=True)]

        with mock.patch.object(ssh_keys, "can_deploy", return_value=True):
            self.assertEqual(self._run(), 0)

        site = self._sites()[0]
        self.assertEqual(site.findtext("Keyfile"), self.key.private_path)
        self.assertEqual(site.findtext("Logontype"), "5")


if __name__ == "__main__":
    unittest.main()
