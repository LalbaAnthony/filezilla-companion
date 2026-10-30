import platform
import sys
import time
from colorama import init as colorama_init, Fore, Style

class Console:
    """Colored terminal output, so every message kind gets the same color everywhere."""

    INFO = Fore.WHITE
    SUCCESS = Fore.GREEN
    WARNING = Fore.YELLOW
    ERROR = Fore.RED

    PROGRESS_INTERVAL = 5.0  # seconds between two progress lines when the output is not a terminal
    _last_progress = 0.0

    @staticmethod
    def setup() -> None:
        """Enable colors for the current platform. Call once, before any output."""
        # Forcing conversion outside Windows strips every ANSI sequence, since there is no win32 console to convert to.
        colorama_init(autoreset=True, strip=False, convert=platform.system() == "Windows")

    @staticmethod
    def paint(color: str, message: str) -> str:
        """Return the message wrapped in the color and a reset."""
        return f"{color}{message}{Style.RESET_ALL}"

    @classmethod
    def info(cls, message: str) -> None:
        print(cls.paint(cls.INFO, message))

    @classmethod
    def success(cls, message: str) -> None:
        print(cls.paint(cls.SUCCESS, message))

    @classmethod
    def warning(cls, message: str) -> None:
        print(cls.paint(cls.WARNING, message))

    @classmethod
    def error(cls, message: str) -> None:
        print(cls.paint(cls.ERROR, message))

    @classmethod
    def progress(cls, message: str, done: bool = False) -> None:
        """
        Show a progress message. On a terminal, it rewrites the current line, and `done` ends that line.
        Otherwise, so logs stay short, it prints at most one line per PROGRESS_INTERVAL, plus the `done` one.
        """
        if sys.stdout.isatty():
            # Callers report growing counters, so a new message always covers the previous one.
            print(f"\r{cls.paint(cls.INFO, message)}", end="\n" if done else "", flush=True)
            return
        now = time.monotonic()
        if done or now - cls._last_progress >= cls.PROGRESS_INTERVAL:
            cls._last_progress = now
            cls.info(message)

    @classmethod
    def confirm(cls, question: str) -> bool:
        """Ask a yes/no question, an empty answer means yes."""
        answer = input(cls.paint(cls.WARNING, f"{question} (Y/n) "))
        return answer.strip().lower() in ("", "y", "yes")
