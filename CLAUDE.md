# CLAUDE.md

## Overview

FileZilla Companion is a CLI that reads FileZilla's saved sites (`sitemanager.xml`) and runs a command on them. The command is picked in a fuzzy-search menu at startup, or passed as a `--<slug>` flag to skip the menu. Commands: `connect` (pick a site, copy its password to the clipboard, open an SSH session in a new terminal window), `copy-password` (pick a site with a password, copy it), `list` (print every site). Supported platforms: Windows and Debian-family Linux.

## Tech stack

- Python. `requires-python >= 3.9`; the code uses no newer syntax (`typing.List`/`Optional`, no `X | Y` unions, no `match`). Keep it that way.
- Packaging: `pyproject.toml` with the setuptools backend (>= 64, for PEP 660 editable installs), src layout, console script `filezilla-companion` → `filezilla_companion.__main__:run`. Dependencies are unpinned. No `requirements.txt`, no lockfile.
- CI: GitHub Actions. `.github/workflows/tests.flow.yml` holds the triggers (pushes to `main`/`develop`, every pull request) and the concurrency group, and includes `.github/workflows/tests.inc.yml`, which runs the test suite across `ubuntu-latest` and `windows-latest` × Python 3.9 to 3.14. When `requires-python` or a new Python release changes the supported range, update the matrix in `tests.inc.yml`.
- Dependencies: `InquirerPy` (fuzzy menus), `colorama` (colored output), `pyperclip` (clipboard).
- Standard library only otherwise: `argparse`, `abc`, `xml.etree`, `subprocess`, `shutil`, `base64`, `dataclasses`, `unittest`.

## Structure

- `src/filezilla_companion/__main__.py` — entry point: `parse_args()` (one `--<slug>` flag per command), `main(argv)` (loads the site manager, picks and runs the command), `run()` (console script target, pauses on failure).
- `src/filezilla_companion/commands/__init__.py` — `COMMANDS`, the explicit registry; its order is the menu order, the first entry is preselected.
- `src/filezilla_companion/commands/base.py` — `Command` ABC (`slug`, `label`, abstract `run(context) -> int`) and the `Context` dataclass (`servers`).
- `src/filezilla_companion/commands/connect.py`, `copy_password.py`, `list_servers.py` — one `Command` subclass per module.
- `src/filezilla_companion/filezilla/sitemanager.py` — locates and parses FileZilla's `sitemanager.xml` into `Server` objects.
- `src/filezilla_companion/filezilla/server.py` — `Server` dataclass: display labels, SSH command string, protocol checks, defaults.
- `src/filezilla_companion/prompts.py` — InquirerPy fuzzy menus: `select_server()`, `select_command()`.
- `src/filezilla_companion/ssh.py` — locates and checks the `ssh` client; `connect()` copies the password and opens the session.
- `src/filezilla_companion/terminal.py` — locates `cmd.exe` and terminal emulators; `open_in_terminal()` runs a shell command in a new window.
- `src/filezilla_companion/clipboard.py` — `copy()`, which raises `ClipboardError` so callers do not depend on pyperclip.
- `src/filezilla_companion/console.py` — `Console`: colored output (`info`/`success`/`warning`/`error`) and a Y/n prompt.
- `tests/` — unittest package mirroring the source tree: `tests/test_<module>.py`, `tests/commands/test_<module>.py`, `tests/filezilla/test_<module>.py`, plus `tests/commands/test_registry.py` for `COMMANDS`.

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
filezilla-companion [--connect | --copy-password | --list]
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
3. `get_sitemanager_path()` then `parse_sitemanager()` collect every `<Server>` element at any depth (folders included). Entries without `Host` or `User` are skipped with a warning. `<Pass>` is base64-decoded; the raw text is kept if decoding fails. A missing file or an empty result aborts before any command runs.
4. Without a flag, `prompts.select_command(COMMANDS)` shows the menu; labels include the flag (`Connect to a server (--connect)`).
5. `command.run(Context(servers))` returns the exit code.

Commands:

