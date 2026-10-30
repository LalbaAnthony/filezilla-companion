from typing import TYPE_CHECKING, Any, Dict, List
from InquirerPy import inquirer
from filezilla_companion.filezilla.server import Server

if TYPE_CHECKING:
    # Type-only import: command modules import this one, so a runtime import would be circular.
    from filezilla_companion.commands.base import Command

def _fuzzy_select(subject: str, choices: List[Dict[str, Any]]) -> Any:
    """Show a fuzzy search menu over the choices and return the value of the selected one."""
    return inquirer.fuzzy(
        message=f"Select a {subject}:",
        instruction="(use arrows to scroll and `enter` to confirm)",
        invalid_message=f"please select a {subject}",
        choices=choices,
        validate=lambda result: result is not None,
        max_height="100%"
    ).execute()

def select_server(servers: List[Server]) -> Server:
    """Prompt the user to select a server via a fuzzy search menu."""
    return _fuzzy_select("server", [{"name": srv.label, "value": srv} for srv in servers])

def select_command(commands: List["Command"]) -> "Command":
    """Prompt the user to select a command via a fuzzy search menu, the first one being preselected."""
    # Showing the flag teaches how to skip this menu next time.
    return _fuzzy_select("command", [{"name": f"{cmd.label} (--{cmd.slug})", "value": cmd} for cmd in commands])
