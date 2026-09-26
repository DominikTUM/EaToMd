"""Visitor abstraction shared by every export format.

Adding a new output format means writing one new ExportVisitor subclass
(visit_package/visit_diagram/visit_element); the tree walk itself
(render()) and the on-disk package layout (layout.assign_package_dirs)
are shared and never duplicated per format.
"""
from __future__ import annotations

import posixpath
from abc import ABC, abstractmethod
from typing import Dict

from .layout import assign_package_dirs
from .model import Diagram, Element, Model, Package


class ExportVisitor(ABC):
    file_extension: str  # e.g. ".md" or ".tex", including the dot

    def __init__(self, model: Model):
        self.model = model
        self.dirs = assign_package_dirs(model)

    def render(self) -> Dict[str, str]:
        """Walk the tree and dispatch each package to visit_package();
        visit_package is expected to call visit_diagram()/visit_element()
        for its own diagrams and elements."""
        files: Dict[str, str] = {}
        index_name = f"index{self.file_extension}"
        for pkg in self.model.walk_packages():
            rel_dir = self.dirs[pkg.guid]
            rel_path = posixpath.join(rel_dir, index_name) if rel_dir else index_name
            files[rel_path] = self.visit_package(pkg)
        return files

    @abstractmethod
    def visit_package(self, pkg: Package) -> str:
        """Render one package's whole page: heading, notes, links to
        subpackages, then its diagrams and elements."""

    @abstractmethod
    def visit_diagram(self, diagram: Diagram) -> str:
        """Render one diagram's section within its owning package's page."""

    @abstractmethod
    def visit_element(self, element: Element) -> str:
        """Render one element's section within its owning package's page."""