- `ConnectCommand` (`--connect`): checks `ssh.find_ssh()` + `ssh_is_functional()` (runs `ssh -V`), then `select_server()`, `Server.defaulting()`, rejects the server if `is_ftp` or not `can_connect`, then `ssh.connect()`. `ssh.connect()` copies the password (a `ClipboardError` is only a warning), then calls `terminal.open_in_terminal(Server.command)`:
  - Windows: `cmd /k <command>` via `subprocess.Popen` (new console window).
  - POSIX with `DISPLAY` or `WAYLAND_DISPLAY` set and a known emulator on PATH: `<terminal> sh -c '<command>; exec "${SHELL:-/bin/sh}"'`, detached with `start_new_session=True`. Emulator preference order is `terminal._POSIX_TERMINALS`.
  - POSIX otherwise: `subprocess.run(command, shell=True)` in the current terminal (blocks until ssh exits).
- `CopyPasswordCommand` (`--copy-password`): menu limited to servers with a password, FTP included, no `defaulting()`. No such server, or a `ClipboardError`, is an error (exit 1).
- `ListServersCommand` (`--list`): prints every server as `name (user@host:port)`, or `user@host:port` without a name, FTP included. Never fails.

The password is never passed to `ssh`; the user pastes it at the ssh prompt. `run()` waits for Enter only when the exit code is not 0; a double-clicked launch of `--list` or `--copy-password` closes its window on success.

Module dependencies (all under `filezilla_companion`): `__main__` → `commands`, `prompts`, `console`, `filezilla.sitemanager`; `commands.*` → `commands.base`, `console`, and as needed `prompts`, `ssh`, `clipboard`; `ssh` → `clipboard`, `terminal`, `console`, `filezilla.server`; `terminal` → `console`; `filezilla.sitemanager` → `console`, `filezilla.server`; `prompts` → `filezilla.server` (imports `commands.base` only under `TYPE_CHECKING`, see Gotchas); `filezilla.server`, `clipboard` and `console` have no internal dependency.

## Adding a command

1. Create `src/filezilla_companion/commands/<name>.py` with a `Command` subclass setting `slug` (kebab-case, becomes the `--<slug>` flag) and `label` (menu text and `--help` text), and implementing `run(self, context: Context) -> int`.
2. Append an instance to `COMMANDS` in `commands/__init__.py` at the wanted menu position.
3. Add `tests/commands/test_<name>.py`. `tests/commands/test_registry.py` already enforces unique kebab-case slugs and non-empty labels.

Checks a command needs (e.g. a working `ssh`) belong in its `run()`; only the site manager loading is shared, through `Context`. Data shared by several commands goes in `Context` instead of a new `run()` parameter.

## Conventions

- All user-facing output goes through `Console.info`/`success`/`warning`/`error`, not bare `print`.
- Fatal errors inside a command: `Console.error(...)` then `return 1` from `run()`. `main()` does the same for the shared site manager checks. Session launch failures in `ssh.connect()`/`terminal.open_in_terminal()` raise `OSError` (including `FileNotFoundError`) and are caught in `ConnectCommand.run()`.
- Modules wrapping a third-party library expose their own exception (`clipboard.ClipboardError`) so callers do not import the library.
- Type hints on every function via `typing`; docstrings on public functions; comments explain why, not what.
- OS branching that tests must exercise uses `platform.system()`. `sys.platform == "win32"` is only used to gate hardcoded Windows fallback paths in `ssh.find_ssh()` and `terminal.find_cmd()`.
- Lookup tables are module constants: `ssh._WINDOWS_SSH_PATHS` (Windows ssh fallbacks) and `terminal._POSIX_TERMINALS` (ordered argv prefixes for terminal emulators).
- GitHub Actions: when appropriate, put the jobs in a reusable workflow named `*.inc.yml` (`on: workflow_call`) and include it from a workflow named `*.flow.yml` that holds the triggers (e.g. `tests.inc.yml` is included in `tests.flow.yml`). Concurrency groups belong in the `*.flow.yml`: inside a called workflow, `github.workflow` is the caller's name, so the same group defined there would deadlock with the caller's.

## Testing

