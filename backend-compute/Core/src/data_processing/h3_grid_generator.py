import geopandas as gpd
import h3
from shapely.geometry import Polygon, Point, MultiPolygon, box
import osmnx as ox
from config.settings import GERMANY_CRS
import time


def get_h3_resolution_info():
    # Returns a dictionary of H3 resolutions and their approximate edge lengths in meters

    return {
        0: 1107712.0, 1: 418676.0, 2: 158244.0, 3: 59810.0,
        4: 22606.0, 5: 8544.0, 6: 3229.0, 7: 1220.0,
        8: 461.0, 9: 174.0, 10: 65.9, 11: 24.9,
        12: 9.4, 13: 3.6, 14: 1.3, 15: 0.5
    }


def polygon_from_h3(h3_index: str) -> Polygon:
    # Create a Shapely polygon from an H3 index
    boundary = h3.cell_to_boundary(h3_index)
    coords = [(lng, lat) for lat, lng in boundary]
    return Polygon(coords)


def h3_indices_to_grid(h3_indices):
    # Convert a set of H3 indices to a GeoDataFrame with desired attributes
    start = time.time()
    print(f"Converting {len(h3_indices)} H3 cells to GeoDataFrame...")

    features = []
    for i, idx in enumerate(h3_indices):
        if i % 1000 == 0 and i:
            print(f" - {i}/{len(h3_indices)} cells processed")

        poly = polygon_from_h3(idx)
        #lat, lng = h3.cell_to_latlng(idx)
        #centroid = Point(lng, lat)

        # Store the H3 center as a reference but don't use for calculations
        lat, lng = h3.cell_to_latlng(idx)


        row = i // 100
        col = i % 100

        features.append({
            'geometry': poly,
            'h3_index': idx,
            'id': idx,
            'row': row,
            'col': col,
            #'centroid': centroid
        })

    gdf = gpd.GeoDataFrame(features, crs='EPSG:4326').to_crs(GERMANY_CRS)
    # Create GeoDataFrame and project to target CRS
    # Calculate centroid AFTER projection to GERMANY_CRS for consistent behavior
    gdf['centroid'] = gdf.geometry.centroid
    gdf['centroid_x'] = gdf.centroid.x
    gdf['centroid_y'] = gdf.centroid.y
    gdf['hexagon_area'] = gdf.geometry.area

    print(f"GeoDataFrame created in {time.time() - start:.2f}s, total {len(gdf)} hexagons")
    return gdf


def create_h3_grid(bounds: tuple, h3_resolution: int) -> gpd.GeoDataFrame:
    # Create an H3 grid within a bounding box (in target CRS)
    start = time.time()
    print(f"Building H3 grid at resolution {h3_resolution} for bounds {bounds}...")

    minx, miny, maxx, maxy = bounds
    bbox = box(minx, miny, maxx, maxy)
    bbox_wgs84 = gpd.GeoSeries([bbox], crs=GERMANY_CRS).to_crs('EPSG:4326').iloc[0]

    # Use new high-level geo_to_cells API
    cells = h3.geo_to_cells(bbox_wgs84, h3_resolution)
    print(f" - {len(cells)} cells generated in bounding box")

    return h3_indices_to_grid(cells)


def create_h3_grid_from_city(city_name: str, h3_resolution: int = 9) -> gpd.GeoDataFrame:
    # Create an H3 grid for a city polygon fetched from OSM
    start = time.time()
    print(f"Building H3 grid for {city_name} at resolution {h3_resolution}...")

    res_info = get_h3_resolution_info()
    print(f"Resolution {h3_resolution} ≈ {res_info.get(h3_resolution, 'unknown')}m edge length")

    city_poly = ox.geocode_to_gdf(city_name).to_crs('EPSG:4326').iloc[0].geometry
    parts = city_poly.geoms if isinstance(city_poly, MultiPolygon) else [city_poly]

    all_cells = set()
    for part in parts:
        cells = h3.geo_to_cells(part, h3_resolution)
        print(f" - added {len(cells)} cells from part")
        all_cells.update(cells)

    print(f"Total {len(all_cells)} cells for {city_name}")
    return h3_indices_to_grid(all_cells)
