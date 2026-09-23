"""Source filter: connects to a live Sparx EA repository via COM Automation
and extracts the package/element/diagram tree into the IR defined in
model.py.

This module requires Windows + pywin32 + a licensed EA install, since it
drives the real EA.Repository COM object. Everything downstream of
`extract_model()` only touches plain dataclasses and has no EA dependency.
"""
from __future__ import annotations

from typing import Optional

from .model import ConnectorRef, Diagram, Element, Model, Package, TaggedValue

try:
    import win32com.client  # type: ignore
except ImportError:  # pragma: no cover - exercised only off-Windows
    win32com = None  # type: ignore


class EaConnectionError(RuntimeError):
    pass


def open_repository(project_path: str):
    """Open an EA repository (.qea/.eapx/.feap, or a full DB connection
    string) and return the EA.Repository COM object."""
    if win32com is None:
        raise EaConnectionError(
            "pywin32 is not installed / not on Windows. "
            "Install with `pip install pywin32` and run on Windows with EA installed."
        )
    repo = win32com.client.Dispatch("EA.Repository")
    if not repo.OpenFile(project_path):
        raise EaConnectionError(f"EA could not open repository: {project_path}")
    return repo


def close_repository(repo) -> None:
    try:
        repo.CloseFile()
        repo.Exit()
    except Exception:
        pass


def extract_model(repo, root_package_name: Optional[str] = None) -> Model:
    """Walk the repository and build the IR Model.

    If root_package_name is given, only that top-level model package is
    exported; otherwise every top-level package under repo.Models is
    combined under a synthetic root.
    """
    synthetic_root = Package(guid="ROOT", name="Model", notes="", parent_guid=None)
    model = Model(root=synthetic_root)
    model.packages_by_guid[synthetic_root.guid] = synthetic_root

    # EA connectors/diagram objects reference elements by numeric ElementID,
    # while the IR keys everything by GUID. Build that mapping during the
    # walk, then resolve numeric references to GUIDs in a second pass below.
    id_to_guid: dict = {}

    for top_pkg in _iter(repo.Models):
        if root_package_name and top_pkg.Name != root_package_name:
            continue
        pkg = _extract_package(top_pkg, parent_guid=synthetic_root.guid, model=model, id_to_guid=id_to_guid)
        synthetic_root.subpackages.append(pkg)

    _resolve_ids(model, id_to_guid)
    return model


def _resolve_ids(model: Model, id_to_guid: dict) -> None:
    for diagram in model.diagrams_by_guid.values():
        diagram.element_guids = [
            id_to_guid[eid] for eid in diagram.element_guids if eid in id_to_guid
        ]
    for element in model.elements_by_guid.values():
        for connector in element.connectors:
            other_guid = id_to_guid.get(connector.other_end_guid)
            if other_guid is None:
                continue
            connector.other_end_guid = other_guid
            other_element = model.elements_by_guid.get(other_guid)
            if other_element is not None:
                connector.other_end_name = other_element.name
    for diagram in model.diagrams_by_guid.values():
        for eguid in diagram.element_guids:
            element = model.elements_by_guid.get(eguid)
            if element is not None and diagram.guid not in element.diagram_guids:
                element.diagram_guids.append(diagram.guid)


def _iter(ea_collection):
    """EA COM collections are 1-indexed and expose .Count / .GetAt(i)."""
    for i in range(ea_collection.Count):
        yield ea_collection.GetAt(i)


def _extract_package(ea_pkg, parent_guid: str, model: Model, id_to_guid: dict) -> Package:
    pkg = Package(
        guid=ea_pkg.PackageGUID,
        name=ea_pkg.Name,
        notes=ea_pkg.Notes or "",
        parent_guid=parent_guid,
    )
    model.packages_by_guid[pkg.guid] = pkg

    for ea_diagram in _iter(ea_pkg.Diagrams):
        pkg.diagrams.append(_extract_diagram(ea_diagram, pkg.guid, model))

    for ea_element in _iter(ea_pkg.Elements):
        pkg.elements.append(_extract_element(ea_element, pkg.guid, model, id_to_guid))

    for ea_sub in _iter(ea_pkg.Packages):
        pkg.subpackages.append(
            _extract_package(ea_sub, parent_guid=pkg.guid, model=model, id_to_guid=id_to_guid)
        )

    return pkg


def _extract_diagram(ea_diagram, package_guid: str, model: Model) -> Diagram:
    diagram = Diagram(
        guid=ea_diagram.DiagramGUID,
        name=ea_diagram.Name,
        type=ea_diagram.Type,
        notes=ea_diagram.Notes or "",
        package_guid=package_guid,
    )
    # DiagramObjects reference elements by numeric ElementID; these get
    # resolved to GUIDs in _resolve_ids() once every element has been seen.
    for ea_diagram_object in _iter(ea_diagram.DiagramObjects):
        if ea_diagram_object.ElementID:
            diagram.element_guids.append(str(ea_diagram_object.ElementID))
    model.diagrams_by_guid[diagram.guid] = diagram
    return diagram


def _extract_element(ea_element, package_guid: str, model: Model, id_to_guid: dict) -> Element:
    element = Element(
        guid=ea_element.ElementGUID,
        name=ea_element.Name,
        type=ea_element.Type,
        stereotype=ea_element.Stereotype or "",
        notes=ea_element.Notes or "",
        package_guid=package_guid,
    )
    id_to_guid[str(ea_element.ElementID)] = element.guid

    for ea_tag in _iter(ea_element.TaggedValues):
        element.tagged_values.append(TaggedValue(name=ea_tag.Name, value=ea_tag.Value))

    for ea_conn in _iter(ea_element.Connectors):
        is_source = ea_conn.ClientID == ea_element.ElementID
        other_end_id = ea_conn.SupplierID if is_source else ea_conn.ClientID
        direction = "Source -> Dest" if is_source else "Dest -> Source"
        element.connectors.append(
            ConnectorRef(
                guid=ea_conn.ConnectorGUID,
                type=ea_conn.Type,
                direction=direction,
                other_end_guid=str(other_end_id),  # resolved to a real GUID in _resolve_ids()
                other_end_name="",
                notes=ea_conn.Notes or "",
            )
        )

    model.elements_by_guid[element.guid] = element
    return element
