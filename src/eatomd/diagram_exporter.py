"""Filter: renders every Diagram in the IR to a PNG using EA's own
rendering engine (via Project.PutDiagramImageToFile), and records each
image's path back onto the IR node. Runs after ea_source.extract_model()
and before markdown_renderer.render_model().
"""
from __future__ import annotations

import os

from .model import Model

EA_IMAGE_TYPE_PNG = 1


class DiagramExportError(RuntimeError):
    pass


def export_diagrams(repo, model: Model, output_dir: str, images_subdir: str = "images") -> None:
    """Export every diagram in the model to <output_dir>/<images_subdir>/<guid>.png
    and set diagram.image_path to that path, relative to output_dir, so the
    markdown renderer can turn it into a relative link.
    """
    project = repo.GetProjectInterface()
    images_dir = os.path.join(output_dir, images_subdir)
    os.makedirs(images_dir, exist_ok=True)

    for diagram in model.diagrams_by_guid.values():
        filename = f"{diagram.guid.strip('{}')}.png"
        abs_path = os.path.join(images_dir, filename)
        ok = project.PutDiagramImageToFile(diagram.guid, abs_path, EA_IMAGE_TYPE_PNG)
        if not ok:
            raise DiagramExportError(f"EA failed to export diagram '{diagram.name}' ({diagram.guid})")
        diagram.image_path = "/".join([images_subdir, filename])
