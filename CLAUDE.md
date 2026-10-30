# CLAUDE.md

## Overview

FileZilla Companion is a CLI that reads FileZilla's saved sites (`sitemanager.xml`) and runs a command on them. The command is picked in a fuzzy-search menu at startup, or passed as a `--<slug>` flag to skip the menu. Commands: `connect` (pick a site, copy its password to the clipboard, open an SSH session in a new terminal window), `copy-password` (pick a site with a password, copy it), `list` (print every site), `clean` (analyze the sites with pluggable criteria, then remove or rename the ones the user confirms in `sitemanager.xml`), `import-bitwarden` (read the FTP/SFTP Login items of a Bitwarden vault through the `bw` CLI, then add or update the sites the user confirms). Supported platforms: Windows and Debian-family Linux.

## Tech stack

- Python. `requires-python >= 3.9`; the code uses no newer syntax (`typing.List`/`Optional`, no `X | Y` unions, no `match`). Keep it that way.
- Packaging: `pyproject.toml` with the setuptools backend (>= 64, for PEP 660 editable installs), src layout, console script `filezilla-companion` → `filezilla_companion.__main__:run`. Dependencies are unpinned. No `requirements.txt`, no lockfile.
- CI: GitHub Actions. `.github/workflows/tests.flow.yml` holds the triggers (pushes to `main`/`develop`, every pull request) and the concurrency group, and includes `.github/workflows/tests.inc.yml`, which runs the test suite across `ubuntu-24.04` and `windows-latest` × Python 3.9 to 3.14. Linux is pinned to `ubuntu-24.04` because `actions/setup-python` has no Python 3.9 build for Ubuntu 26.04 (`ubuntu-latest`); move it back to `ubuntu-latest` once 3.9 is dropped and every version in the matrix has a build for that image. When `requires-python` or a new Python release changes the supported range, update the matrix in `tests.inc.yml`.
- Dependencies: `InquirerPy` (fuzzy and checkbox menus), `colorama` (colored output), `paramiko` (SFTP login test, needs >= 3.2 for `PKey.from_path`), `pyperclip` (clipboard).
- Standard library only otherwise: `argparse`, `abc`, `xml.etree`, `subprocess`, `shutil`, `base64`, `dataclasses`, `ftplib`, `ssl`, `socket`, `ipaddress`, `queue`, `threading`, `json`, `re`, `urllib.parse`, `unittest`.

## Structure

- `src/filezilla_companion/__main__.py` — entry point: `parse_args()` (one `--<slug>` flag per command), `main(argv)` (loads the site manager, picks and runs the command), `run()` (console script target, pauses on failure).
- `src/filezilla_companion/commands/__init__.py` — `COMMANDS`, the explicit registry; its order is the menu order, the first entry is preselected.
- `src/filezilla_companion/commands/base.py` — `Command` ABC (`slug`, `label`, `requires_servers`, abstract `run(context) -> int`), the `Context` dataclass (`sitemanager`, plus a `servers` property), and `confirm_write()` (FileZilla-running warning then Y/n, shared by the commands that write `sitemanager.xml`).
- `src/filezilla_companion/commands/connect.py`, `copy_password.py`, `list_servers.py`, `clean.py`, `import_bitwarden.py` — one `Command` subclass per module. `import_bitwarden.py` also holds the item-to-site mapping, the matching plan and its `Add`/`Update` actions.
- `src/filezilla_companion/criteria/__init__.py` — `CRITERIA`, the explicit registry of the `clean` criteria; its order is the menu, report and change list order.
- `src/filezilla_companion/criteria/base.py` — `Criterion` ABC and its two families `GroupCriterion`/`SiteCriterion`, the `Finding` and `Action` (`Remove`, `Rename`) dataclasses, `Analysis` (sites + cached credential tests), `site_label()`.
- `src/filezilla_companion/criteria/duplicates.py`, `failed_connection.py`, `divergent_passwords.py`, `missing_keyfile.py`, `no_credentials.py`, `duplicate_names.py`, `private_host.py` — one criterion per module.
- `src/filezilla_companion/bitwarden.py` — wraps the `bw` CLI: `find_bw()`, `status()`, `sync()`, `list_logins()` (Login items as `Login` dataclasses); raises `BitwardenError`.
- `src/filezilla_companion/auth.py` — `check()` logs in to a site (SFTP via paramiko, FTP/FTPS via ftplib) and returns an `AuthResult`; `check_all()` runs it in parallel.
- `src/filezilla_companion/filezilla/sitemanager.py` — locates FileZilla's `sitemanager.xml`; `load_sitemanager()` parses it into a `SiteManager` (path, XML tree, `Server` objects) that can `remove()`, `rename()`, `add()`, `update()` and `save()` with a backup; `empty_sitemanager()` stands for a file that does not exist yet; `encode_remote_dir()`/`decode_remote_dir()` convert a Unix path to and from FileZilla's `RemoteDir` format.
- `src/filezilla_companion/filezilla/server.py` — `Server` dataclass: display labels, SSH command string, protocol checks, defaults, and the `<Server>` element it comes from.
- `src/filezilla_companion/filezilla/process.py` — `is_running()` tells whether FileZilla is running (`tasklist`/`pgrep`).
- `src/filezilla_companion/prompts.py` — InquirerPy menus: fuzzy `select_server()`, `select_command()`; checkbox `select_criteria()`, `select_actions()`.
- `src/filezilla_companion/ssh.py` — locates and checks the `ssh` client; `connect()` copies the password and opens the session.
- `src/filezilla_companion/terminal.py` — locates `cmd.exe` and terminal emulators; `open_in_terminal()` runs a shell command in a new window.
- `src/filezilla_companion/clipboard.py` — `copy()`, which raises `ClipboardError` so callers do not depend on pyperclip.
- `src/filezilla_companion/console.py` — `Console`: colored output (`info`/`success`/`warning`/`error`), an in-place `progress()` line and a Y/n prompt.
- `tests/` — unittest package mirroring the source tree: `tests/test_<module>.py`, `tests/commands/test_<module>.py`, `tests/criteria/test_<module>.py`, `tests/filezilla/test_<module>.py`, plus `tests/commands/test_registry.py` for `COMMANDS`, `tests/criteria/test_registry.py` for `CRITERIA`, and `tests/helpers.py` (`make_context()`).

Imports are absolute (`from filezilla_companion.console import Console`).

## Commands

All commands run from the repository root.

Install (editable, for both usage and development):

```sh
# Windows
python -m pip install -e .

# Debian (PEP 668 blocks system-wide pip, so use a venv; Debian 11's pip 20.3 needs the upgrade for -e)
sudo apt install python3 python3-venv openssh-client xclip
python3 -m venv .venv
.venv/bin/pip install --upgrade pip
.venv/bin/pip install -e .
```

Run (interactive without a flag, needs a TTY):

```sh
# Windows
filezilla-companion [--connect | --copy-password | --list | --clean | --import-bitwarden]
python -m filezilla_companion [...]   # when Python's Scripts directory is not on PATH

# Debian
.venv/bin/filezilla-companion [...]
```

Test (requires the editable install):

```sh
# Windows
python -m unittest

# Debian
.venv/bin/python -m unittest
```

There is no build step. No linter, formatter, or type checker is configured.

## Architecture

Single process, linear flow in `main()` (`src/filezilla_companion/__main__.py`):

1. `parse_args()` builds a mutually exclusive group with one `store_const` flag per `COMMANDS` entry; the flag stores the `Command` instance itself. Invalid usage exits with code 2 from argparse, without the failure pause.
2. `Console.setup()` initializes colorama.
3. `get_sitemanager_path()` then `load_sitemanager()` collect every `<Server>` element at any depth (folders included). Entries without `Host` or `User` are skipped with a warning (they stay in the file). `<Pass>` is base64-decoded; the raw text is kept if decoding fails. Each `Server` keeps its element in `Server.element`. A missing file gives `empty_sitemanager()` at the path that would be read.
4. Without any site (missing file or empty result), only the commands with `requires_servers = False` are available: the menu is limited to them after a warning, and a flag for another command is an error (exit 1). With no such command at all, the menu path is an error too.
5. Without a flag, `prompts.select_command()` shows the menu; labels include the flag (`Connect to a server (--connect)`).
6. `command.run(Context(sitemanager))` returns the exit code.

Commands:

