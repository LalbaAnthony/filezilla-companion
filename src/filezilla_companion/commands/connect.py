from filezilla_companion import prompts, ssh
from filezilla_companion.commands.base import Command, Context
from filezilla_companion.console import Console

class ConnectCommand(Command):
    slug = "connect"
    label = "Connect to a server"

    def run(self, context: Context) -> int:
        """Open an SSH session to a server picked by the user, with its password in the clipboard."""
        ssh_path = ssh.find_ssh()
        if not ssh_path or not ssh.ssh_is_functional(ssh_path):
            Console.error("SSH client is not installed or not found in PATH.")
            return 1

        server = prompts.select_server(context.servers)

        defaults = server.defaulting()
        if defaults:
            Console.warning(f"Defaulting missing attributes: {', '.join(defaults)}")

        if server.is_ftp:
            Console.error("Cannot connect to FTP servers. Please select an SFTP server.")
            return 1

        if not server.can_connect:
            Console.error("Cannot connect to the server with the provided details.")
            return 1

        try:
            ssh.connect(server)
        except OSError as e:
            Console.error(f"Cannot open the SSH session: {e}")
            return 1

        return 0
