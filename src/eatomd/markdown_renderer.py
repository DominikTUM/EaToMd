"""Filter: turns the IR Model into a dict of {relative_path: markdown text},
mirroring EA's native HTML export layout - one page per package, in a
folder per package, recursively nested, with diagrams embedded as images
and elements/cross-references as links between pages.

Pure function of the IR: no EA/COM dependency, so it is fully unit-testable
with hand-built Model fixtures.
"""
from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Dict, Optional

from .model import Diagram, Element, Model, Package
from .slugify import github_slug, safe_folder_name

INDEX_FILENAME = "index.md"


@dataclass
class _Location:
    dir_path: str  # posix-style, relative to output root; "" for the root package
    anchor: Optional[str] = None  # None for a package's own index page


def render_model(model: Model) -> Dict[str, str]:
    """Return {relative_file_path: markdown_content} for the whole tree."""
    dirs = _assign_package_dirs(model)
    locations = _assign_locations(model, dirs)

    files: Dict[str, str] = {}
    for pkg in model.walk_packages():
        rel_dir = dirs[pkg.guid]
        rel_path = posixpath.join(rel_dir, INDEX_FILENAME) if rel_dir else INDEX_FILENAME
        files[rel_path] = _render_package(pkg, model, dirs, locations)
    return files


def _assign_package_dirs(model: Model) -> Dict[str, str]:
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


def _assign_locations(model: Model, dirs: Dict[str, str]) -> Dict[str, _Location]:
    """Assign every diagram and element a (containing file, anchor)
    location, using GitHub-style heading slugs scoped per package file."""
    locations: Dict[str, _Location] = {}
    for pkg in model.walk_packages():
        rel_dir = dirs[pkg.guid]
        seen: Dict[str, int] = {}
        for diagram in pkg.diagrams:
            anchor = github_slug(_diagram_heading(diagram), seen)
            locations[diagram.guid] = _Location(rel_dir, anchor)
        for element in pkg.elements:
            anchor = github_slug(_element_heading(element), seen)
            locations[element.guid] = _Location(rel_dir, anchor)
    return locations


def _diagram_heading(diagram: Diagram) -> str:
    return f"{diagram.name} ({diagram.type})"


def _element_heading(element: Element) -> str:
    if element.stereotype:
        return f"{element.name} «{element.stereotype}» ({element.type})"
    return f"{element.name} ({element.type})"


def _link(from_dir: str, to_dir: str, filename: str, anchor: Optional[str]) -> str:
    """Build a Markdown link target from the file in from_dir to the file
    <to_dir>/<filename>#anchor, relative to from_dir."""
    if from_dir == to_dir:
        target = ""
    else:
        rel = posixpath.relpath(to_dir or ".", from_dir or ".")
        target = posixpath.join(rel, filename) if rel != "." else filename
    if anchor:
        target = f"{target}#{anchor}" if target else f"#{anchor}"
    return target or filename


def _package_link(from_dir: str, pkg: Package, dirs: Dict[str, str]) -> str:
    return _link(from_dir, dirs[pkg.guid], INDEX_FILENAME, None)


def _node_link(from_dir: str, guid: str, dirs: Dict[str, str], locations: Dict[str, _Location]) -> str:
    loc = locations[guid]
    return _link(from_dir, loc.dir_path, INDEX_FILENAME, loc.anchor)


def _render_package(
    pkg: Package,
    model: Model,
    dirs: Dict[str, str],
    locations: Dict[str, _Location],
) -> str:
    rel_dir = dirs[pkg.guid]
    lines = [f"# {pkg.name}", ""]

    parent = model.packages_by_guid.get(pkg.parent_guid) if pkg.parent_guid else None
    if parent is not None:
        lines.append(f"[Up to {parent.name}]({_package_link(rel_dir, parent, dirs)})")
        lines.append("")

    if pkg.notes:
        lines.append(pkg.notes.strip())
        lines.append("")

    if pkg.subpackages:
        lines.append("## Packages")
        lines.append("")
        for sub in pkg.subpackages:
            lines.append(f"- [{sub.name}]({_package_link(rel_dir, sub, dirs)})")
        lines.append("")

    if pkg.diagrams:
        lines.append("## Diagrams")
        lines.append("")
        for diagram in pkg.diagrams:
            lines.extend(_render_diagram(diagram, rel_dir, model, dirs, locations))

    if pkg.elements:
        lines.append("## Elements")
        lines.append("")
        for element in pkg.elements:
            lines.extend(_render_element(element, rel_dir, model, dirs, locations))

    return "\n".join(lines).rstrip() + "\n"


def _render_diagram(
    diagram: Diagram,
    rel_dir: str,
    model: Model,
    dirs: Dict[str, str],
    locations: Dict[str, _Location],
) -> list:
    lines = [f"### {_diagram_heading(diagram)}", ""]
    if diagram.image_path:
        image_rel = posixpath.relpath(diagram.image_path, rel_dir or ".")
        lines.append(f"![{diagram.name}]({image_rel})")
        lines.append("")
    if diagram.notes:
        lines.append(diagram.notes.strip())
        lines.append("")
    if diagram.element_guids:
        lines.append("Elements shown on this diagram:")
        lines.append("")
        for eguid in diagram.element_guids:
            element = model.elements_by_guid.get(eguid)
            if element is None:
                continue
            lines.append(f"- [{element.name}]({_node_link(rel_dir, eguid, dirs, locations)})")
        lines.append("")
    return lines


def _render_element(
    element: Element,
    rel_dir: str,
    model: Model,
    dirs: Dict[str, str],
    locations: Dict[str, _Location],
) -> list:
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
            diagram = model.diagrams_by_guid.get(dguid)
            if diagram is None:
                continue
            lines.append(f"- [{diagram.name}]({_node_link(rel_dir, dguid, dirs, locations)})")
        lines.append("")

    if element.connectors:
        lines.append("| Relationship | Direction | Related element |")
        lines.append("| --- | --- | --- |")
        for conn in element.connectors:
            other = model.elements_by_guid.get(conn.other_end_guid)
            if other is None:
                continue
            other_link = f"[{other.name}]({_node_link(rel_dir, conn.other_end_guid, dirs, locations)})"
            lines.append(f"| {conn.type} | {conn.direction} | {other_link} |")
        lines.append("")

    return lines
