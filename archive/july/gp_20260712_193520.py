#!/data/data/com.termux/files/usr/bin/env python


import subprocess
import sys
from datetime import datetime
from pathlib import Path

SKIP_DIRS = frozenset({"lazy", ".git", "__pycache__", ".mypy_cache", ".ruff_cache", ".pytest_cache"})


def runcmd(
    cmd: list[str], run_silently: bool = False, show_output: bool = True, timeout: float | None = None
) -> tuple[int, str, str]:
    from subprocess import DEVNULL as _DEVNULL
    from subprocess import TimeoutExpired as subprocess_TimeoutExpired
    from subprocess import run as subprocess_run
    from sys import stderr as sys_stderr
    from sys import stdout as sys_stdout

    if not cmd:
        msg = "cmd must be a non-empty list (e.g., ['ls', '-l'])"
        raise ValueError(msg)
    try:
        if run_silently:
            result = subprocess_run(cmd, stdout=_DEVNULL, stderr=_DEVNULL, timeout=timeout)
            return result.returncode, "", ""
        result = subprocess_run(cmd, capture_output=True, text=True, timeout=timeout)
        stdout, stderr = result.stdout, result.stderr
        if show_output:
            if stdout:
                sys_stdout.write(stdout)
                sys_stdout.flush()
            if stderr:
                sys_stderr.write(stderr)
                sys_stderr.flush()
        return result.returncode, stdout, stderr
    except FileNotFoundError:
        msg = f"Command not found: '{cmd[0]}'"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return 127, "", msg
    except PermissionError:
        msg = f"Permission denied: '{cmd[0]}'"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return 126, "", msg
    except subprocess_TimeoutExpired:
        msg = f"Command timed out after {timeout}s: {' '.join(cmd)}"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return 124, "", msg
    except Exception as e:
        msg = f"Unexpected error running '{cmd[0]}': {e}"
        if show_output and not run_silently:
            print(msg, file=sys_stderr)
        return 1, "", msg




def ensure_git_repo() -> None:
    try:
        subprocess.check_output("git rev-parse --is-inside-work-tree", shell=True, stderr=subprocess.STDOUT)
    except subprocess.CalledProcessError:
        print("Not inside a Git repository.", file=sys.stderr)
        sys.exit(1)


def copy_global_gitignore() -> None:
    home_gitignore = Path.home() / ".gitignore"
    local_gitignore = Path(".gitignore")
    if local_gitignore.exists():
        return
    content=home_gitignore.read_text(encoding="utf-8")
    local_gitignore.write_text(content,encoding="utf-8")

def get_current_branch(cmd: list[str] = ["git", "branch"]) -> str:
    _, txt, _ = runcmd(cmd, show_output=False)
    branch = txt.strip().replace("* ", "")
    return branch


def main() -> None:
    ensure_git_repo()
    copy_global_gitignore()
    cmd=["git","add","-A"]
    runcmd(cmd,show_output=False)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    commit_msg = f"Auto-commit at {now}"
    runcmd(["git", "commit", "-m", f'{commit_msg}'],show_output=False)
    branch = get_current_branch()
    runcmd(["git", "push","origin", f"{branch}"],show_output=False)
    print(f"Pushed to origin/{branch} with message: {commit_msg}")


if __name__ == "__main__":
    main()
