import os
import sys
import base64
import platform
import subprocess
import shutil
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import List, Optional

from InquirerPy import inquirer
from colorama import init as colorama_init, Fore, Style
import pyperclip


@dataclass
class Server:
    name: str
    host: str
    port: int
    protocol: int  # 0 = FTP, 1 = SFTP
    user: str
    password: Optional[str] = None
    keyfile: Optional[str] = None

    @property
    def display_label(self) -> str:
        """Return the colored label for CLI display."""
        label = f"{self.name} ({self.host}:{self.port})"
        if self.protocol == 1:
            return f"{Fore.GREEN}{label}{Style.RESET_ALL}"
        return f"{Fore.RED}{label}{Style.RESET_ALL}"

    def connect_ssh(self):
        """Open a new terminal window and initiate SSH connection."""
        cmd_parts = ['ssh']
        if self.keyfile:
            cmd_parts += ['-i', f'"{self.keyfile}"']
        cmd_parts += [f"{self.user}@{self.host}", '-p', str(self.port)]
        cmd = ' '.join(cmd_parts)

        if self.password:
            pyperclip.copy(self.password)
            print("Mot de passe copié dans le presse-papier.")

        system = platform.system()
        if system == 'Windows':
            subprocess.Popen(['start', 'cmd', '/k', cmd], shell=True)
        else:
            for emulator in (['gnome-terminal', '--'], ['xterm', '-e'], ['konsole', '-e']):
                if shutil.which(emulator[0]):
                    subprocess.Popen(emulator + [cmd + '; exec $SHELL'])
                    return
            print(f"Lancez manuellement: {cmd}")


def parse_sitemanager(path: str) -> List[Server]:
    """
    Parse FileZilla sitemanager.xml into Server instances.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"Configuration file not found: {path}")

    tree = ET.parse(path)
    servers: List[Server] = []
    for node in tree.findall('.//Server'):
        name = node.findtext('Name') or 'Unnamed'
        host = node.findtext('Host') or ''
        port = int(node.findtext('Port') or 22)
        protocol = int(node.findtext('Protocol') or 0)
        user = node.findtext('User') or ''

        password = None
        pass_elem = node.find('Pass')
        if pass_elem is not None and pass_elem.text:
            try:
                password = base64.b64decode(pass_elem.text).decode('utf-8')
            except Exception:
                password = pass_elem.text

        keyfile = node.findtext('Keyfile')
        servers.append(Server(name, host, port, protocol, user, password, keyfile))
    return servers


def select_server(servers: List[Server]) -> Server:
    """Prompt the user to select a server via a fuzzy search menu."""
    choices = [{'name': srv.display_label, 'value': srv} for srv in servers]
    selected = inquirer.fuzzy(
        message="Sélectionnez un site:",
        choices=choices,
        max_height="70%"
    ).execute()
    return selected


def get_sitemanager_path() -> str:
    """Determine FileZilla sitemanager.xml path for current OS."""
    if platform.system() == 'Windows':
        return os.path.expandvars(r"%APPDATA%\FileZilla\sitemanager.xml")
    return os.path.expanduser('~/.config/filezilla/sitemanager.xml')


def main():
    colorama_init(autoreset=True)

    sitemanager_path = get_sitemanager_path()
    try:
        servers = parse_sitemanager(sitemanager_path)
    except FileNotFoundError as e:
        print(e)
        sys.exit(1)

    server = select_server(servers)

    if server.protocol != 1:
        print(Fore.YELLOW + "Sélection FTP détectée. Connexion SSH non disponible pour ce protocole." + Style.RESET_ALL)
        sys.exit(0)

    server.connect_ssh()


if __name__ == '__main__':
    main()
