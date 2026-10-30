import io
import unittest
from unittest import mock

from colorama import Fore, Style
from filezilla_companion import console
from filezilla_companion.console import Console


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


class _Terminal(io.StringIO):
    def isatty(self) -> bool:
        return True


class ProgressTest(unittest.TestCase):
    def setUp(self):
        patch = mock.patch.object(Console, "_last_progress", 0.0)
        patch.start()
        self.addCleanup(patch.stop)

    def test_terminal_rewrites_the_line_until_done(self):
        with mock.patch("sys.stdout", new_callable=_Terminal) as out:
            Console.progress("1/2")
            Console.progress("2/2", done=True)

        self.assertEqual(
            out.getvalue(),
            f"\r{Fore.WHITE}1/2{Style.RESET_ALL}\r{Fore.WHITE}2/2{Style.RESET_ALL}\n",
        )

    def test_without_terminal_prints_one_line_per_interval_plus_the_last(self):
        with mock.patch("sys.stdout", new_callable=io.StringIO) as out, \
                mock.patch.object(console.time, "monotonic", side_effect=[100.0, 101.0, 106.0, 107.0]):
            Console.progress("1/4")
            Console.progress("2/4")
            Console.progress("3/4")
            Console.progress("4/4", done=True)

        self.assertEqual(
            out.getvalue(),
            "".join(f"{Fore.WHITE}{line}{Style.RESET_ALL}\n" for line in ("1/4", "3/4", "4/4")),
        )


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
