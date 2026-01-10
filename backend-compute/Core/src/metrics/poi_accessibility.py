"""
POI Accessibility Calculation Algorithm - Optimized Implementation
"""
import geopandas as gpd
import pandas as pd
import numpy as np
from src.metrics.base_metric import BaseMetric
from shapely.geometry import Point
import time
from config.settings import DISTANCE_DECAY_EXPONENT, CHUNK_SIZE

class POIAccessibility(BaseMetric):
    """
    Metric that calculates accessibility to Points of Interest (POIs).
    Optimized implementation with improved data handling.
    """
    def __init__(self, weight=1.0, max_distance=1200, data_manager=None):
        """
        Initialize POI accessibility metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score
        max_distance : float
            Maximum distance to consider for POI accessibility
        data_manager : DataManager
            Data manager instance for efficient data loading
        """
        super().__init__("poi_accessibility", weight)
        self.max_distance = max_distance
        self.data_manager = data_manager  # Store data manager reference

        # Define POI categories and their importance weights
        # Categories are grouped by type for easier management
        self.poi_categories = {
            # Food and drink
            'amenity': [
                'cafe',
                'restaurant',
                'ice_cream',

                'bank',
                'pharmacy',
                'university',
                'school'
            ],
            # Shopping
            'shop': [
                'bakery',
                'supermarket',
                'grocery',
                'mall',
                'department_store'
            ],
            # Leisure
            'leisure': [
                'fitness_centre',
                'sports_centre',
                'playground',
                'golf_course',
                'park',
                'swimming_pool',
                'swimming_area',
                'fitness_station'
            ]
        }

        # Importance weights for each category group
        self.category_group_weights = {
            'amenity': 0.5,      # Food and drink
            'shop': 0.7,        # Shopping
            'leisure': 0.6      # Leisure
        }

        # Importance weights for specific POIs
        # Higher weights for more important or frequently used POIs
        self.poi_importance_weights = {
            # Food and drink
            'cafe': 0.8,
            'restaurant': 0.2,

            # Services
            'pharmacy': 0.7,

            # Shopping
            'supermarket': 1.0,
            'bakery': 0.8,

            # Leisure
            'sports_centre': 0.8,
            'fitness_centre': 0.8,
            'playground': 0.7,
            'park': 0.9
        }

        # Default weight for POIs not specifically listed
        self.default_poi_weight = 0.6

    def _load_all_pois(self, city_name):
        """
        Load all POIs for a city from OpenStreetMap based on defined categories.
        Uses the data manager for efficient loading and caching.

        Parameters:
        -----------
        city_name : str
            Name of the city

        Returns:
        --------
        GeoDataFrame:
            GeoDataFrame containing all POIs
        """
        import geopandas as gpd
        import pandas as pd
        import time
        from src.data_processing.data_manager import DataManager

        # Ensure we have a data manager
        if self.data_manager is None:
            self.data_manager = DataManager()

        print(f"Loading POIs for {city_name}...")
        start_time = time.time()

        all_pois = []

        # Fetch POIs for each category group using the data manager
        for category_key, tags_list in self.poi_categories.items():
            try:
                category_pois = self.data_manager.get_pois(city_name, category_key, tags_list)
                if not category_pois.empty:
                    all_pois.append(category_pois)
                    print(f"Found {len(category_pois)} POIs for {category_key}")
            except Exception as e:
                print(f"Error loading {category_key} POIs: {e}")

        if not all_pois:
            print("No POIs found!")
            return gpd.GeoDataFrame([], geometry=[], crs=self.data_manager.get_city_geometry(city_name).crs)

        try:
            # Combine all POIs
            pois_gdf = pd.concat(all_pois)

            # Keep only point geometries
            if not pois_gdf.empty:
                pois_gdf = pois_gdf[pois_gdf.geometry.type == 'Point']
        except Exception as e:
            print(f"Error combining POIs: {e}")
            return gpd.GeoDataFrame([], geometry=[], crs=self.data_manager.get_city_geometry(city_name).crs)

        print(f"Total POIs loaded: {len(pois_gdf)}")
        print(f"POI loading took {time.time() - start_time:.2f} seconds")

        return pois_gdf

    def _calculate_distance_factor(self, distance):
        """
        Calculate a score factor based on distance.
        Uses an exponential decay function to prioritize closer POIs.

        Parameters:
        -----------
        distance : float or array-like
            Distance(s) to calculate factors for

        Returns:
        --------
        float or array-like:
            Distance factor(s)
        """
        # Exponential decay function
        decay_factor = DISTANCE_DECAY_EXPONENT  # Controls how quickly the score decreases with distance
        return np.exp(-decay_factor * distance)

    def _get_poi_weights(self, pois_df):
        """
        Calculate weights for POIs in a vectorized way.

        Parameters:
        -----------
        pois_df : DataFrame
            DataFrame containing POIs

        Returns:
        --------
        Series:
            Series containing POI weights
        """
        # Create a series of default weights
        weights = pd.Series(self.default_poi_weight, index=pois_df.index)

        # Update weights based on POI type
        for poi_type, weight in self.poi_importance_weights.items():
            mask = pois_df['category'] == poi_type
            weights.loc[mask] = weight

        # Apply category group weights
        group_weights = pois_df['category_group'].map(self.category_group_weights)
        group_weights.fillna(1.0, inplace=True)

        # Multiply individual weights by group weights
        return weights * group_weights

    def calculate(self, grid_gdf, city_name):
        """
        Calculate POI accessibility score for each hexagon using vectorized operations.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str
            Name of the city to fetch POIs for

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added poi_accessibility column
        """
        print(f"Calculating POI accessibility for {city_name}...")
        start_time = time.time()

        # Load POIs
        pois_gdf = self._load_all_pois(city_name)

        if pois_gdf.empty:
            # If no POIs found, return grid with zeros
            grid_gdf = grid_gdf.copy()
            grid_gdf[self.name] = 0.0
            grid_gdf[f"{self.name}_score"] = 0.0
            return grid_gdf

        # Ensure POIs are in the same CRS as grid
        pois_gdf = pois_gdf.to_crs(grid_gdf.crs)

        # Create a copy of the grid
        grid_gdf = grid_gdf.copy()

        # Ensure we have centroid data for calculations
        if 'centroid_x' not in grid_gdf.columns or 'centroid_y' not in grid_gdf.columns:
            grid_gdf['centroid_x'] = grid_gdf.geometry.centroid.x
            grid_gdf['centroid_y'] = grid_gdf.geometry.centroid.y

        # Initialize score column
        grid_gdf[self.name] = 0.0

        # Initialize category score columns
        for category_group in self.category_group_weights.keys():
            grid_gdf[f"{self.name}_{category_group}"] = 0.0

        # Pre-calculate POI weights for all POIs once (vectorized operation)
        pois_gdf['weight'] = self._get_poi_weights(pois_gdf)

        print(f"Starting accessibility calculations for {len(grid_gdf)} hexagons...")
        calculation_start = time.time()

        # Create a spatial index for POIs
        pois_sindex = self.data_manager.get_spatial_index(pois_gdf, f"pois_{city_name}") if self.data_manager else pois_gdf.sindex

        # Initialize a dictionary to store category scores for efficient updates
        category_scores = {cat: np.zeros(len(grid_gdf)) for cat in self.category_group_weights.keys()}

        # Process hexagons in chunks to improve memory usage
        chunk_size = CHUNK_SIZE
        total_hexagons = len(grid_gdf)

        for chunk_start in range(0, total_hexagons, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_hexagons)
            chunk = grid_gdf.iloc[chunk_start:chunk_end].copy()  # Make a copy to avoid warning

            # Create buffer geometries for this chunk (more memory efficient than all at once)
            buffers = [Point(row.centroid_x, row.centroid_y).buffer(self.max_distance)
                       for _, row in chunk.iterrows()]

            # Process each hexagon in this chunk
            for i, (idx, hexagon) in enumerate(chunk.iterrows()):
                # Use spatial index to find POIs within buffer
                buffer = buffers[i]
                possible_matches_index = list(pois_sindex.intersection(buffer.bounds))

                if not possible_matches_index:
                    continue

                possible_matches = pois_gdf.iloc[possible_matches_index]

                # Refine to POIs that are actually within the buffer
                pois_in_range = possible_matches[possible_matches.geometry.within(buffer)]

                if pois_in_range.empty:
                    continue

                # Calculate distances from hexagon centroid to POIs (vectorized operation)
                point = Point(hexagon.centroid_x, hexagon.centroid_y)
                pois_in_range = pois_in_range.copy()  # Make a copy to avoid warning
                pois_in_range['distance'] = pois_in_range.geometry.distance(point)

                # Calculate distance factors (vectorized operation)
                pois_in_range['distance_factor'] = self._calculate_distance_factor(pois_in_range['distance'])

                # Calculate POI scores (vectorized operation)
                pois_in_range['score'] = pois_in_range['distance_factor'] * pois_in_range['weight']

                # Update total score for this hexagon
                hexagon_idx = chunk_start + i
                grid_gdf.loc[idx, self.name] = pois_in_range['score'].sum()

                # Update category scores
                for category in self.category_group_weights.keys():
                    category_pois = pois_in_range[pois_in_range['category_group'] == category]
                    if not category_pois.empty:
                        cat_score = category_pois['score'].sum()
                        category_scores[category][hexagon_idx] += cat_score

        # Update category scores in the dataframe
        for category, scores in category_scores.items():
            grid_gdf[f"{self.name}_{category}"] = scores

        print(f"Accessibility calculations took {time.time() - calculation_start:.2f} seconds")

        # Normalize to 0-100 scale
        max_score = grid_gdf[self.name].max()
        if max_score > 0:
            grid_gdf[f"{self.name}_score"] = (
                    grid_gdf[self.name] / max_score * 100
            ).clip(0, 100)
        else:
            grid_gdf[f"{self.name}_score"] = 0

        # Normalize category scores
        for category in self.category_group_weights.keys():
            category_col = f"{self.name}_{category}"
            max_cat_score = grid_gdf[category_col].max()

            if max_cat_score > 0:
                grid_gdf[f"{category_col}_score"] = (
                        grid_gdf[category_col] / max_cat_score * 100
                ).clip(0, 100)
            else:
                grid_gdf[f"{category_col}_score"] = 0.0

        print(f"POI accessibility calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf