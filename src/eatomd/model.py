"""Intermediate representation (IR) shared between all pipeline filters.

The EA source filter builds this tree from the live repository; every
downstream filter (diagram export, markdown rendering, git sink) only
depends on these plain dataclasses, never on the EA COM API. That keeps
rendering and tests decoupled from having EA installed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class TaggedValue:
    name: str
    value: str


@dataclass
class ConnectorRef:
    guid: str
    type: str
    direction: str  # "Source -> Dest", "Dest -> Source", "Unspecified", ...
    other_end_guid: str
    other_end_name: str
    notes: str = ""


@dataclass
class Diagram:
    guid: str
    name: str
    type: str
    notes: str
    package_guid: str
    element_guids: List[str] = field(default_factory=list)
    image_path: Optional[str] = None  # set by the diagram-export filter


@dataclass
class Element:
    guid: str
    name: str
    type: str
    stereotype: str
    notes: str
    package_guid: str
    tagged_values: List[TaggedValue] = field(default_factory=list)
    connectors: List[ConnectorRef] = field(default_factory=list)
    diagram_guids: List[str] = field(default_factory=list)


@dataclass
class Package:
    guid: str
    name: str
    notes: str
    parent_guid: Optional[str]
    subpackages: List["Package"] = field(default_factory=list)
    elements: List[Element] = field(default_factory=list)
    diagrams: List[Diagram] = field(default_factory=list)


@dataclass
class Model:
    """Whole-tree container plus GUID indexes for cross-linking."""

    root: Package
    packages_by_guid: Dict[str, Package] = field(default_factory=dict)
    elements_by_guid: Dict[str, Element] = field(default_factory=dict)
    diagrams_by_guid: Dict[str, Diagram] = field(default_factory=dict)

    def element_owner(self, element_guid: str) -> Optional[Package]:
        element = self.elements_by_guid.get(element_guid)
        if element is None:
            return None
        return self.packages_by_guid.get(element.package_guid)

    def walk_packages(self):
        """Yield every package in the tree, root first, depth-first."""
        stack = [self.root]
        while stack:
            pkg = stack.pop(0)
            yield pkg
            stack = list(pkg.subpackages) + stack
