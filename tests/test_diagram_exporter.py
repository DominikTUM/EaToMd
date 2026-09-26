import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from unittest.mock import MagicMock, patch

from eatomd import diagram_exporter
from eatomd.model import Diagram, Model, Package


def build_single_diagram_model() -> Model:
    root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=root)
    model.packages_by_guid[root.guid] = root
    diagram = Diagram(guid="{ABC-123}", name="Overview", type="Class", notes="", package_guid="ROOT")
    root.diagrams.append(diagram)
    model.diagrams_by_guid[diagram.guid] = diagram
    return model


def test_png_export_uses_derive_from_extension_type(tmp_path):
    model = build_single_diagram_model()
    project = MagicMock()

    def fake_put(guid, path, type_):
        # simulate EA actually writing the file
        open(path, "wb").close()
        return True

    project.PutDiagramImageToFile.side_effect = fake_put
    repo = MagicMock()
    repo.GetProjectInterface.return_value = project

    diagram_exporter.export_diagrams(repo, model, str(tmp_path), image_format="png")

    diagram = model.diagrams_by_guid["{ABC-123}"]
    assert diagram.image_path == "images/ABC-123.png"
    project.PutDiagramImageToFile.assert_called_once()
    args = project.PutDiagramImageToFile.call_args[0]
    assert args[2] == diagram_exporter.EA_DERIVE_FORMAT_FROM_EXTENSION
    assert args[1].endswith("ABC-123.png")


def test_svg_export_uses_native_path_when_ea_supports_it(tmp_path):
    model = build_single_diagram_model()
    project = MagicMock()

    def fake_put(guid, path, type_):
        open(path, "wb").close()
        return True

    project.PutDiagramImageToFile.side_effect = fake_put
    repo = MagicMock()
    repo.GetProjectInterface.return_value = project

    diagram_exporter.export_diagrams(repo, model, str(tmp_path), image_format="svg")

    diagram = model.diagrams_by_guid["{ABC-123}"]
    assert diagram.image_path == "images/ABC-123.svg"
    # only the native .svg attempt was made - no EMF fallback needed
    assert project.PutDiagramImageToFile.call_count == 1


def test_svg_export_falls_back_to_emf_and_converts_when_ea_cannot_produce_svg(tmp_path):
    model = build_single_diagram_model()
    project = MagicMock()

    def fake_put(guid, path, type_):
        if path.endswith(".svg"):
            return False  # EA (e.g. 15.2 without the add-in) can't produce SVG natively
        open(path, "wb").close()  # the .emf fallback export succeeds
        return True

    project.PutDiagramImageToFile.side_effect = fake_put
    repo = MagicMock()
    repo.GetProjectInterface.return_value = project

    with patch("eatomd.diagram_exporter.shutil.which", return_value="/usr/bin/inkscape"), patch(
        "eatomd.diagram_exporter.subprocess.run"
    ) as mock_run:

        def fake_inkscape_run(args, **kwargs):
            svg_path = args[-1].split("=", 1)[1]
            open(svg_path, "wb").close()
            return MagicMock(returncode=0, stderr="")

        mock_run.side_effect = fake_inkscape_run

        diagram_exporter.export_diagrams(repo, model, str(tmp_path), image_format="svg")

    diagram = model.diagrams_by_guid["{ABC-123}"]
    assert diagram.image_path == "images/ABC-123.svg"
    # the intermediate .emf file is cleaned up after conversion
    assert not os.path.exists(os.path.join(str(tmp_path), "images", "ABC-123.emf"))
    assert os.path.exists(os.path.join(str(tmp_path), "images", "ABC-123.svg"))


def test_svg_export_raises_clear_error_without_inkscape(tmp_path):
    model = build_single_diagram_model()
    project = MagicMock()

    def fake_put(guid, path, type_):
        if path.endswith(".svg"):
            return False
        open(path, "wb").close()
        return True

    project.PutDiagramImageToFile.side_effect = fake_put
    repo = MagicMock()
    repo.GetProjectInterface.return_value = project

    with patch("eatomd.diagram_exporter.shutil.which", return_value=None):
        try:
            diagram_exporter.export_diagrams(repo, model, str(tmp_path), image_format="svg")
            assert False, "expected DiagramExportError"
        except diagram_exporter.DiagramExportError as exc:
            assert "Inkscape" in str(exc)
