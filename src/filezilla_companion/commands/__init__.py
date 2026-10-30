from typing import List
from filezilla_companion.commands.base import Command
from filezilla_companion.commands.clean import CleanCommand
from filezilla_companion.commands.connect import ConnectCommand
from filezilla_companion.commands.copy_password import CopyPasswordCommand
from filezilla_companion.commands.list_servers import ListServersCommand

# Order of the startup menu, whose first entry is preselected.
COMMANDS: List[Command] = [
    ConnectCommand(),
    CopyPasswordCommand(),
    ListServersCommand(),
    CleanCommand(),
]
