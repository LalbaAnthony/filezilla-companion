import os
import shutil
import xml.etree.ElementTree as ET
from colorama import init as colorama_init, Fore, Style
from action import Action
from utils import (
    load_actions,
    parse_sitemanager,
    select_server,
    select_actions,
    get_sitemanager_path,
)

def main() -> None:
    colorama_init(autoreset=True, strip=False, convert=True)

    if not shutil.which("ssh"):
        print(
            Fore.RED
            + "SSH client is not installed or not found in PATH."
            + Style.RESET_ALL
        )
        return

    sitemanager_path = get_sitemanager_path()

    if not os.path.exists(sitemanager_path):
        print(
            Fore.RED
            + "FileZilla sitemanager.xml not found. Please ensure FileZilla is installed and has saved at least one site."
            + Style.RESET_ALL
        )
        return

    servers = parse_sitemanager(sitemanager_path)

    if not servers:
        print(
            Fore.RED
            + "No valid server found in the FileZilla site manager."
            + Style.RESET_ALL
        )
        return

    server = select_server(servers)

    defaults = server.defaulting()
    if defaults:
        print(
            Fore.YELLOW
            + f"Defaulting missing attributes: {', '.join(defaults)}"
            + Style.RESET_ALL
        )

    if server.is_ftp:
        print(
            Fore.RED
            + "Cannot connect to FTP servers. Please select an SFTP server."
            + Style.RESET_ALL
        )
        return

    if not server.can_connect:
        print(
            Fore.RED
            + "Cannot connect to the server with the provided details."
            + Style.RESET_ALL
        )
        return

    actions = load_actions("actions.json")
    selected_actions = select_actions(actions)

    for action in selected_actions:
        action.run(server)


if __name__ == "__main__":
    main()
