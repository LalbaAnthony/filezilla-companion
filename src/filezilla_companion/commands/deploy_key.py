from typing import List, Optional
from filezilla_companion import prompts, ssh_keys
from filezilla_companion.commands.base import Command, Context, confirm_write
from filezilla_companion.console import Console
from filezilla_companion.criteria.base import site_label
from filezilla_companion.filezilla.server import Server
from filezilla_companion.ssh_keys import DeployResult, PrivateKey, PublicKey

_LOGONTYPE_KEYFILE = 5

class DeployKeyCommand(Command):
    slug = "deploy-key"
    label = "Deploy an SSH key to servers"

    def run(self, context: Context) -> int:
        """Add a public key to the servers picked by the user, then switch the sites where it logs in to that key."""
        try:
            keys = ssh_keys.list_public_keys()
        except OSError as e:
            Console.error(f"Cannot read {ssh_keys.ssh_dir()}: {e}")
            return 1
        if not keys:
            Console.error(f"No public key found in {ssh_keys.ssh_dir()}. Create one with `ssh-keygen -t ed25519`.")
            return 1

        key = prompts.select_key(keys)
        private = _load_private_key(key)

        servers = [srv for srv in context.servers if ssh_keys.can_deploy(srv, key)]
        excluded = len(context.servers) - len(servers)
        if excluded:
            Console.info(f"{excluded} site(s) not offered: not SFTP, no usable saved credentials, or already using this key.")
        if not servers:
            Console.error("No site to deploy this key to.")
            return 1

        selected = prompts.select_servers(servers)
        if not selected:
            Console.info("No server selected, nothing changed.")
            return 0

        for srv in selected:
            Console.info(f"  {site_label(srv)}")
        if not Console.confirm(f"Add {key.name} to authorized_keys on these {len(selected)} server(s)?"):
            Console.info("Nothing changed.")
            return 0

        results = _deploy(selected, key, private)
        _report(selected, results)
        exit_code = 1 if any(result.failed for result in results) else 0

        verified = [srv for srv, result in zip(selected, results) if result.verified]
        if not verified:
            return exit_code

        Console.warning(
            f"{len(verified)} site(s) will log in with {key.private_path}, and their saved password will be removed from "
            "sitemanager.xml (the backup keeps it)."
        )
        if not confirm_write():
            Console.info("sitemanager.xml left unchanged. The key stays on the servers.")
            return exit_code

        for srv in verified:
            context.sitemanager.update(srv, {
                "logontype": _LOGONTYPE_KEYFILE,
                "keyfile": key.private_path,
                "password": None,
            })
        try:
            backup = context.sitemanager.save()
        except OSError as e:
            Console.error(f"Cannot write sitemanager.xml: {e}")
            return 1

        Console.success(f"{len(verified)} site(s) switched to the key. Backup: {backup}")
        return exit_code

def _load_private_key(key: PublicKey) -> Optional[PrivateKey]:
    """Return the private key of the pair, or None after warning that the sites will not switch to it."""
    try:
        return ssh_keys.load_private_key(key)
    except ssh_keys.KeyUnavailable as e:
        Console.warning(f"Cannot test logins with {key.name}: {e}. It can be deployed, but the sites will keep their logon.")
        return None

def _deploy(servers: List[Server], key: PublicKey, private: Optional[PrivateKey]) -> List[DeployResult]:
    total = len(servers)

    def show(done: int, failed: int) -> None:
        Console.progress(f"Deploying the key: {done}/{total} ({failed} failed)", done == total)

    show(0, 0)
    return ssh_keys.deploy_all(servers, key, private, show)

def _report(servers: List[Server], results: List[DeployResult]) -> None:
    for srv, result in zip(servers, results):
        message = f"{site_label(srv)}: {result.detail}"
        if result.failed:
            Console.error(message)
        elif result.verified:
            Console.success(message)
        else:
            Console.warning(message)
