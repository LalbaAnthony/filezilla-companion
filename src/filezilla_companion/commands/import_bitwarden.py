import os
import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import unquote, urlsplit
from filezilla_companion import bitwarden, prompts
from filezilla_companion.commands.base import Command, Context, confirm_write
from filezilla_companion.console import Console
from filezilla_companion.criteria.base import Action, site_label
from filezilla_companion.filezilla.server import Server
from filezilla_companion.filezilla.sitemanager import decode_remote_dir, encode_remote_dir

# URI schemes, and values of the "protocol" custom field, of the logins to import: FileZilla protocol and default port.
_PROTOCOLS: Dict[str, Tuple[int, int]] = {
    "sftp": (1, 22),
    "ssh": (1, 22),
    "ftp": (0, 21),  # TLS when the server offers it
    "ftps": (3, 990),  # implicit TLS
    "ftpes": (4, 21),  # explicit TLS required
}
_SFTP = 1
_LOGONTYPE_NORMAL = 1
_LOGONTYPE_KEYFILE = 5

# Names shown in the change list.
_PROTOCOL_NAMES = {0: "ftp", 1: "sftp", 3: "ftps", 4: "ftpes", 6: "plain ftp"}
_LOGONTYPE_NAMES = {0: "anonymous", 1: "normal", 2: "ask for password", 3: "interactive", 4: "account", 5: "key file"}

# Server attributes set from a login, with their name in the change list.
_FIELDS: List[Tuple[str, str]] = [
    ("name", "name"),
    ("host", "host"),
    ("port", "port"),
    ("protocol", "protocol"),
    ("user", "user"),
    ("password", "password"),
    ("keyfile", "key file"),
    ("logontype", "logon type"),
    ("remote_dir", "remote dir"),
]

# The line of a site's comments that names the login it comes from. In the comments, because FileZilla drops the XML
# it does not know when it rewrites sitemanager.xml. The lookahead leaves a Windows line ending alone.
_MARKER = re.compile(r"^bitwarden-id:[ \t]*(\S+)[ \t]*(?=\r?$)", re.MULTILINE)

_STATUS_ERRORS = {
    "unauthenticated": "Not logged in to Bitwarden: run `bw login`, then set BW_SESSION to the session key it prints.",
    "locked": "The Bitwarden vault is locked: run `bw unlock`, then set BW_SESSION to the session key it prints.",
}

# Normalized host, user and port: sites at the same address are the same account on the same server.
Address = Tuple[str, str, int]

@dataclass
class Add(Action):
    """A site to create from a login. Its server is not in the site manager until the change is applied."""

    @property
    def label(self) -> str:
        return f"Add {site_label(self.server)}"

@dataclass
class Update(Action):
    """Settings of an existing site to set from the login it comes from or adopts. The reason lists the changes."""
    changes: Dict[str, Any]  # new value by Server attribute, as SiteManager.update() takes them

    @property
    def label(self) -> str:
        return f"Update {site_label(self.server)}: {self.reason}"

class ImportBitwardenCommand(Command):
    slug = "import-bitwarden"
    label = "Import sites from Bitwarden"
    requires_servers = False

    def run(self, context: Context) -> int:
        """Add or update the sites of the vault's FTP/SFTP logins, then apply the changes the user confirms."""
        logins = _read_vault()
        if logins is None:
            return 1

        sites = _sites(logins)
        if not sites:
            Console.warning("No FTP/SFTP login to import in the Bitwarden vault.")
            return 0

        adds, updates, up_to_date = _plan(sites, context.servers)
        if up_to_date:
            Console.info(f"{up_to_date} site(s) up to date.")
        if not adds and not updates:
            Console.success("Nothing to import.")
            return 0

        sections: List[Tuple[str, List[Action]]] = []
        if adds:
            sections.append(("Add", list(adds)))
        if updates:
            sections.append(("Update", list(updates)))
        selected = prompts.select_actions(sections)
        added = [action for action in selected if isinstance(action, Add)]
        updated = [action for action in selected if isinstance(action, Update)]
        if not added and not updated:
            Console.info("No change selected, sitemanager.xml left unchanged.")
            return 0

        Console.info(f"{len(added)} site(s) to add, {len(updated)} to update.")
        if not confirm_write():
            Console.info("sitemanager.xml left unchanged.")
            return 0

        for add in added:
            context.sitemanager.add(add.server)
        for update in updated:
            context.sitemanager.update(update.server, update.changes)
        try:
            backup = context.sitemanager.save()
        except OSError as e:
            Console.error(f"Cannot write sitemanager.xml: {e}")
            return 1

        written = f"Backup: {backup}" if backup else f"Created {context.sitemanager.path}"
        Console.success(f"{len(added)} site(s) added, {len(updated)} updated. {written}")
        return 0

