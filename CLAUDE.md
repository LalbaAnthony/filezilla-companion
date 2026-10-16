# CLAUDE.md

## Overview

FileZilla Companion is a CLI that reads FileZilla's saved sites (`sitemanager.xml`), lets the user pick one in a fuzzy-search menu, copies the site's password to the clipboard, and opens an SSH session to it in a new terminal window. Supported platforms: Windows and Debian-family Linux.

## Tech stack

- Python. README states 3.9+; the code uses no newer syntax (`typing.List`/`Optional`, no `X | Y` unions, no `match`). Keep it that way.
- Package manager: pip with `requirements.txt` (unpinned). No `pyproject.toml`, `setup.py`, lockfile, CI config, or installable entry point.
- Dependencies: `InquirerPy` (fuzzy menu), `colorama` (colored output), `pyperclip` (clipboard), `inquirer` (listed but not imported anywhere).
- Standard library only otherwise: `xml.etree`, `subprocess`, `shutil`, `base64`, `dataclasses`, `unittest`.

## Structure

- `src/main.py` — entry point: preflight checks, server selection, connection.
- `src/sitemanager.py` — locates and parses FileZilla's `sitemanager.xml` into `Server` objects.
- `src/server.py` — `Server` dataclass: display labels, SSH command string, protocol checks, defaults.
- `src/ssh.py` — locates `ssh`, `cmd.exe` and a terminal emulator; copies the password; launches the session.
- `src/console.py` — `Console`: colored output (`info`/`success`/`warning`/`error`) and a Y/n prompt.
- `tests/test_console.py`, `tests/test_sitemanager.py`, `tests/test_ssh.py` — unittest suites.

`src/` is not a package: modules import each other by bare name (`from server import Server`).

## Commands

All commands run from the repository root.

Install:

```sh
# Windows
python -m pip install -r requirements.txt

# Debian (PEP 668 blocks system-wide pip, so use a venv)
sudo apt install python3 python3-venv openssh-client xclip
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

Run (interactive, needs a TTY):

```sh
# Windows
python src/main.py

# Debian
.venv/bin/python src/main.py
```

Test:

```sh
# Windows
python -m unittest discover -s tests

# Debian
.venv/bin/python -m unittest discover -s tests
```

There is no build step. No linter, formatter, or type checker is configured.

## Architecture

Single process, linear flow in `main()` (`src/main.py`):

1. `Console.setup()` initializes colorama.
2. `find_ssh()` and `ssh_is_functional()` (runs `ssh -V`) abort if no working OpenSSH client is found.
3. `get_sitemanager_path()` then `parse_sitemanager()` collect every `<Server>` element at any depth (folders included). Entries without `Host` or `User` are skipped with a warning. `<Pass>` is base64-decoded; the raw text is kept if decoding fails.
4. `select_server()` shows the InquirerPy fuzzy menu.
5. `Server.defaulting()` fills missing fields, then the server is rejected if `is_ftp` or not `can_connect`.
6. `ssh.connect()` copies the password to the clipboard (a failure is only a warning), then launches `Server.command`:
   - Windows: `cmd /k <command>` via `subprocess.Popen` (new console window).
   - POSIX with `DISPLAY` or `WAYLAND_DISPLAY` set and a known emulator on PATH: `<terminal> sh -c '<command>; exec "${SHELL:-/bin/sh}"'`, detached with `start_new_session=True`. Emulator preference order is `ssh._POSIX_TERMINALS`.
   - POSIX otherwise: `subprocess.run(command, shell=True)` in the current terminal (blocks until ssh exits).

The password is never passed to `ssh`; the user pastes it at the ssh prompt. `main()` returns 0 or 1; on 1, the script waits for Enter before exiting.

Module dependencies: `main` → `console`, `server`, `sitemanager`, `ssh`; `sitemanager` and `ssh` → `console`, `server`; `server` has no internal dependency; `console` depends only on colorama.

## Conventions

- All user-facing output goes through `Console.info`/`success`/`warning`/`error`, not bare `print`.
- Fatal errors in the main flow: `Console.error(...)` then `return 1` from `main()`. Session launch failures in `ssh.connect()` raise `OSError` (including `FileNotFoundError`) and are caught in `main()`.
- Type hints on every function via `typing`; docstrings on public functions; comments explain why, not what.
- OS branching that tests must exercise uses `platform.system()`, which tests patch as `<module>.platform.system`. `sys.platform == "win32"` is only used to gate hardcoded Windows fallback paths in `find_ssh()` and `find_cmd()`.
- Lookup tables are module constants in `src/ssh.py`: `_WINDOWS_SSH_PATHS` (Windows ssh fallbacks) and `_POSIX_TERMINALS` (ordered argv prefixes for terminal emulators).

## Testing

- Framework: standard library `unittest` and `unittest.mock`. One file per module: `tests/test_<module>.py`.
- `tests/` has no `__init__.py`; each test file prepends `src/` to `sys.path`, hence `# noqa: E402` on the following imports.
- Covered: `console`, `sitemanager`, `ssh`, and `server` indirectly. `main.py` has no tests.
- Tests never spawn processes or read the real FileZilla config: they patch `ssh.subprocess.Popen`, `ssh.subprocess.run`, `ssh.pyperclip.copy`, `ssh.shutil.which`, and `os.environ` (`mock.patch.dict`), and use `tempfile` for `sitemanager.xml` and fake home directories. Console output is asserted by patching `sys.stdout` with `io.StringIO`.
- `test_windows_uses_appdata` is skipped outside Windows (`%VAR%` expansion only exists in `ntpath`).

