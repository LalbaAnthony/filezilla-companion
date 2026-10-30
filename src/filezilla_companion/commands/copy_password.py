from filezilla_companion import clipboard, prompts
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console

class CopyPasswordCommand(Command):
    slug = "copy-password"
    label = "Copy a server password"

    def run(self, context: Context) -> int:
        """Copy the password of a server picked by the user to the clipboard, FTP servers included."""
        servers = [srv for srv in context.servers if srv.password]
        if not servers:
            Console.error("No server with a saved password found in the FileZilla site manager.")
            return 1

        server = prompts.select_server(servers)

        try:
            clipboard.copy(server.password)
        except clipboard.ClipboardError as e:
            Console.error(f"Cannot copy the password to the clipboard: {e}")
            return 1

        Console.success(f"Password of {server.label} copied to clipboard.")
        return 0
