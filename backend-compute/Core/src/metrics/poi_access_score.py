"""
POI Access Score Calculation - Daily life amenities accessibility
Calculates scores for access to essential amenities via various transportation modes (including car)
"""
import geopandas as gpd
import pandas as pd
import numpy as np
from src.metrics.base_metric import BaseMetric
from shapely.geometry import Point
import time
from config.settings import CHUNK_SIZE, DISTANCE_DECAY_POI_ACCESS

class POIAccessScore(BaseMetric):
    """
    Metric that calculates accessibility to everyday amenities over longer distances.
    Assumes mixed transportation modes (walking, cycling, public transport, car).
    Separate from walkability metrics.
    """
    def __init__(self, weight=1.0, max_distance=6000, data_manager=None):
        """
        Initialize POI access score metric.

        Parameters:
        -----------
        weight : float
            Weight of the metric in the final score (not used in walkability)
        max_distance : float
            Maximum distance to consider for POI accessibility in meters (default: 5000m/5km)
        data_manager : DataManager
            Data manager instance for efficient data loading
        """
        super().__init__("poi_access", weight)
        self.max_distance = max_distance
        self.data_manager = data_manager

        # Define category mapping to OSM tags
        # Maps our custom categories to OSM tags for data extraction
        self.category_mapping = {
            'grocery': {
                'shop': ['supermarket', 'grocery', 'department_store'],
            },
            'cafe': {
                'amenity': ['cafe', 'ice_cream']
            },
            'shopping': {
                'shop': ['mall', 'department_store', 'clothes', 'shoes', 'jewelry',
                         'electronics', 'boutique', 'chemist',
                         'books', 'gift', 'beauty', 'cosmetics'
                         ]
            },
            'nightlife': {
                'amenity': ['bar', 'pub', 'biergarten', 'nightclub', 'cinema', 'theatre']
            },
            'pharmacy': {
                'amenity': ['pharmacy'],
            },
            'fitness': {
                'leisure': ['fitness_centre', 'sports_centre', 'fitness_station']
            }
        }

        # Importance of each category (for internal ranking of POIs)
        self.category_weights = {
            'grocery': 1.0,
            'cafe': 0.9,
            'shopping': 0.7,
            'nightlife': 0.4,
            'pharmacy': 0.8,
            'fitness': 0.7
        }

        # POI importance weights within categories (the most important types for each category)
        self.poi_importance = {
            # Grocery - supermarkets are more important than specialty stores
            'supermarket': 1.0,
            'grocery': 1.0,
            'bakery': 0.5,

            # Cafe - full restaurants more important than just ice cream
            'cafe': 1.0,
            'ice_cream': 0.9,

            # Shopping - malls provide more options
            'mall': 0.9,
            'department_store': 0.9,

            # Nightlife - cinema and theaters are major venues
            'cinema': 0.4,
            'theatre': 0.4,
            'nightclub': 0.7,
            'bar': 0.8,
            'pub': 0.7,

            # Pharmacy - all pharmacies equally important
            'pharmacy': 1.0,

            # Fitness - major facilities weighted higher
            'sports_centre': 0.8,
            'fitness_centre': 1.0
        }

        # Default importance for POIs not specifically listed
        self.default_poi_weight = 0.6

        # Distance decay parameters (different from walkability - slower decay for car travel)
        # This creates a logarithmic decay that makes 5km roughly 20% as valuable as 0km
        self.distance_decay_factor = DISTANCE_DECAY_POI_ACCESS

        # Distance thresholds for perfect scores and minimum scores
        self.perfect_distance = {
            'grocery': 500,     # 1km to groceries is ideal
            'cafe': 700,        # 1.5km to cafe/restaurant is ideal
            'shopping': 1000,    # 3km to shopping is ideal
            'nightlife': 3000,   # 5km to nightlife is ideal
            'pharmacy': 1000,    # 1.5km to pharmacy is ideal
            'fitness': 900      # 2km to fitness facilities is ideal
        }

    def _load_pois_by_category(self, city_name):
        """
        Load POIs for each of our custom categories from OSM.
        Uses data manager to efficiently load and cache data.

        Parameters:
        -----------
        city_name : str
            Name of the city

        Returns:
        --------
        dict:
            Dictionary with category names as keys and GeoDataFrames as values
        """
        # Ensure we have a data manager
        if self.data_manager is None:
            from src.data_processing.data_manager import DataManager
            self.data_manager = DataManager()

        pois_by_category = {}

        print(f"Loading POIs for access score categories in {city_name}...")
        start_time = time.time()

        # For each category, load relevant POIs
        for category, tag_mapping in self.category_mapping.items():
            all_category_pois = []

            # For each tag type (amenity, shop, etc.), load relevant POIs
            for tag_type, tag_values in tag_mapping.items():
                try:
                    # Use the data manager to get POIs efficiently (with caching)
                    pois = self.data_manager.get_pois(city_name, tag_type, tag_values)

                    if not pois.empty:
                        # Make a clean copy
                        pois = pois.copy()

                        # Reset index to ensure clean integer indices
                        pois = pois.reset_index(drop=True)

                        # Add custom category for our classification
                        pois.loc[:, 'access_category'] = category

                        all_category_pois.append(pois)
                        print(f"  Found {len(pois)} POIs for {category} ({tag_type})")
                except Exception as e:
                    print(f"  Error loading {tag_type} POIs for {category}: {e}")

            # Combine all POIs for this category
            if all_category_pois:
                try:
                    # Concatenate and immediately reset the index to ensure it's clean
                    combined_pois = pd.concat(all_category_pois, ignore_index=True)
                    pois_by_category[category] = combined_pois
                except Exception as e:
                    print(f"  Error combining POIs for {category}: {e}")
                    continue
            else:
                print(f"  No POIs found for {category}")
                # Create an empty GeoDataFrame with proper CRS for this category
                try:
                    city_crs = self.data_manager.get_city_geometry(city_name).crs
                except:
                    from config.settings import GERMANY_CRS
                    city_crs = GERMANY_CRS
                pois_by_category[category] = gpd.GeoDataFrame([], geometry=[], crs=city_crs)

        print(f"POI loading for access scores completed in {time.time() - start_time:.2f} seconds")
        return pois_by_category

    def _calculate_distance_factor(self, distance, category):
        """
        Calculate a score factor based on distance.
        Uses an exponential decay function, calibrated for car/mixed transportation.

        Parameters:
        -----------
        distance : float or array-like
            Distance(s) to calculate factors for in meters
        category : str
            Category name to determine ideal distance threshold

        Returns:
        --------
        float or array-like:
            Distance factor(s) between 0 and 1
        """
        # Get perfect distance threshold for this category
        perfect_dist = self.perfect_distance.get(category, 2000)  # Default 2km

        # If distance is less than perfect distance, score is 1.0
        if np.isscalar(distance):
            if distance <= perfect_dist:
                return 1.0
        else:
            # For array input, create result array initialized with 1.0
            result = np.ones_like(distance, dtype=float)
            # Only calculate decay for distances beyond perfect threshold
            mask = distance > perfect_dist
            if not np.any(mask):
                return result
            # Apply decay function only to distances beyond threshold
            distance_to_calculate = distance[mask] - perfect_dist
            result[mask] = np.exp(-self.distance_decay_factor * distance_to_calculate)
            return result

        # For scalar distance beyond threshold, calculate decay
        return np.exp(-self.distance_decay_factor * (distance - perfect_dist))

    def _get_poi_weights(self, pois_df, category):
        """
        Calculate weights for POIs in a vectorized way.

        Parameters:
        -----------
        pois_df : DataFrame
            DataFrame containing POIs
        category : str
            Category name for these POIs

        Returns:
        --------
        Series:
            Series containing POI weights
        """
        # Make sure the index is properly sorted to avoid PerformanceWarning
        if not pois_df.index.is_monotonic_increasing:
            pois_df = pois_df.sort_index()

        # Create a series of default weights
        weights = pd.Series(self.default_poi_weight, index=pois_df.index)

        # For each tag type that could be present, update weights
        if 'amenity' in pois_df.columns:
            for poi_type, weight in self.poi_importance.items():
                mask = pois_df['amenity'] == poi_type
                if mask.any():
                    weights.loc[mask] = weight

        if 'shop' in pois_df.columns:
            for poi_type, weight in self.poi_importance.items():
                mask = pois_df['shop'] == poi_type
                if mask.any():
                    weights.loc[mask] = weight

        # Apply corresponding category weight
        cat_weight = self.category_weights.get(category, 1.0)

        return weights * cat_weight

    def calculate(self, grid_gdf, city_name):
        """
        Calculate POI access scores for each category and hexagon.

        Parameters:
        -----------
        grid_gdf : GeoDataFrame
            Hexagon grid
        city_name : str
            Name of the city to fetch POIs for

        Returns:
        --------
        grid_gdf : GeoDataFrame
            Grid with added poi_access columns for each category
        """
        print(f"Calculating POI access scores for {city_name}...")
        start_time = time.time()

        # Load POIs for all categories
        pois_by_category = self._load_pois_by_category(city_name)

        # Create a copy of the grid
        grid_gdf = grid_gdf.copy()

        # Ensure we have centroid data
        if 'centroid' not in grid_gdf.columns:
            grid_gdf['centroid'] = grid_gdf.geometry.centroid

        if 'centroid_x' not in grid_gdf.columns or 'centroid_y' not in grid_gdf.columns:
            grid_gdf['centroid_x'] = grid_gdf.centroid.x
            grid_gdf['centroid_y'] = grid_gdf.centroid.y

        # Initialize score columns for each category
        for category in self.category_mapping.keys():
            grid_gdf[f"poi_access_{category}"] = 0.0
            grid_gdf[f"poi_access_{category}_score"] = 0.0

        # Process each category
        for category, pois_gdf in pois_by_category.items():
            if pois_gdf.empty:
                print(f"  No POIs for {category}, setting scores to 0")
                continue

            # Ensure POIs are in the same CRS as grid
            pois_gdf = pois_gdf.to_crs(grid_gdf.crs)

            # Get weights for all POIs in this category
            # First make a copy to avoid issues with the index
            pois_gdf = pois_gdf.copy()

            # Reset index to avoid performance warnings
            pois_gdf = pois_gdf.reset_index(drop=True)

            # Set weights using loc
            pois_gdf.loc[:, 'weight'] = self._get_poi_weights(pois_gdf, category)

            # Create a spatial index for efficient querying
            pois_sindex = self.data_manager.get_spatial_index(pois_gdf, f"access_pois_{category}_{city_name}") if self.data_manager else pois_gdf.sindex

            print(f"  Processing {category} with {len(pois_gdf)} POIs...")
            calc_start = time.time()

            # Process hexagons in chunks
            chunk_size = CHUNK_SIZE
            total_hexagons = len(grid_gdf)

            for chunk_start in range(0, total_hexagons, chunk_size):
                chunk_end = min(chunk_start + chunk_size, total_hexagons)
                chunk = grid_gdf.iloc[chunk_start:chunk_end]

                # Process each hexagon
                for i, (idx, hexagon) in enumerate(chunk.iterrows()):
                    centroid = Point(hexagon.centroid_x, hexagon.centroid_y)
                    buffer = centroid.buffer(self.max_distance)

                    # Use spatial index to find potential POIs
                    possible_pois_idxs = list(pois_sindex.intersection(buffer.bounds))

                    if not possible_pois_idxs:
                        continue

                    possible_pois = pois_gdf.iloc[possible_pois_idxs]

                    # Calculate distances to POIs
                    possible_pois = possible_pois.copy()  # Make a copy to avoid SettingWithCopyWarning

                    # Use loc to avoid SettingWithCopyWarning
                    possible_pois.loc[:, 'distance'] = possible_pois.geometry.distance(centroid)

                    # Filter to POIs within max distance
                    pois_in_range = possible_pois[possible_pois['distance'] <= self.max_distance].copy()

                    if pois_in_range.empty:
                        continue

                    # Calculate distance factors using loc
                    pois_in_range.loc[:, 'distance_factor'] = self._calculate_distance_factor(
                        pois_in_range['distance'], category)

                    # Calculate POI scores using loc
                    pois_in_range.loc[:, 'score'] = pois_in_range['distance_factor'] * pois_in_range['weight']

                    # Calculate final score for this hexagon and category
                    # We use a logarithmic sum to account for diminishing returns with multiple nearby POIs
                    # and normalize to a 0-100 scale based on typical density patterns

                    # Sum the scores and apply logarithmic scaling
                    raw_score = pois_in_range['score'].sum()

                    # Determine scaling parameters based on POI count (more POIs → lower relative impact)
                    poi_count = len(pois_in_range)

                    if poi_count <= 3:
                        # Linear scaling for few POIs
                        scaled_score = raw_score * 25
                    else:
                        # Logarithmic scaling for many POIs (diminishing returns)
                        # Formula: log(1 + raw_score) / log(1 + max_expected) * 100
                        # Where max_expected is calibrated based on the category
                        max_expected = {
                            'grocery': 10,
                            'cafe': 15,
                            'shopping': 15,
                            'nightlife': 8,
                            'pharmacy': 5,
                            'fitness': 5
                        }.get(category, 10)

                        scaled_score = np.log1p(raw_score) / np.log1p(max_expected) * 100

                    # Store the score (capped at 100)
                    grid_gdf.at[idx, f"poi_access_{category}"] = min(scaled_score, 100)

            # Copy the raw score to the score column
            grid_gdf[f"poi_access_{category}_score"] = grid_gdf[f"poi_access_{category}"].clip(0, 100)

            print(f"  {category} processed in {time.time() - calc_start:.2f} seconds")

        # Create overall POI access score as weighted average of category scores
        category_weights = self.category_weights
        weight_sum = sum(category_weights.values())

        grid_gdf["poi_access_overall"] = 0.0
        for category, weight in category_weights.items():
            norm_weight = weight / weight_sum
            grid_gdf["poi_access_overall"] += grid_gdf[f"poi_access_{category}_score"] * norm_weight

        # Set the score column
        grid_gdf["poi_access_overall_score"] = grid_gdf["poi_access_overall"].clip(0, 100)

        print(f"POI access score calculation complete. Total time: {time.time() - start_time:.2f} seconds")
        return grid_gdf