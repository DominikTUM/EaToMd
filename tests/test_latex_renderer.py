import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eatomd.latex_renderer import render_model
from eatomd.model import ConnectorRef, Diagram, Element, Model, Package, TaggedValue


def build_sample_model() -> Model:
    root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=root)
    model.packages_by_guid[root.guid] = root

    pkg_a = Package(guid="PKG-A", name="Domain & Co", notes="Domain notes.", parent_guid="ROOT")
    root.subpackages.append(pkg_a)
    model.packages_by_guid[pkg_a.guid] = pkg_a

    engine = Element(
        guid="EL-ENGINE",
        name="Engine_v2",
        type="Class",
        stereotype="component",
        notes="",
        package_guid="PKG-A",
        tagged_values=[TaggedValue(name="version", value="1.0")],
    )
    car = Element(guid="EL-CAR", name="Car", type="Class", stereotype="", notes="", package_guid="PKG-A")
    engine.connectors.append(
        ConnectorRef(guid="CONN-1", type="Aggregation", direction="Source -> Dest", other_end_guid="EL-CAR", other_end_name="")
    )
    pkg_a.elements.extend([engine, car])
    model.elements_by_guid[engine.guid] = engine
    model.elements_by_guid[car.guid] = car

    diagram = Diagram(
        guid="DIA-1",
        name="Overview",
        type="Class",
        notes="",
        package_guid="PKG-A",
        element_guids=["EL-ENGINE"],
        image_path="images/DIA-1.png",
    )
    engine.diagram_guids.append(diagram.guid)
    pkg_a.diagrams.append(diagram)
    model.diagrams_by_guid[diagram.guid] = diagram

    return model


def test_render_produces_one_tex_per_package():
    model = build_sample_model()
    files = render_model(model)
    assert "index.tex" in files
    assert "Domain & Co/index.tex" in files


def test_root_file_has_preamble_and_document_wrapper():
    model = build_sample_model()
    files = render_model(model)
    root_page = files["index.tex"]
    assert "\\documentclass{article}" in root_page
    assert "\\begin{document}" in root_page
    assert root_page.rstrip().endswith("\\end{document}")


def test_root_inputs_subpackage_by_root_relative_path():
    model = build_sample_model()
    files = render_model(model)
    root_page = files["index.tex"]
    assert "\\input{Domain & Co/index}" in root_page


def test_special_characters_are_escaped_in_headings():
    model = build_sample_model()
    files = render_model(model)
    pkg_page = files["Domain & Co/index.tex"]
    assert "\\section{Domain \\& Co}" in pkg_page
    assert "Engine\\_v2" in pkg_page


def test_diagram_image_path_is_root_relative_not_package_relative():
    model = build_sample_model()
    files = render_model(model)
    pkg_page = files["Domain & Co/index.tex"]
    # unlike Markdown, LaTeX \includegraphics paths are resolved from the
    # root document's directory, so the path is used exactly as stored
    assert "\\includegraphics[width=\\textwidth]{images/DIA-1.png}" in pkg_page


def test_element_cross_reference_uses_guid_based_label():
    model = build_sample_model()
    files = render_model(model)
    pkg_page = files["Domain & Co/index.tex"]
    assert "\\label{el-ELCAR}" in pkg_page
    assert "\\hyperref[el-ELCAR]{Car}" in pkg_page