def _read_vault() -> Optional[List[bitwarden.Login]]:
    """Return the logins of the vault, or None after reporting why they cannot be read."""
    bw = bitwarden.find_bw()
    if not bw:
        Console.error("Bitwarden CLI (bw) not found in PATH. Try `npm install -g @bitwarden/cli`.")
        return None
    try:
        status = bitwarden.status(bw)
        if status != "unlocked":
            Console.error(_STATUS_ERRORS.get(status, f"Unexpected Bitwarden vault status: {status}."))
            return None
        Console.info("Syncing the Bitwarden vault...")
        try:
            bitwarden.sync(bw)
        except bitwarden.BitwardenError as e:
            Console.warning(f"Cannot sync the Bitwarden vault, using its local copy: {e}")
        return bitwarden.list_logins(bw)
    except bitwarden.BitwardenError as e:
        Console.error(f"Cannot read the Bitwarden vault: {e}")
        return None

class _Skip(Exception):
    """Raised for a login of an FTP/SFTP site that cannot be imported; the message tells why."""

def _sites(logins: List[bitwarden.Login]) -> List[Tuple[bitwarden.Login, Server]]:
    """Return the logins of FTP/SFTP sites with their site, oldest first, warning about those that cannot be imported."""
    sites: List[Tuple[bitwarden.Login, Server]] = []
    # Oldest first: when several logins claim one address, the original entry wins over its later copies.
    for login in sorted(logins, key=lambda login: (login.created, login.id)):
        try:
            site = _to_site(login)
        except _Skip as e:
            Console.warning(f'Skipping "{login.name}": {e}.')
            continue
        if site is not None:
            sites.append((login, site))
    return sites

def _to_site(login: bitwarden.Login) -> Optional[Server]:
    """
    Return the site described by the login's first FTP/SFTP URI, or None when it has none, e.g. a web login.
    Raises _Skip when the site cannot be imported. Messages never quote the URI, which may hold a password.
    """
    uri = next((uri for uri in login.uris if _scheme(uri) in _PROTOCOLS), None)
    if uri is None:
        return None
    parts = urlsplit(uri)

    protocol_name = login.fields.get("protocol", parts.scheme).lower()
    if protocol_name not in _PROTOCOLS:
        raise _Skip(f'unknown protocol "{protocol_name}"')
    protocol, default_port = _PROTOCOLS[protocol_name]

    if not parts.hostname:
        raise _Skip("no host in its URI")
    try:
        port = parts.port or default_port
    except ValueError:
        raise _Skip("invalid port in its URI") from None

    user = login.username or unquote(parts.username or "")
    if not user:
        raise _Skip("no username")

    keyfile = login.fields.get("keyfile")
    if keyfile:
        if protocol != _SFTP:
            raise _Skip(f"key file on a {protocol_name} site, only SFTP logs in with one")
        # Lets one vault entry name the key on every machine, e.g. `~/.ssh/id_ed25519`.
        keyfile = os.path.expanduser(os.path.expandvars(keyfile))
    password = login.password or None
    if not password and not keyfile:
        raise _Skip("no password or key file")

    # A root path is mostly a trailing slash, not a wish to start in `/` rather than the home directory.
    path = unquote(parts.path)
    return Server(
        login.name, parts.hostname, port, protocol, user, password, keyfile,
        logontype=_LOGONTYPE_KEYFILE if keyfile else _LOGONTYPE_NORMAL,
        remote_dir=encode_remote_dir(path) if path.strip("/") else "",
    )

def _scheme(uri: str) -> str:
    try:
        return urlsplit(uri).scheme
    except ValueError:  # e.g. an unclosed IPv6 bracket
        return ""

