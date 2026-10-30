from typing import TYPE_CHECKING, Any, Dict, List, Tuple, Union
from InquirerPy import inquirer
from InquirerPy.base.control import Choice
from InquirerPy.separator import Separator
from filezilla_companion.filezilla.server import Server

if TYPE_CHECKING:
    # Type-only imports: command modules import this one, so a runtime import would be circular.
    from filezilla_companion.commands.base import Command
    from filezilla_companion.criteria.base import Action, Criterion

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

def select_criteria(criteria: List["Criterion"]) -> List["Criterion"]:
    """Prompt the user to check the criteria to apply, all checked by default."""
    return inquirer.checkbox(
        message="Select the criteria:",
        instruction="(use `space` to toggle and `enter` to confirm)",
        invalid_message="please select at least one criterion",
        choices=[Choice(criterion, name=criterion.label, enabled=True) for criterion in criteria],
        validate=lambda result: len(result) > 0,
        max_height="100%"
    ).execute()

def select_actions(sections: List[Tuple[str, List["Action"]]]) -> List["Action"]:
    """Prompt the user to check the changes to apply, listed under their section title and checked as proposed."""
    choices: List[Union[Choice, Separator]] = []
    for title, actions in sections:
        choices.append(Separator(f"-- {title} --"))
        choices += [Choice(action, name=action.label, enabled=action.checked) for action in actions]
    return inquirer.checkbox(
        message="Select the changes to apply:",
        instruction="(use `space` to toggle and `enter` to confirm)",
        choices=choices,
        max_height="100%"
    ).execute()
