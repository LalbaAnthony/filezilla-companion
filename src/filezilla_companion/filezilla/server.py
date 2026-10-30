import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import List, Optional

server_default_port = 22
server_default_username = ""
server_default_protocol = 1  # 0 = FTP, 1 = SFTP
@dataclass
class Server:
    name: str
    host: str
    port: int
    protocol: int  # 0 = FTP, 1 = SFTP
    user: str
    password: Optional[str] = None
    keyfile: Optional[str] = None
    logontype: Optional[int] = None  # 0 = anonymous, 1 = normal, 2 = ask for password, 3 = interactive, 4 = account, 5 = key file
    comments: str = ""
    colour: int = 0
    remote_dir: str = ""
    local_dir: str = ""
    # The <Server> element the site was parsed from, so the site manager can change it. Not part of the site's identity.
    element: Optional[ET.Element] = field(default=None, compare=False, repr=False)

    @property
    def normalized_host(self) -> str:
        """Return the host as compared between sites: host names are case-insensitive."""
        return self.host.strip().lower()

    @property
    def uses_keyfile(self) -> bool:
        """Check if the site logs in with its key file, which FileZilla ignores under any other logon type."""
        # Without a logon type (files not written by FileZilla), a key file is taken as the way to log in.
        return self.logontype == 5 or (self.logontype is None and bool(self.keyfile))

    @property
    def fullhost(self) -> str:
        """Return the full host string with port if necessary."""
        assert (
            self.host and self.port
        ), "Cannot generate fullhost without host and port."
        return f"{self.host}:{self.port}"

    @property
    def fullname(self) -> str:
        """Return the full name string with user if necessary."""
        assert (
            self.host and self.user
        ), "Cannot generate fullname without host and user."
        return f"{self.user}@{self.host}"

    @property
    def label(self) -> str:
        """Return the nice label."""
        assert self.fullname, "Cannot generate label without fullname."
        if self.name:
            return f"{self.name} ({self.fullname})"
        return f"{self.fullname}"

    @property
    def command(self) -> str:
        """Return the SSH command to connect to the server."""
        assert self.can_connect, "Cannot generate command without host and user."
        cmd_parts = ["ssh"]
        if self.keyfile:
            cmd_parts += ["-i", f'"{self.keyfile}"']
        if self.user and self.host:
            cmd_parts += [f"{self.user}@{self.host}"]
        if self.port and self.port:
            cmd_parts += ["-p", str(self.port)]
        # if self.password:
        #     cmd_parts += ["-o", "PasswordAuthentication=yes"]

        cmd = " ".join(cmd_parts)

        return cmd

    @property
    def is_ftp(self) -> bool:
        """Check if the server is FTP."""
        assert self.protocol in (0, 1), "Invalid protocol value"
        return self.protocol == 0 or self.port == 21 or "ftp." in self.host

    @property
    def is_local(self) -> bool:
        """Check if the server is local. Any server with 192.168.x.x is considered local."""
        assert self.host, "Invalid host value"
        return self.host.startswith("192.168.")

    @property
    def is_sftp(self) -> bool:
        """Check if the server is SFTP."""
        assert self.protocol in (0, 1), "Invalid protocol value"
        return self.protocol == 1 or self.port == 22 or "sftp." in self.host

    @property
    def can_connect(self) -> bool:
        """Check if the server can be connected to."""
        return self.host and self.user and ((not self.is_ftp) or (self.is_sftp))

    def defaulting(self) -> List[str]:
        """Set default values for missing attributes."""

        global server_default_port, server_default_username, server_default_protocol

        updated = []

        if not self.port:
            self.port = server_default_port
            updated.append("port")

        if not self.protocol:
            self.protocol = server_default_protocol
            updated.append("protocol")

        if not self.user:
            self.user = server_default_username
            updated.append("user")

        return updated
