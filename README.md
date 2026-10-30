# FileZilla Companion

FileZilla Companion is a smoll tool that enhances the user experience of FileZilla by providing quick access to the sites saved in the FileZilla site manager. Its main command lets users select a server and automatically opens a terminal window to connect via SSH, copying the password to the clipboard for convenience. It can also clean up the site manager by finding duplicated, broken or ambiguous sites, and import FTP and SFTP sites from a Bitwarden vault.

## Requirements

- Python 3.9+
- An OpenSSH client (`ssh`)
- FileZilla with at least one saved site, except for the Bitwarden import
- The [Bitwarden CLI](https://bitwarden.com/help/cli/) (`bw`) on PATH, only for the Bitwarden import

## Installation

The package is installed in editable mode from the cloned repository, so a `git pull` is enough to update it.

### Windows

1. Install Python if not already installed. You can download it from [python.org](https://www.python.org/downloads/). Ensure that Python is added to your system's PATH during installation.

2. Install pip if not already installed:
    ```sh
    python -m ensurepip --upgrade --user
	# OR
	python -m pip install --upgrade pip
    ```

3. Install the package:
    ```sh
    cd filezilla-companion
    python -m pip install -e .
    ```
    This installs the `filezilla-companion` command in Python's `Scripts` directory. If pip warns that this directory is not on PATH, add it, or run `python -m filezilla_companion` instead.

### Debian

Debian 11 (bullseye) and later. Debian has no `python` command and blocks system-wide `pip install` (PEP 668), so the package goes in a virtual environment.

1. Install the system packages:
    ```sh
    sudo apt install python3 python3-venv openssh-client xclip
    ```
    `xclip` copies the password to the clipboard. On a Wayland session, `wl-clipboard` works too. Without either, the password is not copied and everything else works.

2. Create a virtual environment and install the package:
    ```sh
    cd filezilla-companion
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e .
    ```
    Upgrading pip is required on Debian 11: its pip 20.3 cannot install a `pyproject.toml`-only package in editable mode.

## Usage

```sh
# Windows
filezilla-companion
# Debian
.venv/bin/filezilla-companion
```

Without argument, a menu asks which command to run. Pass a command's flag to skip the menu:

| Flag                 | Command                                                                                                          |
| -------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `--connect`          | Select a server, copy its password to the clipboard and open an SSH session to it in a new terminal window.      |
| `--copy-password`    | Select a server among those with a saved password (FTP servers included) and copy its password to the clipboard. |
| `--list`             | Print every saved server as `name (user@host:port)`.                                                             |
| `--clean`            | Find duplicated, broken or ambiguous sites and remove or rename the ones you confirm. See below.                 |
| `--import-bitwarden` | Add the FTP and SFTP sites of your Bitwarden vault, or update the ones added before. See below.                  |

`filezilla-companion --help` lists the available flags. Without `sitemanager.xml`, or without any valid site in it, the menu only offers the commands that work without saved sites, i.e. the Bitwarden import.

### Cleaning up the site manager

`--clean` asks which criteria to apply (all checked by default), analyzes every site, prints a report, then lists the proposed changes in one checklist where you check or uncheck each change. Nothing is written until you confirm. The previous file is then saved next to it as `sitemanager.<timestamp>.xml.bak`.

| Criterion            | Finds                                                                                         | Proposes                                                                                                 |
| -------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Duplicates           | Sites with the same host, user, password, port and key file.                                  | Removing all copies but the most complete one (most settings filled in).                                 |
| Failed connection    | Sites whose saved credentials do not log in (rejected, timeout, unknown host, refused...).    | Removing them; unchecked for private addresses. Sites that cannot be tested are only reported.           |
| Divergent passwords  | Sites with the same host, user and port but different passwords.                              | Removing those that fail to log in, checked only when another site of the group logs in.                 |
| Missing key file     | Key file logons whose file does not exist.                                                    | Removing them.                                                                                           |
| No credentials       | Normal logons without password or key file.                                                   | Removing them.                                                                                           |
| Duplicate names      | Sites sharing a name while pointing to different servers.                                     | Renaming them to `name (user@host)`, or `name (user@host:port)` when needed.                             |
| Private addresses    | Sites on `localhost` or a private IP address.                                                 | Nothing: report only.                                                                                    |

Before checking connections, keep in mind:

- The failed connection test logs in to every site with its saved password or key, up to 16 servers at a time and one site at a time per host, with a 10 second timeout per step. These logins appear in the servers' logs, and repeated failures may trigger fail2ban or lock an account.
- SFTP host keys and FTPS certificates are not verified: the test sends the saved credentials to whatever answers at the address. Like FileZilla, FTP sites set to "use explicit FTP over TLS if available" fall back to plain FTP, where the password travels unencrypted.
- PuTTY `.ppk` keys and keys protected by a passphrase cannot be tested; such sites are reported as not testable.

Close FileZilla before writing the changes: its Site Manager may overwrite `sitemanager.xml` and undo them. The command warns when it detects FileZilla running.

On Debian, the SSH session opens in the desktop's default terminal (`x-terminal-emulator`), falling back to gnome-terminal, konsole, xfce4-terminal, then xterm. Without a graphical session (e.g. when logged in over SSH), it runs in the current terminal.

FileZilla's `sitemanager.xml` is read from `%APPDATA%\FileZilla` on Windows. On Debian, it is looked up in `~/.filezilla`, then `$XDG_CONFIG_HOME/filezilla` (default `~/.config/filezilla`), then the Flatpak config directory.

### Importing from Bitwarden

`--import-bitwarden` adds the FTP and SFTP sites stored in your Bitwarden vault to the site manager, and updates the ones it added before. It never removes a site. It needs the Bitwarden CLI and an unlocked vault: run `bw login` once, then `bw unlock`, and set the `BW_SESSION` environment variable to the session key it prints. The command first syncs the vault; when that fails (e.g. offline), it warns and uses the CLI's local copy.

Every Login item with an FTP or SFTP URI is imported:

| Item                    | Site                                                                                                                                                                                                                                                                                                                                               |
| ----------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| URI                     | The first URI with a `sftp://`, `ssh://`, `ftp://`, `ftps://` or `ftpes://` scheme gives the host, port and protocol: SFTP (port 22) for `sftp` and `ssh`, FTP over TLS if available (21) for `ftp`, implicit TLS (990) for `ftps`, explicit TLS (21) for `ftpes`. A port in the URI wins. Items without such a URI, like web logins, are ignored. |
| URI path                | Default remote directory: `sftp://host/var/www` starts in `/var/www`. No path, or `/`, leaves it empty.                                                                                                                                                                                                                                            |
| Name                    | Site name.                                                                                                                                                                                                                                                                                                                                         |
| Username                | User. When empty, the user of the URI (`sftp://deploy@host`).                                                                                                                                                                                                                                                                                      |
| Password                | Saved password, in base64 like FileZilla does: anyone who can read `sitemanager.xml` can read it.                                                                                                                                                                                                                                                  |
| `protocol` custom field | Overrides the protocol of the URI scheme, with the same names, e.g. `ftpes` on an `ftp://` URI.                                                                                                                                                                                                                                                    |
| `keyfile` custom field  | Path to a private key, for a key file logon (SFTP only). `~` and environment variables are expanded. A password is saved too.                                                                                                                                                                                                                      |

Items without a username, without a password or key file, with a key file on an FTP site, or with an unknown `protocol` value are skipped with a warning.

An imported site has a `bitwarden-id: <item id>` line in its comments, which links it to its item: the next imports update every site linked to an item, wherever it is in the site manager. An item without a linked site adopts the sites with the same host, user and port that are not linked to another imported item, adding the line to their comments, or else it is added at the top level of the site manager. Items without a linked site whose host, user and port are already covered by another item are skipped with a warning; when several such items compete, the oldest one wins. The settings that do not come from Bitwarden, like the local directory, the colour or the rest of the comments, are kept.

The changes are listed in one checklist, all checked, with the old and new value of each changed setting (the password is only named). Nothing is written until you confirm. The previous file is then saved next to it as `sitemanager.<timestamp>.xml.bak`, or, without any `sitemanager.xml` yet, the file is created (on Debian, readable by you only).

Keep in mind:

- FileZilla does not keep a password under a key file logon: once it rewrites `sitemanager.xml`, the next import proposes to save the password again.
- A password encrypted by FileZilla's master password cannot be compared: such a site always shows a password change, which saves the Bitwarden password in base64.
- Bitwarden's master password re-prompt does not apply to the CLI: such items are imported like the others.
- Close FileZilla before writing the changes, as with `--clean`.

## Tests

The tests import the installed package, so run them after the installation above, from the repository root:

```sh
# Windows
python -m unittest
# Debian
.venv/bin/python -m unittest
```
