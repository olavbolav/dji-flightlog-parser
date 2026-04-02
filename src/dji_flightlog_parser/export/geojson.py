"""GeoJSON flight path export."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from ..frame.models import Frame
from ..layout.details import Details


def export_geojson(
    details: Details,
    frames: list[Frame],
    output_path: Optional[str | Path] = None,
) -> str:
    """Export flight path as GeoJSON LineString feature."""
    coordinates = []
    for f in frames:
        lon = f.osd.longitude
        lat = f.osd.latitude
        alt = f.osd.altitude
        if abs(lon) > 0.001 or abs(lat) > 0.001:
            coordinates.append([lon, lat, alt])

    properties = {
        "subStreet": details.sub_street,
        "street": details.street,
        "city": details.city,
        "area": details.area,
        "aircraftName": details.aircraft_name,
        "aircraftSN": details.aircraft_sn,
        "cameraSN": details.camera_sn,
        "rcSN": details.rc_sn,
        "totalTime": details.total_time,
        "totalDistance": details.total_distance,
        "maxHeight": details.max_height,
        "maxHorizontalSpeed": details.max_horizontal_speed,
        "maxVerticalSpeed": details.max_vertical_speed,
        "productType": details.product_type.name if hasattr(details.product_type, 'name') else str(details.product_type),
    }

    if details.start_time:
        properties["startTime"] = details.start_time.isoformat().replace("+00:00", "Z")

    geojson = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {
                    "type": "LineString",
                    "coordinates": coordinates,
                },
                "properties": properties,
            }
        ],
    }

    result = json.dumps(geojson, ensure_ascii=False)

    if output_path:
        Path(output_path).write_text(result, encoding="utf-8")

    return result
