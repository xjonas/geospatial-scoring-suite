
import geopandas as gpd
import pandas as pd
import h3
import numpy as np
from shapely.geometry import Polygon, Point
import osmnx as ox
from config.settings import GERMANY_CRS, HEXAGON_SIZE

def create_hexagon_grid(bounds, hexagon_size):
    # Create a hexagon grid for a given bounding box.

    # Extract bounds
    minx, miny, maxx, maxy = bounds

    # Calculate hexagon dimensions
    hex_width = hexagon_size
    hex_height = np.sqrt(3) * hexagon_size / 2

    # Calculate number of hexagons in each direction
    cols = int(np.ceil((maxx - minx) / (0.75 * hex_width))) + 1
    rows = int(np.ceil((maxy - miny) / hex_height)) + 1

    # Create empty list to store hexagons
    hexagons = []

    # Generate hexagons
    for row in range(rows):
        for col in range(cols):
            # Calculate center of hexagon
            x = minx + col * (0.75 * hex_width)
            y = miny + row * hex_height

            # Offset every other column
            if col % 2 == 1:
                y += 0.5 * hex_height

            # Create hexagon vertices
            angles = np.linspace(0, 2*np.pi, 7)[:-1]  # 6 vertices
            x_vertices = x + 0.5 * hex_width * np.cos(angles)
            y_vertices = y + 0.5 * hex_width * np.sin(angles)

            # Create hexagon polygon
            hexagon = Polygon([(x_vertices[i], y_vertices[i]) for i in range(6)])

            # Store hexagon with its row and column indices
            hexagons.append({
                'geometry': hexagon,
                'row': row,
                'col': col,
                'id': f"{row}_{col}"
            })

    # Create GeoDataFrame
    grid_gdf = gpd.GeoDataFrame(hexagons, crs=GERMANY_CRS)

    return grid_gdf


def create_grid_from_city(city_name):
    # Create a hexagon grid covering a city.

    # Get city boundaries
    city_gdf = ox.geocode_to_gdf(city_name)

    # Project to specified CRS
    city_gdf = city_gdf.to_crs(GERMANY_CRS)

    # Get bounds
    bounds = city_gdf.total_bounds

    # Create grid
    return create_hexagon_grid(bounds, HEXAGON_SIZE)