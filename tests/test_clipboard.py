import unittest
from unittest import mock

import pyperclip
from filezilla_companion import clipboard


class CopyTest(unittest.TestCase):
    def test_copies_text(self):
        with mock.patch.object(clipboard.pyperclip, "copy") as copy:
            clipboard.copy("secret")

        copy.assert_called_once_with("secret")

    def test_wraps_pyperclip_failure(self):
        error = pyperclip.PyperclipException("no clipboard")
        with mock.patch.object(clipboard.pyperclip, "copy", side_effect=error), \
                self.assertRaises(clipboard.ClipboardError) as raised:
            clipboard.copy("secret")

        self.assertEqual(str(raised.exception), "no clipboard")
        self.assertIs(raised.exception.__cause__, error)


if __name__ == "__main__":
    unittest.main()
