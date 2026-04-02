"""KML flight path export."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
from xml.etree.ElementTree import Element, SubElement, tostring

from ..frame.models import Frame
from ..layout.details import Details


def export_kml(
    details: Details,
    frames: list[Frame],
    output_path: Optional[str | Path] = None,
) -> str:
    """Export flight path as KML document."""
    kml = Element("kml", xmlns="http://www.opengis.net/kml/2.2")
    doc = SubElement(kml, "Document")

    name = SubElement(doc, "name")
    name.text = details.aircraft_name or "DJI Flight"

    placemark = SubElement(doc, "Placemark")
    pm_name = SubElement(placemark, "name")
    pm_name.text = details.aircraft_name or "Flight Path"

    line_string = SubElement(placemark, "LineString")
    altitude_mode = SubElement(line_string, "altitudeMode")
    altitude_mode.text = "absolute"

    coords_parts = []
    for f in frames:
        lon = f.osd.longitude
        lat = f.osd.latitude
        alt = f.osd.altitude
        if abs(lon) > 0.001 or abs(lat) > 0.001:
            coords_parts.append(f"{lon},{lat},{alt}")

    coordinates = SubElement(line_string, "coordinates")
    coordinates.text = " ".join(coords_parts)

    result = '<?xml version="1.0" encoding="UTF-8"?>\n'
    result += tostring(kml, encoding="unicode")

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result
