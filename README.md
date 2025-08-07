# FileZilla Companion

FileZilla Companion is a command-line tool that enhances the user experience of FileZilla by providing quick access to frequently used FTP/SFTP server credentials. It allows users to copy server details to the clipboard and launch FileZilla with the selected server's information.

## Installation

Install pip if not already installed:

```bash
py -m ensurepip --upgrade
```

Install the required packages using pip:

```bash
pip install -r requirements.txt

# OR

py -m pip install inquirer colorama pyperclip
```

## Usage

```bash
py main.py
```