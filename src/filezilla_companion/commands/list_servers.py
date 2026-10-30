from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console

class ListServersCommand(Command):
    slug = "list"
    label = "List servers"

    def run(self, context: Context) -> int:
        """Print every server of the site manager, FTP servers included."""
        for srv in context.servers:
            # Server.label omits the port, which matters for servers off port 22.
            address = f"{srv.user}@{srv.host}:{srv.port}"
            Console.info(f"{srv.name} ({address})" if srv.name else address)
        return 0
