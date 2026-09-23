"""Sink filter: writes the rendered {relative_path: markdown} dict to disk
under output_dir, then (optionally) stages and commits them into a git
repository at that path, initializing one if none exists yet.
"""
from __future__ import annotations

import os
import subprocess
from typing import Dict


def write_files(output_dir: str, files: Dict[str, str]) -> None:
    for rel_path, content in files.items():
        abs_path = os.path.join(output_dir, *rel_path.split("/"))
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)
        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)


def commit(output_dir: str, message: str) -> bool:
    """Stage and commit everything under output_dir. Returns True if a
    commit was made, False if there was nothing to commit."""
    if not os.path.isdir(os.path.join(output_dir, ".git")):
        _run(["git", "init"], cwd=output_dir)
    _run(["git", "add", "-A"], cwd=output_dir)
    result = subprocess.run(
        ["git", "diff", "--cached", "--quiet"], cwd=output_dir
    )
    if result.returncode == 0:
        return False  # nothing staged, nothing to commit
    _run(["git", "commit", "-m", message], cwd=output_dir)
    return True


def push(output_dir: str, remote: str = "origin") -> None:
    """Push the current branch to <remote>/<same branch name>."""
    _run(["git", "push", remote, "HEAD"], cwd=output_dir)


def _run(args, cwd: str) -> None:
    subprocess.run(args, cwd=cwd, check=True)
