import io
import os
import tempfile
import unittest
from unittest import mock

from filezilla_companion import __main__ as app
from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console
from filezilla_companion.filezilla.server import Server

_SITEMANAGER = """<?xml version="1.0" encoding="UTF-8"?>
<FileZilla3>
    <Servers>
        <Server>
            <Host>example.com</Host>
            <Protocol>1</Protocol>
            <User>deploy</User>
            <Name>prod</Name>
        </Server>
    </Servers>
</FileZilla3>"""


class ParseArgsTest(unittest.TestCase):
    def test_no_flag_means_no_command(self):
        self.assertIsNone(app.parse_args([]))

    def test_each_slug_flag_selects_its_command(self):
        for command in COMMANDS:
            with self.subTest(slug=command.slug):
                self.assertIs(app.parse_args([f"--{command.slug}"]), command)

    def test_rejects_invalid_flags(self):
        for argv in (["--connect", "--list"], ["--unknown"]):
            with self.subTest(argv=argv), mock.patch("sys.stderr", new_callable=io.StringIO), \
                    self.assertRaises(SystemExit) as raised:
                app.parse_args(argv)
            self.assertEqual(raised.exception.code, 2)


class MainTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "sitemanager.xml")
        self.command = mock.Mock(spec=Command)
        self.command.run.return_value = 0
        patches = [
            mock.patch("sys.stdout", new_callable=io.StringIO),
            mock.patch.object(Console, "setup"),
            mock.patch.object(app, "get_sitemanager_path", return_value=self.path),
            mock.patch.object(prompts, "select_command", return_value=self.command),
        ]
        self.stdout, _, _, self.select_command = [p.start() for p in patches]
        for p in patches:
            self.addCleanup(p.stop)

    def _write_sitemanager(self, content: str = _SITEMANAGER) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            f.write(content)

    def test_menu_picks_the_command_without_flag(self):
        self._write_sitemanager()

        self.assertEqual(app.main([]), 0)

        self.select_command.assert_called_once_with(COMMANDS)
        self.command.run.assert_called_once_with(Context([Server("prod", "example.com", 22, 1, "deploy")]))

    def test_flag_skips_the_menu(self):
        self._write_sitemanager()
        command = COMMANDS[-1]

        with mock.patch.object(command, "run", return_value=3) as run:
            self.assertEqual(app.main([f"--{command.slug}"]), 3)

        self.select_command.assert_not_called()
        run.assert_called_once()

    def test_missing_sitemanager_aborts(self):
        self.assertEqual(app.main([]), 1)

        self.assertIn("FileZilla sitemanager.xml not found", self.stdout.getvalue())
        self.select_command.assert_not_called()

    def test_no_valid_server_aborts(self):
        self._write_sitemanager("<FileZilla3><Servers/></FileZilla3>")

        self.assertEqual(app.main([]), 1)

        self.assertIn("No valid server found", self.stdout.getvalue())
        self.select_command.assert_not_called()


class RunTest(unittest.TestCase):
    def test_waits_for_enter_on_failure(self):
        with mock.patch.object(app, "main", return_value=1), mock.patch("builtins.input") as input_:
            self.assertEqual(app.run(), 1)

        input_.assert_called_once_with("Press Enter to exit...")

    def test_exits_immediately_on_success(self):
        with mock.patch.object(app, "main", return_value=0), mock.patch("builtins.input") as input_:
            self.assertEqual(app.run(), 0)

        input_.assert_not_called()


if __name__ == "__main__":
    unittest.main()
