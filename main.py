import os
import sys
import base64
import platform
import subprocess
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Callable, Optional

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style
import pyperclip

from server import Server
from action import Action
from utils import parse_sitemanager, select_server, select_action, get_sitemanager_path

server_default_port = 22
server_default_username = ""
server_default_protocol = 1  # 0 = FTP, 1 = SFTP

actions = [
    Action(
        key="ssh",
        name="Connect to SSH",
        interactive=True
    ),
    Action(
        key="ssh_cmd",
        name="Connect to SSH + run ls -la",
        commands=[
            "ls -la",
            "pwd"
        ]
    ),
    Action(
        key="switch_node_version",
        name="Switch to latest Node.js version",
        commands=[
            "command -v n >/dev/null 2>&1 || npm install -g n",
            "sudo n latest"
        ]
    ),
    Action(
        key="cancel",
        name="Cancel",
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
    
    action = select_action(actions)

    if action == "cancel":
        print(Fore.YELLOW + "Operation cancelled." + Style.RESET_ALL)
    else:
        action.run(server)

if __name__ == "__main__":
    main()

