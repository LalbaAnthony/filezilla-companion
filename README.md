# FileZilla Companion

FileZilla Companion is a smoll tool that enhances the user experience of FileZilla by providing quick access to SSH connections directly from the FileZilla site manager. It allows users to select a server and automatically opens a terminal window to connect via SSH, copying the password to the clipboard for convenience.

## Requirements

- Python 3.9+
- An OpenSSH client (`ssh`)
- FileZilla with at least one saved site

## Installation

### Windows

1. Install Python if not already installed. You can download it from [python.org](https://www.python.org/downloads/). Ensure that Python is added to your system's PATH during installation.

2. Install pip if not already installed:
    ```sh
    python -m ensurepip --upgrade --user
	# OR
	python -m pip install --upgrade pip
    ```

3. Install the required packages using pip:
    ```sh
    pip install -r requirements.txt
    # OR
    py -m pip install inquirer InquirerPy colorama pyperclip
    ```

### Debian

Debian 11 (bullseye) and later. Debian has no `python` command and blocks system-wide `pip install` (PEP 668), so the packages go in a virtual environment.

1. Install the system packages:
    ```sh
    sudo apt install python3 python3-venv openssh-client xclip
    ```
    `xclip` copies the password to the clipboard. On a Wayland session, `wl-clipboard` works too. Without either, the password is not copied and everything else works.

2. Create a virtual environment and install the required packages:
    ```sh
    cd filezilla-companion
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
    ```

## Usage

Windows:

```sh
cd filezilla-companion/src
python main.py
```

Debian:

```sh
cd filezilla-companion
.venv/bin/python src/main.py
```

On Debian, the SSH session opens in the desktop's default terminal (`x-terminal-emulator`), falling back to gnome-terminal, konsole, xfce4-terminal, then xterm. Without a graphical session (e.g. when logged in over SSH), it runs in the current terminal.

FileZilla's `sitemanager.xml` is read from `%APPDATA%\FileZilla` on Windows. On Debian, it is looked up in `~/.filezilla`, then `$XDG_CONFIG_HOME/filezilla` (default `~/.config/filezilla`), then the Flatpak config directory.

## Tests

```sh
# Windows
python -m unittest discover -s tests
# Debian
.venv/bin/python -m unittest discover -s tests
```