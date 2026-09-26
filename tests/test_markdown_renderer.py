import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from eatomd.markdown_renderer import render_model
from eatomd.model import ConnectorRef, Diagram, Element, Model, Package, TaggedValue


def build_sample_model() -> Model:
    root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=root)
    model.packages_by_guid[root.guid] = root

    pkg_a = Package(guid="PKG-A", name="Domain", notes="Domain package notes.", parent_guid="ROOT")
    root.subpackages.append(pkg_a)
    model.packages_by_guid[pkg_a.guid] = pkg_a

    pkg_b = Package(guid="PKG-B", name="Domain", notes="", parent_guid="PKG-A")  # name collides with sibling folder rules test
    pkg_a.subpackages.append(pkg_b)
    model.packages_by_guid[pkg_b.guid] = pkg_b

    engine = Element(
        guid="EL-ENGINE",
        name="Engine",
        type="Class",
        stereotype="component",
        notes="The engine.",
        package_guid="PKG-A",
        tagged_values=[TaggedValue(name="version", value="1.0")],
    )
    car = Element(
        guid="EL-CAR",
        name="Car",
        type="Class",
        stereotype="",
        notes="",
        package_guid="PKG-B",
    )
    engine.connectors.append(
        ConnectorRef(guid="CONN-1", type="Aggregation", direction="Source -> Dest", other_end_guid="EL-CAR", other_end_name="")
    )
    pkg_a.elements.append(engine)
    pkg_b.elements.append(car)
    model.elements_by_guid[engine.guid] = engine
    model.elements_by_guid[car.guid] = car

    diagram = Diagram(
        guid="DIA-1",
        name="Overview",
        type="Class",
        notes="Diagram notes.",
        package_guid="PKG-A",
        element_guids=["EL-ENGINE"],
        image_path="images/DIA-1.png",
    )
    engine.diagram_guids.append(diagram.guid)
    pkg_a.diagrams.append(diagram)
    model.diagrams_by_guid[diagram.guid] = diagram

    return model


def test_render_produces_one_index_per_package():
    model = build_sample_model()
    files = render_model(model)

    assert "index.md" in files
    assert "Domain/index.md" in files
    # nested package with the same name is not a sibling collision, so no suffix
    assert "Domain/Domain/index.md" in files


def test_diagram_image_link_is_relative_to_its_package():
    model = build_sample_model()
    files = render_model(model)
    domain_page = files["Domain/index.md"]
    assert "![Overview](../images/DIA-1.png)" in domain_page


def test_cross_package_element_link_resolves_relative_path():
    model = build_sample_model()
    files = render_model(model)
    domain_page = files["Domain/index.md"]
    # Engine (in Domain) links to Car (in Domain/Domain)
    assert "Domain/index.md#car-class" in domain_page


def test_element_heading_and_tagged_values_render():
    model = build_sample_model()
    files = render_model(model)
    domain_page = files["Domain/index.md"]
    assert "### Engine «component» (Class)" in domain_page
    assert "| version | 1.0 |" in domain_page


def test_sibling_packages_with_same_name_are_deduplicated():
    root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=root)
    model.packages_by_guid[root.guid] = root

    for i, guid in enumerate(["PKG-X", "PKG-Y"]):
        pkg = Package(guid=guid, name="Interfaces", notes="", parent_guid="ROOT")
        root.subpackages.append(pkg)
        model.packages_by_guid[guid] = pkg

    files = render_model(model)
    assert "Interfaces/index.md" in files
    assert "Interfaces-1/index.md" in files


def test_links_and_image_paths_are_percent_encoded():
    root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=root)
    model.packages_by_guid[root.guid] = root

    pkg = Package(guid="PKG-A", name="Use Cases (v2)", notes="", parent_guid="ROOT")
    root.subpackages.append(pkg)
    model.packages_by_guid[pkg.guid] = pkg

    element = Element(guid="EL-1", name="Login", type="Use Case", stereotype="", notes="", package_guid="PKG-A")
    pkg.elements.append(element)
    model.elements_by_guid[element.guid] = element

    diagram = Diagram(
        guid="DIA-1",
        name="Overview",
        type="Use Case",
        notes="",
        package_guid="PKG-A",
        image_path="images/DIA-1.png",
    )
    pkg.diagrams.append(diagram)
    model.diagrams_by_guid[diagram.guid] = diagram

    files = render_model(model)
    root_page = files["index.md"]
    # raw space/parentheses in a folder name must not appear unescaped in a link target
    assert "(Use%20Cases%20%28v2%29/index.md)" in root_page

    pkg_page = files["Use Cases (v2)/index.md"]
    assert "![Overview](../images/DIA-1.png)" in pkg_page


def test_root_package_has_no_up_link():
    model = build_sample_model()
    files = render_model(model)
    assert "[Up to" not in files["index.md"]
    assert "[Up to Model]" in files["Domain/index.md"]
