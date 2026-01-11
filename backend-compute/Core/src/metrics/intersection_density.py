

import geopandas as gpd
import time
from src.metrics.base_metric import BaseMetric
from config.settings import MAX_INTERSECTION_DENSITY

class IntersectionDensity(BaseMetric):
    """
    Measures the density of street intersections within each hexagon
    """
    def __init__(self, weight, data_manager=None):
        super().__init__("intersection_density", weight)
        self.data_manager = data_manager

    def calculate(self, grid_gdf, nodes_gdf):
        print("Calculating Intersection Density metric...")
        start_time = time.time() if 'time' in globals() else None

        # Spatial join to count intersections in each hexagon
        joined = gpd.sjoin(grid_gdf, nodes_gdf, how="left", predicate="contains")

        # Count intersections per hexagon
        intersection_counts = joined.groupby('id').size()

        # Add counts to grid
        grid_gdf = grid_gdf.copy()
        grid_gdf[self.name] = grid_gdf['id'].map(intersection_counts).fillna(0)

        # Normalize to 0-100 scale
        grid_gdf[f"{self.name}_score"] = (
                grid_gdf[self.name] / MAX_INTERSECTION_DENSITY * 100
        ).clip(0, 100)

        if start_time:
            print(f"Intersection density calculation complete. Time: {time.time() - start_time:.2f} seconds")

        return grid_gdf