- `ConnectCommand` (`--connect`): checks `ssh.find_ssh()` + `ssh_is_functional()` (runs `ssh -V`), then `select_server()`, `Server.defaulting()`, rejects the server if `is_ftp` or not `can_connect`, then `ssh.connect()`. `ssh.connect()` copies the password (a `ClipboardError` is only a warning), then calls `terminal.open_in_terminal(Server.command)`:
  - Windows: `cmd /k <command>` via `subprocess.Popen` with `CREATE_NEW_CONSOLE` (new console window; a new Windows Terminal window or tab when WT is the default terminal).
  - POSIX with `DISPLAY` or `WAYLAND_DISPLAY` set and a known emulator on PATH: `<terminal> sh -c '<command>; exec "${SHELL:-/bin/sh}"'`, detached with `start_new_session=True`. Emulator preference order is `terminal._POSIX_TERMINALS`.
  - POSIX otherwise: `subprocess.run(command, shell=True)` in the current terminal (blocks until ssh exits).
- `CopyPasswordCommand` (`--copy-password`): menu limited to servers with a password, FTP included, no `defaulting()`. No such server, or a `ClipboardError`, is an error (exit 1).
- `ListServersCommand` (`--list`): prints every server as `name (user@host:port)`, or `user@host:port` without a name, FTP included. Never fails.
- `CleanCommand` (`--clean`):
  1. `prompts.select_criteria(CRITERIA)` (checkbox, all checked, at least one required).
  2. Each selected criterion's `evaluate(Analysis(servers))` returns `Finding`s (title, sites, proposed `Action`s, `keep_one`). Everything is analyzed before any question.
  3. Report: per criterion, `label: summary` then each finding's title and sites.
  4. `_merge_actions()` builds one section per criterion. An action proposed by several criteria (same site, same `Action` type) is listed once, under the first criterion in `CRITERIA` order, with the reasons joined and checked if any criterion checks it. No action at all: exit 0.
  5. `prompts.select_actions()` (checkbox, preset to each `Action.checked`). Renames of removed sites are ignored; renames whose name no longer collides once removals are applied are dropped and reported.
  6. Recap with counts, plus a warning for every `keep_one` finding whose sites are all removed (duplicates, divergent passwords).
  7. `confirm_write()`: `process.is_running()`, a warning if FileZilla runs or cannot be checked, then `Console.confirm()`. Declining exits 0 without writing.
  8. `SiteManager.remove()`/`rename()`, then `save()`: `sitemanager.<YYYYmmdd-HHMMSS>.xml.bak` copy (with a `-N` suffix if taken), write to `sitemanager.xml.tmp` (created `0600`), copy the replaced file's mode onto it outside Windows, `os.replace`. Any exception there, Ctrl+C included, removes the temporary file and a partial backup; an `OSError` is exit 1.
- `ImportBitwardenCommand` (`--import-bitwarden`, `requires_servers = False`):
  1. `bitwarden.find_bw()`; `status()` must be `unlocked` (a valid `BW_SESSION`), otherwise exit 1 with the `bw login`/`bw unlock` instructions. A failing `sync()` is only a warning; a failing `list_logins()` is exit 1. Every `bw` call runs with `--nointeraction`.
  2. `_sites()`: logins sorted by `creationDate` (oldest first, ID on a tie), each mapped by `_to_site()` to a `Server` from its first URI whose scheme is in `_PROTOCOLS` (`sftp`/`ssh` → 1, `ftp` → 0, `ftps` → 3, `ftpes` → 4); other logins are ignored silently. The `protocol` custom field overrides the scheme but does not make a login importable; the port defaults per protocol; the URI path becomes `RemoteDir` (`/` or no path is empty); the username falls back to the URI user; the `keyfile` field (SFTP only, `~` and variables expanded) gives logon type 5 with the password stored too, otherwise logon type 1. A missing username, a missing password and key file, a key file on FTP, an unknown protocol, a bad port or host: skipped with a warning (`_Skip`).
  3. `_plan()`: a site is linked to a login by a `bitwarden-id: <id>` line in its `<Comments>` (`_MARKER`). A login updates every site linked to it, and nothing else. A login without a linked site adopts every unlinked site at its address (`normalized_host`, user, port), or is added at the top level, unless another login already covers that address (one with linked sites, or an earlier one in this run): it is then skipped with a warning. A site linked to an ID that is not imported this run (deleted or skipped login) counts as unlinked. Updates set every `_FIELDS` attribute that differs (host compared case-insensitively, empty and missing settings equal) plus the marker, which leaves the rest of the comments alone; sites without any difference count as up to date.
  4. `prompts.select_actions()` with an `Add` and an `Update` section, all checked; update labels show old → new values (password only named, `RemoteDir` decoded, protocol and logon type by name). Then a recap, `confirm_write()`, `SiteManager.add()`/`update()`, `save()`. A missing file is created, without backup.

