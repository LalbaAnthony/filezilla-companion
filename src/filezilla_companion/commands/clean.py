from typing import Dict, List, Tuple
from filezilla_companion import prompts
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console
from filezilla_companion.criteria import CRITERIA
from filezilla_companion.criteria.base import Action, Analysis, Criterion, Finding, Remove, Rename, site_label
from filezilla_companion.filezilla import process
from filezilla_companion.filezilla.server import Server

Results = List[Tuple[Criterion, List[Finding]]]

class CleanCommand(Command):
    slug = "clean"
    label = "Clean up the site manager"

    def run(self, context: Context) -> int:
        """Analyze the sites with the criteria picked by the user, then apply the changes they confirm."""
        criteria = prompts.select_criteria(CRITERIA)
        analysis = Analysis(context.servers)
        results: Results = [(criterion, criterion.evaluate(analysis)) for criterion in criteria]

        _report(results)

        sections = _merge_actions(results)
        if not sections:
            Console.success("Nothing to clean up.")
            return 0

        selected = prompts.select_actions(sections)
        removals = [action.server for action in selected if isinstance(action, Remove)]
        renames, dropped = _split_renames(selected, removals, context.servers)
        if not removals and not renames:
            Console.info("No change selected, sitemanager.xml left unchanged.")
            return 0

        _recap(results, removals, renames, dropped)
        if not _confirm_write():
            Console.info("sitemanager.xml left unchanged.")
            return 0

        context.sitemanager.remove(removals)
        for rename in renames:
            context.sitemanager.rename(rename.server, rename.new_name)
        try:
            backup = context.sitemanager.save()
        except OSError as e:
            Console.error(f"Cannot write sitemanager.xml: {e}")
            return 1

        Console.success(f"{len(removals)} site(s) removed, {len(renames)} renamed. Backup: {backup}")
        return 0

def _report(results: Results) -> None:
    for criterion, findings in results:
        if not findings:
            Console.success(f"{criterion.label}: none")
            continue
        Console.warning(f"{criterion.label}: {criterion.summary(findings)}")
        for finding in findings:
            Console.info(f"  {finding.title}")
            for srv in finding.servers:
                Console.info(f"    {site_label(srv)}")

def _merge_actions(results: Results) -> List[Tuple[str, List[Action]]]:
    """
    Group the proposed changes by criterion, for the selection menu. A change proposed by several criteria is listed
    once, under the first one, with every reason, and checked if any of them checks it.
    """
    merged: Dict[Tuple[int, type], Action] = {}
    sections: List[Tuple[str, List[Action]]] = []
    for criterion, findings in results:
        actions: List[Action] = []
        for finding in findings:
            for action in finding.actions:
                key = (id(action.server), type(action))
                first = merged.get(key)
                if first is None:
                    merged[key] = action
                    actions.append(action)
                else:
                    first.reason = f"{first.reason}; {action.reason}"
                    first.checked = first.checked or action.checked
        if actions:
            sections.append((criterion.label, actions))
    return sections

def _split_renames(
    selected: List[Action],
    removals: List[Server],
    servers: List[Server],
) -> Tuple[List[Rename], List[Rename]]:
    """
    Split the checked renames of the remaining sites into those to apply, and those dropped because no other
    remaining site has the name anymore.
    """
    removed = {id(srv) for srv in removals}
    remaining = [srv for srv in servers if id(srv) not in removed]
    applied: List[Rename] = []
    dropped: List[Rename] = []
    for action in selected:
        if not isinstance(action, Rename) or id(action.server) in removed:
            continue
        shared = sum(srv.name == action.server.name for srv in remaining) > 1
        (applied if shared else dropped).append(action)
    return applied, dropped

def _recap(results: Results, removals: List[Server], renames: List[Rename], dropped: List[Rename]) -> None:
    Console.info(f"{len(removals)} site(s) to remove, {len(renames)} to rename.")
    for action in dropped:
        Console.info(f"Not renaming {site_label(action.server)}: no other remaining site has its name.")
    removed = {id(srv) for srv in removals}
    for criterion, findings in results:
        for finding in findings:
            if finding.keep_one and all(id(srv) in removed for srv in finding.servers):
                Console.warning(f"Every site of the group {finding.title} ({criterion.slug}) will be removed.")

def _confirm_write() -> bool:
    running = process.is_running()
    if running:
        Console.warning("FileZilla is running: its Site Manager may overwrite sitemanager.xml and undo these changes. Close it first.")
    elif running is None:
        Console.warning("Cannot tell whether FileZilla is running. If it is, close it first: its Site Manager may overwrite sitemanager.xml.")
    return Console.confirm("Write the changes to sitemanager.xml?")
