"""Shared, format-agnostic package-folder layout.

Every export format writes one file per package into the same on-disk
folder tree (mirroring EA's own package hierarchy), so this is computed
once and reused by every ExportVisitor subclass instead of being
recomputed - and potentially diverging - per format.
"""
from __future__ import annotations

import posixpath
from typing import Dict

from .model import Model, Package
from .slugify import safe_folder_name


def assign_package_dirs(model: Model) -> Dict[str, str]:
    """Assign every package a folder path (posix-style, relative to output
    root) by walking the tree and de-duplicating sibling folder names."""
    dirs: Dict[str, str] = {model.root.guid: ""}

    def visit(pkg: Package, parent_dir: str, sibling_seen: Dict[str, int]) -> None:
        if pkg.guid != model.root.guid:
            folder = safe_folder_name(pkg.name, sibling_seen)
            rel_dir = posixpath.join(parent_dir, folder) if parent_dir else folder
            dirs[pkg.guid] = rel_dir
        else:
            rel_dir = parent_dir

        child_seen: Dict[str, int] = {}
        for sub in pkg.subpackages:
            visit(sub, rel_dir, child_seen)

    visit(model.root, "", {})
    return dirs