Criteria (`CRITERIA` order) and what they propose:

| Slug                  | Family | Match                                                                               | Action                                                                                     |
| --------------------- | ------ | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| `duplicates`          | group  | same `normalized_host`, user, password, port, keyfile                               | `Remove` every copy, checked, except the most complete one (first on a tie), unchecked     |
| `failed-connection`   | site   | every `AuthResult` other than `OK`, grouped by `reason`                             | `Remove` checked; unchecked for a private host; nothing for `UNTESTABLE`                   |
| `divergent-passwords` | group  | same `normalized_host`, user, port, more than one password; key file sites excluded | `Remove` each site, checked only if it failed while another site of the group logged in    |
| `missing-keyfile`     | site   | `uses_keyfile` and no keyfile set or file missing                                   | `Remove` checked                                                                           |
| `no-credentials`      | site   | logon type normal or unset, no password, not `uses_keyfile`                         | `Remove` checked                                                                           |
| `duplicate-names`     | group  | same name, at least two different `user@host:port`                                  | `Rename` to `name (user@host)`, or `name (user@host:port)`, avoiding names in use; checked |
| `private-host`        | site   | `localhost`, or a private, loopback or link-local IP literal (no DNS lookup)        | none (report only)                                                                         |

Credential tests (`auth.check()`), shared through `Analysis.check_credentials()`/`auth_result()` and cached per site (`id()`):

- SFTP (protocol 1): `paramiko.Transport` over `socket.create_connection`, `start_client`, then `auth_publickey` (logon type 5, or unset with a keyfile) or `auth_password` (falls back to keyboard-interactive). Host keys are not checked. Partial authentication counts as `OK`.
- FTP: protocol 0 tries `AUTH TLS` and falls back to plain FTP like FileZilla, 4 requires TLS, 3 is implicit TLS (`_ImplicitFTPTLS`), 6 is plain. Certificates are not checked. Login through `login(..., secure=False)` so `FTP_TLS` does not resend `AUTH TLS`.
- Not tested (`UNTESTABLE`, before any connection): other protocols, logon types 2/3/4/6+, no password, anonymous SFTP, key logon over FTP, missing/`.ppk`/passphrase-protected key.
- Exceptions map to `REJECTED` (paramiko `AuthenticationException`, FTP `error_perm` at login), `HOST_NOT_FOUND` (`gaierror`), `TIMEOUT`, `REFUSED`, and `ERROR` for the rest, unexpected exceptions included, so one server cannot abort the run.
- `check_all()`: up to `DEFAULT_WORKERS = 16` daemon threads take hosts from a queue, each host's sites tested sequentially (no login bursts on a shared host), `DEFAULT_TIMEOUT = 10` s per step. `on_progress(done, failed)` runs under a lock; `Analysis` prints it with `Console.progress()`. On Ctrl+C or a failing callback, the exception is raised at once: queued hosts are never started, and the tests in progress end in the background without recording or reporting. Daemon threads, not `ThreadPoolExecutor`, whose non-daemon workers Python joins at exit: a Ctrl+C would wait for every test in progress (up to several timeouts each).

The password is never passed to `ssh`; the user pastes it at the ssh prompt. `run()` waits for Enter only when the exit code is not 0; a double-clicked launch of `--list` or `--copy-password` closes its window on success.

Ctrl+C: `KeyboardInterrupt` (raised by InquirerPy prompts, `input()`, `subprocess.run`, `check_all()`) propagates to `run()`, which prints `Interrupted.` and returns `EXIT_INTERRUPTED` (130) without the pause; nothing is written unless `save()` already completed. Ctrl+C at the pause closes like Enter and keeps the failure exit code. `bw` and the no-GUI `ssh` share the console, so they get the Ctrl+C too; the Windows `cmd` window and the POSIX graphical terminal (`start_new_session`) do not.

