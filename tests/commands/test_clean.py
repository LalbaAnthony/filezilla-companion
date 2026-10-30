import io
import os
import tempfile
import unittest
from typing import List
from unittest import mock

from filezilla_companion import prompts
from filezilla_companion.commands.base import Context
from filezilla_companion.commands.clean import CleanCommand
from filezilla_companion.criteria.base import Analysis, Criterion, Finding, Remove, Rename
from filezilla_companion.filezilla import process, sitemanager
from filezilla_companion.filezilla.sitemanager import SiteManager

_SITEMANAGER = """<?xml version="1.0"?>
<FileZilla3>
    <Servers>
        <Server><Host>a.example</Host><User>u</User><Name>alpha</Name></Server>
        <Server><Host>b.example</Host><User>u</User><Name>prod</Name></Server>
        <Server><Host>c.example</Host><User>u</User><Name>prod</Name></Server>
        <Server><Host>d.example</Host><User>u</User><Name>prod</Name></Server>
    </Servers>
</FileZilla3>"""


class _FakeCriterion(Criterion):
    def __init__(self, slug: str, findings: List[Finding]) -> None:
        self.slug = slug
        self.label = slug.capitalize()
        self.findings = findings

    def evaluate(self, analysis: Analysis) -> List[Finding]:
        return self.findings

    def summary(self, findings: List[Finding]) -> str:
        return f"{len(findings)} found"


class CleanCommandTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.path = os.path.join(self.dir, "sitemanager.xml")
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(_SITEMANAGER)
        self.sitemanager = sitemanager.load_sitemanager(self.path)
        self.alpha, self.prod_b, self.prod_c, self.prod_d = self.sitemanager.servers

        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(prompts, "select_criteria"),
            mock.patch.object(prompts, "select_actions"),
            mock.patch.object(process, "is_running", return_value=False),
            mock.patch("builtins.input", return_value="y"),
        ]
        self.stdout, self.select_criteria, self.select_actions, self.is_running, self.input = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _run(self, *criteria: Criterion) -> int:
        self.select_criteria.return_value = list(criteria)
        return CleanCommand().run(Context(self.sitemanager))

    def _file(self) -> str:
        with open(self.path, encoding="utf-8") as f:
            return f.read()

    def _backups(self) -> List[str]:
        return [name for name in os.listdir(self.dir) if name.endswith(".bak")]

    def _reloaded_names(self) -> List[str]:
        with mock.patch("sys.stdout", new_callable=io.StringIO):
            return [srv.name for srv in sitemanager.load_sitemanager(self.path).servers]

    def test_nothing_found(self):
        self.assertEqual(self._run(_FakeCriterion("empty", [])), 0)

        self.assertIn("Empty: none", self.stdout.getvalue())
        self.assertIn("Nothing to clean up.", self.stdout.getvalue())
        self.select_actions.assert_not_called()
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_report_lists_each_finding_and_its_sites(self):
        finding = Finding("u@b.example:22", [self.prod_b, self.prod_c])
        self.select_actions.return_value = []

        self._run(_FakeCriterion("groups", [finding]))

        output = self.stdout.getvalue()
        self.assertIn("Groups: 1 found", output)
        self.assertIn("  u@b.example:22", output)
        self.assertIn("    prod (u@b.example:22)", output)
        self.assertIn("    prod (u@c.example:22)", output)

    def test_lists_a_change_proposed_by_several_criteria_once(self):
        first = _FakeCriterion("first", [Finding("t", [self.alpha], [Remove(self.alpha, "copy", checked=False)])])
        second = _FakeCriterion("second", [Finding("t", [self.alpha, self.prod_b], [
            Remove(self.alpha, "timed out", checked=True),
            Remove(self.prod_b, "timed out", checked=False),
        ])])
        self.select_actions.return_value = []

        self.assertEqual(self._run(first, second), 0)

        [sections] = self.select_actions.call_args.args
        self.assertEqual(sections, [
            ("First", [Remove(self.alpha, "copy; timed out", checked=True)]),
            ("Second", [Remove(self.prod_b, "timed out", checked=False)]),
        ])
        self.assertIn("No change selected", self.stdout.getvalue())
        self.assertEqual(self._file(), _SITEMANAGER)

    def test_applies_the_selected_changes_after_a_backup(self):
        remove = Remove(self.alpha, "copy", checked=True)
        rename = Rename(self.prod_b, "shared name", checked=True, new_name="prod (u@b.example)")
        self.select_actions.side_effect = lambda sections: [remove, rename]

        self.assertEqual(self._run(_FakeCriterion("fake", [Finding("t", [self.alpha, self.prod_b], [remove, rename])])), 0)

        self.assertEqual(self._reloaded_names(), ["prod (u@b.example)", "prod", "prod"])
        [backup] = self._backups()
        with open(os.path.join(self.dir, backup), encoding="utf-8") as f:
            self.assertEqual(f.read(), _SITEMANAGER)
        output = self.stdout.getvalue()
        self.assertIn("1 site(s) to remove, 1 to rename.", output)
        self.assertIn(f"1 site(s) removed, 1 renamed. Backup: {os.path.join(self.dir, backup)}", output)

    def test_drops_renames_that_removals_made_useless(self):
        actions = [
            Remove(self.prod_c, "copy", checked=True),
            Remove(self.prod_d, "copy", checked=True),
            Rename(self.prod_b, "shared name", checked=True, new_name="prod (u@b.example)"),
        ]
        self.select_actions.return_value = actions

        self.assertEqual(self._run(_FakeCriterion("fake", [Finding("t", [], actions)])), 0)

        self.assertEqual(self._reloaded_names(), ["alpha", "prod"])
        self.assertIn("Not renaming prod (u@b.example:22): no other remaining site has its name.", self.stdout.getvalue())

    def test_warns_when_every_site_of_a_keep_one_group_goes(self):
        actions = [Remove(self.prod_b, "copy", checked=True), Remove(self.prod_c, "timed out", checked=True)]
        finding = Finding("u@b.example:22", [self.prod_b, self.prod_c], actions, keep_one=True)
        self.select_actions.return_value = actions

        self._run(_FakeCriterion("duplicates", [finding]))

        self.assertIn("Every site of the group u@b.example:22 (duplicates) will be removed.", self.stdout.getvalue())

    def test_declining_leaves_the_file_unchanged(self):
        action = Remove(self.alpha, "copy", checked=True)
        self.select_actions.return_value = [action]
        self.input.return_value = "n"

        self.assertEqual(self._run(_FakeCriterion("fake", [Finding("t", [self.alpha], [action])])), 0)

        self.assertEqual(self._file(), _SITEMANAGER)
        self.assertEqual(self._backups(), [])
        self.assertIn("sitemanager.xml left unchanged.", self.stdout.getvalue())

    def test_warns_before_writing_when_filezilla_may_be_running(self):
        cases = [
            (True, "FileZilla is running"),
            (None, "Cannot tell whether FileZilla is running"),
        ]
        for running, warning in cases:
            with self.subTest(running=running):
                action = Remove(self.alpha, "copy", checked=True)
                self.select_actions.return_value = [action]
                self.is_running.return_value = running
                self.input.return_value = "n"

                self._run(_FakeCriterion("fake", [Finding("t", [self.alpha], [action])]))

                self.assertIn(warning, self.stdout.getvalue())
                self.input.assert_called_with(mock.ANY)

    def test_write_failure_is_an_error(self):
        action = Remove(self.alpha, "copy", checked=True)
        self.select_actions.return_value = [action]

        with mock.patch.object(SiteManager, "save", side_effect=OSError("read-only file system")):
            self.assertEqual(self._run(_FakeCriterion("fake", [Finding("t", [self.alpha], [action])])), 1)

        self.assertIn("Cannot write sitemanager.xml: read-only file system", self.stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
