
import time
import numpy as np
import pandas as pd
import geopandas as gpd
from src.metrics.base_metric import BaseMetric
from shapely.ops import nearest_points
from config.settings import CHUNK_SIZE

class FloodResistanceMetric(BaseMetric):
    """
    Metric that calculates flood resistance based on:
    - Elevation and slope (40%)
    - Distance to water bodies (55%)
    - Green space coverage (5%)

    Higher scores indicate better resistance to flooding (0-100 scale)
    """

    def __init__(self, weight=1.0, data_manager=None):
        super().__init__("flood_resistance", weight)
        self.data_manager = data_manager

        # Component weights
        self.elevation_weight = 0.40 
        self.distance_weight = 0.55 
        self.green_space_weight = 0.05 

        # Water body OSM tags
        self.water_tags = {
            'waterway': ['river', 'tidal_channel'],
            'natural': ['coastline'],
            'water': ['river', 'sea']
        }

        # Maximum distance to consider for water impact (in meters)
        self.max_water_distance = 400 

        # Elevation thresholds for scoring (in meters above the nearest water body)
        self.elevation_thresholds = {
            1: 20, # 0-1m: Very high risk 
            2: 45, # 1-2m: High risk 
            5: 70, # 2-5m: Moderate risk 
            10: 80, # 5-10m: Low risk 
            20: 90, # 10-20m: Very low risk 
            float('inf'): 100 # >20m: Minimal risk 
        }

        # Distance thresholds for scoring (in meters)
        self.distance_thresholds = {
            50: 10,      
            100: 30,     
            200: 50,     
            400: 70,     
            500: 90,    
            float('inf'): 100 
        }

    def _load_water_bodies(self, city_name):
        # Load water body features from OSM.
        print("Loading water body data...")

        # Use data manager for efficient API access and caching
        water_features = []

        for tag_type, tag_values in self.water_tags.items():
            try:
                # Pass entire tag_values list at once - like POI metric does
                features = self.data_manager.get_pois(city_name, tag_type, tag_values)
                if not features.empty:
                    # Add type info
                    features['water_type'] = tag_type
                    water_features.append(features)
                    print(f"Found {len(features)} {tag_type} features")
            except Exception as e:
                print(f"Error loading {tag_type} features: {e}")

        if not water_features:
            print("No water features found!")
            return gpd.GeoDataFrame([], geometry=[], crs=self.data_manager.get_city_geometry(city_name).crs)

        try:
            # Combine all water features
            water_gdf = pd.concat(water_features)

            # Keep only relevant geometries (points, lines, polygons)
            water_gdf = water_gdf[water_gdf.geometry.type.isin(['Point', 'LineString', 'Polygon', 'MultiPolygon'])]

            return water_gdf
        except Exception as e:
            print(f"Error combining water features: {e}")
            return gpd.GeoDataFrame([], geometry=[], crs=self.data_manager.get_city_geometry(city_name).crs)

    def _get_elevation_score(self, elevation, water_elevation=None):    
        # Calculate flood resistance score based on elevation difference
        # If water elevation is available, use elevation difference
        if water_elevation is not None:
            # Ensure a minimum difference to avoid negative values
            elevation_diff = max(0, elevation - water_elevation)
        else:
            # Without water elevation, use absolute elevation with more conservative thresholds
            elevation_diff = max(0, elevation)
            # Adjust thresholds if using absolute elevation
            if elevation < 5: # Low-lying areas are at higher risk regardless
                return 30

        # Score based on elevation difference thresholds
        for threshold, score in sorted(self.elevation_thresholds.items()):
            if elevation_diff <= threshold:
                return score

        return 100  # Maximum score if above all thresholds

    def _get_distance_score(self, distance):
        # Calculate flood resistance score based on distance to water
        # If beyond maximum distance, return maximum score
        if distance > self.max_water_distance:
            return 100

        # Score based on distance thresholds
        for threshold, score in sorted(self.distance_thresholds.items()):
            if distance <= threshold:
                return score

        return 100  # Maximum score if above all thresholds

    def calculate(self, grid_gdf, city_name=None):
        # Calculate flood resistance score for each hexagon
        print("Calculating Flood Resistance metric...")
        start_time = time.time()

        # Make a copy of the grid to avoid modifying the original
        grid_gdf = grid_gdf.copy()

        # Check if topography data is available
        has_elevation_data = False
        if 'topography_slope' in grid_gdf.columns:
            has_elevation_data = True
            print("Found existing slope data - will use for flood resistance")

        # Use absolute elevation if available
        has_absolute_elevation = False
        if hasattr(self.data_manager, 'get_elevation') or '_topography_elevation' in grid_gdf.columns:
            has_absolute_elevation = True
            print("Found existing elevation data - will use for flood resistance")

        # If no elevation data available, adjust weights
        if not has_elevation_data and not has_absolute_elevation:
            print("No elevation data found - adjusting component weights")
            self.distance_weight = 0.7
            self.green_space_weight = 0.3
            self.elevation_weight = 0.0

        # Get water bodies
        water_bodies = self._load_water_bodies(city_name)

        if water_bodies.empty:
            print("No water bodies found - using simplified calculation")
            # If no water bodies found, rely solely on elevation and green space
            self.distance_weight = 0.0
            if self.elevation_weight > 0:
                self.elevation_weight = 0.8
                self.green_space_weight = 0.2
            else:
                self.green_space_weight = 1.0

        # Ensure same CRS
        water_bodies = water_bodies.to_crs(grid_gdf.crs)

        # Initialize flood resistance columns
        grid_gdf[self.name] = 0.0
        grid_gdf[f"{self.name}_elevation"] = 0.0
        grid_gdf[f"{self.name}_distance"] = 0.0
        grid_gdf[f"{self.name}_green"] = 0.0
        grid_gdf[f"distance_to_water"] = float('inf')

        # Create spatial index for water bodies for efficient calculations
        if not water_bodies.empty:
            water_sindex = self.data_manager.get_spatial_index(water_bodies, "water_bodies") if self.data_manager else water_bodies.sindex

        # Process in chunks for better memory management
        chunk_size = CHUNK_SIZE
        total_hexagons = len(grid_gdf)

        for chunk_start in range(0, total_hexagons, chunk_size):
            chunk_end = min(chunk_start + chunk_size, total_hexagons)
            chunk = grid_gdf.iloc[chunk_start:chunk_end]

            for idx, hexagon in chunk.iterrows():
                # 1. Calculate distance-based score
                distance_score = 100 # Default (maximum) score

                if not water_bodies.empty:
                    # Use centroid for distance calculation
                    centroid = hexagon.geometry.centroid

                    # Use spatial index to find nearby water bodies
                    buffer_dist = self.max_water_distance
                    buffer = centroid.buffer(buffer_dist)

                    possible_matches_index = list(water_sindex.intersection(buffer.bounds))

                    if possible_matches_index:
                        # Find actual intersections
                        candidates = water_bodies.iloc[possible_matches_index]
                        distances = candidates.geometry.distance(centroid)

                        # Get minimum distance
                        min_distance = distances.min()
                        grid_gdf.at[idx, f"distance_to_water"] = min_distance

                        # Calculate distance score
                        distance_score = self._get_distance_score(min_distance)

                # 2. Calculate elevation-based score
                elevation_score = 100 # Default (maximum) score

                if has_elevation_data or has_absolute_elevation:
                    # Use existing elevation data
                    if has_absolute_elevation and '_topography_elevation' in grid_gdf.columns:
                        # Use absolute elevation
                        elevation = hexagon._topography_elevation
                    elif has_absolute_elevation:
                        # Get from data manager if available
                        elevation = 100 # Default value, replace with actual elevation
                        # Implementation depends on your data manager capabilities
                    elif 'topography_slope' in grid_gdf.columns:
                        # Use slope as a proxy for flood resistance
                        # Steeper slopes = better drainage = higher score
                        slope = hexagon.topography_slope

                        # Convert slope to score: 0% = 10, 5% = 50, 15%+ = 100
                        elevation_score = min(100, 10 + (slope * 6))

                    # If we have actual elevation data, calculate proper score
                    if has_absolute_elevation:
                        # Get water body elevation if available
                        water_elevation = None
                        # This would require additional API calls for the water elevation
                        # For simplicity, we'll use absolute elevation instead

                        elevation_score = self._get_elevation_score(elevation, water_elevation)

                # 3. Calculate green space-based score
                green_score = 50 # Default (neutral) score

                if 'green_percentage' in hexagon:
                    # More green space = better absorption = higher score
                    green_pct = hexagon.green_percentage
                    green_score = min(100, green_pct * 1.3) # 67%+ green space = 100 score
                elif 'green_space' in hexagon:
                    # Use existing green space score directly
                    green_score = hexagon.green_space

                # Store component scores
                grid_gdf.at[idx, f"{self.name}_elevation"] = elevation_score
                grid_gdf.at[idx, f"{self.name}_distance"] = distance_score
                grid_gdf.at[idx, f"{self.name}_green"] = green_score

                # Calculate final weighted score
                final_score = (
                        elevation_score * self.elevation_weight +
                        distance_score * self.distance_weight +
                        green_score * self.green_space_weight
                )

                # Store final score
                grid_gdf.at[idx, self.name] = final_score
                grid_gdf.at[idx, f"{self.name}_score"] = round(final_score)

        print(f"Flood resistance calculation complete. Total time: {time.time() - start_time:.2f} seconds")

        # Print summary statistics
        print(f"Flood resistance score range: {grid_gdf[self.name].min():.1f} - {grid_gdf[self.name].max():.1f}")

        if not water_bodies.empty:
            print(f"Distance to water range: {grid_gdf[grid_gdf['distance_to_water'] < float('inf')]['distance_to_water'].min():.1f} - "
                  f"{grid_gdf[grid_gdf['distance_to_water'] < float('inf')]['distance_to_water'].max():.1f} meters")

        print(f"Component weights used: Elevation {self.elevation_weight:.2f}, "
              f"Distance {self.distance_weight:.2f}, Green Space {self.green_space_weight:.2f}")

        return grid_gdf