- Framework: standard library `unittest` and `unittest.mock`. `tests/` and its subdirectories are packages (`__init__.py`), so `python -m unittest` discovers them from the repository root and imports `filezilla_companion` from the editable install.
- Patching uses `mock.patch.object(<module>, "<attr>")` on imported modules (e.g. `mock.patch.object(terminal.subprocess, "Popen")`, `mock.patch.object(prompts, "select_server")`). Command modules call collaborators through their module (`ssh.connect`, `prompts.select_server`, `clipboard.copy`) so these patches take effect.
- Tests never spawn processes, open menus, or read the real FileZilla config: they patch `subprocess.Popen`/`run`, `shutil.which`, `pyperclip.copy`/`clipboard.copy`, `inquirer.fuzzy`, `prompts.select_*`, `Console.setup`, `os.environ` (`mock.patch.dict`), and use `tempfile` for `sitemanager.xml` and fake home directories. Console output is asserted by patching `sys.stdout` with `io.StringIO`.
- `test_windows_uses_appdata` is skipped outside Windows (`%VAR%` expansion only exists in `ntpath`).
- CI runs the suite headless (no TTY, no display, no clipboard tool) on Linux and Windows with the oldest supported Python, so a test that relies on any of these, on the host OS, or on syntax newer than 3.9 fails there.

Run a single test:

```sh
python -m unittest tests.test_terminal.OpenInTerminalTest.test_windows_opens_cmd
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

Linux `sitemanager.xml` lookup order: `~/.filezilla/`, `$XDG_CONFIG_HOME/filezilla/`, `~/.var/app/org.filezillaproject.Filezilla/config/filezilla/` (Flatpak). If none exists, the XDG path is returned and `main()` reports it as not found.

External dependencies: an OpenSSH client for `connect` (PATH first; on Windows also `Sysnative`/`System32\OpenSSH`, Git for Windows, `Program Files\OpenSSH`); a FileZilla `sitemanager.xml` with at least one site; on Linux, `xclip` or `wl-clipboard` for the clipboard copy (optional for `connect`, required for `copy-password`).

## Gotchas

- The package must be installed (`pip install -e .`) for the app and the tests to import it: absolute imports need `filezilla_companion` on `sys.path`, which neither `src/` nor the repository root provides on its own.
- `prompts.py` imports `Command` only under `TYPE_CHECKING`: command modules import `prompts`, so a runtime import of `commands.base` from `prompts` would run `commands/__init__.py`, which imports the command modules back while `prompts` is half-initialized.
- Command modules are named so they do not shadow builtins in `commands/__init__.py` (`list_servers.py`, not `list.py`): importing a submodule binds its name in the package namespace.
- A command slug must not be `help`: argparse already defines `--help`, and building the parser would fail.
- Command menus and flags hold the `COMMANDS` instances themselves; tests that patch a command's `run` patch that shared instance (`mock.patch.object(COMMANDS[i], "run")`).
- The interactive menus need a TTY, and the failure path blocks on `input()`. `--list` against a fake `%APPDATA%`/`$XDG_CONFIG_HOME` is the only non-interactive smoke run; otherwise validate changes with the test suite.
- `Server.command` returns one shell string, not an argv list. It runs through `cmd.exe` on Windows and `sh` on POSIX, and only the keyfile path is quoted. Changes must stay valid for both shells; `tests/test_ssh.py` and `tests/test_terminal.py` assert the exact strings.
- Protocol handling: `parse_sitemanager()` defaults a missing `<Protocol>` to `0` (FTP) and `<Port>` to `22`. `Server.defaulting()` treats any falsy field as missing, so protocol `0` becomes `1` (SFTP). After that, `is_ftp` is true only for port 21 or a host containing `"ftp."`, which also matches `sftp.` hosts. Only `connect` calls `defaulting()`.
- `Server` invariants are enforced with `assert`, which `python -O` strips.
- The clipboard copy happens before the session launch on purpose: the POSIX no-GUI fallback blocks until ssh exits.
- `Console.setup()` must run before any output. It enables colorama's ANSI conversion only on Windows; forcing it elsewhere strips all colors. argparse output (`--help`, usage errors) is printed before it, uncolored.
- No macOS-specific handling: `Darwin` takes the Linux code paths (Linux config paths, Linux terminal list).
