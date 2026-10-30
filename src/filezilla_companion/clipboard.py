import pyperclip

class ClipboardError(Exception):
    """Raised when the system clipboard cannot be written."""

def copy(text: str) -> None:
    """
    Copy the text to the system clipboard.
    Raises ClipboardError when no clipboard mechanism is available (e.g. neither xclip nor wl-clipboard on Linux).
    """
    try:
        pyperclip.copy(text)
    except pyperclip.PyperclipException as e:
        raise ClipboardError(str(e)) from e
