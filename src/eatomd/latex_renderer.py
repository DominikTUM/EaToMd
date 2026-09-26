"""LaTeX export visitor: turns the IR Model into a dict of
{relative_path: LaTeX source}, one .tex file per package (mirroring the
same on-disk folder layout the Markdown visitor uses), \\input from parent
to child, compiling as a single document from the root package's file.

Unlike Markdown - where every package is its own standalone document and
links must be relative to the linking file - a LaTeX document assembled
with \\input is one continuous file as far as LaTeX is concerned: \\label
names must be unique across the *whole* document (not just per file), and
every \\includegraphics/\\input path is resolved relative to the root
document's directory, never relative to the file doing the including. So
labels here are derived directly from each node's globally-unique GUID
instead of a per-file heading slug, and paths are used as-is (relative to
output_dir) rather than being made relative to the current file.
"""
from __future__ import annotations

import posixpath
import re
from typing import Dict

from .export_visitor import ExportVisitor
from .model import Diagram, Element, Model, Package

_LATEX_SPECIAL_CHARS = {
    "\\": r"\textbackslash{}",
    "&": r"\&",
    "%": r"\%",
    "$": r"\$",
    "#": r"\#",
    "_": r"\_",
    "{": r"\{",
    "}": r"\}",
    "~": r"\textasciitilde{}",
    "^": r"\textasciicircum{}",
}
_LATEX_ESCAPE_RE = re.compile("|".join(re.escape(c) for c in _LATEX_SPECIAL_CHARS))
_LABEL_UNSAFE_RE = re.compile(r"[^A-Za-z0-9]+")


def render_model(model: Model) -> Dict[str, str]:
    return LatexVisitor(model).render()


def escape_latex(text: str) -> str:
    return _LATEX_ESCAPE_RE.sub(lambda m: _LATEX_SPECIAL_CHARS[m.group(0)], text)


def _label(kind: str, guid: str) -> str:
    """A LaTeX \\label must be unique across the whole compiled document;
    a GUID already is, so no per-document collision bookkeeping is needed
    (unlike the Markdown visitor's per-file heading slugs)."""
    return f"{kind}-{_LABEL_UNSAFE_RE.sub('', guid)}"


class LatexVisitor(ExportVisitor):
    file_extension = ".tex"

    def visit_package(self, pkg: Package) -> str:
        is_root = pkg.guid == self.model.root.guid
        lines: list = []

        if is_root:
            lines.extend(_PREAMBLE)

        lines.append(f"\\section{{{escape_latex(pkg.name)}}}")
        lines.append(f"\\label{{{_label('pkg', pkg.guid)}}}")
        lines.append("")

        if pkg.notes:
            lines.append(escape_latex(pkg.notes.strip()))
            lines.append("")

        for diagram in pkg.diagrams:
            lines.append(self.visit_diagram(diagram))

        for element in pkg.elements:
            lines.append(self.visit_element(element))

        for sub in pkg.subpackages:
            sub_path = posixpath.join(self.dirs[sub.guid], "index")
            lines.append(f"\\input{{{sub_path}}}")
        if pkg.subpackages:
            lines.append("")

        if is_root:
            lines.append("\\end{document}")

        return "\n".join(lines).rstrip() + "\n"

    def visit_diagram(self, diagram: Diagram) -> str:
        lines = [
            f"\\subsection{{{escape_latex(diagram.name)} ({escape_latex(diagram.type)})}}",
            f"\\label{{{_label('dia', diagram.guid)}}}",
            "",
        ]
        if diagram.image_path:
            lines.append(f"\\includegraphics[width=\\textwidth]{{{diagram.image_path}}}")
            lines.append("")
        if diagram.notes:
            lines.append(escape_latex(diagram.notes.strip()))
            lines.append("")
        if diagram.element_guids:
            lines.append("Elements shown on this diagram:")
            lines.append("\\begin{itemize}")
            for eguid in diagram.element_guids:
                element = self.model.elements_by_guid.get(eguid)
                if element is None:
                    continue
                lines.append(
                    f"  \\item \\hyperref[{_label('el', eguid)}]{{{escape_latex(element.name)}}}"
                )
            lines.append("\\end{itemize}")
            lines.append("")
        return "\n".join(lines)

    def visit_element(self, element: Element) -> str:
        heading = escape_latex(element.name)
        if element.stereotype:
            heading += f" (\\textit{{{escape_latex(element.stereotype)}}}, {escape_latex(element.type)})"
        else:
            heading += f" ({escape_latex(element.type)})"

        lines = [
            f"\\subsection{{{heading}}}",
            f"\\label{{{_label('el', element.guid)}}}",
            "",
        ]
        if element.notes:
            lines.append(escape_latex(element.notes.strip()))
            lines.append("")

        if element.tagged_values:
            lines.append("\\begin{tabular}{ll}")
            lines.append("\\textbf{Tag} & \\textbf{Value} \\\\")
            for tag in element.tagged_values:
                lines.append(f"{escape_latex(tag.name)} & {escape_latex(tag.value)} \\\\")
            lines.append("\\end{tabular}")
            lines.append("")

        if element.diagram_guids:
            lines.append("Appears on:")
            lines.append("\\begin{itemize}")
            for dguid in element.diagram_guids:
                diagram = self.model.diagrams_by_guid.get(dguid)
                if diagram is None:
                    continue
                lines.append(
                    f"  \\item \\hyperref[{_label('dia', dguid)}]{{{escape_latex(diagram.name)}}}"
                )
            lines.append("\\end{itemize}")
            lines.append("")

        if element.connectors:
            lines.append("\\begin{tabular}{lll}")
            lines.append("\\textbf{Relationship} & \\textbf{Direction} & \\textbf{Related element} \\\\")
            for conn in element.connectors:
                other = self.model.elements_by_guid.get(conn.other_end_guid)
                if other is None:
                    continue
                other_ref = f"\\hyperref[{_label('el', conn.other_end_guid)}]{{{escape_latex(other.name)}}}"
                lines.append(f"{escape_latex(conn.type)} & {escape_latex(conn.direction)} & {other_ref} \\\\")
            lines.append("\\end{tabular}")
            lines.append("")

        return "\n".join(lines)


_PREAMBLE = [
    "\\documentclass{article}",
    "\\usepackage{graphicx}",
    "\\usepackage{hyperref}",
    "\\begin{document}",
    "",
]
