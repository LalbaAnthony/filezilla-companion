import argparse
import os
import sys
from typing import List, Optional
from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console
from filezilla_companion.filezilla.sitemanager import empty_sitemanager, get_sitemanager_path, load_sitemanager

EXIT_INTERRUPTED = 130  # 128 + SIGINT, the shell convention for a program stopped by Ctrl+C

def parse_args(argv: Optional[List[str]] = None) -> Optional[Command]:
    """Return the command requested with a `--<slug>` flag, or None when the user must pick one."""
    parser = argparse.ArgumentParser(
        prog="filezilla-companion",
        description="Act on the sites saved in FileZilla's site manager. Without a flag, a menu asks for the command.",
    )
    flags = parser.add_mutually_exclusive_group()
    for command in COMMANDS:
        flags.add_argument(f"--{command.slug}", dest="command", action="store_const", const=command, help=command.label)
    return parser.parse_args(argv).command

def main(argv: Optional[List[str]] = None) -> int:
    command = parse_args(argv)

    Console.setup()

    sitemanager_path = get_sitemanager_path()

    if os.path.exists(sitemanager_path):
        sitemanager = load_sitemanager(sitemanager_path)
        problem = None if sitemanager.servers else "No valid server found in the FileZilla site manager."
    else:
        sitemanager = empty_sitemanager(sitemanager_path)
        problem = "FileZilla sitemanager.xml not found. Please ensure FileZilla is installed and has saved at least one site."

    available = COMMANDS if problem is None else [cmd for cmd in COMMANDS if not cmd.requires_servers]
    if command is None:
        if not available:
            Console.error(problem)
            return 1
        if problem is not None:
            Console.warning(f"{problem} Only the commands that work without saved sites are offered.")
        command = prompts.select_command(available)
    elif command not in available:
        Console.error(problem)
        return 1

    return command.run(Context(sitemanager))

def run() -> int:
    """
    Console script entry point: keeps the window open on failure, so a double-clicked launch shows the error, and
    turns Ctrl+C into a message instead of a traceback.
    """
    try:
        exit_code = main()
    except KeyboardInterrupt:
        # No pause: Ctrl+C means quit, not another key press to close the window. The leading newline ends the line
        # ^C was pressed on, e.g. a question or the progress line.
        Console.warning("\nInterrupted.")
        return EXIT_INTERRUPTED
    if exit_code != 0:
        try:
            input("Press Enter to exit...")
        except KeyboardInterrupt:
            # Ctrl+C closes the window like Enter does; the failure stays the exit code. The newline keeps the
            # shell prompt off the pause line.
            print()
    return exit_code

if __name__ == "__main__":
    sys.exit(run())
