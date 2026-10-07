"""Build specs/registry/district_geo.json (shipped) from local-research/data/district_boundaries_raw.json (made by local-research/scripts/fetch_district_boundaries.py).

Keeps, per district: the simplified boundary rings (coordinates rounded to 4 decimals, about 11 m), a bounding box for cheap rejection, and the centre point of the boundary.
Data: OpenStreetMap contributors, ODbL. Boundaries are simplified to about 2 km: right inside a district, but a point within a couple of kilometres of a border can land in the
neighbour. Run:  python backend/scripts/build_district_geo.py
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "local-research" / "data" / "district_boundaries_raw.json"
OUT = ROOT / "specs" / "registry" / "district_geo.json"


def rings(geometry: dict) -> list[list[list[list[float]]]]:
    polys = [geometry["coordinates"]] if geometry["type"] == "Polygon" else geometry["coordinates"]
    return [[[[round(x, 4), round(y, 4)] for x, y in ring] for ring in poly] for poly in polys]


def main() -> None:
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    districts = {}
    for name, v in sorted(raw.items()):
        if not v.get("geojson"):
            if v.get("lat") is not None:
                districts[name] = {"centre": [round(v["lat"], 4), round(v["lng"], 4)], "polygons": []}
            continue
        polygons = rings(v["geojson"])
        xs = [x for poly in polygons for ring in poly for x, _ in ring]
        ys = [y for poly in polygons for ring in poly for _, y in ring]
        districts[name] = {
            "bbox": [min(xs), min(ys), max(xs), max(ys)],
            "centre": [round(v["lat"], 4), round(v["lng"], 4)],
            "polygons": polygons,
            "source": f"osm:{v['osm']}",
        }
    out = {
        "note": "District boundaries simplified to about 2 km, from OpenStreetMap (ODbL). Built by backend/scripts/build_district_geo.py. Used by app/district_geo.py.",
        "districts": districts,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {OUT} ({OUT.stat().st_size // 1024} KB): {len(districts)} districts, {sum(1 for d in districts.values() if d['polygons'])} with a boundary")


if __name__ == "__main__":
    main()
