import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

import utils  # noqa: E402


def _touch(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("<FileZilla3/>")


class GetSitemanagerPathTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = self.tmp.name
        # expanduser reads HOME on POSIX and USERPROFILE on Windows.
        env = {"HOME": self.home, "USERPROFILE": self.home}
        self.env_patch = mock.patch.dict(os.environ, env)
        self.env_patch.start()
        os.environ.pop("XDG_CONFIG_HOME", None)
        self.platform_patch = mock.patch("utils.platform.system", return_value="Linux")
        self.platform_patch.start()

    def tearDown(self):
        self.platform_patch.stop()
        self.env_patch.stop()
        self.tmp.cleanup()

    @unittest.skipUnless(sys.platform == "win32", "%VAR% expansion is only supported by ntpath")
    def test_windows_uses_appdata(self):
        with mock.patch("utils.platform.system", return_value="Windows"), \
                mock.patch.dict(os.environ, {"APPDATA": r"C:\Users\me\AppData\Roaming"}):
            self.assertEqual(
                utils.get_sitemanager_path(),
                r"C:\Users\me\AppData\Roaming\FileZilla\sitemanager.xml",
            )

    def test_defaults_to_xdg_path_when_nothing_exists(self):
        expected = os.path.join(self.home, ".config", "filezilla", "sitemanager.xml")
        self.assertEqual(utils.get_sitemanager_path(), expected)

    def test_honors_xdg_config_home(self):
        xdg = os.path.join(self.home, "custom-config")
        expected = os.path.join(xdg, "filezilla", "sitemanager.xml")
        _touch(expected)
        with mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": xdg}):
            self.assertEqual(utils.get_sitemanager_path(), expected)

    def test_prefers_legacy_dir_over_xdg(self):
        legacy = os.path.join(self.home, ".filezilla", "sitemanager.xml")
        _touch(legacy)
        _touch(os.path.join(self.home, ".config", "filezilla", "sitemanager.xml"))
        self.assertEqual(utils.get_sitemanager_path(), legacy)

    def test_finds_flatpak_config(self):
        flatpak = os.path.join(
            self.home, ".var", "app", "org.filezillaproject.Filezilla", "config", "filezilla", "sitemanager.xml"
        )
        _touch(flatpak)
        self.assertEqual(utils.get_sitemanager_path(), flatpak)


class FindTerminalTest(unittest.TestCase):
    def setUp(self):
        self.env_patch = mock.patch.dict(os.environ, {"DISPLAY": ":0"})
        self.env_patch.start()
        os.environ.pop("WAYLAND_DISPLAY", None)

    def tearDown(self):
        self.env_patch.stop()

    def test_none_without_display(self):
        os.environ.pop("DISPLAY")
        with mock.patch("utils.shutil.which", return_value="/usr/bin/xterm"):
            self.assertIsNone(utils.find_terminal())

    def test_wayland_display_is_enough(self):
        os.environ.pop("DISPLAY")
        os.environ["WAYLAND_DISPLAY"] = "wayland-0"
        with mock.patch("utils.shutil.which", side_effect=lambda name: name == "gnome-terminal" or None):
            self.assertEqual(utils.find_terminal(), ["gnome-terminal", "--"])

    def test_prefers_debian_default_terminal(self):
        with mock.patch("utils.shutil.which", return_value="/usr/bin/found"):
            self.assertEqual(utils.find_terminal(), ["x-terminal-emulator", "-e"])

    def test_falls_back_to_installed_emulator(self):
        with mock.patch("utils.shutil.which", side_effect=lambda name: name == "xterm" or None):
            self.assertEqual(utils.find_terminal(), ["xterm", "-e"])

    def test_none_when_no_emulator_installed(self):
        with mock.patch("utils.shutil.which", return_value=None):
            self.assertIsNone(utils.find_terminal())

    def test_returns_a_copy(self):
        with mock.patch("utils.shutil.which", return_value="/usr/bin/found"):
            utils.find_terminal().append("mutated")
            self.assertEqual(utils.find_terminal(), ["x-terminal-emulator", "-e"])


if __name__ == "__main__":
    unittest.main()