Module dependencies (all under `filezilla_companion`): `__main__` → `commands`, `prompts`, `console`, `filezilla.sitemanager`; `commands.base` → `console`, `filezilla.process`, `filezilla.sitemanager`, `filezilla.server`; `commands.*` → `commands.base`, `console`, and as needed `prompts`, `ssh`, `clipboard`, `criteria`, `bitwarden`, `filezilla.sitemanager`, `filezilla.process`; `criteria.*` → `criteria.base`, `auth`, `filezilla.server`; `criteria.base` → `auth`, `console`, `filezilla.server`; `auth` → `filezilla.server`; `ssh` → `clipboard`, `terminal`, `console`, `filezilla.server`; `terminal` → `console`; `filezilla.sitemanager` → `console`, `filezilla.server`; `prompts` → `filezilla.server` (imports `commands.base` and `criteria.base` only under `TYPE_CHECKING`, see Gotchas); `filezilla.server`, `filezilla.process`, `bitwarden`, `clipboard` and `console` have no internal dependency.

## Adding a command

1. Create `src/filezilla_companion/commands/<name>.py` with a `Command` subclass setting `slug` (kebab-case, becomes the `--<slug>` flag) and `label` (menu text and `--help` text), and implementing `run(self, context: Context) -> int`.
2. Append an instance to `COMMANDS` in `commands/__init__.py` at the wanted menu position.
3. Add `tests/commands/test_<name>.py`. `tests/commands/test_registry.py` already enforces unique kebab-case slugs and non-empty labels.

Checks a command needs (e.g. a working `ssh`) belong in its `run()`; only the site manager loading is shared, through `Context`. Set `requires_servers = False` on a command that works without saved sites: it then runs with an empty site manager when `sitemanager.xml` is missing or empty. A command that writes `sitemanager.xml` calls `confirm_write()` first. Data shared by several commands goes in `Context` instead of a new `run()` parameter.

## Adding a criterion

1. Create `src/filezilla_companion/criteria/<name>.py` with a subclass setting `slug` (kebab-case) and `label` (menu and report heading):
   - `GroupCriterion` for sites sharing something: implement `key(server)` (None leaves the site out), `describe(group)` (finding title) and `resolve(group, analysis)` (actions); override `is_group()` when sharing the key is not enough, `prepare(servers, analysis)` to compute something for every grouped site at once, and set `keep_one = True` when removing a whole group deserves a warning.
   - `SiteCriterion` for a check on each site: implement `check(server, analysis)` returning a reason or None (sites are grouped by reason); override `propose()` to change the default checked `Remove` (return None for report-only), and `prepare(analysis)` for batch work.
   - `Criterion` directly only when neither fits: implement `evaluate()` and `summary()`.
2. Add an instance to `CRITERIA` in `criteria/__init__.py`. Its position sets the menu, report and change list order, and which section lists a change proposed by several criteria.
3. Add `tests/criteria/test_<name>.py`. `tests/criteria/test_registry.py` already enforces unique kebab-case slugs and non-empty labels.

A criterion needing credential tests calls `analysis.check_credentials(servers)` in `prepare()` (one parallel pass with progress), then `analysis.auth_result(server)`; a criterion listed after `failed-connection` reuses its results. Results computed for several criteria go in `Analysis` rather than on the criterion: `CRITERIA` holds shared instances. New action kinds subclass `Action` (dataclass with a `label` property) and need handling in `CleanCommand.run()`.

## Conventions

- All user-facing output goes through `Console.info`/`success`/`warning`/`error`, not bare `print`.
- Fatal errors inside a command: `Console.error(...)` then `return 1` from `run()`. `main()` does the same for the shared site manager checks. Session launch failures in `ssh.connect()`/`terminal.open_in_terminal()` raise `OSError` (including `FileNotFoundError`) and are caught in `ConnectCommand.run()`.
- Ctrl+C: only `run()` catches `KeyboardInterrupt`. Catch `Exception`, never `BaseException` or a bare `except:`, unless it re-raises: cleanup that must also run on Ctrl+C is `except BaseException:` + `raise` (`SiteManager.save()`, `auth.check_all()`).
- Modules wrapping a third-party library or tool expose their own exception (`clipboard.ClipboardError`, `bitwarden.BitwardenError`) or result type (`auth.AuthResult`, `bitwarden.Login`) so callers do not import the library or parse the tool's output.
- Type hints on every function via `typing`; docstrings on public functions; comments explain why, not what.
- OS branching that tests must exercise uses `platform.system()`. `sys.platform == "win32"` is only used to gate hardcoded Windows fallback paths in `ssh.find_ssh()` and `terminal.find_cmd()`.
- Lookup tables are module constants: `ssh._WINDOWS_SSH_PATHS` (Windows ssh fallbacks), `terminal._POSIX_TERMINALS` (ordered argv prefixes for terminal emulators), `auth._UNSUPPORTED_LOGONTYPES`, `duplicate_names._SUFFIXES`, `import_bitwarden._PROTOCOLS`/`_FIELDS`, `sitemanager._SETTINGS` (the attributes `add()`/`update()` write, with their element).
- GitHub Actions: when appropriate, put the jobs in a reusable workflow named `*.inc.yml` (`on: workflow_call`) and include it from a workflow named `*.flow.yml` that holds the triggers (e.g. `tests.inc.yml` is included in `tests.flow.yml`). Concurrency groups belong in the `*.flow.yml`: inside a called workflow, `github.workflow` is the caller's name, so the same group defined there would deadlock with the caller's.