Run a single test:

```sh
python -m unittest tests.test_ssh.ConnectTest.test_windows_opens_cmd
python -m unittest discover -s tests -k test_prefers_legacy_dir_over_xdg
```

## Environment

No `.env` or `.env.example`; nothing to configure. Variables read at runtime:

| Variable                     | Read by                               | Purpose                                                        |
| ---------------------------- | ------------------------------------- | -------------------------------------------------------------- |
| `APPDATA`                    | `sitemanager.get_sitemanager_path`    | Windows config location: `%APPDATA%\FileZilla\sitemanager.xml` |
| `HOME` / `USERPROFILE`       | `os.path.expanduser` in `sitemanager` | Home directory for the Linux candidate paths                   |
| `XDG_CONFIG_HOME`            | `sitemanager.get_sitemanager_path`    | Linux config directory, default `~/.config`                    |
| `DISPLAY`, `WAYLAND_DISPLAY` | `ssh.find_terminal`                   | Either one enables launching a graphical terminal              |
| `SHELL`                      | the launched `sh -c`                  | Shell kept open after ssh exits, default `/bin/sh`             |

Linux `sitemanager.xml` lookup order: `~/.filezilla/`, `$XDG_CONFIG_HOME/filezilla/`, `~/.var/app/org.filezillaproject.Filezilla/config/filezilla/` (Flatpak). If none exists, the XDG path is returned and `main()` reports it as not found.

External dependencies: an OpenSSH client (PATH first; on Windows also `Sysnative`/`System32\OpenSSH`, Git for Windows, `Program Files\OpenSSH`); a FileZilla `sitemanager.xml` with at least one site; on Linux, `xclip` or `wl-clipboard` for the clipboard copy (optional).

## Gotchas

- Run the app as a script (`python src/main.py`, or `cd src` then `python main.py`). `python -m src.main` fails: the bare-name imports need `src/` on `sys.path`, which only the script form provides.
- `main.py` is interactive end to end (the InquirerPy menu needs a TTY, and the failure path blocks on `input()`), so it cannot be smoke-run non-interactively. Validate changes with the test suite.
- `Server.command` returns one shell string, not an argv list. It runs through `cmd.exe` on Windows and `sh` on POSIX, and only the keyfile path is quoted. Changes must stay valid for both shells; `tests/test_ssh.py` asserts the exact strings.
- Protocol handling: `parse_sitemanager()` defaults a missing `<Protocol>` to `0` (FTP) and `<Port>` to `22`. `Server.defaulting()` treats any falsy field as missing, so protocol `0` becomes `1` (SFTP). After that, `is_ftp` is true only for port 21 or a host containing `"ftp."`, which also matches `sftp.` hosts.
- `Server` invariants are enforced with `assert`, which `python -O` strips.
- The clipboard copy happens before the session launch on purpose: the POSIX no-GUI fallback blocks until ssh exits.
- `Console.setup()` must run before any output. It enables colorama's ANSI conversion only on Windows; forcing it elsewhere strips all colors.
- No macOS-specific handling: `Darwin` takes the Linux code paths (Linux config paths, Linux terminal list).