def _plan(sites: List[Tuple[bitwarden.Login, Server]], servers: List[Server]) -> Tuple[List[Add], List[Update], int]:
    """
    Return the sites to add, the updates, and the number of sites already up to date. A login updates every site
    marked with its ID. Without any, it adopts every unmarked site at its address, or adds a site, unless another
    login already covers that address: it is then skipped. A site marked with the ID of a login that is not imported
    this run counts as unmarked.
    """
    imported = {login.id for login, _ in sites}
    owned: Dict[str, List[Server]] = {}
    adoptable: Dict[Address, List[Server]] = {}
    for srv in servers:
        item_id = _marker(srv.comments)
        if item_id in imported:
            owned.setdefault(item_id, []).append(srv)
        else:
            adoptable.setdefault(_address(srv), []).append(srv)

    # Once updated, the sites of a login are at its address, whichever login comes first.
    covered: Dict[Address, bitwarden.Login] = {}
    for login, site in sites:
        if login.id in owned:
            covered.setdefault(_address(site), login)

    adds: List[Add] = []
    updates: List[Update] = []
    up_to_date = 0
    for login, site in sites:
        targets = owned.get(login.id)
        if targets is None:
            address = _address(site)
            other = covered.get(address)
            if other is not None:
                Console.warning(f'Skipping "{login.name}": {_format_address(address)} already comes from "{other.name}".')
                continue
            covered[address] = login
            targets = adoptable.pop(address, [])
        if not targets:
            site.comments = _with_marker("", login.id)
            adds.append(Add(site, "", checked=True))
            continue
        for target in targets:
            changes = _changes(target, site, login.id)
            if changes:
                updates.append(Update(target, _describe(target, changes), checked=True, changes=changes))
            else:
                up_to_date += 1
    return adds, updates, up_to_date

def _address(server: Server) -> Address:
    return (server.normalized_host, server.user, server.port)

def _format_address(address: Address) -> str:
    host, user, port = address
    return f"{user}@{host}:{port}"

def _marker(comments: str) -> Optional[str]:
    """Return the ID of the login the site comes from, read in its comments, or None."""
    match = _MARKER.search(comments)
    return match.group(1) if match else None

def _with_marker(comments: str, item_id: str) -> str:
    """Return the comments with the marker line of the login, replacing a former one, or after a blank line."""
    line = f"bitwarden-id: {item_id}"
    if _MARKER.search(comments):
        return _MARKER.sub(lambda _: line, comments, count=1)
    if not comments.strip():
        return line
    return f"{comments.rstrip()}\n\n{line}"

def _changes(target: Server, site: Server, item_id: str) -> Dict[str, Any]:
    """Return the attributes of the target that differ from the login's site, with the login's values."""
    changes: Dict[str, Any] = {}
    for attr, _ in _FIELDS:
        old, new = getattr(target, attr), getattr(site, attr)
        if attr == "host":
            # Host names are case-insensitive, and urlsplit lowercases them.
            same = target.normalized_host == site.normalized_host
        else:
            # A setting saved empty and a missing one are the same.
            same = _empty_as_none(old) == _empty_as_none(new)
        if not same:
            changes[attr] = new
    comments = _with_marker(target.comments, item_id)
    if comments != target.comments:
        changes["comments"] = comments
    return changes

def _empty_as_none(value: Any) -> Any:
    return None if value == "" else value

def _describe(target: Server, changes: Dict[str, Any]) -> str:
    """Return the changes as shown in the change list: old and new values, except the password's."""
    described: List[str] = []
    for attr, name in _FIELDS:
        if attr not in changes:
            continue
        if attr == "password":
            described.append(name)
        else:
            described.append(f"{name} {_show(attr, getattr(target, attr))} → {_show(attr, changes[attr])}")
    if "comments" in changes:
        described.append("link to Bitwarden")
    return ", ".join(described)

def _show(attr: str, value: Any) -> str:
    if attr == "port":
        return str(value)
    if attr in ("protocol", "logontype"):
        if value is None:
            return "unset"
        names = _PROTOCOL_NAMES if attr == "protocol" else _LOGONTYPE_NAMES
        return names.get(value, str(value))
    if attr == "remote_dir" and value:
        value = decode_remote_dir(value) or value
    return f'"{value or ""}"'
