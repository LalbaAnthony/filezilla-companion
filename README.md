# FileZilla Companion

FileZilla Companion is a smoll tool that enhances the user experience of FileZilla by providing quick access to SSH connections directly from the FileZilla site manager. It allows users to select a server and automatically opens a terminal window to connect via SSH, copying the password to the clipboard for convenience.

## Installation

1. Install Python if not already installed. You can download it from [python.org](https://www.python.org/downloads/). Ensure that Python is added to your system's PATH during installation.

2. Install pip if not already installed:
    ```bash
    python -m ensurepip --upgrade --user
	# OR
	python -m pip install --upgrade pip
    ```

3. Install the required packages using pip:
    ```bash
    pip install -r requirements.txt
    ```

## Usage

```bash
cd filezilla-companion
python main.py
```