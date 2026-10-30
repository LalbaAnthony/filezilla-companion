import argparse
import os
import sys
from typing import List, Optional
from filezilla_companion import prompts
from filezilla_companion.commands import COMMANDS
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console
from filezilla_companion.filezilla.sitemanager import get_sitemanager_path, load_sitemanager

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

    if not os.path.exists(sitemanager_path):
        Console.error("FileZilla sitemanager.xml not found. Please ensure FileZilla is installed and has saved at least one site.")
        return 1

    sitemanager = load_sitemanager(sitemanager_path)

    if not sitemanager.servers:
        Console.error("No valid server found in the FileZilla site manager.")
        return 1

    if command is None:
        command = prompts.select_command(COMMANDS)

    return command.run(Context(sitemanager))

def run() -> int:
    """Console script entry point: keeps the window open on failure, so a double-clicked launch shows the error."""
    exit_code = main()
    if exit_code != 0:
        input("Press Enter to exit...")
    return exit_code

if __name__ == "__main__":
    sys.exit(run())