## Testing

- Framework: standard library `unittest` and `unittest.mock`. `tests/` and its subdirectories are packages (`__init__.py`), so `python -m unittest` discovers them from the repository root and imports `filezilla_companion` from the editable install.
- Patching uses `mock.patch.object(<module>, "<attr>")` on imported modules (e.g. `mock.patch.object(terminal.subprocess, "Popen")`, `mock.patch.object(prompts, "select_server")`). Command modules call collaborators through their module (`ssh.connect`, `prompts.select_server`, `clipboard.copy`) so these patches take effect.
- Tests never spawn processes, open menus, open network connections, or read the real FileZilla config: they patch `subprocess.Popen`/`run`, `shutil.which`, `pyperclip.copy`/`clipboard.copy`, `inquirer.fuzzy`/`checkbox`, `prompts.select_*`, `Console.setup`, `os.environ` (`mock.patch.dict`), `auth.check` (criteria and `Analysis` tests), `auth.socket.create_connection`, `auth.paramiko.Transport`, `auth.ftplib.FTP`/`FTP_TLS`, `auth._ImplicitFTPTLS`, `process.subprocess.run`, `bitwarden.subprocess.run`, `bitwarden.find_bw`/`status`/`sync`/`list_logins` (command tests), and use `tempfile` for `sitemanager.xml`, key files and fake home directories. Console output is asserted by patching `sys.stdout` with `io.StringIO`.
- Commands get their `Context` from `tests.helpers.make_context(servers)` (in-memory site manager); `CleanCommand` and `ImportBitwardenCommand` tests load a real temporary `sitemanager.xml` instead, since they check what is written. `ImportBitwardenCommand` tests record the change labels when the mocked `select_actions` is called: labels are properties computed from the sites, which show the new values once the changes are applied.
- Key file tests generate keys with `cryptography` (a paramiko dependency); the `.ppk` test only needs the file header.
- `Console.progress()` throttles non-terminal output through the class attribute `Console._last_progress`, which outlives a test: tests asserting progress lines patch it to `0.0`.
- The `check_all()` Ctrl+C test simulates it with `_thread.interrupt_main()` from the mocked `check`, after a short sleep so `check_all()` already waits (an earlier interrupt lands on ordinary bytecode and proves nothing), and bounds every wait so a regression fails instead of hanging.
- Checkbox prompt tests feed the choices given to the mocked `inquirer.checkbox` to InquirerPy's real `InquirerPyCheckboxControl` (it needs no terminal) and assert each value is the original object (`assertIs`): asserting only on the mock's arguments missed the `Choice`/`asdict` conversion described in Gotchas.
- `test_windows_uses_appdata` is skipped outside Windows (`%VAR%` expansion only exists in `ntpath`), and the `sitemanager.xml` file mode tests on Windows.
- CI runs the suite headless (no TTY, no display, no clipboard tool) on Linux and Windows with the oldest supported Python, so a test that relies on any of these, on the host OS, or on syntax newer than 3.9 fails there.

Run a single test:

```sh
python -m unittest tests.test_terminal.OpenInTerminalTest.test_windows_opens_cmd_in_its_own_console
python -m unittest tests.commands.test_connect
python -m unittest -k test_prefers_legacy_dir_over_xdg
```

## Environment

No `.env` or `.env.example`; nothing to configure. Variables read at runtime:

