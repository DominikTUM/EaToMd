"""Markdown export visitor: turns the IR Model into a dict of
{relative_path: markdown text}, mirroring EA's native HTML export layout -
one page per package, in a folder per package, recursively nested, with
diagrams embedded as images and elements/cross-references as links
between pages.

Pure function of the IR: no EA/COM dependency, so it is fully unit-testable
with hand-built Model fixtures.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import quote

from .export_visitor import ExportVisitor
from .model import Diagram, Element, Model, Package
from .slugify import github_slug

INDEX_FILENAME = "index.md"


def render_model(model: Model) -> Dict[str, str]:
    return MarkdownVisitor(model).render()


@dataclass
class _Location:
    dir_path: str  # posix-style, relative to output root; "" for the root package
    anchor: Optional[str] = None  # None for a package's own index page


class MarkdownVisitor(ExportVisitor):
    file_extension = ".md"

    def __init__(self, model: Model):
        super().__init__(model)
        self.locations = self._assign_locations()

    def _assign_locations(self) -> Dict[str, _Location]:
        """Assign every diagram and element a (containing file, anchor)
        location, using GitHub-style heading slugs scoped per package
        file, so generated links match what GitHub/VS Code will actually
        auto-assign to those headings."""
        locations: Dict[str, _Location] = {}
        for pkg in self.model.walk_packages():
            rel_dir = self.dirs[pkg.guid]
            seen: Dict[str, int] = {}
            for diagram in pkg.diagrams:
                anchor = github_slug(_diagram_heading(diagram), seen)
                locations[diagram.guid] = _Location(rel_dir, anchor)
            for element in pkg.elements:
                anchor = github_slug(_element_heading(element), seen)
                locations[element.guid] = _Location(rel_dir, anchor)
        return locations

    def visit_package(self, pkg: Package) -> str:
        rel_dir = self.dirs[pkg.guid]
        lines = [f"# {pkg.name}", ""]

        parent = self.model.packages_by_guid.get(pkg.parent_guid) if pkg.parent_guid else None
        if parent is not None:
            lines.append(f"[Up to {parent.name}]({self._package_link(rel_dir, parent)})")
            lines.append("")

        if pkg.notes:
            lines.append(pkg.notes.strip())
            lines.append("")

        if pkg.subpackages:
            lines.append("## Packages")
            lines.append("")
            for sub in pkg.subpackages:
                lines.append(f"- [{sub.name}]({self._package_link(rel_dir, sub)})")
            lines.append("")

        if pkg.diagrams:
            lines.append("## Diagrams")
            lines.append("")
            for diagram in pkg.diagrams:
                lines.append(self.visit_diagram(diagram))

        if pkg.elements:
            lines.append("## Elements")
            lines.append("")
            for element in pkg.elements:
                lines.append(self.visit_element(element))

        return "\n".join(lines).rstrip() + "\n"

    def visit_diagram(self, diagram: Diagram) -> str:
        rel_dir = self.dirs[diagram.package_guid]
        lines = [f"### {_diagram_heading(diagram)}", ""]
        if diagram.image_path:
            image_rel = posixpath.relpath(diagram.image_path, rel_dir or ".")
            lines.append(f"![{diagram.name}]({_encode_path(image_rel)})")
            lines.append("")
        if diagram.notes:
            lines.append(diagram.notes.strip())
            lines.append("")
        if diagram.element_guids:
            lines.append("Elements shown on this diagram:")
            lines.append("")
            for eguid in diagram.element_guids:
                element = self.model.elements_by_guid.get(eguid)
                if element is None:
                    continue
                lines.append(f"- [{element.name}]({self._node_link(rel_dir, eguid)})")
            lines.append("")
        return "\n".join(lines)

    def visit_element(self, element: Element) -> str:
        rel_dir = self.dirs[element.package_guid]
        lines = [f"### {_element_heading(element)}", ""]
        if element.notes:
            lines.append(element.notes.strip())
            lines.append("")

        if element.tagged_values:
            lines.append("| Tag | Value |")
            lines.append("| --- | --- |")
            for tag in element.tagged_values:
                lines.append(f"| {tag.name} | {tag.value} |")
            lines.append("")

        if element.diagram_guids:
            lines.append("Appears on:")
            lines.append("")
            for dguid in element.diagram_guids:
                diagram = self.model.diagrams_by_guid.get(dguid)
                if diagram is None:
                    continue
                lines.append(f"- [{diagram.name}]({self._node_link(rel_dir, dguid)})")
            lines.append("")

        if element.connectors:
            lines.append("| Relationship | Direction | Related element |")
            lines.append("| --- | --- | --- |")
            for conn in element.connectors:
                other = self.model.elements_by_guid.get(conn.other_end_guid)
                if other is None:
                    continue
                other_link = f"[{other.name}]({self._node_link(rel_dir, conn.other_end_guid)})"
                lines.append(f"| {conn.type} | {conn.direction} | {other_link} |")
            lines.append("")

        return "\n".join(lines)

    def _link(self, from_dir: str, to_dir: str, filename: str, anchor: Optional[str]) -> str:
        """Build a Markdown link target from the file in from_dir to the
        file <to_dir>/<filename>#anchor, relative to from_dir."""
        if from_dir == to_dir:
            target = ""
        else:
            rel = posixpath.relpath(to_dir or ".", from_dir or ".")
            target = posixpath.join(rel, filename) if rel != "." else filename
        target = _encode_path(target) if target else target
        if anchor:
            target = f"{target}#{anchor}" if target else f"#{anchor}"
        return target or _encode_path(filename)

    def _package_link(self, from_dir: str, pkg: Package) -> str:
        return self._link(from_dir, self.dirs[pkg.guid], INDEX_FILENAME, None)

    def _node_link(self, from_dir: str, guid: str) -> str:
        loc = self.locations[guid]
        return self._link(from_dir, loc.dir_path, INDEX_FILENAME, loc.anchor)


def _encode_path(path: str) -> str:
    """Percent-encode a relative path for use as a Markdown link destination.
    CommonMark link targets can't contain raw spaces/parentheses/etc unless
    wrapped in <...>, and folder/file names are derived from arbitrary EA
    package/element names, so every segment needs escaping - '/' stays as
    the path separator and is never encoded itself."""
    return "/".join(quote(segment) for segment in path.split("/"))


def _diagram_heading(diagram: Diagram) -> str:
    return f"{diagram.name} ({diagram.type})"


def _element_heading(element: Element) -> str:
    if element.stereotype:
        return f"{element.name} «{element.stereotype}» ({element.type})"
    return f"{element.name} ({element.type})"
