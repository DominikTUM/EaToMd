"""Filter: renders every Diagram in the IR to an image using EA's own
rendering engine (via Project.PutDiagramImageToFile), and records each
image's path back onto the IR node. Runs after ea_source.extract_model()
and before the markdown/LaTeX renderer.

Image format notes
-------------------
PutDiagramImageToFile's Type parameter has exactly one well-documented,
widely-used value: 1, meaning "derive the actual image format from the
target file's extension" - real-world sample code always passes 1 and
just changes the file extension (.png, .bmp, .emf, ...) to pick the
format. There is no separate constant per format.

Native SVG export via this call only exists from EA 16.1 onward (or with
Sparx's separate community SVG export add-in on older versions) - on
EA 15.2 without that add-in, asking for a ".svg" file here will most
likely fail. So when image_format="svg", this module first tries the
native path, and if EA rejects it, falls back to exporting the always
-supported vector format EMF and converting that to SVG with Inkscape
(https://inkscape.org, must be on PATH) - which yields a real vector SVG
either way, whichever EA version is in use.
"""
from __future__ import annotations

import os
import shutil
import subprocess

from .model import Model

EA_DERIVE_FORMAT_FROM_EXTENSION = 1


class DiagramExportError(RuntimeError):
    pass


def export_diagrams(
    repo,
    model: Model,
    output_dir: str,
    images_subdir: str = "images",
    image_format: str = "png",
) -> None:
    """Export every diagram in the model to <output_dir>/<images_subdir>/<guid>.<ext>
    and set diagram.image_path to that path, relative to output_dir, so the
    renderer can turn it into a relative link/embed.
    """
    project = repo.GetProjectInterface()
    images_dir = os.path.join(output_dir, images_subdir)
    os.makedirs(images_dir, exist_ok=True)

    for diagram in model.diagrams_by_guid.values():
        stem = diagram.guid.strip("{}")

        if image_format == "svg":
            filename = _export_svg(project, diagram, images_dir, stem)
        else:
            filename = f"{stem}.{image_format}"
            _put_diagram_image(project, diagram, os.path.join(images_dir, filename))

        diagram.image_path = "/".join([images_subdir, filename])


def _put_diagram_image(project, diagram, abs_path: str) -> None:
    ok = project.PutDiagramImageToFile(diagram.guid, abs_path, EA_DERIVE_FORMAT_FROM_EXTENSION)
    if not ok:
        raise DiagramExportError(f"EA failed to export diagram '{diagram.name}' ({diagram.guid}) to {abs_path}")


def _export_svg(project, diagram, images_dir: str, stem: str) -> str:
    svg_filename = f"{stem}.svg"
    svg_path = os.path.join(images_dir, svg_filename)

    try:
        ok = project.PutDiagramImageToFile(diagram.guid, svg_path, EA_DERIVE_FORMAT_FROM_EXTENSION)
    except Exception:
        ok = False
    if ok and os.path.exists(svg_path):
        return svg_filename

    # EA couldn't produce SVG natively (pre-16.1 without the SVG add-in) -
    # fall back to its always-supported vector format, EMF, then convert.
    emf_path = os.path.join(images_dir, f"{stem}.emf")
    _put_diagram_image(project, diagram, emf_path)
    _convert_emf_to_svg(emf_path, svg_path)
    os.remove(emf_path)
    return svg_filename


def _convert_emf_to_svg(emf_path: str, svg_path: str) -> None:
    inkscape = shutil.which("inkscape")
    if inkscape is None:
        raise DiagramExportError(
            "EA could not export SVG natively (needs EA 16.1+ or the SVG export add-in on 15.2), "
            "and falling back to EMF->SVG conversion requires Inkscape on PATH: "
            "install it from https://inkscape.org and try again."
        )

    # Inkscape 1.0+ CLI syntax.
    result = subprocess.run(
        [inkscape, emf_path, "--export-type=svg", f"--export-filename={svg_path}"],
        capture_output=True,
        text=True,
    )
    if result.returncode == 0 and os.path.exists(svg_path):
        return

    # Fall back to the Inkscape 0.92 CLI syntax in case an older version is installed.
    result_legacy = subprocess.run(
        [inkscape, emf_path, f"--export-plain-svg={svg_path}"],
        capture_output=True,
        text=True,
    )
    if result_legacy.returncode != 0 or not os.path.exists(svg_path):
        raise DiagramExportError(
            f"Inkscape failed to convert {emf_path} to SVG: {result.stderr or result_legacy.stderr}"
        )