| Variable                     | Read by                                         | Purpose                                                        |
| ---------------------------- | ----------------------------------------------- | -------------------------------------------------------------- |
| `APPDATA`                    | `filezilla.sitemanager.get_sitemanager_path`    | Windows config location: `%APPDATA%\FileZilla\sitemanager.xml` |
| `HOME` / `USERPROFILE`       | `os.path.expanduser` in `filezilla.sitemanager` | Home directory for the Linux candidate paths                   |
| `XDG_CONFIG_HOME`            | `filezilla.sitemanager.get_sitemanager_path`    | Linux config directory, default `~/.config`                    |
| `DISPLAY`, `WAYLAND_DISPLAY` | `terminal.find_terminal`                        | Either one enables launching a graphical terminal              |
| `SHELL`                      | the launched `sh -c`                            | Shell kept open after ssh exits, default `/bin/sh`             |
| `BW_SESSION`                 | the `bw` CLI, inherited                         | Session key of the unlocked vault, for `import-bitwarden`      |

Linux `sitemanager.xml` lookup order: `~/.filezilla/`, `$XDG_CONFIG_HOME/filezilla/`, `~/.var/app/org.filezillaproject.Filezilla/config/filezilla/` (Flatpak). If none exists, the XDG path is returned: `main()` reports it as not found, and `import-bitwarden` creates the file there.

External dependencies: an OpenSSH client for `connect` (PATH first; on Windows also `Sysnative`/`System32\OpenSSH`, Git for Windows, `Program Files\OpenSSH`); a FileZilla `sitemanager.xml` with at least one site, except for `import-bitwarden`; the Bitwarden CLI (`bw`, on PATH), logged in and unlocked, for `import-bitwarden`; on Linux, `xclip` or `wl-clipboard` for the clipboard copy (optional for `connect`, required for `copy-password`); network access to the servers for the `failed-connection` and `divergent-passwords` criteria of `clean`; `tasklist` (Windows) or `pgrep` (Linux) to detect a running FileZilla before `clean` writes (optional: without it, `clean` warns that it cannot tell).

## Gotchas

