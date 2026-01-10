import geopandas as gpd
import pandas as pd
import numpy as np
import time
from src.metrics.base_metric import BaseMetric

class GreenSpace(BaseMetric):
    """
    Metric that calculates green space score based on a weighted combination of
    internal green area and proximity to nearby green hexagons

    - green_percentage: The actual percentage of green area within the hexagon
    - green_space_score: A composite score where:
        - 60% of the score is from the internal green percentage (scaled so 60% coverage = max points)
        - 40% of the score is from the distance-weighted green percentage of neighboring hexagons within 1km
    """

    def __init__(self, weight=1.0, data_manager=None):
        super().__init__("green_space", weight)
        self.data_manager = data_manager

        # Define tags to identify green spaces
        self.green_space_tags = {
            'leisure': ['park', 'garden', 'nature_reserve', 'playground'],
            'landuse': ['forest', 'meadow', 'grass', 'recreation_ground', 'allotments', 'farmland'],
            'natural': ['wood', 'grassland', 'heath', 'scrub', 'tree', 'tree_row'],
            'boundary': ['protected_area', 'national_park']
        }

    def calculate(self, grid_gdf, city_name):
        print("Calculating Green Space metric...")
        start_time = time.time()

        if self.data_manager is None:
            from src.data_processing.data_manager import DataManager
            self.data_manager = DataManager()

        # Load green spaces
        green_spaces_gdf = self.data_manager.get_green_spaces(city_name, self.green_space_tags)

        if green_spaces_gdf.empty:
            print("No green spaces found. Setting scores to 0.")
            grid_gdf['green_percentage'] = 0.0
            grid_gdf[f"{self.name}_score"] = 0.0
            return grid_gdf

        print("Step 1/4: Calculating green percentage per hexagon (vectorized)...")
        grid_gdf = grid_gdf.copy()
        green_spaces_gdf = green_spaces_gdf.to_crs(grid_gdf.crs)

        # Ensure grid has a unique ID column for the overlay operation
        grid_gdf['hex_id'] = grid_gdf.index
        grid_gdf['hexagon_area'] = grid_gdf.geometry.area

        # Use gpd.overlay for a vectorized intersection
        intersections = gpd.overlay(grid_gdf[['hex_id', 'geometry']], green_spaces_gdf[['geometry']], how='intersection')

        # Calculate the area of each intersection piece
        intersections['intersection_area'] = intersections.geometry.area

        # Sum all intersection areas for each unique hexagon
        green_area_per_hex = intersections.groupby('hex_id')['intersection_area'].sum()

        # Merge the summed green areas back into the main grid
        grid_gdf = grid_gdf.merge(green_area_per_hex, on='hex_id', how='left')
        grid_gdf['intersection_area'] = grid_gdf['intersection_area'].fillna(0) # Handle hexagons with no green space

        # Calculate the final green percentage
        grid_gdf['green_percentage'] = (grid_gdf['intersection_area'] / grid_gdf['hexagon_area'] * 100).clip(0, 100)

        print("Step 2/4: Calculating internal score component...")
        # Score is scaled so that 60% green coverage yields 100 points for this component
        internal_score_points = (grid_gdf['green_percentage'] / 60.0 * 100).clip(0, 100)

        print("Step 3/4: Calculating external score component (proximity to neighbors)...")
        grid_gdf['centroid'] = grid_gdf.geometry.centroid
        sindex = grid_gdf.sindex

        max_distance = 800.0
        # Exponential decay function for weighting
        decay_func = lambda dist: np.exp(-1.1 * dist / max_distance)

        external_scores = []

        # Iterate through each hexagon to calculate its neighborhood score
        for index, hexagon in grid_gdf.iterrows():
            # Find neighbors within 1km radius using the spatial index
            buffer = hexagon.geometry.buffer(max_distance)
            possible_matches_idx = list(sindex.intersection(buffer.bounds))
            neighbors = grid_gdf.iloc[possible_matches_idx]

            # Refine selection to actual neighbors and exclude the hexagon itself
            actual_neighbors = neighbors[neighbors.intersects(buffer) & (neighbors.index != index)]

            if actual_neighbors.empty:
                external_scores.append(0)
                continue

            # Calculate distances and weights in a vectorized way for speed
            distances = actual_neighbors['centroid'].distance(hexagon['centroid'])
            weights = decay_func(distances)

            # Calculate the distance-weighted average of neighbors' green percentage
            if np.sum(weights) > 0:
                weighted_avg = np.average(actual_neighbors['green_percentage'], weights=weights)
                external_scores.append(weighted_avg)
            else:
                external_scores.append(0)

        grid_gdf['external_score'] = external_scores

        # Normalize the external score to a 0-100 scale
        max_ext_score = grid_gdf['external_score'].max()
        if max_ext_score > 0:
            external_score_points = (grid_gdf['external_score'] / max_ext_score * 100).clip(0, 100)
        else:
            # Handle case where there are no external interactions
            external_score_points = pd.Series(0.0, index=grid_gdf.index)

        print("Step 4/4: Combining scores and finalizing...")
        grid_gdf[f"{self.name}_score"] = (0.55 * internal_score_points) + (0.45 * external_score_points)

        # Final cleanup
        grid_gdf.set_index('hex_id', inplace=True)
        grid_gdf.drop(columns=['hexagon_area', 'intersection_area', 'centroid'], inplace=True)


        print(f"Green space metric complete. Total time: {time.time() - start_time:.2f} seconds")
        print(f"Score range: {grid_gdf[f'{self.name}_score'].min()} - {grid_gdf[f'{self.name}_score'].max()}")
        print("External score range: ")
        print(f"{grid_gdf['external_score'].min()} - {grid_gdf['external_score'].max()}")
        print("Green percentage range: ")
        print(f"{grid_gdf['green_percentage'].min()} - {grid_gdf['green_percentage'].max()}")

        return grid_gdf