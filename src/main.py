import os
import sys
from typing import List
from InquirerPy import inquirer
from console import Console
from server import Server
from sitemanager import get_sitemanager_path, parse_sitemanager
from ssh import connect, find_ssh, ssh_is_functional

def select_server(servers: List[Server]) -> Server:
    """Prompt the user to select a server via a fuzzy search menu."""
    choices = [{"name": srv.label, "value": srv} for srv in servers]
    selected = inquirer.fuzzy(
        message="Select a server:",
        instruction="(use arrows to scroll and `enter` to confirm)",
        invalid_message="please select a server",
        choices=choices,
        validate=lambda result: result is not None,
        max_height="100%"
    ).execute()
    return selected

def main() -> int:
    Console.setup()

    ssh_path = find_ssh()
    if not ssh_path or not ssh_is_functional(ssh_path):
        Console.error("SSH client is not installed or not found in PATH.")
        return 1

    sitemanager_path = get_sitemanager_path()

    if not os.path.exists(sitemanager_path):
        Console.error("FileZilla sitemanager.xml not found. Please ensure FileZilla is installed and has saved at least one site.")
        return 1

    servers = parse_sitemanager(sitemanager_path)

    if not servers:
        Console.error("No valid server found in the FileZilla site manager.")
        return 1

    server = select_server(servers)

    defaults = server.defaulting()
    if defaults:
        Console.warning(f"Defaulting missing attributes: {', '.join(defaults)}")

    if server.is_ftp:
        Console.error("Cannot connect to FTP servers. Please select an SFTP server.")
        return 1

    if not server.can_connect:
        Console.error("Cannot connect to the server with the provided details.")
        return 1

    if not server.is_local:
        if not Console.confirm("Warning: This server is likely to be a production server. Do you want to continue?"):
            Console.error("Operation cancelled.")
            return 1

    try:
        connect(server)
    except OSError as e:
        Console.error(f"Cannot open the SSH session: {e}")
        return 1

    return 0

if __name__ == "__main__":
    exit_code = main()
    if exit_code != 0:
        input("Press Enter to exit...")
    sys.exit(exit_code)