- The package must be installed (`pip install -e .`) for the app and the tests to import it: absolute imports need `filezilla_companion` on `sys.path`, which neither `src/` nor the repository root provides on its own.
- `prompts.py` imports `Command` only under `TYPE_CHECKING`: command modules import `prompts`, so a runtime import of `commands.base` from `prompts` would run `commands/__init__.py`, which imports the command modules back while `prompts` is half-initialized. `Action` and `Criterion` are imported the same way for consistency, and so `prompts` does not load paramiko.
- Command modules are named so they do not shadow builtins in `commands/__init__.py` (`list_servers.py`, not `list.py`): importing a submodule binds its name in the package namespace.
- A command slug must not be `help`: argparse already defines `--help`, and building the parser would fail.
- Command menus and flags hold the `COMMANDS` instances themselves; tests that patch a command's `run` patch that shared instance (`mock.patch.object(COMMANDS[i], "run")`).
- InquirerPy choices are passed as dicts (`{"name", "value", "enabled"}`), never as `InquirerPy.base.control.Choice`: InquirerPy converts a `Choice` with `dataclasses.asdict()`, which recursively turns a dataclass value (`Action`, `Server`) into a dict and deep-copies any other value, so the prompt returns copies instead of the objects passed in.
- The interactive menus need a TTY, and the failure path blocks on `input()`. `--list` against a fake `%APPDATA%`/`$XDG_CONFIG_HOME` runs non-interactively, and so does `--import-bitwarden` with a fake `bw` on PATH as long as there is nothing to import; otherwise validate changes with the test suite.
- `Server.command` returns one shell string, not an argv list. It runs through `cmd.exe` on Windows and `sh` on POSIX, and only the keyfile path is quoted. Changes must stay valid for both shells; `tests/test_ssh.py` and `tests/test_terminal.py` assert the exact strings.
- Protocol handling: `load_sitemanager()` defaults a missing `<Protocol>` to `0` (FTP) and `<Port>` to `22`. `Server.defaulting()` treats any falsy field as missing, so protocol `0` becomes `1` (SFTP). After that, `is_ftp` is true only for port 21 or a host containing `"ftp."`, which also matches `sftp.` hosts. Only `connect` calls `defaulting()`.
- FileZilla protocols go beyond 0/1 (2 = HTTP, 3 = implicit FTPS, 4 = explicit FTPS, 5 = HTTPS, 6 = plain FTP, then cloud storage). `Server.is_ftp`/`is_sftp` assert `protocol in (0, 1)` and raise `AssertionError` on the others, so `connect` fails on such a site. The `clean` code never calls them: `auth` reads `Server.protocol` directly.
- `Server` is a dataclass with value equality (`element` is excluded), and copies of a site compare equal; it is also unhashable. Code that tracks particular sites (`SiteManager.remove()`, `Analysis` cache, `CleanCommand` sets) matches them by `id()`, never with `==`, `in` or `list.remove()`.
- `SiteManager.save()` rewrites the whole file through ElementTree: the XML declaration becomes `<?xml version='1.0' encoding='UTF-8'?>` and XML comments are dropped; elements, attributes and whitespace are kept. Unparsed `<Server>` entries (no host or user) are kept, and folders emptied by removals stay. Elements added by `add()`/`update()` are indented with the unit read before the root's first child, at their depth (`ET.indent` on the new subtree); in a file without indentation, or among children written on one line, they are appended as is.
- `save()` creates the temporary file `0600` before writing: the file holds passwords, and a mode set after the write would leave them readable in between. A replaced file then gets its own mode back (`shutil.copymode`), skipped on Windows, where a mode only holds the read-only flag.
- FileZilla drops any XML it does not model when it rewrites `sitemanager.xml`, so the import's link to a Bitwarden item lives in `<Comments>`, the only free-form field. FileZilla also writes `<Pass>` only for logon types 1 and 4, and `<Keyfile>` only for the others: once it has saved, the import proposes again the password of a key file site.
- `<Pass encoding="crypt">` (FileZilla master password) cannot be decoded, so `load_sitemanager()` keeps its raw text and the import always sees a password change; `update()` then writes it in base64 and drops the `crypt` attributes.
- `RemoteDir` segment lengths count `wchar_t` units: UTF-16 on Windows (`_wchar_len()`), code points elsewhere. `decode_remote_dir()` slices by code point and returns None when the value does not round-trip; the change list then shows the raw value.
- On Windows, an npm-installed `bw` is `bw.cmd`, which `subprocess.run` runs through `cmd.exe`: the arguments passed to `bw` must stay constants, never data from the vault. `bw` prints UTF-8 whatever the console code page, hence `encoding="utf-8"`. Its errors go to stderr, and only stderr is shown.
- Import warnings never quote a URI: it may carry a password (`sftp://user:pass@host`).
- FileZilla's Site Manager writes `sitemanager.xml` from its own copy when it closes with OK, which would undo a `clean` or an import written while it was open; hence the `process.is_running()` warning.
- `auth` adds a `NullHandler` to the `paramiko` logger at import: paramiko logs transport errors from its threads, and without a handler Python's last-resort handler prints them on stderr, across the progress line.
- On Windows, Ctrl+C does not interrupt a main-thread wait without timeout (`Lock.acquire()`, `Event.wait()`, `Future.result()`, `Thread.join()`): `KeyboardInterrupt` only arrives once the wait ends. Waits for other threads poll with a timeout (`auth._POLL_INTERVAL`), on a `Semaphore`, not with `Thread.join(timeout)`: on Python 3.10 at least, an interrupted `join()` marks the thread as stopped while it still runs.
- `failed-connection` sends every saved password to its server (no host key or certificate check, plain FTP fallback for protocol 0), and failed logins can trigger fail2ban or account lockouts. Never run it against the real FileZilla config from a test or a smoke run.
- `Server` invariants are enforced with `assert`, which `python -O` strips.
- The clipboard copy happens before the session launch on purpose: the POSIX no-GUI fallback blocks until ssh exits.
- On Windows, `cmd` must get its own console (`terminal._CREATE_NEW_CONSOLE`). A plain `Popen` attaches it to the caller's console: the app exits, the calling shell shows its prompt again, and the shell and ssh both read the keyboard, so a pasted password lands at the shell prompt (and in its history if Enter is pressed). The flag is a hardcoded value because `subprocess.CREATE_NEW_CONSOLE` does not exist outside Windows, where CI also runs the Windows branch.
- `Console.setup()` must run before any output. It enables colorama's ANSI conversion only on Windows; forcing it elsewhere strips all colors. argparse output (`--help`, usage errors) is printed before it, uncolored.
- No macOS-specific handling: `Darwin` takes the Linux code paths (Linux config paths, Linux terminal list).
