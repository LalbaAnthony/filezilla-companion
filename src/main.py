from http import server
import os
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from colorama import init as colorama_init, Fore, Style

from action import Action
from utils import (
    parse_sitemanager,
    select_server,
    select_actions,
    get_sitemanager_path,
)

server_default_port = 22
server_default_username = ""
server_default_protocol = 1  # 0 = FTP, 1 = SFTP

actions = [
    Action(key="ssh", name="Connect to SSH", interactive=True),
    Action(
        key="ssh_node_version_18",
        name="Switch to Node.js version 18",
        commands=["npm install -g n", "n 18"],
    ),
    Action(
        key="ssh_node_version_22",
        name="Switch to Node.js version 22",
        commands=["npm install -g n", "n 22"],
    ),
    Action(
        key="ssh_node_version_latest",
        name="Switch to latest Node.js version",
        commands=["npm install -g n", "n latest"],
    ),
    Action(
        key="ssh_apache2_vhost_nuxt",
        name="Switch to Nuxt.js vhost",
        commands=[
            "sudo a2dissite *.conf",
            "sudo a2ensite dev-nuxt.conf",
            "sudo systemctl restart apache2",
        ],
    ),
]


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

    selected_actions = select_actions(actions)

    for action in selected_actions:
        action.run(server)



if __name__ == "__main__":
    main()
