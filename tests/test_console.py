import io
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))

from colorama import Fore, Style  # noqa: E402
from console import Console  # noqa: E402


class OutputTest(unittest.TestCase):
    def test_each_kind_uses_its_color_and_resets(self):
        cases = [
            (Console.info, Fore.WHITE),
            (Console.success, Fore.GREEN),
            (Console.warning, Fore.YELLOW),
            (Console.error, Fore.RED),
        ]
        for method, color in cases:
            with self.subTest(method=method.__name__), mock.patch("sys.stdout", new_callable=io.StringIO) as out:
                method("hello")
                self.assertEqual(out.getvalue(), f"{color}hello{Style.RESET_ALL}\n")


class ConfirmTest(unittest.TestCase):
    def test_empty_and_yes_answers_confirm(self):
        for answer in ("", "y", "Y", "yes", "YES", " y "):
            with self.subTest(answer=answer), mock.patch("builtins.input", return_value=answer):
                self.assertTrue(Console.confirm("Continue?"))

    def test_other_answers_decline(self):
        for answer in ("n", "no", "N", "nope", "yess"):
            with self.subTest(answer=answer), mock.patch("builtins.input", return_value=answer):
                self.assertFalse(Console.confirm("Continue?"))

    def test_prompt_shows_default(self):
        with mock.patch("builtins.input", return_value="") as input_:
            Console.confirm("Continue?")
        input_.assert_called_once_with(f"{Fore.YELLOW}Continue? (Y/n) {Style.RESET_ALL}")


if __name__ == "__main__":
    unittest.main()
