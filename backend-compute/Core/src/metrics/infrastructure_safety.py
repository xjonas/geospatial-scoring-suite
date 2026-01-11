
import pandas as pd
import geopandas as gpd
import numpy as np
import time
from src.metrics.base_metric import BaseMetric

class InfrastructureSafety(BaseMetric):
    """
    Metric that evaluates the quality and safety of walking infrastructure.

    This metric analyzes OSM data to score the walkability based on:
    - Surface quality
    - Presence of lighting
    - Footway types
    - Speed limits of adjacent roads
    - Presence of pedestrian infrastructure
    - Barriers and obstacles
    """

    def __init__(self, weight=1.0, data_manager=None):
        super().__init__("infrastructure_safety", weight)
        self.data_manager = data_manager

        self.surface_scores = {
            # Good surfaces (high score)
            'paved': 1.0,
            'asphalt': 1.0,
            'concrete': 0.9,
            'concrete:plates': 0.85,
            'paving_stones': 0.95,
            'sett': 0.8,
            # Medium surfaces
            'cobblestone': 0.7,
            'cobblestone:flattened': 0.8,
            'unhewn_cobblestone': 0.65,
            'compacted': 0.75,
            # Poor surfaces (low score)
            'dirt': 0.5,
            'earth': 0.4,
            'fine_gravel': 0.6,
            'gravel': 0.5,
            'ground': 0.45,
            'mud': 0.2,
            'pebblestone': 0.55,
            'sand': 0.3,
            'woodchips': 0.4,
            'grass': 0.3,
            # Default for unknown
            'unknown': 0.6
        }

        self.footway_type_scores = {
            'footway': 1.0,
            'pedestrian': 1.0,
            'path': 0.8,
            'sidewalk': 0.9,
            'crossing': 0.9,
            'steps': 0.6, # Lower score for accessibility reasons
            'cycleway': 0.7, # Shared with bicycles
            'track': 0.7,
            'service': 0.6,
            'living_street': 0.9,
            'residential': 0.7,
            'unclassified': 0.6,
            'road': 0.5,
            # Default for unknown
            'unknown': 0.5
        }

        # Speed limit impact (higher speeds = lower pedestrian safety)
        # Key = speed limit in km/h, Value = safety score
        self.speed_limit_scores = {
            0: 1.0, # Pedestrian only
            5: 0.95,
            10: 0.9,
            20: 0.85,
            30: 0.8,
            40: 0.65,
            50: 0.5,
            60: 0.35,
            70: 0.2,
            80: 0.1,
            90: 0.05,
            100: 0.0,
            110: 0.0,
            120: 0.0,
            130: 0.0,
            # Default for unknown
            -1: 0.6
        }

        # Importance of different factors (weights sum to 1.0)
        self.factor_weights = {
            'surface': 0.25,
            'footway_type': 0.25,
            'lighting': 0.2,
            'speed_limit': 0.2,
            'barriers': 0.1
        }

    def _extract_speed_limit(self, speed_tag):
        #Extract numerical speed limit from OSM maxspeed tag.

        # Handle case where speed_tag is a list
        if isinstance(speed_tag, list):
            if not speed_tag:  # Empty list
                return -1
            speed_tag = speed_tag[0]  # Take the first value

        if pd.isna(speed_tag) or speed_tag is None:
            return -1

        try:
            # Try direct conversion to int
            return int(speed_tag)
        except ValueError:
            # Handle common formats like "50 km/h"
            try:
                return int(speed_tag.split()[0])
            except (ValueError, IndexError):
                # Handle special values
                if speed_tag == 'walk' or speed_tag == 'walking':
                    return 5
                elif speed_tag == 'none' or speed_tag == 'unlimited':
                    return 100  # Assume high speed
                return -1

    def _get_nearest_speed_limit_score(self, speed):
        #Get the safety score for the nearest defined speed limit.

        if speed in self.speed_limit_scores:
            return self.speed_limit_scores[speed]

        # Find nearest defined speed limit
        speed_limits = sorted(k for k in self.speed_limit_scores.keys() if k >= 0)

        if speed <= speed_limits[0]:
            return self.speed_limit_scores[speed_limits[0]]

        if speed >= speed_limits[-1]:
            return self.speed_limit_scores[speed_limits[-1]]

        # Binary search for nearest speed limit
        idx = np.searchsorted(speed_limits, speed)
        lower = speed_limits[idx-1]
        upper = speed_limits[idx]

        # Interpolate between lower and upper
        proportion = (speed - lower) / (upper - lower)
        lower_score = self.speed_limit_scores[lower]
        upper_score = self.speed_limit_scores[upper]

        return lower_score + proportion * (upper_score - lower_score)

    def _preprocess_edges(self, edges_gdf):
        #Preprocess edge data to extract and normalize attributes.

        edges = edges_gdf.copy()

        # Add length column if not already present
        if 'length' not in edges.columns:
            edges['length'] = edges.geometry.length

        # 1. Surface quality scoring
        edges['surface'] = edges.get('surface', 'unknown')
        # Convert lists to strings
        edges.loc[edges['surface'].apply(lambda x: isinstance(x, list)), 'surface'] = \
            edges.loc[edges['surface'].apply(lambda x: isinstance(x, list)), 'surface'].apply(
                lambda x: x[0] if x else 'unknown'
            )
        # Map surface values to scores
        edges['surface_score'] = edges['surface'].map(self.surface_scores).fillna(self.surface_scores['unknown'])

        # 2. Footway type scoring
        edges['highway'] = edges.get('highway', 'unknown')
        edges['footway'] = edges.get('footway', edges['highway'])

        # Handle list values
        edges.loc[edges['highway'].apply(lambda x: isinstance(x, list)), 'highway'] = \
            edges.loc[edges['highway'].apply(lambda x: isinstance(x, list)), 'highway'].apply(
                lambda x: x[0] if x else 'unknown'
            )
        edges.loc[edges['footway'].apply(lambda x: isinstance(x, list)), 'footway'] = \
            edges.loc[edges['footway'].apply(lambda x: isinstance(x, list)), 'footway'].apply(
                lambda x: x[0] if x else 'unknown'
            )

        # Map footway values to scores
        edges['footway_score'] = edges.apply(
            lambda row: self.footway_type_scores.get(
                row['footway'],
                self.footway_type_scores.get(row['highway'], self.footway_type_scores['unknown'])
            ),
            axis=1
        )

        # 3. Lighting scoring
        edges['lit'] = edges.get('lit', 'unknown')
        edges['lighting_score'] = edges['lit'].map({'yes': 1.0, 'no': 0.0}).fillna(0.5)

        # 4. Speed limit scoring
        edges['maxspeed_val'] = edges['maxspeed'].apply(self._extract_speed_limit)
        edges['speed_score'] = edges['maxspeed_val'].apply(self._get_nearest_speed_limit_score)

        # 5. Barriers/obstacles
        # Check if barrier column exists
        if 'barrier' in edges.columns:
            edges['has_barrier'] = edges['barrier'].notna() & (edges['barrier'] != 'no')
        else:
            # If barrier column doesn't exist, assume no barriers
            edges['has_barrier'] = False

        edges['barrier_score'] = (~edges['has_barrier']).astype(float)

        return edges

    def calculate(self, grid_gdf, graph):
        print("Calculating Infrastructure Safety metric...")
        start_time = time.time()

        # Ensure we have a data manager
        if self.data_manager is None:
            from src.data_processing.data_manager import DataManager
            self.data_manager = DataManager()

        # Convert graph to GeoDataFrames (if needed)
        if isinstance(graph, gpd.GeoDataFrame):
            edges_gdf = graph
        elif hasattr(graph, 'edges'):
            # Get edges from network using data_manager's graph_to_gdfs instead of get_simplified_intersections
            _, edges_gdf = self.data_manager.graph_to_gdfs(graph)
        else:
            # Direct conversion as fallback
            import osmnx as ox
            _, edges_gdf = ox.graph_to_gdfs(graph)
            print("Warning: Using direct OSM API call. Consider passing a DataManager instance.")

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Initialize score column
        grid_gdf[self.name] = 50.0  # Default score for hexagons with no data
        grid_gdf[f"{self.name}_data_available"] = False

        # Preprocess edges to extract and score attributes (vectorized operation)
        print("Preprocessing edge attributes...")
        edges_gdf = self._preprocess_edges(edges_gdf)

        # Ensure same CRS
        edges_gdf = edges_gdf.to_crs(grid_gdf.crs)

        # Get spatial index for edges
        if self.data_manager is not None:
            edges_sindex = self.data_manager.get_spatial_index(edges_gdf, "edges")
        else:
            edges_sindex = edges_gdf.sindex

        print("Performing spatial join between edges and hexagons...")
        # Spatial join to associate edges with hexagons - more efficient approach
        joined = gpd.sjoin(grid_gdf, edges_gdf, how="left", predicate="intersects")

        # Group by hexagon ID
        print("Calculating per-hexagon scores...")
        calc_start = time.time()

        # Process in chunks to reduce memory usage
        chunk_size = 200 

        # Get all unique hexagon IDs from the join
        hexagon_ids = joined['id'].unique()

        for i in range(0, len(hexagon_ids), chunk_size):
            chunk_ids = hexagon_ids[i:i+chunk_size]

            # Filter joined data for current chunk
            chunk_data = joined[joined['id'].isin(chunk_ids)]

            # Group by hexagon ID
            grouped = chunk_data.groupby('id')

            for hexagon_id, group in grouped:
                # Check if enough data is available
                if len(group) < 3: # Require at least 3 road segments for reliable scoring
                    continue


                # Get relevant scores
                surface_scores = group['surface_score']
                footway_scores = group['footway_score']
                lighting_scores = group['lighting_score']
                speed_scores = group['speed_score']
                barrier_scores = group['barrier_score']

                # Get edge lengths for weighting
                edge_lengths = group['length']
                total_length = edge_lengths.sum()

                # Calculate length-weighted average scores
                weighted_scores = {
                    'surface': np.average(surface_scores, weights=edge_lengths),
                    'footway_type': np.average(footway_scores, weights=edge_lengths),
                    'lighting': np.average(lighting_scores, weights=edge_lengths),
                    'speed_limit': np.average(speed_scores, weights=edge_lengths),
                    'barriers': np.average(barrier_scores, weights=edge_lengths)
                }

                # Calculate final score as weighted average of factor scores
                final_score = sum(
                    weighted_scores[factor] * weight
                    for factor, weight in self.factor_weights.items()
                )

                # Scale to 0-100
                final_score_scaled = final_score * 100

                # Update grid dataframe
                idx = grid_gdf[grid_gdf['id'] == hexagon_id].index
                grid_gdf.loc[idx, self.name] = final_score_scaled
                grid_gdf.loc[idx, f"{self.name}_data_available"] = True

        print(f"Per-hexagon score calculations took {time.time() - calc_start:.2f} seconds")

        # Add score column
        grid_gdf[f"{self.name}_score"] = grid_gdf[self.name]

        print(f"Infrastructure safety calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf