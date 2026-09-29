"""Shared helpers for constructing Space Engineers blueprint XML in tests."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, Optional, Sequence, Union

BlockSpec = Union[str, dict]

_XSI_NS = "http://www.w3.org/2001/XMLSchema-instance"
_XSI_TYPE = f"{{{_XSI_NS}}}type"
_SHIP_TYPE = "MyObjectBuilder_ShipBlueprintDefinition"


def write_blueprint(
    destination: Path,
    blocks: Sequence[BlockSpec],
    grid_size: str = "Large",
    include_grid: bool = True,
    identity: Optional[str] = None,
) -> Path:
    """
    Write a minimal bp.sbc.

    Each block may be a subtype string or a dict with keys:
    subtype, orientation (Forward), up, min (x, y, z tuple),
    tag (element name, default MyObjectBuilder_CubeBlock),
    xsi_type, entity_id.
    """
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)

    ET.register_namespace("xsi", _XSI_NS)
    ET.register_namespace("xsd", "http://www.w3.org/2001/XMLSchema")

    root = ET.Element("Definitions")
    ship_blueprints = ET.SubElement(root, "ShipBlueprints")
    ship_blueprint = ET.SubElement(ship_blueprints, "ShipBlueprint")
    if identity:
        id_elem = ET.SubElement(ship_blueprint, "Id")
        id_elem.set("Type", _SHIP_TYPE)
        id_elem.set("Subtype", identity)
        ET.SubElement(id_elem, "SubtypeId").text = identity
        ET.SubElement(ship_blueprint, "DisplayName").text = identity

    if include_grid:
        cube_grid = ET.SubElement(ship_blueprint, "CubeGrid")
        ET.SubElement(cube_grid, "GridSizeEnum").text = grid_size
        cube_blocks = ET.SubElement(cube_grid, "CubeBlocks")
    else:
        cube_blocks = ET.SubElement(ship_blueprint, "CubeBlocks")

    for spec in blocks:
        tag = "MyObjectBuilder_CubeBlock"
        xsi_type = None
        entity_id = None
        up = None
        if isinstance(spec, str):
            subtype = spec
            orientation = None
            min_xyz = None
        else:
            subtype = spec["subtype"]
            orientation = spec.get("orientation")
            min_xyz = spec.get("min")
            tag = spec.get("tag", tag)
            xsi_type = spec.get("xsi_type")
            entity_id = spec.get("entity_id")
            up = spec.get("up")

        block = ET.SubElement(cube_blocks, tag)
        if xsi_type:
            block.set(_XSI_TYPE, xsi_type)
        ET.SubElement(block, "SubtypeId").text = subtype
        ET.SubElement(block, "SubtypeName").text = subtype
        if entity_id is not None:
            ET.SubElement(block, "EntityId").text = str(entity_id)
        if orientation:
            ET.SubElement(block, "BlockOrientation").attrib.update(
                {"Forward": orientation, "Up": up or "Up"}
            )
        if min_xyz:
            ET.SubElement(block, "Min").attrib.update(
                {"x": str(min_xyz[0]), "y": str(min_xyz[1]), "z": str(min_xyz[2])}
            )

    ET.ElementTree(root).write(destination, encoding="utf-8", xml_declaration=True)
    return destination


def write_blueprint_dir(
    parent: Path,
    name: str,
    blocks: Sequence[BlockSpec],
    grid_size: str = "Large",
    extra_files: Optional[Iterable[str]] = None,
    identity: Optional[str] = None,
) -> Path:
    folder = Path(parent) / name
    folder.mkdir(parents=True, exist_ok=True)
    write_blueprint(
        folder / "bp.sbc",
        blocks,
        grid_size=grid_size,
        identity=name if identity is None else identity,
    )
    for extra in extra_files or ():
        (folder / extra).write_text("dummy", encoding="utf-8")
    return folder
